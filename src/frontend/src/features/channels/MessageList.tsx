/**
 * A channel's history, oldest at the top, loading more as you scroll back.
 *
 * Two pieces of scroll behaviour that no design doc specifies and that every
 * chat app needs:
 *
 * **Anchoring on prepend.** Older messages are added *above* what the reader is
 * looking at, and the browser keeps `scrollTop` where it was — so the content
 * under the cursor jumps down by a page every time a page loads. The fix is to
 * record `scrollHeight` before the prepend and add the difference back in a
 * `useLayoutEffect`, before the browser paints.
 *
 * **Sticking to the bottom, but only if you were there.** A new message should
 * scroll into view for someone watching the live end of a conversation, and
 * must not yank someone who has scrolled up to read something. So the decision
 * is made *before* the render that adds the message, not after.
 *
 * **Who may cancel whom.** History has three fetchers: the mount and join-ack
 * refetches, and `loadOlder` (a scroll to the top, or a jump paging back). A page
 * fetch never cancels a refetch — it passes `cancelRefetch: false` and fetches
 * only when nothing is running — and a refetch never cancels a page fetch
 * (`refetchHistory` waits for it). A scroll to the top that finds a refetch
 * running fetches nothing and sets no anchor; the older page is fetched when the
 * refetch lands, if the reader is still near the top, because no further scroll
 * event can fire for someone already at `scrollTop` 0.
 */

import { useQueryClient } from '@tanstack/react-query'
import { Fragment, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'

import { ProblemBanner } from '../../components/ProblemBanner'
import type { Message } from '../../lib/api/messaging'
import { useSocket } from '../../lib/realtime/SocketProvider'
import { useChatStore } from '../../stores/chat'
import { AttachmentList } from '../attachments/AttachmentList'
import { MessageItem } from './MessageItem'
import { captureFor, findDivider, readTarget, type DividerCapture } from './readState'
import { useMarkRead } from './useMarkRead'
import { usePageAttention } from './usePageAttention'
import { useMessageJump } from './useMessageJump'
import {
  loadedPageCount,
  messageKeys,
  useDeleteMessage,
  useEditMessage,
  useMessages,
  useToggleReaction,
} from './useMessages'
import { useWorkspaceMembers } from './useWorkspaceMembers'

interface Props {
  accessToken: string
  workspaceId: string | null
  channelId: string
  /** The signed-in user, so each row knows whose words it is showing. */
  userId: string
  /** The caller's role in this channel — `admin` may delete anyone's message. */
  myRole: string | null
  /** The channel detail's marker, as `ChannelView` holds it — captured once per visit. */
  lastReadId: string | null
  /** The detail query's `isFetching`: the capture waits for it to settle. */
  channelFetching: boolean
  /** Open a message's thread; absent and the rows offer no thread action. */
  onOpenThread?: (rootId: string) => void
}

/** Within this many pixels of the bottom counts as "watching the live end". */
export const STICK_THRESHOLD = 80
/** Within this many pixels of the top starts fetching the next page back. */
export const LOAD_THRESHOLD = 120

/** Nothing loaded yet — one array, so an effect that depends on it is not re-run each render. */
const NO_MESSAGES: Message[] = []

/**
 * Whether the viewport is at the live end. The gap below the viewport, not the
 * gap below the top edge: at the very bottom `scrollTop` stops a whole
 * `clientHeight` short of `scrollHeight`.
 */
function measure(element: HTMLElement): boolean {
  return element.scrollHeight - element.scrollTop - element.clientHeight < STICK_THRESHOLD
}

export function MessageList({
  accessToken,
  workspaceId,
  channelId,
  userId,
  myRole,
  lastReadId,
  channelFetching,
  onOpenThread,
}: Props) {
  const scroller = useRef<HTMLDivElement>(null)
  const heightBeforePrepend = useRef<number | null>(null)
  const wasAtBottom = useRef(true)
  const previousCount = useRef(0)
  // Measured, never assumed: a fresh list is not "at the bottom" until its own
  // scroll to the newest message has been measured.
  const [atBottom, setAtBottom] = useState(false)
  const [capture, setCapture] = useState<DividerCapture | null>(null)
  const [pinnedDivider, setPinnedDivider] = useState<string | null>(null)

  const socket = useSocket()
  const attending = usePageAttention()
  const { request, connected, flush } = useMarkRead(socket, workspaceId, channelId)
  const setReadingChannel = useChatStore((state) => state.setReadingChannel)
  const queryClient = useQueryClient()
  // Memoised: the key is a dependency of `loadOlder`, which the jump's effect
  // depends on in turn.
  const historyKey = useMemo(
    () => messageKeys.list(workspaceId, channelId),
    [workspaceId, channelId],
  )
  // Asked in the scroll handler and the effects, so read from the cache then.
  const olderWanted = useRef(false)

  const directory = useWorkspaceMembers(accessToken, workspaceId)
  const {
    data,
    isPending,
    isFetching,
    isSuccess,
    isError,
    error,
    hasNextPage,
    isFetchingNextPage,
    fetchNextPage,
  } = useMessages(accessToken, workspaceId, channelId)
  // One mutation for the whole list rather than one per row: an edit is a
  // modal act — nobody edits two messages at once — and hanging the hooks off
  // each `MessageItem` would mean a mutation object per rendered message.
  const edit = useEditMessage(accessToken, workspaceId, channelId)
  const remove = useDeleteMessage(accessToken, workspaceId, channelId)
  const toggleReaction = useToggleReaction(accessToken, workspaceId, channelId, userId)

  const messages: Message[] = data ?? NO_MESSAGES

  /**
   * Fetch the next older page, anchored so the prepend keeps the view where it
   * was — for a scroll to the top and for a jump paging back alike. Only when
   * there is an older page and nothing is fetching *now* (the cache, not this
   * render's `isFetching`), so there is one fetch at a time whoever asks.
   */
  const loadOlder = useCallback(() => {
    if (!hasNextPage || queryClient.isFetching({ queryKey: historyKey, exact: true }) > 0) return
    const element = scroller.current
    // Remember where the content started so the prepend can be undone.
    if (element) heightBeforePrepend.current = element.scrollHeight
    void fetchNextPage({ cancelRefetch: false })
  }, [hasNextPage, queryClient, historyKey, fetchNextPage])

  const onScrolled = useCallback(() => {
    const element = scroller.current
    if (!element) return
    const bottom = measure(element)
    wasAtBottom.current = bottom
    setAtBottom(bottom)
  }, [])

  const jump = useMessageJump(
    {
      messages,
      loadedPages: loadedPageCount(queryClient, historyKey),
      hasNextPage: Boolean(hasNextPage),
      isFetching,
      isError,
      isSuccess,
      loadOlder,
    },
    scroller,
    onScrolled,
  )

  // A read held by the throttle when a jump starts was earned before it; send it
  // now rather than at the end of its window, which would be a read mid-jump.
  useEffect(() => {
    if (jump.jumping) flush()
  }, [jump.jumping, flush])

  // A refetch that was running when the reader reached the top: fetch the older
  // page now it has landed, if they are still near the top.
  useEffect(() => {
    if (isFetching || !olderWanted.current) return
    olderWanted.current = false
    const element = scroller.current
    if (element && element.scrollTop < LOAD_THRESHOLD) loadOlder()
  }, [isFetching, loadOlder])

  // The divider's anchor is taken once per visit (the list is remounted per
  // channel), at the first render where both the detail and the history have
  // settled. A cached channel is refetched on return, so this waits for the
  // refetches and takes today's marker, not the stale cached one.
  useEffect(() => {
    if (capture !== null || channelFetching || !isSuccess || isFetching) return
    setCapture(captureFor(lastReadId, messages))
  }, [capture, channelFetching, isSuccess, isFetching, lastReadId, messages])

  // Once found, the divider's message is pinned for the visit: the marker moves
  // as the user reads, and a deleted message stops qualifying.
  const found = capture ? findDivider(messages, capture, userId, Boolean(hasNextPage)) : null
  useEffect(() => {
    if (pinnedDivider === null && found !== null) setPinnedDivider(found)
  }, [pinnedDivider, found])
  const dividerId = pinnedDivider ?? found

  // Not during a jump: a fresh list is "at the bottom" for a moment, and the
  // open channel usually is, but the reader is about to be moved away from it.
  const beingRead = attending && atBottom && !jump.jumping
  useEffect(() => {
    setReadingChannel(beingRead ? channelId : null)
    return () => setReadingChannel(null)
  }, [beingRead, channelId, setReadingChannel])

  // Ask for a read whenever every condition holds, and again when any changes —
  // a new newest message, the connection coming back. The sender decides whether
  // there is anything to send. Not before the capture: the read would move the
  // marker the divider is about to be taken from.
  const target = readTarget(messages)
  useEffect(() => {
    if (beingRead && capture !== null && connected && target !== null) request(target)
  }, [beingRead, capture, connected, target, request])

  function onScroll() {
    const element = scroller.current
    if (!element) return

    const bottom = measure(element)
    wasAtBottom.current = bottom
    setAtBottom(bottom)

    if (element.scrollTop < LOAD_THRESHOLD && hasNextPage && !isFetchingNextPage) {
      // A refetch is running: it must not be cancelled, and an anchor set now
      // would be stale when it lands. Remember the wish instead.
      if (queryClient.isFetching({ queryKey: historyKey, exact: true }) > 0) {
        olderWanted.current = true
        return
      }
      loadOlder()
    }
  }

  useLayoutEffect(() => {
    const element = scroller.current
    if (!element) return

    const before = heightBeforePrepend.current
    if (before !== null && element.scrollHeight !== before) {
      element.scrollTop += element.scrollHeight - before
      heightBeforePrepend.current = null
      previousCount.current = messages.length
    } else {
      const previous = previousCount.current
      const grew = messages.length > previous
      previousCount.current = messages.length
      // A fresh list still makes its first scroll to the newest message; after
      // that, growth does not pull the reader away from a message being sought.
      if (grew && wasAtBottom.current && (!jump.jumping || previous === 0)) {
        element.scrollTop = element.scrollHeight
      }
    }

    // Measure after any programmatic scroll: that is what says whether the
    // reader is, now, at the live end. `isPending` is a dependency because the
    // scroller does not exist until the history arrives, even when it is empty.
    setAtBottom(measure(element))
  }, [messages.length, isPending, jump.jumping])

  if (isPending) {
    return (
      <p data-testid="message-list-loading" className="p-6 text-sm text-ink-muted">
        Loading messages…
      </p>
    )
  }

  if (error) {
    return (
      <p data-testid="message-list-error" role="alert" className="p-6 text-sm text-danger">
        {error.message}
      </p>
    )
  }

  return (
    <>
      {jump.tooFarBack && (
        <p
          role="status"
          data-testid="jump-notice"
          className="border-b border-line bg-surface px-4 py-2 text-sm text-ink-muted"
        >
          That message is too far back to show.
        </p>
      )}
    <div
      ref={scroller}
      onScroll={onScroll}
      data-testid="message-list"
      className="flex-1 overflow-y-auto"
      // Where focus goes when the row holding it goes away (a live delete).
      data-focus-fallback
      tabIndex={-1}
    >
      {isFetchingNextPage && (
        <p data-testid="message-list-older" className="p-2 text-center text-xs text-ink-muted">
          Loading older messages…
        </p>
      )}

      {messages.length === 0 ? (
        <p data-testid="message-list-empty" className="p-6 text-sm text-ink-muted">
          Nothing here yet. Say something.
        </p>
      ) : (
        messages.map((message) => (
          <Fragment key={message.id}>
            {message.id === dividerId && (
              <div
                role="separator"
                aria-label="New messages"
                data-testid="new-messages-divider"
                className="flex items-center gap-2 px-4 py-1 text-xs font-semibold text-danger"
              >
                <span aria-hidden="true" className="h-px flex-1 bg-current opacity-40" />
                New messages
                <span aria-hidden="true" className="h-px flex-1 bg-current opacity-40" />
              </div>
            )}
            <MessageItem
              message={message}
              authorName={directory.nameFor(message.authorId)}
              userId={userId}
              myRole={myRole}
              editError={edit.variables?.messageId === message.id ? edit.error : undefined}
              editPending={edit.isPending && edit.variables?.messageId === message.id}
              onEdit={(body, version) => edit.mutate({ messageId: message.id, body, version })}
              onDelete={() => remove.mutate(message.id)}
              onToggleReaction={(emoji) => toggleReaction.mutate({ message, emoji })}
              onOpenThread={onOpenThread && (() => onOpenThread(message.id))}
              highlighted={message.id === jump.highlightedId}
              attachments={
                message.attachments.length > 0 ? (
                  <AttachmentList
                    message={message}
                    accessToken={accessToken}
                    workspaceId={workspaceId}
                  />
                ) : undefined
              }
            />
          </Fragment>
        ))
      )}

      {/* A refused delete has no field to sit against and no editor open to
          show it in, so it belongs here rather than on the row. */}
      <ProblemBanner error={remove.error} />
    </div>
    </>
  )
}
