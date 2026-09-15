import { describe, expect, it } from 'vitest'

import { useChatStore } from './chat'

describe('the chat store', () => {
  it('starts with nothing open, nothing drafted and no connection', () => {
    const state = useChatStore.getState()

    expect(state.activeChannelId).toBeNull()
    expect(state.drafts).toEqual({})
    expect(state.connectionStatus).toBe('disconnected')
  })

  it('remembers which channel is open', () => {
    useChatStore.getState().setActiveChannel('channel-1')

    expect(useChatStore.getState().activeChannelId).toBe('channel-1')
  })

  it('keeps a draft per channel, and clears only the one sent', () => {
    const { setDraft, clearDraft } = useChatStore.getState()

    setDraft('general', 'half a thought')
    setDraft('random', 'another')
    clearDraft('general')

    expect(useChatStore.getState().drafts).toEqual({ random: 'another' })
  })

  it('records the connection status', () => {
    useChatStore.getState().setConnectionStatus('connected')

    expect(useChatStore.getState().connectionStatus).toBe('connected')
  })
})
