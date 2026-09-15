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

/**
 * Starts a history fetch for a channel and holds its response back.
 *
 * The response is the page the server read *before* the message the test is
 * about to broadcast existed — which is exactly what a real fetch answers when
 * the broadcast lands while it is in flight.
 */
function holdHistoryFetch(
  queryClient: ReturnType<typeof createTestQueryClient>,
  channelId: string,
) {
  let release!: (page: MessagePage) => void
  const response = new Promise<MessagePage>((resolve) => {
    release = resolve
  })
  const done = queryClient.fetchInfiniteQuery({
    queryKey: messageKeys.list(WORKSPACE, channelId),
    queryFn: () => response,
    initialPageParam: undefined as string | undefined,
  })

  return {
    async answer(page: MessagePage) {
      await act(async () => {
        release(page)
        await done
      })
    },
  }
}

function historyItems(queryClient: ReturnType<typeof createTestQueryClient>, channelId: string) {
  return queryClient.getQueryData<InfiniteData<MessagePage>>(
    messageKeys.list(WORKSPACE, channelId),
  )?.pages[0].items
}

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

    it('keeps a message that arrives while the channel’s history first loads', async () => {
      const queryClient = createTestQueryClient()
      const history = holdHistoryFetch(queryClient, CHANNEL)
      renderHookWithProviders(() => useChannelSocket('token', WORKSPACE, CHANNEL), { queryClient })
      const socket = latestSocket()
      act(() => socket.serverConnect())
      const message = aMessage({ channelId: CHANNEL, body: 'the coffee has arrived' })

      act(() => socket.serverEmit('message_received', message))
      await history.answer(aMessagePage([]))

      expect(historyItems(queryClient, CHANNEL)).toEqual([message])
    })

    it('keeps a message that arrives while the channel’s history is being refetched', async () => {
      const queryClient = createTestQueryClient()
      seedHistory(queryClient, CHANNEL)
      const history = holdHistoryFetch(queryClient, CHANNEL)
      renderHookWithProviders(() => useChannelSocket('token', WORKSPACE, CHANNEL), { queryClient })
      const socket = latestSocket()
      act(() => socket.serverConnect())
      const message = aMessage({ channelId: CHANNEL, body: 'the coffee has arrived' })

      act(() => socket.serverEmit('message_received', message))
      await history.answer(aMessagePage([]))

      expect(historyItems(queryClient, CHANNEL)).toEqual([message])
    })

    it('keeps an edit that arrives during a refetch over the older copy it returns', async () => {
      const queryClient = createTestQueryClient()
      const original = aMessage({ channelId: CHANNEL, body: 'standup at four' })
      queryClient.setQueryData<InfiniteData<MessagePage>>(messageKeys.list(WORKSPACE, CHANNEL), {
        pages: [aMessagePage([original])],
        pageParams: [undefined],
      })
      const history = holdHistoryFetch(queryClient, CHANNEL)
      renderHookWithProviders(() => useChannelSocket('token', WORKSPACE, CHANNEL), { queryClient })
      const socket = latestSocket()
      act(() => socket.serverConnect())
      const edited = { ...original, body: 'standup at five', version: original.version + 1 }

      act(() => socket.serverEmit('message_edited', edited))
      await history.answer(aMessagePage([original]))

      expect(historyItems(queryClient, CHANNEL)).toEqual([edited])
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
