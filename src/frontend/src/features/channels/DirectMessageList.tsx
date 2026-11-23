/**
 * The sidebar's *Direct messages* section and its member picker (issue 5).
 *
 * Lists the caller's `kind: 'dm'` channels — the server sends a DM only once it
 * has a message — each named after the other person, with the same count pill and
 * bold name as a channel. The **+** opens a picker of everyone else in the
 * workspace; picking someone opens (get or create) the one DM the two share and
 * goes to it.
 *
 * Reads the channel list and the directory itself, so `ChannelList` stays a list
 * of channels that never waits on the directory.
 *
 * **Opening can outlive a workspace switch.** The mutation records the workspace
 * it started in, and the navigation happens only if that is still the current one
 * (a ref, because the callback closes over an older render); landing in another
 * workspace on a channel id that does not exist there would show a 404.
 */

import { useEffect, useRef, useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'

import { useChatStore } from '../../stores/chat'
import { channelLabel, sortedDms } from './directMessages'
import { UnreadBadge } from './UnreadBadge'
import { useChannels, useOpenDirectMessage } from './useChannels'
import { useWorkspaceMembers } from './useWorkspaceMembers'

interface Props {
  accessToken: string
  workspaceId: string | null
  userId: string
  /**
   * Called when a DM link is followed, and when a picked DM has opened and the app
   * has navigated to it — not at the pick: a failed open shows nothing, and a
   * drawer closed at the pick would leave the user on the old screen with no sign why.
   */
  onNavigate?: () => void
}

export function DirectMessageList({ accessToken, workspaceId, userId, onNavigate }: Props) {
  const navigate = useNavigate()
  const { data: channels } = useChannels(accessToken, workspaceId)
  const directory = useWorkspaceMembers(accessToken, workspaceId)
  const readingChannelId = useChatStore((state) => state.readingChannelId)
  const open = useOpenDirectMessage(accessToken)
  const [picking, setPicking] = useState(false)

  const currentWorkspace = useRef(workspaceId)
  useEffect(() => {
    currentWorkspace.current = workspaceId
  }, [workspaceId])

  const dms = sortedDms(channels ?? [], directory.nameFor)
  const others = directory.members
    .filter((member) => member.user.id !== userId)
    .sort((a, b) => a.user.displayName.localeCompare(b.user.displayName))

  function pick(otherId: string) {
    setPicking(false)
    open.mutate(
      { userId: otherId, workspaceId },
      {
        onSuccess: (channel, variables) => {
          if (variables.workspaceId === currentWorkspace.current) {
            navigate(`/c/${channel.id}`)
            onNavigate?.()
          }
        },
      },
    )
  }

  return (
    <section aria-labelledby="dm-heading" className="p-2">
      <div className="flex items-center justify-between px-2">
        <h3
          id="dm-heading"
          className="text-xs font-semibold uppercase tracking-wide text-ink-muted"
        >
          Direct messages
        </h3>
        <button
          type="button"
          data-testid="dm-new"
          aria-label="New direct message"
          aria-expanded={picking}
          onClick={() => setPicking((value) => !value)}
          className="rounded px-1.5 text-sm text-ink-muted hover:bg-surface-sunken"
        >
          +
        </button>
      </div>

      {picking && (
        <ul className="mt-1 flex flex-col gap-0.5 rounded border border-border bg-surface p-1">
          {others.map((member) => (
            <li key={member.user.id}>
              <button
                type="button"
                data-testid="dm-pick"
                data-member-name={member.user.displayName}
                onClick={() => pick(member.user.id)}
                className="w-full rounded px-2 py-1 text-left text-sm text-ink hover:bg-surface-sunken"
              >
                {member.user.displayName}
              </button>
            </li>
          ))}
        </ul>
      )}

      <ul className="mt-1 flex flex-col gap-0.5">
        {dms.map((dm) => {
          const label = channelLabel(dm, directory.nameFor)
          const unread = dm.unreadCount > 0 && dm.id !== readingChannelId
          return (
            <li key={dm.id}>
              <NavLink
                to={`/c/${dm.id}`}
                data-testid="dm-list-item"
                data-dm-name={label}
                onClick={onNavigate}
                className={({ isActive }) =>
                  [
                    'flex items-center justify-between gap-2 rounded px-2 py-1 text-sm',
                    isActive ? 'bg-accent text-accent-ink' : 'text-ink hover:bg-surface-sunken',
                  ].join(' ')
                }
              >
                <span className={unread ? 'font-semibold' : undefined}>{label}</span>
                {unread && <UnreadBadge count={dm.unreadCount} />}
              </NavLink>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
