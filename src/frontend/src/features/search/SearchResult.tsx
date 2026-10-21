/**
 * One search hit: where it was said, who said it, when, and the words.
 *
 * The whole row is a link to `/c/<channel>?message=<id>` — a real anchor, so a
 * middle-click and a reload both work — and the channel's jump does the rest. The
 * body is a React text child, never markup, and nothing is highlighted in it: the
 * server returns no match offsets. The date format is the browser's locale, with
 * the hour cycle of the user's clock preference (register D28).
 */

import { Link } from 'react-router-dom'

import type { Message } from '../../lib/api/messaging'
import { formatDateTime, useClock } from '../settings/clock'

interface Props {
  message: Message
  /** `#general`, or the other person's name for a DM; `null` while unknown — shown as `#…`. */
  channelTitle: string | null
  authorName: string
}

export function SearchResult({ message, channelTitle, authorName }: Props) {
  const clock = useClock()
  return (
    <Link
      to={`/c/${message.channelId}?message=${message.id}`}
      data-testid="search-result"
      data-message-id={message.id}
      className="flex flex-col gap-0.5 rounded px-3 py-2 hover:bg-surface-sunken"
    >
      <span className="flex items-baseline gap-2 text-xs text-ink-muted">
        <span className="font-medium text-ink">{channelTitle ?? '#…'}</span>
        <span>{authorName}</span>
        <time dateTime={message.createdAt}>{formatDateTime(message.createdAt, clock)}</time>
        {message.editedAt && <span>(edited)</span>}
      </span>
      <p className="text-sm whitespace-pre-wrap text-ink">{message.body}</p>
    </Link>
  )
}
