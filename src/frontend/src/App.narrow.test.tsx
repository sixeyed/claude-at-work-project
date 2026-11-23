/**
 * The shell below 768px, through the real `App` (issue Req 1 to 4 and 7; plan
 * Decisions 7 to 16, 23, 24).
 *
 * Narrow comes from `setViewportWidth` (`test/viewport.ts`): jsdom evaluates no
 * media query. As in `App.settings.test.tsx`, each test imports a fresh `App` and
 * with it a fresh session store and chat store, and the Auth stubs decide what
 * `restore()` finds.
 *
 * What "open" and "closed" mean here (plan Task 2): the drawer is open ⇔ there is
 * a dialog named **Sidebar**; closed while narrow ⇔ no such dialog *and* the
 * sidebar's links are not accessible (the `hidden` attribute). Every "closed"
 * check first finds the same links with `hidden: true`, so it cannot pass because
 * the sidebar never rendered.
 *
 * Queries are by role, label and text. Real time throughout; `fireEvent.click`
 * where a pointer event would close a "⋯" menu by itself.
 */

import { act, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Profile, TokenPair, Workspace } from './lib/auth/api'
import { auth, messaging, requests } from './test/api'
import {
  aChannel,
  aMessage,
  aMessagePage,
  aThreadPage,
  aWorkspaceMember,
  messageIdAt,
  WORKSPACE_ID,
} from './test/factories'
import { giveLayout } from './test/layout'
import { renderWithProviders } from './test/render'
import { setViewportWidth } from './test/viewport'

type ChatModule = typeof import('./stores/chat')
type AppModule = typeof import('./App')

const AWAY = '0199a000-0000-7000-8000-0000000000f1'
const GENERAL = '0199a000-0000-7000-8000-00000000c001'
const RANDOM = '0199a000-0000-7000-8000-00000000c002'
const DM = '0199a000-0000-7000-8000-00000000c003'
const CREATED = '0199a000-0000-7000-8000-00000000c004'
const ADA = 'user-ada'
const GRACE = 'user-grace'
const ROOT = messageIdAt(1)
const THREAD = '/api/v1/messages/{message_id}/thread' as const

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

let App: AppModule['App']
let chat: ChatModule

beforeEach(async () => {
  vi.resetModules()
  window.sessionStorage.clear()
  ;({ App } = await import('./App'))
  chat = await import('./stores/chat')
})

afterEach(() => {
  window.sessionStorage.clear()
})

const root = aMessage({
  id: ROOT,
  channelId: GENERAL,
  authorId: GRACE,
  body: 'the kettle is on',
  replyCount: 1,
  lastReplyAt: '2026-09-15T10:00:00Z',
})
const reply = aMessage({
  channelId: GENERAL,
  threadRootId: ROOT,
  authorId: GRACE,
  body: 'boiling now',
})

/** A returning user, a channel list `general` and `random` plus a DM with Grace, and every route's reads. */
function aReturningUser() {
  const channels: Record<string, ReturnType<typeof aChannel>> = {
    [GENERAL]: aChannel({ id: GENERAL, name: 'general' }),
    [RANDOM]: aChannel({ id: RANDOM, name: 'random' }),
    [DM]: aChannel({ id: DM, name: `dm:${ADA}:${GRACE}`, kind: 'dm', dmPartnerId: GRACE }),
    [CREATED]: aChannel({ id: CREATED, name: 'newchan' }),
  }
  auth.refresh(pair(WORKSPACE_ID))
  auth.me(PROFILE)
  auth.workspaces(WORKSPACES)
  auth.preferences({})
  auth.members([
    aWorkspaceMember({ id: ADA, displayName: 'Ada Lovelace' }),
    aWorkspaceMember({ id: GRACE, displayName: 'Grace Hopper' }),
  ])
  messaging.get('/api/v1/channels', {
    items: [channels[GENERAL], channels[RANDOM], channels[DM]],
    nextCursor: null,
  })
  messaging.get('/api/v1/channels/{channel_id}', ({ params }) => ({ ...channels[params.channel_id] }))
  messaging.get('/api/v1/channels/{channel_id}/messages', ({ params }) =>
    aMessagePage(params.channel_id === GENERAL ? [root] : []),
  )
  messaging.get('/api/v1/channels/{channel_id}/members', { items: [], nextCursor: null })
  messaging.get(THREAD, () => aThreadPage(root, [reply]))
  messaging.get('/api/v1/search/messages', { items: [], nextCursor: null })
  auth.switchWorkspace(pair(AWAY))
}

function renderApp(route: string, width = 390) {
  setViewportWidth(width)
  return renderWithProviders(<App />, { route })
}

type User = ReturnType<typeof renderWithProviders>['user']

const drawer = () => screen.queryByRole('dialog', { name: 'Sidebar' })
const findDrawer = () => screen.findByRole('dialog', { name: 'Sidebar' })
const openButton = () => screen.queryByRole('button', { name: 'Open sidebar' })
const findOpenButton = () => screen.findByRole('button', { name: 'Open sidebar' })
const channelLink = (name = 'general') => screen.queryByRole('link', { name })
const searchBox = () => screen.getByRole('searchbox', { name: 'Search messages' })
const composer = () => screen.getByRole('textbox', { name: 'Message #general', hidden: true })
const threadPanel = () => screen.queryByRole('complementary', { name: 'Thread' })
const findThreadPanel = () => screen.findByRole('complementary', { name: 'Thread' })
const mainElement = () => screen.getByRole('main', { hidden: true })

/** The sidebar's links, found even while hidden: a closed drawer is closed, not unrendered. */
async function sidebarIsRendered() {
  await screen.findByRole('link', { name: 'general', hidden: true })
}

/** The message column is covered ⇔ the composer sits inside an `inert` ancestor. */
const columnIsInert = () => composer().closest('[inert]') !== null

async function waitForFocusOn(element: () => HTMLElement | null) {
  await waitFor(() => {
    const target = element()
    expect(target).not.toBeNull()
    expect(document.activeElement).toBe(target)
  })
}

async function openFromHamburger(user: User) {
  await user.click(await findOpenButton())
  return findDrawer()
}

describe('the drawer', () => {
  it('opens on a narrow / and holds focus inside it', async () => {
    aReturningUser()
    renderApp('/')

    const dialog = await findDrawer()

    await waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true))
    expect(mainElement()).toHaveAttribute('inert')
  })

  it('on a narrow / it can be closed, and stays closed', async () => {
    aReturningUser()
    const { user, location } = renderApp('/')
    await findDrawer()

    // Each close is itself a re-render of the shell: a build whose arrival effect
    // depends on the drawer's state, or runs on every render, opens it again here.
    await user.click(screen.getByRole('button', { name: 'Close sidebar' }))
    await waitFor(() => expect(drawer()).not.toBeInTheDocument())
    await waitForFocusOn(openButton)
    expect(location().pathname).toBe('/')
    await act(() => new Promise<void>((resolve) => setTimeout(resolve, 25)))
    expect(drawer()).not.toBeInTheDocument()

    // The positive: ☰ brings it back. Then Escape closes it for good.
    await user.click(openButton() as HTMLElement)
    await findDrawer()
    await user.keyboard('{Escape}')
    await waitFor(() => expect(drawer()).not.toBeInTheDocument())
    await waitForFocusOn(openButton)
    expect(location().pathname).toBe('/')
    await act(() => new Promise<void>((resolve) => setTimeout(resolve, 25)))
    expect(drawer()).not.toBeInTheDocument()
  })

  it.each([
    ['a channel', `/c/${GENERAL}`],
    ['a DM', `/c/${DM}`],
    ['/search', '/search?q=zeppelin'],
    ['/settings', '/settings'],
  ])('a link straight to %s opens closed, with ☰', async (_screen, route) => {
    aReturningUser()
    renderApp(route)

    await findOpenButton()
    await sidebarIsRendered()

    expect(drawer()).not.toBeInTheDocument()
    expect(channelLink('general')).not.toBeInTheDocument()
    expect(channelLink('Ada Lovelace')).not.toBeInTheDocument()
  })

  it('wide / shows the sidebar and no ☰', async () => {
    // Green at red, by design: today's layout. It fails a build that opens the
    // drawer, or shows ☰, at 768px and over.
    aReturningUser()
    renderApp('/', 1024)

    expect(await screen.findByRole('link', { name: 'general' })).toBeInTheDocument()
    expect(drawer()).not.toBeInTheDocument()
    expect(openButton()).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Close sidebar' })).not.toBeInTheDocument()
  })

  it('crossing to narrow on / leaves it closed', async () => {
    aReturningUser()
    renderApp('/', 1024)
    await screen.findByRole('link', { name: 'general' })

    setViewportWidth(767)

    await findOpenButton()
    expect(drawer()).not.toBeInTheDocument()
    expect(channelLink('general')).not.toBeInTheDocument()
  })

  it('☰ opens it and Close sidebar closes it, focus back on ☰', async () => {
    aReturningUser()
    const { user } = renderApp(`/c/${GENERAL}`)

    const dialog = await openFromHamburger(user)
    await waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true))
    expect(screen.getByRole('button', { name: 'Open sidebar' })).toHaveAttribute('aria-expanded', 'true')
    await user.click(within(dialog).getByRole('button', { name: 'Close sidebar' }))

    await waitFor(() => expect(drawer()).not.toBeInTheDocument())
    await waitForFocusOn(openButton)
    expect(openButton()).toHaveAttribute('aria-expanded', 'false')
  })

  it('a press on the backdrop closes it and nothing else', async () => {
    aReturningUser()
    const { user, location } = renderApp(`/c/${GENERAL}?thread=${ROOT}`)
    await findThreadPanel()
    const pathBefore = location().pathname
    const searchBefore = location().search
    expect(searchBefore).toBe(`?thread=${ROOT}`)
    await openFromHamburger(user)

    await user.click(screen.getByRole('button', { name: 'Dismiss sidebar', hidden: true }))

    await waitFor(() => expect(drawer()).not.toBeInTheDocument())
    expect(location().pathname).toBe(pathBefore)
    expect(location().search).toBe(searchBefore)
    expect(threadPanel()).toBeInTheDocument()
    await waitForFocusOn(openButton)
  })

  it('Escape closes it, focus back on ☰', async () => {
    aReturningUser()
    const { user } = renderApp(`/c/${GENERAL}`)
    const dialog = await openFromHamburger(user)
    await waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true))

    await user.keyboard('{Escape}')

    await waitFor(() => expect(drawer()).not.toBeInTheDocument())
    await waitForFocusOn(openButton)
  })

  it('Tab and Shift+Tab wrap inside it', async () => {
    aReturningUser()
    const { user } = renderApp('/')
    const dialog = await findDrawer()
    const close = screen.getByRole('button', { name: 'Close sidebar' })
    await waitFor(() => expect(document.activeElement).toBe(close))

    // Shift+Tab from the first control: not out to ☰ or the page, but round to the end.
    await user.tab({ shift: true })
    expect(dialog.contains(document.activeElement)).toBe(true)
    expect(document.activeElement).not.toBe(close)

    // Tab from the last control (Sign out; the connection status has none): round to the first.
    screen.getByRole('button', { name: 'Sign out' }).focus()
    await user.tab()
    expect(document.activeElement).toBe(close)
  })

  it('picking a channel closes it and opens the channel', async () => {
    aReturningUser()
    const { user, location } = renderApp('/')
    await findDrawer()

    await user.click(await screen.findByRole('link', { name: 'general' }))

    await waitFor(() => expect(drawer()).not.toBeInTheDocument())
    expect(location().pathname).toBe(`/c/${GENERAL}`)
    await waitForFocusOn(openButton)
  })

  it('picking a DM from the list closes it', async () => {
    aReturningUser()
    const { user, location } = renderApp(`/c/${GENERAL}`)
    await openFromHamburger(user)

    await user.click(await screen.findByRole('link', { name: 'Grace Hopper' }))

    await waitFor(() => expect(drawer()).not.toBeInTheDocument())
    expect(location().pathname).toBe(`/c/${DM}`)
  })

  it('starting a new DM closes it once it opens', async () => {
    aReturningUser()
    const held = deferred<ReturnType<typeof aChannel>>()
    messaging.post('/api/v1/channels/dm', () => held.promise)
    const { user, location } = renderApp('/')
    await findDrawer()

    await user.click(screen.getByRole('button', { name: 'New direct message' }))
    await user.click(await screen.findByRole('button', { name: 'Grace Hopper' }))
    await waitFor(() =>
      expect(requests().some((r) => r.method === 'POST' && r.url.pathname === '/api/v1/channels/dm')).toBe(
        true,
      ),
    )

    // Still on the old screen, with no sign of why, if it closed at the pick.
    expect(drawer()).toBeInTheDocument()
    expect(location().pathname).toBe('/')

    await act(async () => held.release(aChannel({ id: DM, kind: 'dm', dmPartnerId: GRACE })))

    await waitFor(() => expect(drawer()).not.toBeInTheDocument())
    expect(location().pathname).toBe(`/c/${DM}`)
  })

  it('submitting a search closes it and shows /search', async () => {
    aReturningUser()
    const { user, location } = renderApp('/')
    await findDrawer()

    await user.type(searchBox(), 'zeppelin{Enter}')

    await waitFor(() => expect(drawer()).not.toBeInTheDocument())
    expect(location().pathname).toBe('/search')
    expect(location().search).toBe('?q=zeppelin')
  })

  it('submitting the query already on /search closes it', async () => {
    aReturningUser()
    const { user, location } = renderApp('/search?q=zeppelin')
    await openFromHamburger(user)
    expect(searchBox()).toHaveValue('zeppelin')

    // The other branch of `SearchBox.submit`: it refetches and navigates nowhere.
    await user.click(searchBox())
    await user.keyboard('{Enter}')

    await waitFor(() => expect(drawer()).not.toBeInTheDocument())
    expect(location().pathname).toBe('/search')
    expect(location().search).toBe('?q=zeppelin')
  })

  it('a blank search leaves it open', async () => {
    aReturningUser()
    const { user, location } = renderApp('/')
    await findDrawer()

    await user.type(searchBox(), '   {Enter}')
    await act(() => new Promise<void>((resolve) => setTimeout(resolve, 25)))

    expect(drawer()).toBeInTheDocument()
    expect(location().pathname).toBe('/')

    // The neighbour that does close it, in the same drawer: a real query.
    await user.clear(searchBox())
    await user.type(searchBox(), 'zeppelin{Enter}')
    await waitFor(() => expect(drawer()).not.toBeInTheDocument())
    expect(location().pathname).toBe('/search')
  })

  it('following your name to /settings closes it', async () => {
    aReturningUser()
    const { user, location } = renderApp('/')
    await findDrawer()

    await user.click(screen.getByRole('link', { name: 'Ada Lovelace' }))

    await waitFor(() => expect(drawer()).not.toBeInTheDocument())
    expect(location().pathname).toBe('/settings')
  })

  it('switching workspace closes it', async () => {
    aReturningUser()
    const { user } = renderApp(`/c/${GENERAL}`)
    const dialog = await openFromHamburger(user)

    await user.click(within(dialog).getByRole('button', { name: 'Away' }))

    await waitFor(() => expect(drawer()).not.toBeInTheDocument())
    // The shell was reconciled, not remounted: remounting would close it by itself.
    expect(dialog).toBeInTheDocument()
    expect(dialog).toHaveAttribute('hidden')
  })

  it('creating a channel closes it and opens the channel', async () => {
    aReturningUser()
    messaging.post('/api/v1/channels', aChannel({ id: CREATED, name: 'newchan' }))
    const { user, location } = renderApp('/')
    await findDrawer()

    await user.type(screen.getByRole('textbox', { name: 'New channel' }), 'newchan')
    await user.click(screen.getByRole('button', { name: 'Create' }))

    await waitFor(() => expect(drawer()).not.toBeInTheDocument())
    expect(location().pathname).toBe(`/c/${CREATED}`)
    await waitForFocusOn(openButton)
  })

  it('a refused create leaves it open, with the error', async () => {
    aReturningUser()
    messaging.problem('post', '/api/v1/channels', 409, {
      title: 'Conflict',
      detail: 'A channel with that name already exists.',
    })
    const { user, location } = renderApp('/')
    await findDrawer()

    await user.type(screen.getByRole('textbox', { name: 'New channel' }), 'general')
    await user.click(screen.getByRole('button', { name: 'Create' }))

    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(drawer()).toBeInTheDocument()
    expect(location().pathname).toBe('/')
  })

  it('typing in the create form or opening the new-DM list leaves it open', async () => {
    aReturningUser()
    const { user } = renderApp('/')
    await findDrawer()

    const name = screen.getByRole('textbox', { name: 'New channel' })
    await user.type(name, 'abc')
    expect(name).toHaveValue('abc')
    expect(drawer()).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'New direct message' }))
    expect(screen.getByRole('button', { name: 'New direct message' })).toHaveAttribute(
      'aria-expanded',
      'true',
    )
    expect(await screen.findByRole('button', { name: 'Grace Hopper' })).toBeInTheDocument()
    expect(drawer()).toBeInTheDocument()
  })

  it('opening it closes an open "⋯" menu', async () => {
    aReturningUser()
    renderApp(`/c/${GENERAL}`)
    await screen.findByText('the kettle is on')
    const opener = screen.getAllByRole('button', { name: 'Message actions' })[0]
    fireEvent.click(opener)
    expect(screen.getAllByRole('menu')).toHaveLength(1)
    expect(chat.useChatStore.getState().openMessageMenu).not.toBeNull()

    // No pointer-down, as a screen reader activates it: only the drawer can close the menu.
    fireEvent.click(await findOpenButton())

    expect(await findDrawer()).toBeInTheDocument()
    expect(screen.queryAllByRole('menu')).toHaveLength(0)
    expect(chat.useChatStore.getState().openMessageMenu).toBeNull()
  })

  it('picking a search result opens the channel with the drawer still closed', async () => {
    aReturningUser()
    const hit = aMessage({ id: messageIdAt(2), channelId: GENERAL, authorId: GRACE, body: 'the zeppelin lands' })
    messaging.get('/api/v1/search/messages', { items: [hit], nextCursor: null })
    const { user, location } = renderApp('/')
    await findDrawer()
    await user.type(searchBox(), 'zeppelin{Enter}')
    await waitFor(() => expect(drawer()).not.toBeInTheDocument())

    await user.click(await screen.findByText('the zeppelin lands'))

    await waitFor(() => expect(location().pathname).toBe(`/c/${GENERAL}`))
    // `?message=` is removed by the jump once it has run; either way it names no other message.
    expect(new URLSearchParams(location().search).get('message') ?? hit.id).toBe(hit.id)
    await findOpenButton()
    expect(drawer()).not.toBeInTheDocument()
  })
})

describe('crossing the breakpoint', () => {
  it('a thread stays open, the same panel, side ⇄ full screen', async () => {
    aReturningUser()
    renderApp(`/c/${GENERAL}?thread=${ROOT}`, 1024)
    const panel = await findThreadPanel()
    await within(panel).findByText('boiling now')
    expect(within(panel).getByRole('button', { name: 'Close thread' })).toBeInTheDocument()
    expect(columnIsInert()).toBe(false)

    setViewportWidth(390)

    expect(threadPanel()).toBe(panel)
    expect(within(panel).getByRole('button', { name: 'Back to channel' })).toBeInTheDocument()
    expect(columnIsInert()).toBe(true)

    setViewportWidth(1024)

    expect(threadPanel()).toBe(panel)
    expect(within(panel).getByRole('button', { name: 'Close thread' })).toBeInTheDocument()
    expect(columnIsInert()).toBe(false)
  })

  it('with a thread open, both drafts and their nodes survive 1024 → 390 → 1024', async () => {
    aReturningUser()
    const { user } = renderApp(`/c/${GENERAL}?thread=${ROOT}`, 1024)
    const panel = await findThreadPanel()
    const replyBox = await within(panel).findByRole('textbox', { name: 'Reply' })
    const channelBox = composer()
    await user.type(channelBox, 'channel draft')
    await user.type(replyBox, 'reply draft')

    setViewportWidth(390)

    expect(within(panel).getByRole('button', { name: 'Back to channel' })).toBeInTheDocument()
    expect(composer()).toBe(channelBox)
    expect(within(panel).getByRole('textbox', { name: 'Reply' })).toBe(replyBox)
    expect(channelBox).toHaveValue('channel draft')
    expect(replyBox).toHaveValue('reply draft')

    setViewportWidth(1024)

    expect(within(panel).getByRole('button', { name: 'Close thread' })).toBeInTheDocument()
    expect(composer()).toBe(channelBox)
    expect(within(panel).getByRole('textbox', { name: 'Reply' })).toBe(replyBox)
    expect(channelBox).toHaveValue('channel draft')
    expect(replyBox).toHaveValue('reply draft')
  })

  it('acceptance check 3’s order: a channel draft, then a thread and a reply draft, 390 → 844 → 390', async () => {
    aReturningUser()
    const { user } = renderApp(`/c/${GENERAL}`, 390)
    await findOpenButton()
    await screen.findByText('the kettle is on')
    await user.type(composer(), 'channel draft')
    fireEvent.click(screen.getByRole('button', { name: /^1 reply/ }))
    const panel = await findThreadPanel()
    const replyBox = await within(panel).findByRole('textbox', { name: 'Reply' })
    await user.type(replyBox, 'reply draft')
    expect(within(panel).getByRole('button', { name: 'Back to channel' })).toBeInTheDocument()

    setViewportWidth(844)

    expect(within(panel).getByRole('button', { name: 'Close thread' })).toBeInTheDocument()
    expect(composer()).toHaveValue('channel draft')
    expect(replyBox).toHaveValue('reply draft')

    setViewportWidth(390)

    expect(threadPanel()).toBe(panel)
    expect(within(panel).getByRole('textbox', { name: 'Reply' })).toHaveValue('reply draft')
    await user.click(within(panel).getByRole('button', { name: 'Back to channel' }))

    await waitFor(() => expect(threadPanel()).not.toBeInTheDocument())
    expect(composer()).toHaveValue('channel draft')
    await waitFor(() => expect(document.activeElement).toBe(composer()))
  })

  it('the channel list keeps its scroll position across both crossings', async () => {
    aReturningUser()
    renderApp(`/c/${GENERAL}`, 1024)
    const row = (await screen.findByText('the kettle is on')).closest('article') as HTMLElement
    const scroller = row.parentElement as HTMLElement
    giveLayout(scroller, { clientHeight: 500, scrollHeight: 1200, scrollTop: 300 })

    setViewportWidth(390)

    await findOpenButton()
    const narrowRow = screen.getByText('the kettle is on').closest('article') as HTMLElement
    expect(narrowRow.parentElement).toBe(scroller)
    expect(scroller.scrollTop).toBe(300)

    setViewportWidth(1024)

    const wideRow = screen.getByText('the kettle is on').closest('article') as HTMLElement
    expect(wideRow.parentElement).toBe(scroller)
    expect(scroller.scrollTop).toBe(300)
  })

  it('the member panel takes each width’s default', async () => {
    aReturningUser()
    const { user } = renderApp(`/c/${GENERAL}`, 1024)
    expect(await screen.findByRole('heading', { name: 'Members' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Members' })).not.toBeInTheDocument()

    setViewportWidth(390)

    expect(screen.queryByRole('heading', { name: 'Members' })).not.toBeInTheDocument()
    await user.click(await screen.findByRole('button', { name: 'Members' }))
    expect(await screen.findByRole('heading', { name: 'Members' })).toBeInTheDocument()

    setViewportWidth(1024)

    expect(await screen.findByRole('heading', { name: 'Members' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Back to channel' })).not.toBeInTheDocument()

    setViewportWidth(390)

    expect(screen.queryByRole('heading', { name: 'Members' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Members' })).toBeInTheDocument()
  })

  it('wide to narrow with a thread open keeps the thread covering', async () => {
    aReturningUser()
    renderApp(`/c/${GENERAL}?thread=${ROOT}`, 1024)
    const panel = await findThreadPanel()
    await within(panel).findByText('boiling now')

    setViewportWidth(390)

    expect(threadPanel()).toBe(panel)
    expect(within(panel).getByRole('button', { name: 'Back to channel' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Members' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Members' })).not.toBeInTheDocument()
  })

  it('the drawer is closed after crossing to wide and back', async () => {
    aReturningUser()
    const { user } = renderApp(`/c/${GENERAL}`, 390)
    await openFromHamburger(user)

    setViewportWidth(1024)

    expect(drawer()).not.toBeInTheDocument()
    expect(openButton()).not.toBeInTheDocument()
    expect(await screen.findByRole('link', { name: 'general' })).toBeInTheDocument()

    setViewportWidth(390)

    await findOpenButton()
    expect(drawer()).not.toBeInTheDocument()
    expect(channelLink('general')).not.toBeInTheDocument()
  })

  it('crossing to narrow with focus in the sidebar moves it to ☰', async () => {
    aReturningUser()
    renderApp(`/c/${GENERAL}`, 1024)
    const random = await screen.findByRole('link', { name: 'random' })
    await screen.findByText('the kettle is on')
    act(() => random.focus())
    expect(document.activeElement).toBe(random)

    setViewportWidth(390)

    await waitForFocusOn(openButton)

    // Its neighbour: focus that was never in the sidebar is left where it was.
    setViewportWidth(1024)
    await screen.findByRole('link', { name: 'random' })
    act(() => composer().focus())
    expect(document.activeElement).toBe(composer())

    setViewportWidth(390)

    await findOpenButton()
    expect(document.activeElement).toBe(composer())
  })
})
