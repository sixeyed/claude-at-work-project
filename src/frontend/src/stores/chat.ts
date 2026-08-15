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

interface ChatState {
  activeChannelId: string | null
  /** Per-channel composer text, so switching channels does not lose it. */
  drafts: Record<string, string>
  setActiveChannel: (channelId: string | null) => void
  setDraft: (channelId: string, text: string) => void
  clearDraft: (channelId: string) => void
}

export const useChatStore = create<ChatState>((set) => ({
  activeChannelId: null,
  drafts: {},
  setActiveChannel: (channelId) => set({ activeChannelId: channelId }),
  setDraft: (channelId, text) =>
    set((state) => ({ drafts: { ...state.drafts, [channelId]: text } })),
  clearDraft: (channelId) =>
    set((state) => {
      const { [channelId]: _removed, ...rest } = state.drafts
      return { drafts: rest }
    }),
}))
