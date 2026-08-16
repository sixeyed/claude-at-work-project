/**
 * Client-side chat state (register D24: Zustand for client state).
 *
 * The split this file exists to keep: **TanStack Query owns server state, this
 * owns client state.** No channel, message or membership lives here — those are
 * the server's and are cached by Query, where one fetch serves every component
 * and an invalidation refreshes all of them at once. What lives here is what
 * the server has no opinion about: which channel the user is looking at, and
 * what they have half-typed.
 *
 * Keeping a copy of the channel list here as well is the mistake this comment
 * is trying to prevent. Two copies of server state diverge, and the bug shows
 * up as a sidebar that is one action out of date.
 */

import { create } from 'zustand'

/**
 * Whether the live connection is up. A fact *about* a resource, which is client
 * state; the socket itself is the resource and lives in a React context.
 */
export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected'

interface ChatState {
  activeChannelId: string | null
  /** Per-channel composer text, so switching channels does not lose it. */
  drafts: Record<string, string>
  connectionStatus: ConnectionStatus
  setActiveChannel: (channelId: string | null) => void
  setDraft: (channelId: string, text: string) => void
  clearDraft: (channelId: string) => void
  setConnectionStatus: (status: ConnectionStatus) => void
}

export const useChatStore = create<ChatState>((set) => ({
  activeChannelId: null,
  drafts: {},
  connectionStatus: 'disconnected',
  setActiveChannel: (channelId) => set({ activeChannelId: channelId }),
  setConnectionStatus: (status) => set({ connectionStatus: status }),
  setDraft: (channelId, text) =>
    set((state) => ({ drafts: { ...state.drafts, [channelId]: text } })),
  clearDraft: (channelId) =>
    set((state) => {
      const { [channelId]: _removed, ...rest } = state.drafts
      return { drafts: rest }
    }),
}))
