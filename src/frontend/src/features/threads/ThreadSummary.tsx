/**
 * "2 replies", and when the last one came, under the message they answer.
 *
 * A button, because it is how a thread opens from the channel — and the only way
 * into a deleted root's thread. Renders nothing at zero: a message nobody has
 * answered shows no thread furniture. The time is `<time dateTime>` like every
 * other time in the UI, in the browser's own locale and the user's clock
 * preference (register D28).
 */

import { formatTime, useClock } from '../settings/clock'

interface Props {
  replyCount: number
  lastReplyAt: string | null
  onOpen: () => void
}

export function ThreadSummary({ replyCount, lastReplyAt, onOpen }: Props) {
  const clock = useClock()
  if (replyCount === 0) return null

  return (
    <button
      type="button"
      data-testid="thread-summary"
      data-reply-count={replyCount}
      onClick={onOpen}
      className="flex w-fit items-baseline gap-2 text-xs text-accent hover:underline"
    >
      {replyCount === 1 ? '1 reply' : `${replyCount} replies`}
      {lastReplyAt && (
        <span className="text-ink-muted">
          last reply <time dateTime={lastReplyAt}>{formatTime(lastReplyAt, clock)}</time>
        </span>
      )}
    </button>
  )
}
