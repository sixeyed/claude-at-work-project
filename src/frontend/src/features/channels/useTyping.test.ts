import { act } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { renderHookWithProviders } from '../../test/render'
import { asSocket, FakeSocket } from '../../test/socket'
import { useTyping } from './useTyping'

const CHANNEL = 'channel-general'
const ADA = 'user-ada'
const GRACE = 'user-grace'

let socket: FakeSocket

beforeEach(() => {
  vi.useFakeTimers()
  socket = new FakeSocket('token')
})

afterEach(() => {
  vi.useRealTimers()
})

function renderTyping(channelId = CHANNEL) {
  return renderHookWithProviders(() => useTyping(asSocket(socket), channelId, ADA))
}

describe('useTyping — being told', () => {
  it('shows someone as typing when they start, and clears them once they stop', () => {
    const { result } = renderTyping()

    act(() => socket.serverEmit('user_typing', { channelId: CHANNEL, userId: GRACE }))
    expect(result.current.typingUserIds).toEqual([GRACE])

    // No stop event exists: the name goes four seconds after the last one.
    act(() => vi.advanceTimersByTime(3_000))
    expect(result.current.typingUserIds).toEqual([GRACE])

    act(() => vi.advanceTimersByTime(2_000))
    expect(result.current.typingUserIds).toEqual([])
  })

  it('keeps someone who is still typing', () => {
    const { result } = renderTyping()

    act(() => socket.serverEmit('user_typing', { channelId: CHANNEL, userId: GRACE }))
    act(() => vi.advanceTimersByTime(3_000))
    act(() => socket.serverEmit('user_typing', { channelId: CHANNEL, userId: GRACE }))
    act(() => vi.advanceTimersByTime(3_000))

    expect(result.current.typingUserIds).toEqual([GRACE])
  })

  it('ignores the caller’s own typing, from another tab', () => {
    const { result } = renderTyping()

    act(() => socket.serverEmit('user_typing', { channelId: CHANNEL, userId: ADA }))

    expect(result.current.typingUserIds).toEqual([])
  })

  it('ignores typing in a different channel', () => {
    const { result } = renderTyping()

    act(() => socket.serverEmit('user_typing', { channelId: 'channel-random', userId: GRACE }))

    expect(result.current.typingUserIds).toEqual([])
  })

  it('stops listening when unmounted', () => {
    const { unmount } = renderTyping()
    expect(socket.listenerCount('user_typing')).toBe(1)

    unmount()

    expect(socket.listenerCount('user_typing')).toBe(0)
  })
})

describe('useTyping — telling people', () => {
  it('emits on the first keystroke, then at most once every two seconds', () => {
    const { result } = renderTyping()
    const typingEmits = () => socket.emitted.filter((e) => e.event === 'typing')

    act(() => result.current.onKeystroke())
    act(() => result.current.onKeystroke())
    expect(typingEmits()).toEqual([{ event: 'typing', args: [{ channelId: CHANNEL }] }])

    act(() => vi.advanceTimersByTime(2_000))
    act(() => result.current.onKeystroke())
    expect(typingEmits()).toHaveLength(2)
  })
})
