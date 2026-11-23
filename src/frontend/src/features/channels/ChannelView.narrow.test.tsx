/**
 * The thread and member panels below 768px, inside the real channel view (issue
 * Req 5; plan Decisions 8, 9, 17, 18, 24).
 *
 * Built as `ChannelView.thread.test.tsx` is: Messaging stubbed at the network
 * edge, the channel list, history, thread and members real, a `Back` button as a
 * browser has one, and `fireEvent.click` where a pointer event would close a "⋯"
 * menu by itself. Narrow comes from `setViewportWidth`; 390 unless a test says.
 *
 * "Covered" is read as the message column being `inert`: the composer sits inside
 * an `inert` ancestor. "The member panel is shown" ⇔ the heading **Members**.
 */

import { act, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Link, useNavigate } from 'react-router-dom'

import { snapshot } from '../../lib/auth/session'
import { auth, messaging } from '../../test/api'
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
import { setViewportWidth } from '../../test/viewport'
import { ChannelList } from './ChannelList'
import { ChannelView } from './ChannelView'

vi.mock('../../lib/auth/session', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../lib/auth/session')>()),
  snapshot: vi.fn(() => ({ status: 'loading' })),
}))

const ADA = 'user-ada'
const GRACE = 'user-grace'
const GENERAL = 'channel-general'
const RANDOM = 'channel-random'
const DM = 'channel-dm'
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
const replyToA = aMessage({ channelId: GENERAL, threadRootId: rootA.id, authorId: GRACE, body: 'reply to A' })

function startServer() {
  const channels = {
    [GENERAL]: aChannel({ id: GENERAL, name: 'general' }),
    [RANDOM]: aChannel({ id: RANDOM, name: 'random' }),
    [DM]: aChannel({ id: DM, name: 'dm:pair', kind: 'dm', dmPartnerId: GRACE }),
  }
  messaging.get('/api/v1/channels', {
    items: [channels[GENERAL], channels[RANDOM]],
    nextCursor: null,
  })
  messaging.get('/api/v1/channels/{channel_id}', ({ params }) => ({
    ...channels[params.channel_id as keyof typeof channels],
  }))
  messaging.get('/api/v1/channels/{channel_id}/messages', ({ params }) =>
    aMessagePage(params.channel_id === GENERAL ? [rootB, rootA] : []),
  )
  messaging.get('/api/v1/channels/{channel_id}/members', { items: [], nextCursor: null })
  messaging.get(THREAD, () => aThreadPage(rootA, [replyToA]))
  auth.members([
    aWorkspaceMember({ id: ADA }),
    aWorkspaceMember({ id: GRACE, displayName: 'Grace Hopper' }),
  ])
}

/** What a test needs beyond a click: a Back button as a browser has one, and a way into the DM. */
function Shell() {
  const navigate = useNavigate()
  return (
    <>
      <button type="button" onClick={() => navigate(-1)}>
        Back
      </button>
      <Link to={`/c/${DM}`}>Open the DM</Link>
      <ChannelList accessToken="token" workspaceId={WORKSPACE_ID} />
      <ChannelView accessToken="token" workspaceId={WORKSPACE_ID} userId={ADA} />
    </>
  )
}

function renderShell(width = 390, route = `/c/${GENERAL}`) {
  startServer()
  setViewportWidth(width)
  const socket = new FakeSocket('token')
  socket.connected = true
  return renderWithProviders(<Shell />, { route, path: '/c/:channelId', socket })
}

const composer = () => screen.getByRole('textbox', { name: 'Message #general', hidden: true })
const columnIsInert = () => composer().closest('[inert]') !== null
const threadPanel = () => screen.queryByRole('complementary', { name: 'Thread' })
const findThreadPanel = () => screen.findByRole('complementary', { name: 'Thread' })
const membersHeading = () => screen.queryByRole('heading', { name: 'Members' })
const membersButton = () => screen.queryByRole('button', { name: 'Members' })
/** The history's scroller: the parent of its rows, outside any thread panel. */
const listScroller = () => {
  const panel = threadPanel()
  const rows = screen.getAllByRole('article').filter((row) => !panel?.contains(row))
  return rows[0].parentElement as HTMLElement
}

describe('ChannelView — the panels below 768px', () => {
  it('at 768 the member panel is beside the list; at 767 it is closed with a Members button', async () => {
    const wide = renderShell(768)
    expect(await screen.findByRole('heading', { name: 'Members' })).toBeInTheDocument()
    expect(membersButton()).not.toBeInTheDocument()
    wide.unmount()

    renderShell(767)

    await screen.findByText('root B')
    expect(membersHeading()).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Members' })).toHaveAttribute('aria-expanded', 'false')
  })

  it('a thread covers the list; Back to channel returns at the scroll position left', async () => {
    renderShell()
    await screen.findByText('root B')
    const scroller = listScroller()
    giveLayout(scroller, { clientHeight: 500, scrollHeight: 1200, scrollTop: 300 })

    fireEvent.click(screen.getByRole('button', { name: /^1 reply/ }))
    const panel = await findThreadPanel()
    await within(panel).findByText('reply to A')
    expect(columnIsInert()).toBe(true)
    const back = within(panel).getByRole('button', { name: 'Back to channel' })
    expect(within(panel).queryByRole('button', { name: 'Close thread' })).not.toBeInTheDocument()

    fireEvent.click(back)

    await waitFor(() => expect(threadPanel()).not.toBeInTheDocument())
    expect(listScroller()).toBe(scroller)
    expect(scroller.scrollTop).toBe(300)
    expect(columnIsInert()).toBe(false)
    await waitFor(() => expect(document.activeElement).toBe(composer()))
  })

  it('the browser’s Back closes a covering thread at the same position', async () => {
    const view = renderShell()
    await screen.findByText('root B')
    const scroller = listScroller()
    giveLayout(scroller, { clientHeight: 500, scrollHeight: 1200, scrollTop: 300 })
    fireEvent.click(screen.getByRole('button', { name: /^1 reply/ }))
    const panel = await findThreadPanel()
    expect(within(panel).getByRole('button', { name: 'Back to channel' })).toBeInTheDocument()
    expect(new URLSearchParams(view.location().search).get('thread')).toBe(rootA.id)

    fireEvent.click(screen.getByRole('button', { name: 'Back' }))

    await waitFor(() => expect(threadPanel()).not.toBeInTheDocument())
    expect(view.location().search).toBe('')
    expect(listScroller()).toBe(scroller)
    expect(scroller.scrollTop).toBe(300)
  })

  it('Members opens a covering panel; Back to channel closes it; no history entry', async () => {
    const view = renderShell()
    await screen.findByText('root B')
    const keyBefore = view.location().key
    expect(membersHeading()).not.toBeInTheDocument()
    expect(columnIsInert()).toBe(false)

    fireEvent.click(screen.getByRole('button', { name: 'Members' }))

    expect(await screen.findByRole('heading', { name: 'Members' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Members' })).toHaveAttribute('aria-expanded', 'true')
    expect(columnIsInert()).toBe(true)
    expect(view.location().key).toBe(keyBefore)

    fireEvent.click(screen.getByRole('button', { name: 'Back to channel' }))

    await waitFor(() => expect(membersHeading()).not.toBeInTheDocument())
    expect(columnIsInert()).toBe(false)
    expect(view.location().key).toBe(keyBefore)
    await waitFor(() => expect(document.activeElement).toBe(composer()))
  })

  it('the member panel closes on a channel switch', async () => {
    renderShell()
    await screen.findByText('root B')
    fireEvent.click(screen.getByRole('button', { name: 'Members' }))
    await screen.findByRole('heading', { name: 'Members' })

    fireEvent.click(await screen.findByRole('link', { name: /random/ }))

    await screen.findByText('Nothing here yet. Say something.')
    expect(membersHeading()).not.toBeInTheDocument()
    // The positive: random offers it, closed.
    expect(screen.getByRole('button', { name: 'Members' })).toHaveAttribute('aria-expanded', 'false')
  })

  it('a DM offers no Members button', async () => {
    renderShell()
    await screen.findByText('root B')
    expect(screen.getByRole('button', { name: 'Members' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('link', { name: 'Open the DM' }))

    expect(await screen.findByRole('heading', { name: 'Grace Hopper', level: 2 })).toBeInTheDocument()
    await act(() => new Promise<void>((resolve) => setTimeout(resolve, 25)))
    expect(membersButton()).not.toBeInTheDocument()
    expect(membersHeading()).not.toBeInTheDocument()
  })
})
