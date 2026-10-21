/**
 * The signed-in user's preferences — server state, so TanStack Query holds them
 * and nothing else does (register D24, D28).
 *
 * Keyed by user, not workspace: a preference follows the person across every
 * workspace they belong to, and a workspace switch must not refetch it.
 *
 * **Choosing a clock is optimistic**, and writes are serialised
 * (`scope: { id: 'user-preferences' }`) so two quick choices reach the server in
 * the order they were made. Each write snapshots the cache before it applies its
 * own value. A failure puts the snapshot back only if the cache still holds that
 * write's own value — otherwise a later choice would be undone by an earlier
 * failure — and re-reads from the server once nothing else is pending, so two
 * failures end on the server's truth rather than on either guess. A success
 * likewise writes the server's answer into the cache only when nothing newer is
 * waiting behind it, or the screen would flicker back to a choice already
 * replaced.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { type Clock, type Preferences, preferences, updatePreferences } from '../../lib/auth/api'

export const preferencesKeys = {
  mine: (userId: string) => ['user-preferences', userId] as const,
}

const SAVE_KEY = ['user-preferences', 'save'] as const

export function usePreferences(
  accessToken: string,
  userId: string,
  options?: { refetchOnMount?: 'always' },
) {
  return useQuery({
    queryKey: preferencesKeys.mine(userId),
    queryFn: () => preferences(accessToken),
    ...options,
  })
}

interface SaveContext {
  previous: Preferences | undefined
  optimistic: Preferences
}

export function useSetClock(accessToken: string, userId: string) {
  const queryClient = useQueryClient()
  const key = preferencesKeys.mine(userId)
  // `isMutating` counts the mutation being settled, so "nothing else" is one.
  const aloneInQueue = () => queryClient.isMutating({ mutationKey: SAVE_KEY }) <= 1

  return useMutation<Preferences, Error, Clock | null, SaveContext>({
    mutationKey: SAVE_KEY,
    scope: { id: 'user-preferences' },
    mutationFn: (clock) => updatePreferences(accessToken, { clock }),
    onMutate: (clock) => {
      // Cancel first: a read in flight would otherwise land the old value over this
      // choice. Cancelling reverts the query to its state before that read began, so
      // it must come before the write below, not after.
      void queryClient.cancelQueries({ queryKey: key })
      const previous = queryClient.getQueryData<Preferences>(key)
      const optimistic: Preferences = clock === null ? {} : { clock }
      queryClient.setQueryData(key, optimistic)
      return { previous, optimistic }
    },
    onSuccess: (saved) => {
      if (aloneInQueue()) queryClient.setQueryData(key, saved)
    },
    onError: (_error, _clock, context) => {
      const current = queryClient.getQueryData<Preferences>(key)
      if (context?.previous && current?.clock === context.optimistic.clock) {
        queryClient.setQueryData(key, context.previous)
      }
      if (aloneInQueue()) void queryClient.invalidateQueries({ queryKey: key })
    },
  })
}
