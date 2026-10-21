/**
 * `/settings` through the real `App` (issue Req 5, 7, 8 and its Paths table; plan
 * Decisions 25 to 28).
 *
 * As in `App.test.tsx`, each test imports a fresh `App`, and with it a fresh session
 * store and chat store: those are module state. The session is driven the way the
 * app drives it — `App` calls `restore()` on mount and the Auth stubs decide what
 * that finds. Auth keeps the profile and preferences in `server`, so a test changes
 * what "the server says" between visits by assigning to it.
 */

import { act, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Preferences, Profile, TokenPair, Workspace, WorkspaceMember } from './lib/auth/api'
import { auth, messaging, requests } from './test/api'
import {
  aChannel,
  aMessage,
  aMessagePage,
  aWorkspaceMember,
  messageIdAt,
  WORKSPACE_ID,
} from './test/factories'
import { setPageAttention } from './test/page'
import { renderWithProviders } from './test/render'

type SessionModule = typeof import('./lib/auth/session')
type ChatModule = typeof import('./stores/chat')

const AWAY = '0199a000-0000-7000-8000-0000000000f1'
const CHANNEL = '0199a000-0000-7000-8000-00000000c001'
const ADA = 'user-ada'
const GRACE = 'user-grace'
const RETURN_KEY = 'collabhub.returnTo'
const VERIFIER_KEY = 'collabhub.pkceVerifier'

const PROFILE: Profile = {
  id: ADA,
  email: 'ada@collabhub.dev',
  displayName: 'Ada Lovelace',
  avatarAsset: null,
}
const WORKSPACES: Workspace[] = [
  { id: WORKSPACE_ID, name: 'Home', role: 'owner' },
  { id: AWAY, name: 'Away', role: 'member' },
]
const afternoon = new Date(2026, 8, 15, 13, 5).toISOString()
const automaticTime = new Date(afternoon).toLocaleTimeString([], {
  hour: '2-digit',
  minute: '2-digit',
})

function tokenFor(workspaceId: string): string {
  const payload = btoa(JSON.stringify({ wsp: workspaceId }))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
  return `header.${payload}.signature`
}
const pair = (workspaceId: string): TokenPair => ({
  accessToken: tokenFor(workspaceId),
  tokenType: 'Bearer',
  expiresIn: 900,
})

function deferred<T = void>() {
  let release!: (value: T) => void
  const promise = new Promise<T>((resolve) => {
    release = resolve
  })
  return { promise, release }
}

type AppModule = typeof import('./App')
let App: AppModule['App']
let session: SessionModule
let chat: ChatModule

/** What Auth currently holds, read by the stubs on every request. */
const server = { prefs: {} as Preferences, members: [] as WorkspaceMember[] }

beforeEach(async () => {
  vi.resetModules()
  window.sessionStorage.clear()
  server.prefs = {}
  server.members = [aWorkspaceMember({ id: ADA, displayName: 'Ada Lovelace' })]
  ;({ App } = await import('./App'))
  session = await import('./lib/auth/session')
  chat = await import('./stores/chat')
})

afterEach(() => {
  vi.unstubAllGlobals()
  window.sessionStorage.clear()
})

function aReturningUser() {
  auth.refresh(pair(WORKSPACE_ID))
  auth.me(PROFILE)
  auth.workspaces(WORKSPACES)
  auth.preferences(() => ({ ...server.prefs }))
  auth.updatePreferences((body) => {
    server.prefs = body.clock === null ? {} : { clock: body.clock }
    return { ...server.prefs }
  })
  auth.membersBy(() => server.members)
  messaging.get('/api/v1/channels', { items: [aChannel({ id: CHANNEL, name: 'general' })], nextCursor: null })
}

function aFirstVisit() {
  auth.problem('post', '/api/v1/auth/refresh', 401, { title: 'Unauthorized' })
}

/** The channel route's own stubs: a channel with one message from Grace at 13:05. */
function aChannelWithAMessage() {
  server.members = [
    aWorkspaceMember({ id: ADA, displayName: 'Ada Lovelace' }),
    aWorkspaceMember({ id: GRACE, displayName: 'Grace Hopper' }),
  ]
  messaging.get('/api/v1/channels/{channel_id}', aChannel({ id: CHANNEL, name: 'general' }))
  messaging.get(
    '/api/v1/channels/{channel_id}/messages',
    aMessagePage([
      aMessage({
        id: messageIdAt(1),
        channelId: CHANNEL,
        authorId: GRACE,
        body: 'the kettle is on',
        createdAt: afternoon,
      }),
    ]),
  )
  messaging.get('/api/v1/channels/{channel_id}/members', { items: [], nextCursor: null })
}

const historyGets = () =>
  requests().filter((r) => r.url.pathname === `/api/v1/channels/${CHANNEL}/messages`).length
const yourName = (name = 'Ada Lovelace') => screen.getByRole('link', { name })

/** Open Settings from the sidebar and wait for the page. */
async function openSettings(user: ReturnType<typeof renderWithProviders>['user']) {
  await user.click(yourName())
  return screen.findByRole('textbox', { name: 'Display name' })
}

describe('reaching and leaving Settings', () => {
  it('opens Settings inside the shell when you click your name', async () => {
    aReturningUser()
    const { user, location } = renderWithProviders(<App />, { route: '/' })
    await screen.findByText('Pick a channel, or create one.')

    await user.click(yourName())

    expect(await screen.findByRole('heading', { name: 'Settings' })).toBeInTheDocument()
    expect(location().pathname).toBe('/settings')
    // Still the shell: the sidebar, with your name in it, and Sign out.
    expect(screen.getByRole('button', { name: 'Sign out' })).toBeInTheDocument()
    expect(yourName()).toBeInTheDocument()
  })

  it('shows the server’s current name on a direct load of /settings', async () => {
    aReturningUser()
    auth.meBy((call) => (call === 1 ? PROFILE : { ...PROFILE, displayName: 'Ada Newer' }))

    renderWithProviders(<App />, { route: '/settings' })

    expect(await screen.findByRole('textbox', { name: 'Display name' })).toHaveValue('Ada Newer')
  })

  it('reads the profile and the preferences again on every visit', async () => {
    aReturningUser()
    auth.meBy((call) => {
      if (call === 1) return PROFILE
      return { ...PROFILE, displayName: call === 2 ? 'Visit A' : 'Visit B' }
    })
    server.prefs = { clock: '12h' }
    const { user, location } = renderWithProviders(<App />, { route: '/' })
    await screen.findByText('Pick a channel, or create one.')

    const first = await openSettings(user)
    expect(first).toHaveValue('Visit A')
    await vi.waitFor(() => expect(screen.getByRole('radio', { name: '12-hour' })).toBeChecked())
    await user.click(screen.getByRole('link', { name: 'Back to chat' }))
    expect(location().pathname).toBe('/')
    server.prefs = { clock: '24h' }

    const second = await openSettings(user)

    expect(second).toHaveValue('Visit B')
    await vi.waitFor(() => expect(screen.getByRole('radio', { name: '24-hour' })).toBeChecked())
  })

  it('takes Back to chat to the last channel', async () => {
    aReturningUser()
    aChannelWithAMessage()
    const { user, location } = renderWithProviders(<App />, { route: `/c/${CHANNEL}` })
    await screen.findByText('the kettle is on')

    await openSettings(user)
    const back = screen.getByRole('link', { name: 'Back to chat' })
    expect(back).toHaveAttribute('href', `/c/${CHANNEL}`)
    await user.click(back)

    expect(location().pathname).toBe(`/c/${CHANNEL}`)
  })

  it('takes Back to chat to / when no channel was open', async () => {
    aReturningUser()
    const { user, location } = renderWithProviders(<App />, { route: '/' })
    await screen.findByText('Pick a channel, or create one.')

    await openSettings(user)
    const back = screen.getByRole('link', { name: 'Back to chat' })
    expect(back).toHaveAttribute('href', '/')
    await user.click(back)

    expect(location().pathname).toBe('/')
  })

  it('takes Back to chat to / after a workspace switch', async () => {
    aReturningUser()
    auth.switchWorkspace(pair(AWAY))
    const { user } = renderWithProviders(<App />, { route: '/' })
    await screen.findByText('Pick a channel, or create one.')
    act(() => chat.useChatStore.getState().setActiveChannel(CHANNEL))
    expect(chat.useChatStore.getState().lastChannelId).toBe(CHANNEL)

    await act(() => session.changeWorkspace(AWAY))
    await openSettings(user)

    // A channel id from the old workspace would open its 404.
    expect(chat.useChatStore.getState().lastChannelId).toBeNull()
    expect(screen.getByRole('link', { name: 'Back to chat' })).toHaveAttribute('href', '/')
  })

  it('drops an unsaved edit when you leave', async () => {
    aReturningUser()
    const { user } = renderWithProviders(<App />, { route: '/' })
    await screen.findByText('Pick a channel, or create one.')
    const first = await openSettings(user)
    await user.type(first, ' draft')
    expect(first).toHaveValue('Ada Lovelace draft')
    await user.click(screen.getByRole('link', { name: 'Back to chat' }))

    const second = await openSettings(user)

    expect(second).toHaveValue('Ada Lovelace')
  })
})

describe('signing in on the way to Settings', () => {
  it('remembers a signed-out visit to /settings for sign-in', async () => {
    aFirstVisit()
    const assign = vi.fn()
    vi.stubGlobal('location', { ...window.location, assign })
    const { user, location } = renderWithProviders(<App />, { route: '/settings' })

    await user.click(await screen.findByRole('button', { name: 'Sign in' }))

    await vi.waitFor(() => expect(assign).toHaveBeenCalled())
    expect(location().pathname).toBe('/sign-in')
    expect(window.sessionStorage.getItem(RETURN_KEY)).toBe('/settings')
  })

  it('returns to the remembered route from the callback, once', async () => {
    aFirstVisit()
    auth.exchange(pair(WORKSPACE_ID))
    auth.me(PROFILE)
    auth.workspaces(WORKSPACES)
    auth.preferences({})
    auth.members([aWorkspaceMember({ id: ADA, displayName: 'Ada Lovelace' })])
    messaging.get('/api/v1/channels', { items: [], nextCursor: null })
    window.sessionStorage.setItem(VERIFIER_KEY, 'the-verifier')
    window.sessionStorage.setItem(RETURN_KEY, '/settings')

    const { location } = renderWithProviders(<App />, { route: '/auth/callback?code=the-code' })

    expect(await screen.findByRole('heading', { name: 'Settings' })).toBeInTheDocument()
    expect(location().pathname).toBe('/settings')
    expect(window.sessionStorage.getItem(RETURN_KEY)).toBeNull()
  })
})

describe('a rename and the page that made it', () => {
  it('still renames the sidebar and the directory when you leave mid-save', async () => {
    aReturningUser()
    const held = deferred<Profile>()
    auth.updateMe(() => held.promise)
    const { user, queryClient } = renderWithProviders(<App />, { route: '/' })
    await screen.findByText('Pick a channel, or create one.')
    await vi.waitFor(() =>
      expect(queryClient.getQueryData(['workspace-members', WORKSPACE_ID])).toBeDefined(),
    )
    const input = await openSettings(user)
    await user.clear(input)
    await user.type(input, 'Ada New')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await vi.waitFor(() =>
      expect(requests().some((r) => r.method === 'PATCH' && r.url.pathname === '/api/v1/users/me')).toBe(true),
    )
    await user.click(screen.getByRole('link', { name: 'Back to chat' }))
    expect(screen.queryByRole('textbox', { name: 'Display name' })).not.toBeInTheDocument()
    server.members = [aWorkspaceMember({ id: ADA, displayName: 'Ada New' })]

    await act(async () => held.release({ ...PROFILE, displayName: 'Ada New' }))

    expect(await screen.findByRole('link', { name: 'Ada New' })).toBeInTheDocument()
    const directory = queryClient.getQueryData<WorkspaceMember[]>(['workspace-members', WORKSPACE_ID])
    expect(directory?.find((m) => m.user.id === ADA)?.user.displayName).toBe('Ada New')
  })

  it('keeps the field and the clock through a workspace switch on Settings', async () => {
    aReturningUser()
    auth.switchWorkspace(pair(AWAY))
    const { user } = renderWithProviders(<App />, { route: '/settings' })
    const input = await screen.findByRole('textbox', { name: 'Display name' })
    await user.type(input, ' draft')
    await user.click(screen.getByRole('radio', { name: '24-hour' }))
    await vi.waitFor(() => expect(server.prefs).toEqual({ clock: '24h' }))

    await act(() => session.changeWorkspace(AWAY))

    const state = session.snapshot()
    expect(state.status === 'signedIn' && state.session.activeWorkspaceId).toBe(AWAY)
    expect(input).toBeInTheDocument()
    expect(input).toHaveValue('Ada Lovelace draft')
    expect(screen.getByRole('radio', { name: '24-hour' })).toBeChecked()
  })
})

describe('the clock across the app', () => {
  it('re-renders cached messages when the preference changes, without refetching them', async () => {
    aReturningUser()
    aChannelWithAMessage()
    const { queryClient } = renderWithProviders(<App />, { route: `/c/${CHANNEL}` })
    await screen.findByText('the kettle is on')
    expect(screen.getByText(automaticTime)).toBeInTheDocument()
    const reads = historyGets()
    expect(reads).toBeGreaterThan(0)

    act(() => {
      queryClient.setQueryData(['user-preferences', ADA], { clock: '24h' })
    })

    expect(await screen.findByText('13:05')).toBeInTheDocument()
    await act(() => new Promise<void>((resolve) => setTimeout(resolve, 25)))
    expect(historyGets()).toBe(reads)
  })

  it('follows another tab’s change on the next focus', async () => {
    aReturningUser()
    aChannelWithAMessage()
    renderWithProviders(<App />, { route: `/c/${CHANNEL}` })
    await screen.findByText('the kettle is on')
    expect(screen.getByText(automaticTime)).toBeInTheDocument()

    setPageAttention({ visible: false, focused: false })
    server.prefs = { clock: '24h' }
    expect(screen.queryByText('13:05')).not.toBeInTheDocument()
    setPageAttention({ visible: true, focused: true })

    expect(await screen.findByText('13:05')).toBeInTheDocument()
  })
})
