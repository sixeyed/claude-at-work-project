import type { InfiniteData, QueryClient } from '@tanstack/react-query'
import { act } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ProblemError } from '../../lib/api/client'
import type { Message, MessagePage } from '../../lib/api/messaging'
import { aMessage, aMessagePage } from '../../test/factories'
import { createTestQueryClient, renderHookWithProviders } from '../../test/render'
import { asSocket, FakeSocket } from '../../test/socket'
import { isPending, messageKeys, removeMessage, upsertMessage, useSendMessage } from './useMessages'

const WORKSPACE = 'workspace-1'
const CHANNEL = 'channel-1'
const ADA = 'user-ada'
const key = messageKeys.list(WORKSPACE, CHANNEL)

function seeded(...pages: MessagePage[]) {
  const queryClient = createTestQueryClient()
  queryClient.setQueryData<InfiniteData<MessagePage>>(key, {
    pages,
    pageParams: pages.map(() => undefined),
  })
  return queryClient
}

function pagesIn(queryClient: QueryClient) {
  return queryClient.getQueryData<InfiniteData<MessagePage>>(key)?.pages
}

function itemsIn(queryClient: QueryClient): Message[] {
  return (pagesIn(queryClient) ?? []).flatMap((page) => page.items)
}

describe('upsertMessage', () => {
  it('puts a new message at the head of the newest page', () => {
    const older = aMessage({ body: 'older' })
    const queryClient = seeded(aMessagePage([older], 'cursor-2'))
    const arrived = aMessage({ body: 'arrived' })

    upsertMessage(queryClient, key, arrived)

    expect(pagesIn(queryClient)?.[0].items).toEqual([arrived, older])
    // The cursor belongs to the page, and a live message must not reset it.
    expect(pagesIn(queryClient)?.[0].nextCursor).toBe('cursor-2')
  })

  it('replaces a message where it sits, on whichever page holds it', () => {
    const edited = aMessage({ body: 'before' })
    const newest = aMessagePage([aMessage({ body: 'newest' })], 'cursor-2')
    const queryClient = seeded(newest, aMessagePage([edited]))

    upsertMessage(queryClient, key, { ...edited, body: 'after', editedAt: '2026-09-15T10:00:00Z' })

    expect(pagesIn(queryClient)?.[0]).toEqual(newest)
    expect(pagesIn(queryClient)?.[1].items.map((m) => m.body)).toEqual(['after'])
  })

  it('does not render a message twice when its broadcast arrives again', () => {
    const message = aMessage()
    const queryClient = seeded(aMessagePage([]))

    upsertMessage(queryClient, key, message)
    upsertMessage(queryClient, key, message)

    expect(itemsIn(queryClient)).toEqual([message])
  })

  it('invents no history for a channel nothing has loaded', () => {
    const queryClient = createTestQueryClient()

    upsertMessage(queryClient, key, aMessage())

    expect(queryClient.getQueryData(key)).toBeUndefined()
  })
})

describe('removeMessage', () => {
  it('drops the message from every page', () => {
    const doomed = aMessage()
    const kept = aMessage()
    const queryClient = seeded(aMessagePage([doomed, kept]))

    removeMessage(queryClient, key, doomed.id)

    expect(itemsIn(queryClient)).toEqual([kept])
  })

  it('leaves an uncached channel uncached', () => {
    const queryClient = createTestQueryClient()

    removeMessage(queryClient, key, 'anything')

    expect(queryClient.getQueryData(key)).toBeUndefined()
  })
})

describe('isPending', () => {
  it('is true only for a browser-made temp id', () => {
    expect(isPending(aMessage({ id: 'temp:1234' }))).toBe(true)
    expect(isPending(aMessage())).toBe(false)
  })
})

describe('useSendMessage', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  function renderSend(queryClient: QueryClient, socket: FakeSocket | null) {
    return renderHookWithProviders(
      () => useSendMessage(socket ? asSocket(socket) : null, WORKSPACE, CHANNEL, ADA),
      { queryClient },
    )
  }

  it('shows the message at once, then swaps in the confirmed one', async () => {
    const queryClient = seeded(aMessagePage([]))
    const socket = new FakeSocket('token')
    const confirmed = aMessage({ channelId: CHANNEL, authorId: ADA, body: 'lunch is at one' })
    let confirm: (ack: unknown) => void = () => undefined
    socket.onEmit('send_message', () => new Promise((resolve) => (confirm = resolve)))
    const { result } = renderSend(queryClient, socket)

    act(() => result.current.mutate('lunch is at one'))

    await vi.waitFor(() => expect(itemsIn(queryClient)).toHaveLength(1))
    const [pending] = itemsIn(queryClient)
    expect(isPending(pending)).toBe(true)
    expect(pending).toMatchObject({ body: 'lunch is at one', authorId: ADA, channelId: CHANNEL })
    expect(socket.emitted).toEqual([
      { event: 'send_message', args: [{ channelId: CHANNEL, body: 'lunch is at one' }] },
    ])

    await act(async () => confirm({ ok: true, data: confirmed }))

    await vi.waitFor(() => expect(itemsIn(queryClient)).toEqual([confirmed]))
  })

  it('shows a message once when its broadcast beats its acknowledgement', async () => {
    const queryClient = seeded(aMessagePage([]))
    const socket = new FakeSocket('token')
    const confirmed = aMessage({ channelId: CHANNEL, authorId: ADA, body: 'race' })
    let confirm: (ack: unknown) => void = () => undefined
    socket.onEmit('send_message', () => new Promise((resolve) => (confirm = resolve)))
    const { result } = renderSend(queryClient, socket)

    act(() => result.current.mutate('race'))
    await vi.waitFor(() => expect(itemsIn(queryClient)).toHaveLength(1))
    // What `useChannelSocket` does with `message_received`.
    upsertMessage(queryClient, key, confirmed)
    await act(async () => confirm({ ok: true, data: confirmed }))

    await vi.waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(itemsIn(queryClient)).toEqual([confirmed])
  })

  it('rolls a refused send back and keeps the server’s reason', async () => {
    const queryClient = seeded(aMessagePage([]))
    const socket = new FakeSocket('token')
    socket.onEmit('send_message', () => ({
      ok: false,
      problem: {
        status: 400,
        title: 'Validation error',
        detail: 'A message must be 8000 characters or fewer.',
        errors: { body: ['A message must be 8000 characters or fewer.'] },
      },
    }))
    const { result } = renderSend(queryClient, socket)

    act(() => result.current.mutate('a'.repeat(8001)))

    await vi.waitFor(() => expect(result.current.isError).toBe(true))
    expect(itemsIn(queryClient)).toEqual([])
    expect(result.current.error).toBeInstanceOf(ProblemError)
    expect((result.current.error as ProblemError).fieldError('body')).toBe(
      'A message must be 8000 characters or fewer.',
    )
  })

  it('rolls back within five seconds when no acknowledgement comes', async () => {
    vi.useFakeTimers()
    const queryClient = seeded(aMessagePage([]))
    const { result } = renderSend(queryClient, new FakeSocket('token'))

    act(() => result.current.mutate('into the void'))
    await act(() => vi.advanceTimersByTimeAsync(4_999))
    expect(itemsIn(queryClient)).toHaveLength(1)

    await act(() => vi.advanceTimersByTimeAsync(1))

    await vi.waitFor(() =>
      expect(result.current.error?.message).toBe(
        'The server did not confirm that message. Nothing was sent.',
      ),
    )
    expect(itemsIn(queryClient)).toEqual([])
  })

  it('refuses to send with no socket', async () => {
    const queryClient = seeded(aMessagePage([]))
    const { result } = renderSend(queryClient, null)

    act(() => result.current.mutate('hello'))

    await vi.waitFor(() =>
      expect(result.current.error?.message).toBe('Not connected. Try again in a moment.'),
    )
    expect(itemsIn(queryClient)).toEqual([])
  })
})
