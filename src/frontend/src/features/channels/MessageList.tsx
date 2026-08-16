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
 */

import { useEffect, useLayoutEffect, useRef } from 'react'

import { ProblemBanner } from '../../components/ProblemBanner'
import type { Message } from '../../lib/api/messaging'
import { MessageItem } from './MessageItem'
import { useDeleteMessage, useEditMessage, useMessages } from './useMessages'
import { useWorkspaceMembers } from './useWorkspaceMembers'

interface Props {
  accessToken: string
  workspaceId: string | null
  channelId: string
  /** The signed-in user, so each row knows whose words it is showing. */
  userId: string
  /** The caller's role in this channel — `admin` may delete anyone's message. */
  myRole: string | null
}

/** Within this many pixels of the bottom counts as "watching the live end". */
const STICK_THRESHOLD = 80
/** Within this many pixels of the top starts fetching the next page back. */
const LOAD_THRESHOLD = 120

export function MessageList({ accessToken, workspaceId, channelId, userId, myRole }: Props) {
  const scroller = useRef<HTMLDivElement>(null)
  const heightBeforePrepend = useRef<number | null>(null)
  const wasAtBottom = useRef(true)
  const previousCount = useRef(0)

  const directory = useWorkspaceMembers(accessToken, workspaceId)
  const { data, isPending, error, hasNextPage, isFetchingNextPage, fetchNextPage } = useMessages(
    accessToken,
    workspaceId,
    channelId,
  )
  // One mutation for the whole list rather than one per row: an edit is a
  // modal act — nobody edits two messages at once — and hanging the hooks off
  // each `MessageItem` would mean a mutation object per rendered message.
  const edit = useEditMessage(accessToken, workspaceId, channelId)
  const remove = useDeleteMessage(accessToken, workspaceId, channelId)

  const messages: Message[] = data ?? []

  function onScroll() {
    const element = scroller.current
    if (!element) return

    wasAtBottom.current =
      element.scrollHeight - element.scrollTop - element.clientHeight < STICK_THRESHOLD

    if (element.scrollTop < LOAD_THRESHOLD && hasNextPage && !isFetchingNextPage) {
      // Remember where the content started so the prepend can be undone.
      heightBeforePrepend.current = element.scrollHeight
      void fetchNextPage()
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
      return
    }

    const grew = messages.length > previousCount.current
    previousCount.current = messages.length
    if (grew && wasAtBottom.current) {
      element.scrollTop = element.scrollHeight
    }
  }, [messages.length])

  // A different channel is a different conversation: start at its live end.
  useEffect(() => {
    wasAtBottom.current = true
    previousCount.current = 0
    heightBeforePrepend.current = null
  }, [channelId])

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
    <div
      ref={scroller}
      onScroll={onScroll}
      data-testid="message-list"
      className="flex-1 overflow-y-auto"
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
          <MessageItem
            key={message.id}
            message={message}
            authorName={directory.nameFor(message.authorId)}
            userId={userId}
            myRole={myRole}
            editError={edit.variables?.messageId === message.id ? edit.error : undefined}
            editPending={edit.isPending && edit.variables?.messageId === message.id}
            onEdit={(body, version) => edit.mutate({ messageId: message.id, body, version })}
            onDelete={() => remove.mutate(message.id)}
          />
        ))
      )}

      {/* A refused delete has no field to sit against and no editor open to
          show it in, so it belongs here rather than on the row. */}
      <ProblemBanner error={remove.error} />
    </div>
  )
}
