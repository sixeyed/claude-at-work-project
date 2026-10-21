/**
 * The signed-in user's own profile, and renaming it.
 *
 * A rename touches three places that each hold the old name: the session's
 * profile (the sidebar and the author-is-me check), the cached profile read, and
 * every cached workspace directory (every author line). `applyRename` writes all
 * three, and it does so from the mutation's *own* `onSuccess` — not from a
 * callback handed to `mutate()`, which TanStack skips once the component that
 * called it has unmounted. Leaving Settings mid-save must still rename.
 *
 * Writing the caches is not enough on its own. A directory or profile read that
 * was answered before the commit and lands after the write carries the old name
 * (`setQueriesData` cancels nothing), and `invalidateQueries` alone cancels only a
 * query that already has data and leaves the sidebar on the old name until it
 * lands. So, in order and synchronously: cancel the reads in flight (their
 * answers are discarded), write the new name, then re-read every cached directory
 * — mounted or not — after the commit.
 */

import { type QueryClient, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { me, type Profile, updateMe, type WorkspaceMember } from '../../lib/auth/api'
import * as session from '../../lib/auth/session'

export const profileKeys = {
  me: (userId: string) => ['me', userId] as const,
}

/** Every workspace's directory, whatever its workspace id (see `directoryKeys`). */
const DIRECTORIES = ['workspace-members'] as const

/** The profile as the server holds it: read again on every visit to Settings. */
export function useMyProfile(accessToken: string, userId: string) {
  return useQuery({
    queryKey: profileKeys.me(userId),
    queryFn: () => me(accessToken),
    staleTime: 0,
    refetchOnMount: 'always',
  })
}

export function applyRename(queryClient: QueryClient, profile: Profile): void {
  session.updateProfile(profile)

  const meKey = profileKeys.me(profile.id)
  void queryClient.cancelQueries({ queryKey: DIRECTORIES })
  void queryClient.cancelQueries({ queryKey: meKey })

  queryClient.setQueryData(meKey, profile)
  // A directory still loading for the first time has no data: the updater is
  // handed `undefined` and leaves it be.
  queryClient.setQueriesData<WorkspaceMember[]>({ queryKey: DIRECTORIES }, (members) =>
    members?.map((member) =>
      member.user.id === profile.id
        ? { ...member, user: { ...member.user, displayName: profile.displayName } }
        : member,
    ),
  )

  void queryClient.invalidateQueries({ queryKey: DIRECTORIES, refetchType: 'all' })
}

export function useRenameMe(accessToken: string, userId: string) {
  const queryClient = useQueryClient()

  return useMutation<Profile, Error, string>({
    mutationKey: ['rename-me', userId],
    mutationFn: (displayName) => updateMe(accessToken, { displayName }),
    onSuccess: (profile) => applyRename(queryClient, profile),
  })
}
