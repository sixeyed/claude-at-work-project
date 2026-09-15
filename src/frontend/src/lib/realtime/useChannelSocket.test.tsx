import type { InfiniteData } from '@tanstack/react-query'
import { act } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { messageKeys } from '../../features/channels/useMessages'
import { useChatStore } from '../../stores/chat'
import { aMessage, aMessagePage } from '../../test/factories'
import { createTestQueryClient, renderHookWithProviders } from '../../test/render'
import { latestSocket, type FakeSocket } from '../../test/socket'
import type { MessagePage } from '../api/messaging'
import { useChannelSocket } from './useChannelSocket'

const WORKSPACE = 'workspace-1'
const CHANNEL = 'channel-1'
const OTHER = 'channel-2'

interface JoinAck {
  ok: boolean
}

/**
 * Plays a server that has received each `join_channel` but not answered yet.
 *
 * The gap between the emit and its acknowledgement is the whole bug: the
 * server enters the room only when it has checked the channel is visible, so
 * anything broadcast before the ack never reaches this connection.
 */
function holdJoins(socket: FakeSocket) {
  const pending: Array<(ack: JoinAck) => void> = []
  socket.onEmit('join_channel', () => new Promise<JoinAck>((resolve) => pending.push(resolve)))

  return {
    async reply(ack: JoinAck) {
      await act(async () => {
        pending.shift()?.(ack)
        await new Promise((resolve) => setTimeout(resolve, 0))
      })
    },
  }
}

function seedHistory(queryClient: ReturnType<typeof createTestQueryClient>, channelId: string) {
  queryClient.setQueryData<InfiniteData<MessagePage>>(messageKeys.list(WORKSPACE, channelId), {
    pages: [aMessagePage([])],
    pageParams: [undefined],
  })
}

function isInvalidated(queryClient: ReturnType<typeof createTestQueryClient>, channelId: string) {
  return queryClient.getQueryState(messageKeys.list(WORKSPACE, channelId))?.isInvalidated
}

const joinedChannel = () => useChatStore.getState().joinedChannelId

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

  describe('joining the open channel', () => {
    it('counts the channel as joined only once the server acknowledges the join', async () => {
      renderHookWithProviders(() => useChannelSocket('token', WORKSPACE, CHANNEL))
      const socket = latestSocket()
      const joins = holdJoins(socket)

      act(() => socket.serverConnect())

      expect(socket.emitted).toContainEqual({ event: 'join_channel', args: [CHANNEL] })
      expect(joinedChannel()).toBeNull()

      await joins.reply({ ok: true })

      expect(joinedChannel()).toBe(CHANNEL)
    })

    it('refetches the history on connect only after the join is acknowledged', async () => {
      const queryClient = createTestQueryClient()
      seedHistory(queryClient, CHANNEL)
      renderHookWithProviders(() => useChannelSocket('token', WORKSPACE, CHANNEL), { queryClient })
      const socket = latestSocket()
      const joins = holdJoins(socket)

      act(() => socket.serverConnect())

      // A refetch before the room is entered can miss a message sent in between.
      expect(isInvalidated(queryClient, CHANNEL)).toBe(false)

      await joins.reply({ ok: true })

      expect(isInvalidated(queryClient, CHANNEL)).toBe(true)
    })

    it('counts a channel opened on a live connection as joined once acknowledged', async () => {
      let channel: string | null = null
      const { rerender } = renderHookWithProviders(() =>
        useChannelSocket('token', WORKSPACE, channel),
      )
      const socket = latestSocket()
      const joins = holdJoins(socket)
      act(() => socket.serverConnect())

      channel = OTHER
      rerender()

      expect(socket.emitted).toContainEqual({ event: 'join_channel', args: [OTHER] })
      expect(joinedChannel()).toBeNull()

      await joins.reply({ ok: true })

      expect(joinedChannel()).toBe(OTHER)
    })

    it('refetches a newly opened channel once its join is acknowledged', async () => {
      const queryClient = createTestQueryClient()
      seedHistory(queryClient, OTHER)
      let channel: string | null = null
      const { rerender } = renderHookWithProviders(
        () => useChannelSocket('token', WORKSPACE, channel),
        { queryClient },
      )
      const socket = latestSocket()
      const joins = holdJoins(socket)
      act(() => socket.serverConnect())

      channel = OTHER
      rerender()

      // The history loaded as the channel opened, while the join was in flight.
      expect(isInvalidated(queryClient, OTHER)).toBe(false)

      await joins.reply({ ok: true })

      expect(isInvalidated(queryClient, OTHER)).toBe(true)
    })

    it('does not count a refused join as joined', async () => {
      renderHookWithProviders(() => useChannelSocket('token', WORKSPACE, CHANNEL))
      const socket = latestSocket()
      const joins = holdJoins(socket)

      act(() => socket.serverConnect())
      await joins.reply({ ok: false })

      expect(joinedChannel()).toBeNull()
    })

    it('forgets the joined channel when the connection drops', async () => {
      renderHookWithProviders(() => useChannelSocket('token', WORKSPACE, CHANNEL))
      const socket = latestSocket()
      const joins = holdJoins(socket)
      act(() => socket.serverConnect())
      await joins.reply({ ok: true })

      act(() => socket.serverDisconnect())

      expect(joinedChannel()).toBeNull()
    })
  })
})
