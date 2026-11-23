/**
 * The thread panel inside the real channel view (R6, R7, *Paths*): the URL param,
 * the right column, Back, and what closes the panel.
 *
 * Messaging is stubbed at the network edge; the channel list, the history, the
 * thread and the members are the real components. Real time throughout, with
 * `fireEvent.click` — the same reasons as `ChannelView.test.tsx`.
 *
 * Every guard finds the panel open first, so "no panel" cannot pass for a build
 * that never opens one.
 */

import type { InfiniteData } from '@tanstack/react-query'
import { act, fireEvent, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useNavigate } from 'react-router-dom'

import type { ThreadPage } from '../../lib/api/messaging'
import { snapshot } from '../../lib/auth/session'
import { useChatStore } from '../../stores/chat'
import { auth, messaging, requests } from '../../test/api'
import {
  aChannel,
  aMessage,
  aMessagePage,
  aThreadPage,
  aWorkspaceMember,
  WORKSPACE_ID,
} from '../../test/factories'
import { giveLayout } from '../../test/layout'
import { renderWithProviders } from '../../test/render'
import { FakeSocket } from '../../test/socket'
import { ChannelList } from './ChannelList'
import { ChannelView } from './ChannelView'
import { channelKeys } from './useChannels'

vi.mock('../../lib/auth/session', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../lib/auth/session')>()),
  snapshot: vi.fn(() => ({ status: 'loading' })),
}))

const ADA = 'user-ada'
const GRACE = 'user-grace'
const GENERAL = 'channel-general'
const RANDOM = 'channel-random'
const THREAD = '/api/v1/messages/{message_id}/thread' as const

beforeEach(() => {
  vi.mocked(snapshot).mockReturnValue({ status: 'loading' })
})

const rootA = aMessage({
  channelId: GENERAL,
  authorId: GRACE,
  body: 'root A',
  replyCount: 1,
  lastReplyAt: '2026-09-15T10:00:00Z',
})
const rootB = aMessage({
  channelId: GENERAL,
  authorId: GRACE,
  body: 'root B',
  replyCount: 2,
  lastReplyAt: '2026-09-15T11:00:00Z',
})
/** Older than anything loaded: reachable only by its URL. */
const rootOld = aMessage({
  channelId: GENERAL,
  authorId: GRACE,
  body: 'a root from long ago',
  replyCount: 1,
  lastReplyAt: '2026-01-01T10:00:00Z',
})
/**
 * One reply per (root, body), created once: the panel refetches a cached thread on
 * Back, and a fresh id each time would re-key the row under the test's feet.
 */
const replies = new Map<string, ReturnType<typeof aMessage>>()
const replyTo = (root: typeof rootA, body: string) => {
  const id = `${root.id}:${body}`
  let reply = replies.get(id)
  if (!reply) {
    reply = aMessage({ channelId: GENERAL, threadRootId: root.id, authorId: GRACE, body })
    replies.set(id, reply)
  }
  return reply
}

function startServer() {
  const channels = {
    [GENERAL]: aChannel({ id: GENERAL, name: 'general' }),
    [RANDOM]: aChannel({ id: RANDOM, name: 'random' }),
  }
  messaging.get('/api/v1/channels', {
    items: Object.values(channels).map((c) => ({ ...c })),
    nextCursor: null,
  })
  messaging.get('/api/v1/channels/{channel_id}', ({ params }) => ({
    ...channels[params.channel_id as keyof typeof channels],
  }))
  messaging.get('/api/v1/channels/{channel_id}/messages', ({ params }) =>
    aMessagePage(params.channel_id === GENERAL ? [rootB, rootA] : []),
  )
  messaging.get('/api/v1/channels/{channel_id}/members', { items: [], nextCursor: null })
  messaging.get(THREAD, ({ params }) => {
    if (params.message_id === rootB.id) return aThreadPage(rootB, [replyTo(rootB, 'reply to B')])
    if (params.message_id === rootOld.id)
      return aThreadPage(rootOld, [replyTo(rootOld, 'reply to old')])
    return aThreadPage(rootA, [replyTo(rootA, 'reply to A')])
  })
  auth.members([aWorkspaceMember({ id: ADA }), aWorkspaceMember({ id: GRACE })])
}

/** What a test needs beyond a click: a Back button, as a browser has one. */
function Back() {
  const navigate = useNavigate()
  return (
    <button type="button" onClick={() => navigate(-1)}>
      Back
    </button>
  )
}

function Shell({ workspaceId = WORKSPACE_ID }: { workspaceId?: string }) {
  return (
    <>
      <Back />
      <ChannelList accessToken="token" workspaceId={workspaceId} />
      <ChannelView accessToken="token" workspaceId={workspaceId} userId={ADA} />
    </>
  )
}

/** `override` runs after the default stubs, so its handlers win. */
function renderShell(route = `/c/${GENERAL}`, override?: () => void) {
  startServer()
  override?.()
  const socket = new FakeSocket('token')
  socket.connected = true
  return renderWithProviders(<Shell />, { route, path: '/c/:channelId', socket })
}

const threadPanel = () => screen.queryByRole('complementary', { name: 'Thread' })
const findThreadPanel = () => screen.findByRole('complementary', { name: 'Thread' })
const openSummary = (name: RegExp) => fireEvent.click(screen.getByRole('button', { name }))
const searchOf = (view: { location: () => { search: string } }) =>
  new URLSearchParams(view.location().search)

describe('ChannelView — the thread panel', () => {
  it('?thread= on load opens the panel in place of the members, for a root not in the loaded history', async () => {
    renderShell(`/c/${GENERAL}?thread=${rootOld.id}`)

    const panel = await findThreadPanel()

    expect(await within(panel).findByText('a root from long ago')).toBeInTheDocument()
    expect(within(panel).getByText('reply to old')).toBeInTheDocument()
    // Not in the channel's history: that is what makes the thread fetch its own root.
    await screen.findByText('root A')
    expect(screen.getAllByText('a root from long ago')).toHaveLength(1)
    // The panel took the right column; the members are not beside it.
    expect(screen.getAllByRole('complementary')).toHaveLength(1)
  })

  it('a reply arriving in the panel leaves the channel list’s scrollTop where it was', async () => {
    const view = renderShell(`/c/${GENERAL}?thread=${rootA.id}`)
    const panel = await findThreadPanel()
    await within(panel).findByText('reply to A')
    await screen.findByText('root B')
    const channelRows = screen.getAllByRole('article').filter((row) => !panel.contains(row))
    const channelScroller = channelRows[0].parentElement as HTMLElement
    giveLayout(channelScroller, { clientHeight: 500, scrollHeight: 1200, scrollTop: 300 })
    giveLayout(within(panel).getByRole('log', { name: 'Replies' }), {
      clientHeight: 300,
      scrollHeight: 2000,
      scrollTop: 0,
    })

    // What `message_received` does to the thread's cache, written by hand so this
    // file does not depend on the module that does it.
    act(() =>
      view.queryClient.setQueryData<InfiniteData<ThreadPage>>(
        ['messages', WORKSPACE_ID, GENERAL, 'thread', rootA.id],
        (cached) =>
          cached && {
            ...cached,
            pages: cached.pages.map((page, index) =>
              index === 0 ? { ...page, items: [replyTo(rootA, 'a late reply'), ...page.items] } : page,
            ),
          },
      ),
    )

    await within(panel).findByText('a late reply')
    expect(channelScroller.scrollTop).toBe(300)
  })

  it('opening A then B pushes: Back shows A, Back again closes', async () => {
    const view = renderShell()
    await screen.findByText('root B')

    openSummary(/^1 reply/)
    expect(await within(await findThreadPanel()).findByText('reply to A')).toBeInTheDocument()
    expect(searchOf(view).get('thread')).toBe(rootA.id)

    openSummary(/^2 replies/)
    expect(await within(await findThreadPanel()).findByText('reply to B')).toBeInTheDocument()
    expect(searchOf(view).get('thread')).toBe(rootB.id)

    fireEvent.click(screen.getByRole('button', { name: 'Back' }))
    expect(await within(await findThreadPanel()).findByText('reply to A')).toBeInTheDocument()
    expect(searchOf(view).get('thread')).toBe(rootA.id)

    fireEvent.click(screen.getByRole('button', { name: 'Back' }))
    await vi.waitFor(() => expect(threadPanel()).not.toBeInTheDocument())
    expect(searchOf(view).has('thread')).toBe(false)
  })

  it('closing keeps other params and Back does not reopen it', async () => {
    // A param nothing acts on: `?message=` would start a search jump, which
    // removes it by itself.
    const view = renderShell(`/c/${GENERAL}?ref=x`)
    await screen.findByText('root B')
    openSummary(/^1 reply/)
    const panel = await findThreadPanel()
    expect(searchOf(view).get('thread')).toBe(rootA.id)
    expect(searchOf(view).get('ref')).toBe('x')

    fireEvent.click(within(panel).getByRole('button', { name: 'Close thread' }))

    await vi.waitFor(() => expect(threadPanel()).not.toBeInTheDocument())
    expect(searchOf(view).has('thread')).toBe(false)
    expect(searchOf(view).get('ref')).toBe('x')

    // `replace`, so the entry with the thread in it is gone: Back leaves it closed.
    fireEvent.click(screen.getByRole('button', { name: 'Back' }))
    await screen.findByText('root B')
    expect(threadPanel()).not.toBeInTheDocument()
  })

  it('switching channel closes the panel', async () => {
    renderShell(`/c/${GENERAL}?thread=${rootA.id}`)
    await findThreadPanel()

    fireEvent.click(await screen.findByRole('link', { name: /random/ }))

    await screen.findByText('Nothing here yet. Say something.')
    expect(threadPanel()).not.toBeInTheDocument()
  })

  it('a bad thread leaves the history showing', async () => {
    renderShell(`/c/${GENERAL}?thread=not-a-real-id`, () =>
      messaging.problem('get', THREAD, 404, { title: 'Not Found', detail: 'No such channel.' }),
    )

    expect(await screen.findByText("This thread isn't available.")).toBeInTheDocument()

    expect(await screen.findByText('root A')).toBeInTheDocument()
    expect(screen.getByText('root B')).toBeInTheDocument()
  })

  it('a channel that 404s shows no panel, though its thread is cached', async () => {
    const view = renderShell(`/c/${GENERAL}?thread=${rootA.id}`)
    const panel = await findThreadPanel()
    await within(panel).findByText('reply to A')

    messaging.problem('get', '/api/v1/channels/{channel_id}', 404, {
      title: 'Not Found',
      detail: 'No such channel.',
    })
    await act(() =>
      view.queryClient.invalidateQueries({ queryKey: channelKeys.detail(WORKSPACE_ID, GENERAL) }),
    )

    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(threadPanel()).not.toBeInTheDocument()
    expect(screen.queryByText('reply to A')).not.toBeInTheDocument()
  })

  it('closing the thread with a reply’s menu open leaves no menu open anywhere', async () => {
    renderShell(`/c/${GENERAL}?thread=${rootA.id}`)
    const panel = await findThreadPanel()
    const replyRow = (await within(panel).findByText('reply to A')).closest('article') as HTMLElement
    fireEvent.click(within(replyRow).getByRole('button', { name: 'Message actions' }))
    expect(screen.getAllByRole('menu')).toHaveLength(1)

    fireEvent.click(within(panel).getByRole('button', { name: 'Close thread' }))

    await vi.waitFor(() => expect(threadPanel()).not.toBeInTheDocument())
    expect(screen.queryAllByRole('menu')).toHaveLength(0)
    expect(useChatStore.getState().openMessageMenu).toBeNull()
    // The channel's own rows still have their "⋯", all of them shut.
    await screen.findByText('root B')
    for (const opener of screen.getAllByRole('button', { name: 'Message actions' })) {
      expect(opener).toHaveAttribute('aria-expanded', 'false')
    }
  })

  it('switching channel with a menu open leaves no menu, and none on the next view', async () => {
    renderShell()
    const rootBRow = (await screen.findByText('root B')).closest('article') as HTMLElement
    fireEvent.click(within(rootBRow).getByRole('button', { name: 'Message actions' }))
    expect(screen.getAllByRole('menu')).toHaveLength(1)

    fireEvent.click(await screen.findByRole('link', { name: /random/ }))

    await screen.findByText('Nothing here yet. Say something.')
    expect(screen.queryAllByRole('menu')).toHaveLength(0)
    expect(useChatStore.getState().openMessageMenu).toBeNull()

    // And back: the same message is on screen again, with its menu shut.
    fireEvent.click(await screen.findByRole('link', { name: /general/ }))
    const again = (await screen.findByText('root B')).closest('article') as HTMLElement
    expect(within(again).getByRole('button', { name: 'Message actions' })).toHaveAttribute(
      'aria-expanded',
      'false',
    )
    expect(screen.queryAllByRole('menu')).toHaveLength(0)
  })

  it('a menu opened in the thread panel closes the one open in the channel', async () => {
    renderShell(`/c/${GENERAL}?thread=${rootA.id}`)
    const panel = await findThreadPanel()
    const replyRow = (await within(panel).findByText('reply to A')).closest('article') as HTMLElement
    const channelRow = (await screen.findByText('root B')).closest('article') as HTMLElement
    const channelOpener = within(channelRow).getByRole('button', { name: 'Message actions' })
    const panelOpener = within(replyRow).getByRole('button', { name: 'Message actions' })

    fireEvent.click(channelOpener)
    expect(channelOpener).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getAllByRole('menu')).toHaveLength(1)

    // No pointer-down, as a screen reader activates it: only the shared id can close the other.
    fireEvent.click(panelOpener)

    expect(channelOpener).toHaveAttribute('aria-expanded', 'false')
    expect(panelOpener).toHaveAttribute('aria-expanded', 'true')
    const open = screen.getAllByRole('menu')
    expect(open).toHaveLength(1)
    expect(open[0].id).toBe(panelOpener.getAttribute('aria-controls'))
  })

  it('a new workspace shows no thread from the old one', async () => {
    const view = renderShell(`/c/${GENERAL}?thread=${rootA.id}`)
    const panel = await findThreadPanel()
    await within(panel).findByText('reply to A')
    const threadGetsBefore = requests().filter((r) => r.url.pathname.endsWith('/thread')).length

    // The new workspace's token cannot see the old workspace's channel.
    messaging.problem('get', '/api/v1/channels/{channel_id}', 404, {
      title: 'Not Found',
      detail: 'No such channel.',
    })
    view.rerender(<Shell workspaceId="another-workspace" />)

    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(threadPanel()).not.toBeInTheDocument()
    expect(screen.queryByText('reply to A')).not.toBeInTheDocument()
    expect(requests().filter((r) => r.url.pathname.endsWith('/thread'))).toHaveLength(
      threadGetsBefore,
    )
  })
})

