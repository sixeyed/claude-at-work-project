/**
 * Server state for channel membership, owned by TanStack Query (register D24).
 *
 * A separate file from `useChannels.ts` rather than more exports in it: the
 * member list is a different resource with a different key and a different
 * lifetime, and the two only look related because they share a URL prefix.
 *
 * The workspace id leads the key for the reason `useChannels.ts` gives — a
 * token is scoped to one workspace, so a switch reads a different entry rather
 * than relying on someone remembering to clear the cache.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  addChannelMember,
  listChannelMembers,
  removeChannelMember,
  type ChannelMember,
  type ChannelMemberRole,
} from '../../lib/api/messaging'
import { channelKeys } from './useChannels'

export const memberKeys = {
  list: (workspaceId: string | null, channelId: string | undefined) =>
    ['channel-members', workspaceId, channelId] as const,
}

export function useChannelMembers(
  accessToken: string,
  workspaceId: string | null,
  channelId: string | undefined,
) {
  return useQuery({
    queryKey: memberKeys.list(workspaceId, channelId),
    queryFn: () => listChannelMembers(accessToken, channelId as string),
    enabled: Boolean(channelId),
    select: (page) => page.items,
  })
}

/**
 * Both mutations invalidate the *channel* list as well as the member list.
 *
 * Adding someone to a private channel is what makes it appear in their sidebar,
 * and removing them is what takes it away — but it also changes `myRole` on the
 * channel the caller is looking at, which is what decides whether the admin
 * controls render at all.
 */
function useMemberMutation<TVariables>(
  workspaceId: string | null,
  channelId: string,
  mutationFn: (variables: TVariables) => Promise<unknown>,
) {
  const queryClient = useQueryClient()

  return useMutation<unknown, Error, TVariables>({
    mutationFn,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: memberKeys.list(workspaceId, channelId) }),
        queryClient.invalidateQueries({ queryKey: channelKeys.list(workspaceId) }),
        queryClient.invalidateQueries({ queryKey: channelKeys.detail(workspaceId, channelId) }),
      ])
    },
  })
}

export function useAddMember(
  accessToken: string,
  workspaceId: string | null,
  channelId: string,
) {
  return useMemberMutation<{ userId: string; role?: ChannelMemberRole }>(
    workspaceId,
    channelId,
    (body): Promise<ChannelMember> => addChannelMember(accessToken, channelId, body),
  )
}

export function useRemoveMember(
  accessToken: string,
  workspaceId: string | null,
  channelId: string,
) {
  return useMemberMutation<{ userId: string }>(workspaceId, channelId, ({ userId }) =>
    removeChannelMember(accessToken, channelId, userId),
  )
}
