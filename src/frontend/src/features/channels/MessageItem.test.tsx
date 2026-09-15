/**
 * What a message row shows, and what it offers. Hiding a control is a courtesy
 * and not authorization — `check_editable` and `check_deletable` are the rules,
 * unit-tested in Messaging — so these tests are about the offer.
 */

import { screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { Message } from '../../lib/api/messaging'
import { aMessage } from '../../test/factories'
import { renderWithProviders } from '../../test/render'
import { MessageItem } from './MessageItem'

const ADA = '0199a000-0000-7000-8000-00000000000a'
const GRACE = '0199a000-0000-7000-8000-00000000000b'

function renderItem(message: Message, viewer: { userId?: string; myRole?: string | null } = {}) {
  const onEdit = vi.fn()
  const onDelete = vi.fn()
  const view = renderWithProviders(
    <MessageItem
      message={message}
      authorName="Ada Lovelace"
      userId={viewer.userId ?? ADA}
      myRole={viewer.myRole ?? null}
      editError={undefined}
      editPending={false}
      onEdit={onEdit}
      onDelete={onDelete}
    />,
  )
  return { ...view, onEdit, onDelete }
}

const edit = () => screen.queryByRole('button', { name: 'Edit' })
const remove = () => screen.queryByRole('button', { name: 'Delete' })

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

  it('offers the author both edit and delete', () => {
    renderItem(aMessage({ authorId: ADA }), { userId: ADA, myRole: 'member' })

    expect(edit()).toBeInTheDocument()
    expect(remove()).toBeInTheDocument()
  })

  it('offers Ada no way to edit or delete Grace’s message', () => {
    renderItem(aMessage({ authorId: GRACE, body: 'shipping this afternoon' }), {
      userId: ADA,
      myRole: 'member',
    })

    expect(screen.getByText('shipping this afternoon')).toBeInTheDocument()
    expect(edit()).not.toBeInTheDocument()
    expect(remove()).not.toBeInTheDocument()
  })

  it('offers a channel admin delete, but never edit, on someone else’s message', () => {
    renderItem(aMessage({ authorId: GRACE }), { userId: ADA, myRole: 'admin' })

    expect(remove()).toBeInTheDocument()
    expect(edit()).not.toBeInTheDocument()
  })

  it('renders a deleted message as a tombstone with nothing to act on', () => {
    renderItem(
      aMessage({
        authorId: ADA,
        body: '',
        editedAt: '2026-09-15T09:31:00Z',
        deletedAt: '2026-09-15T09:32:00Z',
      }),
      { userId: ADA, myRole: 'admin' },
    )

    expect(screen.getByText('This message was deleted.')).toBeInTheDocument()
    expect(screen.queryByText('(edited)')).not.toBeInTheDocument()
    expect(edit()).not.toBeInTheDocument()
    expect(remove()).not.toBeInTheDocument()
  })

  it('offers nothing on a message the server has not confirmed yet', () => {
    renderItem(aMessage({ id: 'temp:1234', authorId: ADA, body: 'lunch is at one' }))

    expect(screen.getByText('lunch is at one')).toBeInTheDocument()
    expect(edit()).not.toBeInTheDocument()
    expect(remove()).not.toBeInTheDocument()
  })

  it('edits in place, sending the version it holds', async () => {
    const message = aMessage({ authorId: ADA, body: 'teh plan', version: 2 })
    const { user, onEdit } = renderItem(message)

    await user.click(screen.getByRole('button', { name: 'Edit' }))
    const input = screen.getByRole('textbox', { name: 'Edit message' })
    await user.clear(input)
    await user.type(input, 'the plan{Enter}')

    expect(onEdit).toHaveBeenCalledWith('the plan', 2)
  })

  it('asks for a delete when Delete is pressed', async () => {
    const { user, onDelete } = renderItem(aMessage({ authorId: ADA }))

    await user.click(screen.getByRole('button', { name: 'Delete' }))

    expect(onDelete).toHaveBeenCalledOnce()
  })
})
