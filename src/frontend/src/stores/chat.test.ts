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

  it('keeps a thread draft per root, apart from the channel’s, and clears only the one sent', () => {
    const { setDraft, setThreadDraft, clearThreadDraft } = useChatStore.getState()

    setDraft('general', 'for the channel')
    setThreadDraft('root-a', 'for thread a')
    setThreadDraft('root-b', 'for thread b')
    clearThreadDraft('root-a')

    expect(useChatStore.getState().threadDrafts).toEqual({ 'root-b': 'for thread b' })
    expect(useChatStore.getState().drafts).toEqual({ general: 'for the channel' })
  })

  it('remembers the last channel after the active one is cleared', () => {
    const { setActiveChannel } = useChatStore.getState()
    expect(useChatStore.getState().lastChannelId).toBeNull()

    setActiveChannel('channel-1')
    setActiveChannel(null)

    expect(useChatStore.getState().activeChannelId).toBeNull()
    expect(useChatStore.getState().lastChannelId).toBe('channel-1')

    setActiveChannel('channel-2')
    expect(useChatStore.getState().lastChannelId).toBe('channel-2')
  })

  it('forgets the last channel when told to, and clears nothing else', () => {
    const { setActiveChannel, setDraft, clearLastChannel } = useChatStore.getState()
    setActiveChannel('channel-1')
    setDraft('channel-1', 'half a thought')

    clearLastChannel()

    expect(useChatStore.getState().lastChannelId).toBeNull()
    expect(useChatStore.getState().activeChannelId).toBe('channel-1')
    expect(useChatStore.getState().drafts).toEqual({ 'channel-1': 'half a thought' })
  })

  it('records the connection status', () => {
    useChatStore.getState().setConnectionStatus('connected')

    expect(useChatStore.getState().connectionStatus).toBe('connected')
  })

  it('starts with no channel joined, and records the one the server has joined', () => {
    expect(useChatStore.getState().joinedChannelId).toBeNull()

    useChatStore.getState().setJoinedChannel('channel-1')

    expect(useChatStore.getState().joinedChannelId).toBe('channel-1')
  })
})
