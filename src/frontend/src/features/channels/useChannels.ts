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

import {
  archiveChannel,
  createChannel,
  listChannels,
  updateChannel,
  type Channel,
  type ChannelKind,
} from '../../lib/api/messaging'

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

  return useMutation<Channel, Error, { name: string; kind: ChannelKind }>({
    mutationFn: (body) => createChannel(accessToken, body),
    onSuccess: async () => {
      // Refetch rather than push the new channel into the cached array: the
      // list is ordered by name, and re-sorting it here would be a second
      // implementation of the server's ordering waiting to disagree with it.
      await queryClient.invalidateQueries({ queryKey: channelKeys.list(workspaceId) })
    },
  })
}

/**
 * Rename a channel, or set its topic.
 *
 * Both the list and the detail entry are invalidated: the sidebar shows the
 * name and is ordered by it, and the open channel's header shows it too. A
 * rename that refreshed only one of them leaves the other reading the old name
 * until something else happens to refetch it.
 */
export function useRenameChannel(
  accessToken: string,
  workspaceId: string | null,
  channelId: string,
) {
  const queryClient = useQueryClient()

  return useMutation<Channel, Error, { version: number; name?: string; topic?: string | null }>({
    mutationFn: (body) => updateChannel(accessToken, channelId, body),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: channelKeys.list(workspaceId) }),
        queryClient.invalidateQueries({ queryKey: channelKeys.detail(workspaceId, channelId) }),
      ])
    },
  })
}

/**
 * Archive a channel.
 *
 * The detail entry is removed rather than invalidated: refetching it would ask
 * for a channel the server now hides, get a 404, and render the error page over
 * the top of wherever the user has just been sent. Navigating away is the
 * caller's job, and it has to happen — leaving Ada looking at a channel whose
 * next fetch 404s is the whole reason this is not just an invalidate.
 */
export function useArchiveChannel(
  accessToken: string,
  workspaceId: string | null,
  channelId: string,
) {
  const queryClient = useQueryClient()

  return useMutation<Channel, Error, void>({
    mutationFn: () => archiveChannel(accessToken, channelId),
    onSuccess: async () => {
      queryClient.removeQueries({ queryKey: channelKeys.detail(workspaceId, channelId) })
      await queryClient.invalidateQueries({ queryKey: channelKeys.list(workspaceId) })
    },
  })
}
