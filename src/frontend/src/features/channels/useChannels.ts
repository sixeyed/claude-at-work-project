/**
 * Server state for channels, owned by TanStack Query (register D24).
 *
 * **The workspace id is part of every key.** An access token is scoped to one
 * workspace (Conventions §5.4), so a cached channel list belongs to that
 * workspace and to no other. Doc 06 §4 asks for the cache to be cleared on a
 * switch; keying by workspace gets the same guarantee without a lifecycle hook
 * that could be forgotten — the new workspace simply reads a different entry,
 * and switching back does not refetch what is still valid.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { createChannel, listChannels, type Channel } from '../../lib/api/messaging'

export const channelKeys = {
  list: (workspaceId: string | null) => ['channels', workspaceId] as const,
  detail: (workspaceId: string | null, channelId: string | undefined) =>
    ['channel', workspaceId, channelId] as const,
}

export function useChannels(accessToken: string, workspaceId: string | null) {
  return useQuery({
    queryKey: channelKeys.list(workspaceId),
    queryFn: () => listChannels(accessToken),
    select: (page) => page.items,
  })
}

export function useCreateChannel(accessToken: string, workspaceId: string | null) {
  const queryClient = useQueryClient()

  return useMutation<Channel, Error, { name: string; kind?: string }>({
    mutationFn: (body) => createChannel(accessToken, body),
    onSuccess: async () => {
      // Refetch rather than push the new channel into the cached array: the
      // list is ordered by name, and re-sorting it here would be a second
      // implementation of the server's ordering waiting to disagree with it.
      await queryClient.invalidateQueries({ queryKey: channelKeys.list(workspaceId) })
    },
  })
}
