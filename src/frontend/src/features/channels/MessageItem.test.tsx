/**
 * What a message row shows, and what it offers. Hiding a control is a courtesy
 * and not authorization — `check_editable` and `check_deletable` are the rules,
 * unit-tested in Messaging — so these tests are about the offer.
 *
 * Every action sits behind the row's "⋯" menu button (gh-8): the menu is in a
 * portal, so its items are found with `screen`, never `within(row)`.
 */

import { screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { Message } from '../../lib/api/messaging'
import { aMessage } from '../../test/factories'
import { renderWithProviders } from '../../test/render'
import { MessageItem } from './MessageItem'

const ADA = '0199a000-0000-7000-8000-00000000000a'
const GRACE = '0199a000-0000-7000-8000-00000000000b'

function itemElement(
  message: Message,
  viewer: { userId?: string; myRole?: string | null } = {},
  handlers: { onEdit?: () => void; onDelete?: () => void; onOpenThread?: () => void } = {},
) {
  return (
    <MessageItem
      key={message.id}
      message={message}
      authorName="Ada Lovelace"
      userId={viewer.userId ?? ADA}
      myRole={viewer.myRole ?? null}
      editError={undefined}
      editPending={false}
      onEdit={handlers.onEdit ?? vi.fn()}
      onDelete={handlers.onDelete ?? vi.fn()}
      onToggleReaction={vi.fn()}
      onOpenThread={handlers.onOpenThread}
    />
  )
}

function renderItem(
  message: Message,
  viewer: { userId?: string; myRole?: string | null } = {},
  options: { onOpenThread?: () => void } = {},
) {
  const onEdit = vi.fn()
  const onDelete = vi.fn()
  const view = renderWithProviders(itemElement(message, viewer, { onEdit, onDelete, ...options }))
  return { ...view, onEdit, onDelete }
}

const actions = (row?: HTMLElement) =>
  (row ? within(row) : screen).getByRole('button', { name: 'Message actions' })
const items = () => screen.getAllByRole('menuitem').map((e) => e.textContent?.trim())
const menus = () => screen.queryAllByRole('menu')

describe('MessageItem', () => {
  it('shows its author and the time it was sent', () => {
    const message = aMessage({
      authorId: ADA,
      body: 'the eagle has landed',
      createdAt: '2026-09-15T09:30:00Z',
    })

    renderItem(message)

    expect(screen.getByText('Ada Lovelace')).toBeInTheDocument()
    expect(screen.getByText('the eagle has landed')).toBeInTheDocument()
    const shown = new Date(message.createdAt).toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
    })
    expect(screen.getByText(shown).closest('time')).toHaveAttribute('dateTime', message.createdAt)
  })

  it('marks a message that has been edited', () => {
    renderItem(aMessage({ authorId: ADA, editedAt: '2026-09-15T09:31:00Z' }))

    expect(screen.getByText('(edited)')).toBeInTheDocument()
  })

  it('does not mark a message nobody edited', () => {
    renderItem(aMessage({ authorId: ADA }))

    expect(screen.queryByText('(edited)')).not.toBeInTheDocument()
  })
})

describe('MessageItem — the "⋯" menu', () => {
  it('has no hover-revealed row: before "⋯" is pressed no React, Reply, Edit or Delete control is in the document; after, Edit is a menuitem', async () => {
    const { user } = renderItem(aMessage({ authorId: ADA }), {}, { onOpenThread: vi.fn() })

    // jsdom ignores `opacity-0`, so a row hidden by CSS is still in the DOM: it must not be.
    expect(
      screen.queryAllByRole('button', { name: /^(Add a reaction|React|Reply in thread|Edit|Delete)$/ }),
    ).toHaveLength(0)
    expect(screen.queryAllByRole('menuitem')).toHaveLength(0)

    await user.click(actions())

    expect(screen.getByRole('menuitem', { name: 'Edit' })).toBeInTheDocument()
  })

  it('your own message’s "⋯" offers React, Reply in thread, Edit, Delete', async () => {
    const { user } = renderItem(aMessage({ authorId: ADA }), { userId: ADA, myRole: 'member' }, {
      onOpenThread: vi.fn(),
    })

    await user.click(actions())

    expect(items()).toEqual(['React', 'Reply in thread', 'Edit', 'Delete'])
  })

  it('"⋯" on Grace’s message offers React and Reply in thread only', async () => {
    const { user } = renderItem(aMessage({ authorId: GRACE, body: 'shipping this afternoon' }), {
      userId: ADA,
      myRole: 'member',
    }, { onOpenThread: vi.fn() })

    await user.click(actions())

    expect(items()).toEqual(['React', 'Reply in thread'])
  })

  it('a channel admin’s "⋯" on someone else’s message offers Delete, never Edit', async () => {
    const { user } = renderItem(aMessage({ authorId: GRACE }), { userId: ADA, myRole: 'admin' })

    await user.click(actions())

    expect(items()).toEqual(['React', 'Delete'])
  })

  it('a tombstone has no "⋯" — the live message beside it does', () => {
    renderWithProviders(
      <>
        {itemElement(aMessage({ authorId: ADA, body: 'still here' }), { myRole: 'admin' })}
        {itemElement(
          aMessage({
            authorId: ADA,
            body: '',
            editedAt: '2026-09-15T09:31:00Z',
            deletedAt: '2026-09-15T09:32:00Z',
          }),
          { myRole: 'admin' },
        )}
      </>,
    )
    const [live, tombstone] = screen.getAllByRole('article')

    expect(actions(live)).toBeInTheDocument()
    expect(within(tombstone).getByText('This message was deleted.')).toBeInTheDocument()
    expect(within(tombstone).queryByText('(edited)')).not.toBeInTheDocument()
    expect(
      within(tombstone).queryByRole('button', { name: 'Message actions' }),
    ).not.toBeInTheDocument()
  })

  it('a pending message has no "⋯" — the confirmed one beside it does', () => {
    renderWithProviders(
      <>
        {itemElement(aMessage({ authorId: ADA, body: 'delivered' }))}
        {itemElement(aMessage({ id: 'temp:1234', authorId: ADA, body: 'lunch is at one' }))}
      </>,
    )
    const [confirmed, pending] = screen.getAllByRole('article')

    expect(actions(confirmed)).toBeInTheDocument()
    expect(within(pending).getByText('lunch is at one')).toBeInTheDocument()
    expect(within(pending).queryByRole('button', { name: 'Message actions' })).not.toBeInTheDocument()
  })

  it('choosing Edit closes the menu and puts focus in the editor', async () => {
    const { user } = renderItem(aMessage({ authorId: ADA }))
    await user.click(actions())

    await user.click(screen.getByRole('menuitem', { name: 'Edit' }))

    expect(menus()).toHaveLength(0)
    expect(screen.getByRole('textbox', { name: 'Edit message' })).toHaveFocus()
  })

  it('editing through the menu sends the version it holds; after Enter, focus is on "⋯" and no menu is open', async () => {
    const message = aMessage({ authorId: ADA, body: 'teh plan', version: 2 })
    const { user, onEdit } = renderItem(message)
    await user.click(actions())
    await user.click(screen.getByRole('menuitem', { name: 'Edit' }))

    const input = screen.getByRole('textbox', { name: 'Edit message' })
    await user.clear(input)
    await user.type(input, 'the plan{Enter}')

    expect(onEdit).toHaveBeenCalledExactlyOnceWith('the plan', 2)
    expect(screen.queryByRole('textbox', { name: 'Edit message' })).not.toBeInTheDocument()
    expect(actions()).toHaveFocus()
    expect(menus()).toHaveLength(0)
  })

  it('Escape in the editor cancels; focus returns to "⋯" and the menu stays shut', async () => {
    const { user, onEdit } = renderItem(aMessage({ authorId: ADA, body: 'as it was' }))
    await user.click(actions())
    await user.click(screen.getByRole('menuitem', { name: 'Edit' }))
    expect(screen.getByRole('textbox', { name: 'Edit message' })).toHaveFocus()

    await user.keyboard('{Escape}')

    expect(screen.queryByRole('textbox', { name: 'Edit message' })).not.toBeInTheDocument()
    expect(screen.getByText('as it was')).toBeInTheDocument()
    expect(onEdit).not.toHaveBeenCalled()
    expect(actions()).toHaveFocus()
    expect(menus()).toHaveLength(0)
  })

  it('Delete in the menu asks for a delete once', async () => {
    const { user, onDelete } = renderItem(aMessage({ authorId: ADA }))
    await user.click(actions())

    await user.click(screen.getByRole('menuitem', { name: 'Delete' }))

    expect(onDelete).toHaveBeenCalledOnce()
  })

  it('keyboard only: Tab reaches "⋯", Enter opens it, ArrowDown reaches Reply in thread, Enter opens the thread', async () => {
    const onOpenThread = vi.fn()
    const { user } = renderItem(aMessage({ authorId: GRACE }), {}, { onOpenThread })

    await user.tab()
    expect(screen.getByRole('button', { name: 'Message actions' })).toHaveFocus()
    await user.keyboard('{Enter}')
    expect(screen.getByRole('menuitem', { name: 'React' })).toHaveFocus()
    await user.keyboard('{ArrowDown}')
    expect(screen.getByRole('menuitem', { name: 'Reply in thread' })).toHaveFocus()
    await user.keyboard('{Enter}')

    expect(onOpenThread).toHaveBeenCalledOnce()
  })
})
