/**
 * Who is in this channel, and — for an admin — who else could be.
 *
 * Two services answer this one panel. Messaging says which user ids are in the
 * channel; Auth says what those people are called and who else is in the
 * workspace. Messaging holds no names and must not read Auth's tables
 * (Conventions §2), so the join happens here, in the browser, which holds a
 * token entitling it to both.
 *
 * Sorted by display name, which is a rendering decision and not the server's
 * order: the endpoint pages by user id, because that is the primary key it can
 * walk without a sort. With the default page of 50 that is the whole list for
 * any channel this size; across pages the sort would be per-page, which is a
 * real limit and cheaper to accept than an index for a query nobody runs yet.
 */

import { useState } from 'react'

import { ProblemBanner } from '../../components/ProblemBanner'
import type { Channel } from '../../lib/api/messaging'
import { useAddMember, useChannelMembers, useRemoveMember } from './useMembers'
import { useWorkspaceMembers } from './useWorkspaceMembers'

interface Props {
  accessToken: string
  workspaceId: string | null
  channel: Channel
}

export function MemberPanel({ accessToken, workspaceId, channel }: Props) {
  const [selected, setSelected] = useState('')

  const directory = useWorkspaceMembers(accessToken, workspaceId)
  const { data: members, isPending } = useChannelMembers(accessToken, workspaceId, channel.id)
  const add = useAddMember(accessToken, workspaceId, channel.id)
  const remove = useRemoveMember(accessToken, workspaceId, channel.id)

  const isAdmin = channel.myRole === 'admin'
  const inChannel = new Set((members ?? []).map((member) => member.userId))
  const named = (members ?? [])
    .map((member) => ({ ...member, name: directory.nameFor(member.userId) }))
    .sort((a, b) => a.name.localeCompare(b.name))
  const addable = directory.members.filter((member) => !inChannel.has(member.user.id))

  return (
    <aside data-testid="member-panel" className="w-64 shrink-0 border-l border-border p-4">
      <h3 className="text-xs font-medium tracking-wide text-ink-muted uppercase">Members</h3>

      {isPending ? (
        <p className="mt-2 text-sm text-ink-muted">Loading…</p>
      ) : (
        <ul className="mt-2 flex flex-col gap-1">
          {named.map((member) => (
            <li
              key={member.userId}
              data-testid="member-item"
              data-member-name={member.name}
              className="flex items-center justify-between gap-2 text-sm text-ink"
            >
              <span className="truncate">
                {member.name}
                {member.role === 'admin' && (
                  <span className="ml-1 text-xs text-ink-muted">admin</span>
                )}
              </span>
              {isAdmin && (
                <button
                  type="button"
                  data-testid="member-remove"
                  data-member-name={member.name}
                  disabled={remove.isPending}
                  onClick={() => remove.mutate({ userId: member.userId })}
                  className="text-xs text-danger underline disabled:opacity-60"
                >
                  Remove
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {isAdmin && (
        <div className="mt-4 flex flex-col gap-2">
          <select
            data-testid="member-add-select"
            aria-label="Add someone to this channel"
            value={selected}
            onChange={(event) => setSelected(event.target.value)}
            className="rounded border border-border bg-surface px-2 py-1 text-sm text-ink"
          >
            <option value="">Add someone…</option>
            {addable.map((member) => (
              <option key={member.user.id} value={member.user.id}>
                {member.user.displayName}
              </option>
            ))}
          </select>
          <button
            type="button"
            data-testid="member-add-submit"
            disabled={!selected || add.isPending}
            onClick={() =>
              add.mutate({ userId: selected }, { onSuccess: () => setSelected('') })
            }
            className="rounded bg-accent px-3 py-1 text-sm font-medium text-accent-ink disabled:opacity-60"
          >
            Add
          </button>
        </div>
      )}

      <ProblemBanner error={add.error ?? remove.error} />
    </aside>
  )
}
