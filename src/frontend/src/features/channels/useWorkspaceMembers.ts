/**
 * Everyone in the workspace, and a way to put a name to a user id.
 *
 * Messaging returns bare user ids on membership rows, and will return them on
 * message authors too: it owns no user records and must not read Auth's tables
 * (Conventions §2). So the *browser* resolves names, from Auth's own workspace
 * member list, with the token it already holds.
 *
 * One hook, used by every part of the UI that has an id and needs a name — the
 * member panel today, message authors and the typing indicator later. A second
 * fetch with a second key would mean the same directory cached twice under two
 * names, and going stale at two different moments.
 *
 * An id with no matching member renders as a shortened id rather than a blank:
 * someone can be in a channel and no longer in the workspace, and a row with no
 * label in it looks like a bug.
 */

import { useQuery } from '@tanstack/react-query'

import { workspaceMembers, type WorkspaceMember } from '../../lib/auth/api'

export const directoryKeys = {
  members: (workspaceId: string | null) => ['workspace-members', workspaceId] as const,
}

export interface Directory {
  /** A display name for a user id, or a shortened id if we have no better. */
  nameFor: (userId: string) => string
  members: WorkspaceMember[]
}

export function shortId(userId: string): string {
  return userId.slice(0, 8)
}

export function useWorkspaceMembers(accessToken: string, workspaceId: string | null): Directory {
  const { data } = useQuery({
    queryKey: directoryKeys.members(workspaceId),
    queryFn: () => workspaceMembers(accessToken, workspaceId as string),
    enabled: Boolean(workspaceId),
    // Display names change rarely and this is read on every render of every
    // author line; refetching it on each mount would be a call per navigation.
    staleTime: 5 * 60 * 1000,
  })

  const members = data ?? []
  const byId = new Map(members.map((member) => [member.user.id, member.user.displayName]))

  return { members, nameFor: (userId) => byId.get(userId) ?? shortId(userId) }
}
