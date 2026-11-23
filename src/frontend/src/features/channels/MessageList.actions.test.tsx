/**
 * The "⋯" menu through the real message list (gh-8 *A live delete and an open
 * menu*, *Paths: pending, then confirmed*): the cache changes under an open menu
 * exactly as a socket event or a send changes it, through `upsertMessage` and
 * `removeMessage`.
 *
 * Every "no menu" assertion comes after the menu was found open, so it cannot
 * pass for a build that never opens one.
 */

import type { QueryClient } from '@tanstack/react-query'
import { act, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { Message } from '../../lib/api/messaging'
import { auth, messaging } from '../../test/api'
import { aMessage, aMessagePage, aWorkspaceMember, WORKSPACE_ID } from '../../test/factories'
import { renderWithProviders } from '../../test/render'
import { MessageList } from './MessageList'
import { messageKeys, removeMessage, upsertMessage } from './useMessages'

const CHANNEL = 'channel-general'
const ADA = 'user-ada'
const GRACE = 'user-grace'

const fromGrace = aMessage({
  channelId: CHANNEL,
  authorId: GRACE,
  body: 'a message from Grace',
  version: 1,
})

function list(myRole: string | null) {
  return (
    <MessageList
      accessToken="token"
      workspaceId={WORKSPACE_ID}
      channelId={CHANNEL}
      userId={ADA}
      myRole={myRole}
      lastReadId={null}
      channelFetching={false}
    />
  )
}

async function renderList(myRole: string | null = 'admin', history: Message[] = [fromGrace]) {
  auth.members([
    aWorkspaceMember({ id: ADA, displayName: 'Ada Lovelace' }),
    aWorkspaceMember({ id: GRACE, displayName: 'Grace Hopper' }),
  ])
  messaging.get('/api/v1/channels/{channel_id}/messages', aMessagePage(history))
  const view = renderWithProviders(list(myRole))
  await screen.findByText(history[0].body)
  return view
}

const key = messageKeys.list(WORKSPACE_ID, CHANNEL)
const lands = (queryClient: QueryClient, message: Message) =>
  act(() => upsertMessage(queryClient, key, message))
const rowOf = (body: string) => screen.getByText(body).closest('article') as HTMLElement
const opener = (row: HTMLElement) => within(row).getByRole('button', { name: 'Message actions' })
const menus = () => screen.queryAllByRole('menu')
/** The message list's own scroller: the one element whose child is the article. */
const scroller = () => screen.getAllByRole('article')[0].parentElement as HTMLElement

describe('MessageList — the "⋯" menu under live changes', () => {
  it('Grace’s delete lands while Ada’s menu is open: the tombstone has no "⋯", no menu is open, and focus is on the message list, not the body', async () => {
    const { user, queryClient } = await renderList('admin')
    await user.click(opener(rowOf('a message from Grace')))
    expect(screen.getByRole('menuitem', { name: 'Delete' })).toBeInTheDocument()

    lands(queryClient, {
      ...fromGrace,
      body: '',
      deletedAt: '2026-09-15T09:32:00Z',
      version: 2,
    })

    expect(await screen.findByText('This message was deleted.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Message actions' })).not.toBeInTheDocument()
    expect(menus()).toHaveLength(0)
    expect(document.activeElement).toBe(scroller())
    expect(document.activeElement).not.toBe(document.body)
  })

  it('Ada’s admin role ends while her menu offers Delete: the menu closes and focus is on that message’s "⋯"', async () => {
    const view = await renderList('admin')
    await view.user.click(opener(rowOf('a message from Grace')))
    expect(screen.getByRole('menuitem', { name: 'Delete' })).toBeInTheDocument()

    view.rerender(list(null))

    expect(menus()).toHaveLength(0)
    expect(opener(rowOf('a message from Grace'))).toHaveFocus()
  })

  it('a live reaction, then a live edit, to the message leave its open menu open, focus on the item it was on', async () => {
    const { user, queryClient } = await renderList('admin')
    await user.click(opener(rowOf('a message from Grace')))
    await user.keyboard('{ArrowDown}')
    const onDelete = screen.getByRole('menuitem', { name: 'Delete' })
    expect(onDelete).toHaveFocus()

    lands(queryClient, {
      ...fromGrace,
      reactions: [{ emoji: 'tada', count: 1, reacted: false }],
      version: 2,
    })

    expect(screen.getAllByRole('menu')).toHaveLength(1)
    expect(screen.getByRole('menuitem', { name: 'Delete' })).toHaveFocus()

    lands(queryClient, {
      ...fromGrace,
      body: 'a message from Grace, corrected',
      editedAt: '2026-09-15T09:33:00Z',
      reactions: [{ emoji: 'tada', count: 1, reacted: false }],
      version: 3,
    })

    expect(await screen.findByText('a message from Grace, corrected')).toBeInTheDocument()
    expect(screen.getAllByRole('menu')).toHaveLength(1)
    expect(screen.getByRole('menuitem', { name: 'Delete' })).toHaveFocus()
  })

  it('a pending message has no "⋯"; once confirmed, it does', async () => {
    const { queryClient } = await renderList('member')
    const pending = aMessage({
      id: 'temp:42',
      channelId: CHANNEL,
      authorId: ADA,
      body: 'on its way',
    })

    lands(queryClient, pending)

    const pendingRow = await screen.findByText('on its way').then((e) => e.closest('article') as HTMLElement)
    // The positive half: the confirmed message beside it has one.
    expect(opener(rowOf('a message from Grace'))).toBeInTheDocument()
    expect(
      within(pendingRow).queryByRole('button', { name: 'Message actions' }),
    ).not.toBeInTheDocument()

    act(() => removeMessage(queryClient, key, 'temp:42'))
    lands(queryClient, { ...pending, id: 'real-42' })

    await screen.findByText('on its way')
    expect(opener(rowOf('on its way'))).toBeInTheDocument()
  })
})
