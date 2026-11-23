/**
 * The channel sidebar.
 *
 * Shows every channel the caller may know about — public channels in the
 * workspace whether or not they have joined, plus private ones they belong to.
 * The server decides that and the order; this renders what it returns.
 *
 * A channel with unread messages gets a bold name and a count pill, except the
 * one being read right now (`readingChannelId`): its count is about to be
 * cleared by that very read, and flashing it between a refetch and the ack would
 * be noise. The moment the page stops being watched the badge is back.
 */

import { NavLink } from 'react-router-dom'

import { useChatStore } from '../../stores/chat'
import { isDm } from './directMessages'
import { UnreadBadge } from './UnreadBadge'
import { useChannelListRefresh, useChannels } from './useChannels'

interface Props {
  accessToken: string
  workspaceId: string | null
  /** Called when a channel link is followed — the narrow shell closes its drawer. */
  onNavigate?: () => void
}

export function ChannelList({ accessToken, workspaceId, onNavigate }: Props) {
  const { data: all, isPending, error } = useChannels(accessToken, workspaceId)
  // Direct messages have a section of their own (`DirectMessageList`).
  const channels = all?.filter((channel) => !isDm(channel))
  const readingChannelId = useChatStore((state) => state.readingChannelId)
  useChannelListRefresh(workspaceId)

  if (isPending) {
    return (
      <p data-testid="channel-list-loading" className="p-3 text-sm text-ink-muted">
        Loading channels…
      </p>
    )
  }

  // TanStack keeps `data` when a refetch fails but still sets `error`, so
  // testing `error` alone would replace a list the user is using with a banner.
  if (channels === undefined) {
    return (
      <p data-testid="channel-list-error" role="alert" className="p-3 text-sm text-danger">
        {error?.message}
      </p>
    )
  }

  if (channels.length === 0) {
    return (
      <p data-testid="channel-list-empty" className="p-3 text-sm text-ink-muted">
        No channels yet. Create the first one.
      </p>
    )
  }

  return (
    <ul data-testid="channel-list" className="flex flex-col gap-0.5 p-2">
      {channels.map((channel) => {
        const unread = channel.unreadCount > 0 && channel.id !== readingChannelId
        return (
          <li key={channel.id}>
            <NavLink
              to={`/c/${channel.id}`}
              data-testid="channel-list-item"
              data-channel-name={channel.name}
              onClick={onNavigate}
              className={({ isActive }) =>
                [
                  'flex items-center justify-between gap-2 rounded px-2 py-1 text-sm',
                  isActive ? 'bg-accent text-accent-ink' : 'text-ink hover:bg-surface-sunken',
                ].join(' ')
              }
            >
              <span>
                <span aria-hidden="true" className="opacity-60">
                  #
                </span>{' '}
                <span className={unread ? 'font-semibold' : undefined}>{channel.name}</span>
              </span>
              {unread && <UnreadBadge count={channel.unreadCount} />}
            </NavLink>
          </li>
        )
      })}
    </ul>
  )
}
