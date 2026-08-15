/**
 * The channel sidebar.
 *
 * Shows every channel the caller may know about — public channels in the
 * workspace whether or not they have joined, plus private ones they belong to.
 * The server decides that and the order; this renders what it returns.
 */

import { NavLink } from 'react-router-dom'

import { useChannels } from './useChannels'

interface Props {
  accessToken: string
  workspaceId: string | null
}

export function ChannelList({ accessToken, workspaceId }: Props) {
  const { data: channels, isPending, error } = useChannels(accessToken, workspaceId)

  if (isPending) {
    return (
      <p data-testid="channel-list-loading" className="p-3 text-sm text-ink-muted">
        Loading channels…
      </p>
    )
  }

  if (error) {
    return (
      <p data-testid="channel-list-error" role="alert" className="p-3 text-sm text-danger">
        {error.message}
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
      {channels.map((channel) => (
        <li key={channel.id}>
          <NavLink
            to={`/c/${channel.id}`}
            data-testid="channel-list-item"
            data-channel-name={channel.name}
            className={({ isActive }) =>
              [
                'block rounded px-2 py-1 text-sm',
                isActive ? 'bg-accent text-accent-ink' : 'text-ink hover:bg-surface-sunken',
              ].join(' ')
            }
          >
            <span aria-hidden="true" className="opacity-60">
              #
            </span>{' '}
            {channel.name}
          </NavLink>
        </li>
      ))}
    </ul>
  )
}
