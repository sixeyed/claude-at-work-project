import type { InfiniteData } from '@tanstack/react-query'
import { act } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { messageKeys } from '../../features/channels/useMessages'
import { aMessage, aMessagePage } from '../../test/factories'
import { createTestQueryClient, renderHookWithProviders } from '../../test/render'
import { latestSocket } from '../../test/socket'
import type { MessagePage } from '../api/messaging'
import { useChannelSocket } from './useChannelSocket'

const WORKSPACE = 'workspace-1'
const CHANNEL = 'channel-1'

describe('useChannelSocket', () => {
  it('writes a received message into that channel’s cached history', () => {
    const queryClient = createTestQueryClient()
    const key = messageKeys.list(WORKSPACE, CHANNEL)
    queryClient.setQueryData<InfiniteData<MessagePage>>(key, {
      pages: [aMessagePage([])],
      pageParams: [undefined],
    })

    renderHookWithProviders(() => useChannelSocket('token', WORKSPACE, CHANNEL), { queryClient })
    const socket = latestSocket()
    const message = aMessage({ channelId: CHANNEL, body: 'hello from grace' })

    act(() => socket.serverConnect())
    act(() => socket.serverEmit('message_received', message))

    expect(queryClient.getQueryData<InfiniteData<MessagePage>>(key)?.pages[0].items).toEqual([
      message,
    ])
    expect(socket.emitted).toContainEqual({ event: 'join_channel', args: [CHANNEL] })
  })
})
