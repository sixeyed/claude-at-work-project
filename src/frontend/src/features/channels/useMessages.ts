/**
 * Server state for messages, owned by TanStack Query (register D24).
 *
 * **Ordering, once, so nothing flips it twice.** The three layers do not agree,
 * and that is deliberate rather than an oversight:
 *
 * | layer | order | why |
 * |---|---|---|
 * | SQL and the wire | newest first (`id DESC`) | matches `ix_messages_channel_time`, and makes "the first page is what you see on open" a single query |
 * | this cache | `pages[0]` is the **newest** page; items within a page are newest-first | it is the raw server response — `useInfiniteQuery` appends each page it fetches, so later pages are older |
 * | the DOM | oldest first | how a chat log reads |
 *
 * The reversal happens in exactly one place: `select` below. It **copies before
 * reversing**, because `Array.reverse` mutates and the array it would mutate is
 * the cached server response.
 *
 * It follows that a newly arrived message belongs at the **head of
 * `pages[0].items`**, which is what `upsertMessage` does.
 *
 * **The workspace id leads every key**, for the reason `useChannels.ts` gives:
 * a token is scoped to one workspace, so a switch reads a different cache entry
 * rather than relying on a lifecycle hook somebody could forget.
 */

import {
  useInfiniteQuery,
  useMutation,
  useQueryClient,
  type QueryClient,
} from '@tanstack/react-query'

import { problemFromBody } from '../../lib/api/client'
import {
  deleteMessage,
  editMessage,
  listMessages,
  type Message,
  type MessagePage,
} from '../../lib/api/messaging'
import type { Socket } from '../../lib/realtime/socket'

/**
 * How long to wait for an acknowledgement before rolling a send back.
 *
 * Short enough that nobody is left staring at a greyed bubble, long enough that
 * an ordinary slow round trip is not mistaken for a failure.
 */
const SEND_TIMEOUT_MS = 5000

/** The acknowledgement envelope the socket handlers return (doc 02 §3.2.3). */
interface Ack {
  ok: boolean
  data?: unknown
  problem?: { status?: number; title?: string; detail?: string; errors?: Record<string, string[]> }
}

export const messageKeys = {
  list: (workspaceId: string | null, channelId: string | undefined) =>
    ['messages', workspaceId, channelId] as const,
}

/** What `useInfiniteQuery` keeps in the cache. */
interface InfiniteMessages {
  pages: MessagePage[]
  pageParams: unknown[]
}

export function useMessages(
  accessToken: string,
  workspaceId: string | null,
  channelId: string | undefined,
) {
  return useInfiniteQuery({
    queryKey: messageKeys.list(workspaceId, channelId),
    queryFn: ({ pageParam }) =>
      listMessages(accessToken, channelId as string, pageParam as string | undefined),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.nextCursor ?? undefined,
    enabled: Boolean(channelId),
    // Copy, then reverse. Both levels: the pages arrive newest-page-first and
    // each page is newest-message-first, and the DOM wants the whole thing the
    // other way up.
    select: (data) => [...data.pages].reverse().flatMap((page) => [...page.items].reverse()),
  })
}

/**
 * Insert a message, or replace it where it already sits.
 *
 * **Never a blind append.** The sender receives its own broadcast once the
 * socket exists, and there is no id to skip it by — so Ada's message would
 * arrive twice and render twice. Keying on `message.id` and replacing in place
 * makes the second arrival a no-op instead.
 *
 * Head of the newest page *is* id order here: history is newest-first and
 * `messages.id` is UUID v7, so anything new sorts above everything cached.
 *
 * **No-ops when nothing is cached.** Seeding a one-message page with a null
 * `nextCursor` would fabricate a history the user can never scroll past —
 * which is what an inbound event for a channel nobody has opened would
 * otherwise do.
 */
export function upsertMessage(
  queryClient: QueryClient,
  key: readonly unknown[],
  message: Message,
): void {
  queryClient.setQueryData<InfiniteMessages>(key, (cached) => {
    if (!cached) return cached

    const existing = cached.pages.some((page) => page.items.some((m) => m.id === message.id))
    if (existing) {
      return {
        ...cached,
        pages: cached.pages.map((page) => ({
          ...page,
          items: page.items.map((m) => (m.id === message.id ? message : m)),
        })),
      }
    }

    const [newest, ...rest] = cached.pages
    return {
      ...cached,
      pages: [{ ...newest, items: [message, ...newest.items] }, ...rest],
    }
  })
}

/**
 * Drop a message from the cache entirely.
 *
 * Not what a *delete* does — a deleted message stays in history as a tombstone
 * and goes through `upsertMessage` like any other change. This is for a row
 * that was never real: the optimistic placeholder an unconfirmed send leaves
 * behind, which has to disappear when the server refuses it.
 */
export function removeMessage(
  queryClient: QueryClient,
  key: readonly unknown[],
  messageId: string,
): void {
  queryClient.setQueryData<InfiniteMessages>(key, (cached) => {
    if (!cached) return cached
    return {
      ...cached,
      pages: cached.pages.map((page) => ({
        ...page,
        items: page.items.filter((m) => m.id !== messageId),
      })),
    }
  })
}

/** A message id that only exists in this browser. The prefix *is* the marker. */
export const PENDING_PREFIX = 'temp:'

export function isPending(message: Message): boolean {
  return message.id.startsWith(PENDING_PREFIX)
}

/**
 * The row rendered the instant someone hits enter.
 *
 * A complete `Message`-shaped object, so `MessageItem` draws it with no second
 * component and no branch — the only thing that distinguishes it is the `temp:`
 * id, which is also what greys it. **Nothing goes into Zustand:** a map of
 * in-flight sends keyed by temp id is a second copy of the message list wearing
 * a hat, and the store holds no server-shaped data.
 */
function optimistic(channelId: string, authorId: string, body: string): Message {
  return {
    id: `${PENDING_PREFIX}${crypto.randomUUID()}`,
    channelId,
    authorId,
    threadRootId: null,
    body,
    attachments: [],
    createdAt: new Date().toISOString(),
    editedAt: null,
    deletedAt: null,
    version: 0,
  }
}

/**
 * Send over the socket, rendering the message before the server has it.
 *
 * **Reconciliation is remove-then-upsert, and the order matters.** Socket.IO
 * gives no ordering guarantee between a broadcast and an ack, and the sender is
 * in the room — so `message_received` for Ada's own message can arrive *before*
 * her ack does. Dropping the `temp:` row and then upserting by real id is
 * idempotent, so it does not matter which got there first; reconciling on the
 * ack alone would render the message twice.
 *
 * **A lost ack rolls back within five seconds.** `emit` with no connection does
 * not fail — it buffers, and the callback never fires — so without the timeout
 * the bubble would sit there greyed forever with no error and no way out.
 *
 * **A timed-out send is never retried.** It rolls back, puts the text back in
 * the composer's draft, and says why. `send_message` carries no idempotency key,
 * so an automatic retry is how one message becomes two. There is no offline
 * queue in this scope for the same reason: it would need ordering, durable
 * storage and dedupe against a write that cannot be deduped.
 */
export function useSendMessage(
  socket: Socket | null,
  workspaceId: string | null,
  channelId: string,
  userId: string,
) {
  const queryClient = useQueryClient()
  const key = messageKeys.list(workspaceId, channelId)

  return useMutation<Message, Error, string, { pendingId: string; body: string }>({
    mutationFn: (body) =>
      new Promise((resolve, reject) => {
        if (!socket) {
          reject(new Error('Not connected. Try again in a moment.'))
          return
        }
        socket
          .timeout(SEND_TIMEOUT_MS)
          .emit('send_message', { channelId, body }, (transportError: unknown, ack?: Ack) => {
            if (transportError || !ack) {
              reject(new Error('The server did not confirm that message. Nothing was sent.'))
            } else if (ack.ok) {
              resolve(ack.data as Message)
            } else {
              reject(problemFromBody(ack.problem?.status ?? 500, ack.problem))
            }
          })
      }),
    onMutate: (body) => {
      const pending = optimistic(channelId, userId, body)
      upsertMessage(queryClient, key, pending)
      return { pendingId: pending.id, body }
    },
    onSuccess: (message, _body, context) => {
      if (context) removeMessage(queryClient, key, context.pendingId)
      upsertMessage(queryClient, key, message)
    },
    onError: (_error, _body, context) => {
      if (context) removeMessage(queryClient, key, context.pendingId)
    },
  })
}

/**
 * Edit and delete both write the returned message straight back into the cache.
 *
 * Not `invalidateQueries`: this is an infinite query, so invalidating refetches
 * every loaded page and throws away the scroll position `MessageList` works to
 * hold. `upsertMessage` replaces the one row that changed.
 *
 * A delete goes through the same helper as an edit, and not through
 * `removeMessage` — the tombstone stays in the list and has to be rendered.
 */
export function useEditMessage(
  accessToken: string,
  workspaceId: string | null,
  channelId: string,
) {
  const queryClient = useQueryClient()
  const key = messageKeys.list(workspaceId, channelId)

  return useMutation<Message, Error, { messageId: string; body: string; version: number }>({
    mutationFn: ({ messageId, body, version }) =>
      editMessage(accessToken, messageId, { body, version }),
    onSuccess: (message) => upsertMessage(queryClient, key, message),
  })
}

export function useDeleteMessage(
  accessToken: string,
  workspaceId: string | null,
  channelId: string,
) {
  const queryClient = useQueryClient()
  const key = messageKeys.list(workspaceId, channelId)

  return useMutation<Message, Error, string>({
    mutationFn: (messageId) => deleteMessage(accessToken, messageId),
    onSuccess: (message) => upsertMessage(queryClient, key, message),
  })
}
