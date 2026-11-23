/**
 * A thread, beside the channel: the root, its replies oldest first, a composer.
 *
 * **It never touches the channel's read state** (R13) — no `setReadingChannel`,
 * no `useMarkRead`. A reply is not in the channel's history, so reading one is
 * not reading the channel, and the server refuses a `mark_read` that names one.
 *
 * **What "not there" means.** With no data (the first load: a 404 for an unknown
 * id, a reply's id or a channel the caller cannot see, a 422 for a malformed id,
 * a 5xx alike) the panel says "This thread isn't available." and the channel
 * beside it is unaffected. With data already loaded, a failed background refetch
 * keeps showing the thread — replacing a readable thread over a transient error
 * would be worse than showing it a moment stale. A root that belongs to another
 * channel is the same notice: the thread route knows nothing of the URL's
 * channel, so this is where that is checked.
 *
 * **The replies scroll on their own rules**, the channel list's rules over its
 * own element: older replies are loaded when the reader reaches the top, and the
 * scroll position is held by the height they add; a new reply sticks to the
 * bottom when it is yours, or when the reader was already at the live end —
 * decided before the render that adds it. The root sits above the scroller, not
 * in it, so it stays in view.
 */

import { useLayoutEffect, useRef } from 'react'

import { ProblemBanner } from '../../components/ProblemBanner'
import type { Message } from '../../lib/api/messaging'
import { MessageItem } from '../channels/MessageItem'
import { LOAD_THRESHOLD, STICK_THRESHOLD } from '../channels/MessageList'
import { useWorkspaceMembers } from '../channels/useWorkspaceMembers'
import { ThreadComposer } from './ThreadComposer'
import { useThread, useThreadActions } from './useThread'

interface Props {
  accessToken: string
  workspaceId: string | null
  channelId: string
  rootId: string
  userId: string
  /** The caller's role in the channel — `admin` may delete anyone's message. */
  myRole: string | null
  onClose: () => void
  /**
   * Below 768px the panel covers the channel instead of sitting beside it. The same
   * element either way, so a rotation never remounts it and its scroll position and
   * reply draft survive; only the class and the close control's name change.
   */
  fullScreen?: boolean
}

/** Nothing loaded yet — one array, so the layout effect is not re-run each render. */
const NO_REPLIES: Message[] = []

/** The gap below the viewport, as `MessageList`'s `measure` takes it. */
function atLiveEnd(element: HTMLElement): boolean {
  return element.scrollHeight - element.scrollTop - element.clientHeight < STICK_THRESHOLD
}

export function ThreadPanel({
  accessToken,
  workspaceId,
  channelId,
  rootId,
  userId,
  myRole,
  onClose,
  fullScreen = false,
}: Props) {
  const scroller = useRef<HTMLDivElement>(null)
  const heightBeforePrepend = useRef<number | null>(null)
  const wasAtBottom = useRef(true)
  const previousCount = useRef(0)

  const directory = useWorkspaceMembers(accessToken, workspaceId)
  const thread = useThread(accessToken, workspaceId, channelId, rootId)
  const { edit, remove, toggleReaction } = useThreadActions(
    accessToken,
    workspaceId,
    channelId,
    rootId,
    userId,
  )

  const root = thread.data?.root
  const replies = thread.data?.replies ?? NO_REPLIES
  const foreign = root !== undefined && root.channelId !== channelId
  const unavailable = foreign || (thread.isError && root === undefined)
  const showing = root !== undefined && !foreign

  const newest = replies.at(-1)

  // Anchor on a prepend, and stick to the bottom for your own reply, or for
  // someone else's when you were at the live end.
  useLayoutEffect(() => {
    const element = scroller.current
    if (!element) return

    const before = heightBeforePrepend.current
    if (before !== null && element.scrollHeight !== before) {
      element.scrollTop += element.scrollHeight - before
      heightBeforePrepend.current = null
      previousCount.current = replies.length
    } else {
      const grew = replies.length > previousCount.current
      previousCount.current = replies.length
      if (grew && (wasAtBottom.current || newest?.authorId === userId)) {
        element.scrollTop = element.scrollHeight
      }
    }
  }, [replies.length, newest?.authorId, userId, showing])

  function onScroll() {
    const element = scroller.current
    if (!element) return

    wasAtBottom.current = atLiveEnd(element)
    if (element.scrollTop < LOAD_THRESHOLD && thread.hasNextPage && !thread.isFetchingNextPage) {
      // Remember where the content started so the prepend can be undone.
      heightBeforePrepend.current = element.scrollHeight
      void thread.fetchNextPage()
    }
  }

  function row(message: Message) {
    return (
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
        onToggleReaction={(emoji) => toggleReaction.mutate({ message, emoji })}
      />
    )
  }

  return (
    <aside
      aria-label="Thread"
      data-testid="thread-panel"
      // Where focus goes when the row holding it goes away (a live delete).
      data-focus-fallback
      tabIndex={-1}
      className={
        fullScreen
          ? 'absolute inset-0 z-10 flex w-full flex-col bg-surface'
          : 'flex w-80 shrink-0 flex-col border-l border-border'
      }
    >
      <header className="flex items-center justify-between border-b border-border px-4 py-3">
        <h2 className="text-sm font-semibold text-ink">Thread</h2>
        <button
          type="button"
          data-testid="thread-close"
          onClick={onClose}
          className="text-xs text-ink-muted underline"
        >
          {fullScreen ? 'Back to channel' : 'Close thread'}
        </button>
      </header>

      {unavailable ? (
        <p data-testid="thread-unavailable" className="p-4 text-sm text-ink-muted">
          This thread isn&apos;t available.
        </p>
      ) : !showing ? (
        <p className="p-4 text-sm text-ink-muted">Loading thread…</p>
      ) : (
        <>
          <div className="max-h-48 shrink-0 overflow-y-auto border-b border-border">{row(root)}</div>

          <div
            ref={scroller}
            onScroll={onScroll}
            role="log"
            aria-label="Replies"
            className="min-h-0 flex-1 overflow-y-auto"
          >
            {thread.isFetchingNextPage && (
              <p className="p-2 text-center text-xs text-ink-muted">Loading older replies…</p>
            )}
            {replies.map(row)}
            <ProblemBanner error={remove.error} />
          </div>

          <ThreadComposer
            workspaceId={workspaceId}
            channelId={channelId}
            rootId={rootId}
            userId={userId}
          />
        </>
      )}
    </aside>
  )
}
