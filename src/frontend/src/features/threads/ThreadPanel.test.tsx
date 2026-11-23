/**
 * The thread panel (R5, R7, R10, R13): the root, its replies oldest first, a
 * composer; its own scroll rules; and what it shows for a thread that is not
 * there.
 *
 * jsdom does no layout, so every scroll rule gives the replies scroller its
 * dimensions with `giveLayout`, one test per direction of each boundary.
 */

import type { QueryClient } from '@tanstack/react-query'
import { act, fireEvent, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { Message } from '../../lib/api/messaging'
import { useChatStore } from '../../stores/chat'
import { auth, messaging, requests } from '../../test/api'
import { aMessage, aThreadPage, aWorkspaceMember, WORKSPACE_ID } from '../../test/factories'
import { giveLayout } from '../../test/layout'
import { renderWithProviders } from '../../test/render'
import { FakeSocket } from '../../test/socket'
import { threadKeys, upsertThreadMessage } from './threadCache'
import { ThreadPanel } from './ThreadPanel'

const CHANNEL = 'channel-general'
const ADA = 'user-ada'
const GRACE = 'user-grace'
const THREAD = '/api/v1/messages/{message_id}/thread' as const

const root = aMessage({
  channelId: CHANNEL,
  authorId: ADA,
  body: 'who is on call tonight?',
  replyCount: 2,
  lastReplyAt: '2026-09-15T10:00:00Z',
})
const key = threadKeys.detail(WORKSPACE_ID, CHANNEL, root.id)

function reply(overrides: Partial<Message> = {}): Message {
  return aMessage({ channelId: CHANNEL, threadRootId: root.id, authorId: GRACE, ...overrides })
}

function panel(channelId = CHANNEL, onClose = vi.fn()) {
  return (
    <ThreadPanel
      accessToken="token"
      workspaceId={WORKSPACE_ID}
      channelId={channelId}
      rootId={root.id}
      userId={ADA}
      myRole={null}
      onClose={onClose}
    />
  )
}

function renderPanel({ channelId = CHANNEL, onClose = vi.fn() } = {}) {
  auth.members([
    aWorkspaceMember({ id: ADA, displayName: 'Ada Lovelace' }),
    aWorkspaceMember({ id: GRACE, displayName: 'Grace Hopper' }),
  ])
  useChatStore.getState().setConnectionStatus('connected')
  const socket = new FakeSocket('token')
  const view = renderWithProviders(panel(channelId, onClose), { socket })
  return { ...view, socket, onClose }
}

const articles = () => screen.getAllByRole('article')
const bodies = () => articles().map((article) => article.querySelector('p')?.textContent)
const scroller = () => screen.getByRole('log', { name: 'Replies' })
const arrives = (queryClient: QueryClient, message: Message) =>
  act(() => upsertThreadMessage(queryClient, key, message))

describe('ThreadPanel — what it shows', () => {
  it('shows the root, then the replies oldest first, then the composer', async () => {
    const older = reply({ body: 'older reply' })
    const newer = reply({ body: 'newer reply' })
    messaging.get(THREAD, aThreadPage(root, [newer, older]))

    renderPanel()

    await screen.findByText('newer reply')
    expect(screen.getByRole('complementary', { name: 'Thread' })).toBeInTheDocument()
    expect(bodies()).toEqual(['who is on call tonight?', 'older reply', 'newer reply'])
    const composer = screen.getByRole('textbox', { name: 'Reply' })
    const lastReply = articles().at(-1) as HTMLElement
    expect(lastReply.compareDocumentPosition(composer) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('the panel’s root has reactions, edit and delete, no summary, no Reply in thread', async () => {
    const reacted = { ...root, reactions: [{ emoji: 'tada', count: 1, reacted: false }] }
    messaging.get(THREAD, aThreadPage(reacted, [reply()]))
    const { user } = renderPanel()
    await screen.findByText('who is on call tonight?')
    const [rootRow] = articles()

    // The positives first: the root takes everything a message takes.
    expect(within(rootRow).getByRole('button', { name: /, 1$/ })).toBeInTheDocument()
    await user.click(within(rootRow).getByRole('button', { name: 'Message actions' }))
    expect(screen.getByRole('menuitem', { name: 'React' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Edit' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Delete' })).toBeInTheDocument()
    expect(within(rootRow).queryByText(/repl(y|ies)/)).not.toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: 'Reply in thread' })).not.toBeInTheDocument()
    expect(screen.getAllByRole('menuitem')).toHaveLength(3)
  })

  it('replies offer no Reply in thread', async () => {
    messaging.get(
      THREAD,
      aThreadPage(root, [
        reply({ authorId: ADA, body: 'my own reply' }),
        reply({ authorId: GRACE, body: 'her reply' }),
      ]),
    )
    const { user } = renderPanel()
    await screen.findByText('my own reply')
    // Replies are oldest first: Ada's is last in the wire page, so it comes first.
    const rows = articles()
    const mine = rows.find((row) => within(row).queryByText('my own reply')) as HTMLElement
    const hers = rows.find((row) => within(row).queryByText('her reply')) as HTMLElement

    await user.click(within(mine).getByRole('button', { name: 'Message actions' }))
    expect(screen.getAllByRole('menuitem').map((e) => e.textContent?.trim())).toEqual([
      'React',
      'Edit',
      'Delete',
    ])

    await user.click(within(hers).getByRole('button', { name: 'Message actions' }))
    expect(screen.getAllByRole('menuitem').map((e) => e.textContent?.trim())).toEqual(['React'])
    expect(screen.queryByRole('menuitem', { name: 'Reply in thread' })).not.toBeInTheDocument()
  })

  it('a reply deleted while its menu is open: no menu, and focus is on the thread panel', async () => {
    const mine = reply({ authorId: ADA, body: 'my own reply' })
    messaging.get(THREAD, aThreadPage(root, [mine]))
    const { user, queryClient } = renderPanel()
    await screen.findByText('my own reply')
    const row = articles().find((r) => within(r).queryByText('my own reply')) as HTMLElement
    await user.click(within(row).getByRole('button', { name: 'Message actions' }))
    expect(screen.getByRole('menuitem', { name: 'Delete' })).toBeInTheDocument()

    arrives(queryClient, { ...mine, body: '', deletedAt: '2026-09-15T09:32:00Z', version: 2 })

    expect(await screen.findByText('This message was deleted.')).toBeInTheDocument()
    expect(screen.queryAllByRole('menu')).toHaveLength(0)
    expect(screen.getByRole('complementary', { name: 'Thread' })).toHaveFocus()
  })

  it('a deleted reply is a tombstone', async () => {
    messaging.get(
      THREAD,
      aThreadPage(root, [
        reply({ body: 'a live reply' }),
        reply({ body: '', deletedAt: '2026-09-15T09:32:00Z' }),
      ]),
    )

    renderPanel()

    await screen.findByText('a live reply')
    expect(screen.getByText('This message was deleted.')).toBeInTheDocument()
  })

  it('Close thread calls onClose', async () => {
    messaging.get(THREAD, aThreadPage(root, []))
    const { user, onClose } = renderPanel()
    await screen.findByText('who is on call tonight?')

    await user.click(screen.getByRole('button', { name: 'Close thread' }))

    expect(onClose).toHaveBeenCalledOnce()
  })
})

describe('ThreadPanel — scrolling', () => {
  it('scrolling to the top loads older replies and keeps the position', async () => {
    const [newest, middle, oldest] = ['newest', 'middle', 'oldest'].map((body) => reply({ body }))
    messaging.get(THREAD, ({ request }) =>
      new URL(request.url).searchParams.get('cursor') === 'older'
        ? aThreadPage(root, [oldest])
        : aThreadPage(root, [newest, middle], 'older'),
    )
    renderPanel()
    await screen.findByText('newest')
    const log = scroller()
    // Every reply is 100px tall, so the height grows when the older page lands —
    // before the panel's layout effect measures it, as a browser would.
    giveLayout(log, { clientHeight: 100, scrollHeight: 200, scrollTop: 0 })
    Object.defineProperty(log, 'scrollHeight', {
      configurable: true,
      get: () => log.querySelectorAll('article').length * 100,
    })

    fireEvent.scroll(log)

    await screen.findByText('oldest')
    // 300 now, 200 before: what was under the reader's eye is still under it.
    expect(log.scrollTop).toBe(100)
    // Only the thread's own requests: the panel also fetches member names.
    expect(
      requests()
        .filter((r) => r.url.pathname.endsWith('/thread'))
        .map((r) => r.url.searchParams.get('cursor')),
    ).toEqual([null, 'older'])
  })

  it('your own reply scrolls to the bottom from far up', async () => {
    messaging.get(THREAD, aThreadPage(root, [reply({ body: 'already here' })]))
    const { queryClient } = renderPanel()
    await screen.findByText('already here')
    const log = scroller()
    giveLayout(log, { clientHeight: 300, scrollHeight: 2000, scrollTop: 0 })
    fireEvent.scroll(log)

    arrives(queryClient, reply({ authorId: ADA, body: 'my reply' }))

    await screen.findByText('my reply')
    expect(log.scrollTop).toBe(2000)
  })

  it('someone else’s reply scrolls at a 79px gap', async () => {
    messaging.get(THREAD, aThreadPage(root, [reply({ body: 'already here' })]))
    const { queryClient } = renderPanel()
    await screen.findByText('already here')
    const log = scroller()
    // 1000 − 421 − 500 = 79 below the viewport.
    giveLayout(log, { clientHeight: 500, scrollHeight: 1000, scrollTop: 421 })
    fireEvent.scroll(log)

    arrives(queryClient, reply({ body: 'from grace' }))

    await screen.findByText('from grace')
    expect(log.scrollTop).toBe(1000)
  })

  it('…and not at 80px', async () => {
    messaging.get(THREAD, aThreadPage(root, [reply({ body: 'already here' })]))
    const { queryClient } = renderPanel()
    await screen.findByText('already here')
    const log = scroller()
    // 1000 − 420 − 500 = 80: on the threshold, which is not within it.
    giveLayout(log, { clientHeight: 500, scrollHeight: 1000, scrollTop: 420 })
    fireEvent.scroll(log)

    arrives(queryClient, reply({ body: 'from grace' }))

    await screen.findByText('from grace')
    expect(log.scrollTop).toBe(420)
  })
})

describe('ThreadPanel — the channel’s read state', () => {
  it('a reply leaves the channel’s read state alone', async () => {
    messaging.get(THREAD, aThreadPage(root, [reply({ body: 'already here' })]))
    useChatStore.getState().setReadingChannel(CHANNEL)
    const { queryClient, socket } = renderPanel()
    await screen.findByText('already here')

    arrives(queryClient, reply({ body: 'a new reply' }))
    await screen.findByText('a new reply')

    expect(useChatStore.getState().readingChannelId).toBe(CHANNEL)
    expect(socket.emitted.filter((e) => e.event === 'mark_read')).toEqual([])
  })
})

describe('ThreadPanel — a thread that is not there', () => {
  const NOTICE = "This thread isn't available."

  it('a 404 shows the notice', async () => {
    messaging.problem('get', THREAD, 404, { title: 'Not Found', detail: 'No such channel.' })

    renderPanel()

    expect(await screen.findByText(NOTICE)).toBeInTheDocument()
  })

  it('a reply id (404) shows the notice', async () => {
    messaging.problem('get', THREAD, 404, { title: 'Not Found', detail: 'No such thread.' })

    renderPanel()

    expect(await screen.findByText(NOTICE)).toBeInTheDocument()
  })

  it('a root from another channel shows the notice', async () => {
    const foreign = { ...root, channelId: 'channel-elsewhere' }
    messaging.get(THREAD, aThreadPage(foreign, [reply({ body: 'a foreign reply' })]))
    const first = renderPanel({ channelId: 'channel-elsewhere' })
    // The positive half: the same thread under its own channel shows the root.
    await screen.findByText('who is on call tonight?')
    first.unmount()

    renderPanel({ channelId: CHANNEL })

    expect(await screen.findByText(NOTICE)).toBeInTheDocument()
    expect(screen.queryByText('who is on call tonight?')).not.toBeInTheDocument()
    expect(screen.queryByText('a foreign reply')).not.toBeInTheDocument()
  })

  it('a failed refetch keeps the loaded thread', async () => {
    // Decision 23: with data in hand, a background failure is not "unavailable".
    messaging.get(THREAD, aThreadPage(root, [reply({ body: 'already here' })]))
    const { queryClient } = renderPanel()
    await screen.findByText('already here')
    messaging.problem('get', THREAD, 500, { title: 'Internal Server Error' })

    await act(() => queryClient.invalidateQueries({ queryKey: key }))
    // `retry: false` in the test client: the 500 is an error state at once.
    await vi.waitFor(() => expect(queryClient.getQueryState(key)?.status).toBe('error'))
    // The cache reads `error` before React re-renders: let the render happen, so the
    // "no notice" check below is made after a wrong build's notice could have appeared.
    await act(() => new Promise((resolve) => setTimeout(resolve, 100)))

    expect(screen.getByText('already here')).toBeInTheDocument()
    expect(screen.queryByText(NOTICE)).not.toBeInTheDocument()
  })
})

describe('ThreadPanel — a deleted root', () => {
  it('shows the tombstone and the composer still sends', async () => {
    messaging.get(THREAD, aThreadPage(root, [reply({ body: 'already here' })]))
    const { queryClient, socket, user } = renderPanel()
    await screen.findByText('already here')
    socket.onEmit('send_message', () => new Promise(() => undefined))

    arrives(queryClient, { ...root, body: '', deletedAt: '2026-09-15T11:00:00Z' })

    expect(await screen.findByText('This message was deleted.')).toBeInTheDocument()
    await user.type(screen.getByRole('textbox', { name: 'Reply' }), 'still here{Enter}')
    expect(socket.emitted.filter((e) => e.event === 'send_message')).toEqual([
      {
        event: 'send_message',
        args: [{ channelId: CHANNEL, body: 'still here', threadRootId: root.id }],
      },
    ])
  })
})
