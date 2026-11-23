/**
 * What a message row offers for threads (R1, R4): the "Reply in thread" action and
 * the reply summary.
 *
 * **Every guard here carries its positive.** "Offers no action on X" passes when
 * the prop is ignored altogether, so each such test renders a confirmed top-level
 * message beside the case, both with `onOpenThread`, and finds the action on the
 * confirmed one first.
 */

import { screen, within } from '@testing-library/react'
import type { UserEvent } from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { Message } from '../../lib/api/messaging'
import { aMessage } from '../../test/factories'
import { renderWithProviders } from '../../test/render'
import { MessageItem } from './MessageItem'

const ADA = '0199a000-0000-7000-8000-00000000000a'

function row(message: Message, onOpenThread: (() => void) | undefined) {
  return (
    <MessageItem
      key={message.id}
      message={message}
      authorName="Ada Lovelace"
      userId={ADA}
      myRole={null}
      editError={undefined}
      editPending={false}
      onEdit={vi.fn()}
      onDelete={vi.fn()}
      onToggleReaction={vi.fn()}
      onOpenThread={onOpenThread}
    />
  )
}

/** The confirmed top-level message first, then the case under test. */
function renderBeside(subject: Message) {
  const onOpenThread = vi.fn()
  const confirmed = aMessage({ authorId: ADA, body: 'a confirmed message' })
  const view = renderWithProviders(
    <>
      {row(confirmed, onOpenThread)}
      {row(subject, onOpenThread)}
    </>,
  )
  const [first, second] = screen.getAllByRole('article')
  return { ...view, onOpenThread, confirmed: first, subject: second }
}

/**
 * Open that row's "⋯" and look for Reply in thread. A row with no "⋯" offers
 * nothing, so it answers `null`; every guard below finds the action on the
 * confirmed row first, so `null` cannot come from a build with no menu at all.
 */
async function replyAction(user: UserEvent, within_: HTMLElement) {
  const opener = within(within_).queryByRole('button', { name: 'Message actions' })
  if (!opener) return null
  await user.click(opener)
  return screen.queryByRole('menuitem', { name: 'Reply in thread' })
}

describe('MessageItem — Reply in thread', () => {
  it('a top-level message offers Reply in thread, which opens it', async () => {
    const onOpenThread = vi.fn()
    const { user } = renderWithProviders(row(aMessage({ authorId: ADA }), onOpenThread))

    await user.click(screen.getByRole('button', { name: 'Message actions' }))
    await user.click(screen.getByRole('menuitem', { name: 'Reply in thread' }))

    expect(onOpenThread).toHaveBeenCalledOnce()
  })

  it('none on a pending message', async () => {
    const { user, confirmed, subject } = renderBeside(aMessage({ id: 'temp:1234', authorId: ADA }))

    expect(await replyAction(user, confirmed)).toBeInTheDocument()
    expect(await replyAction(user, subject)).not.toBeInTheDocument()
  })

  it('none on a deleted one', async () => {
    const { user, confirmed, subject } = renderBeside(
      aMessage({ authorId: ADA, body: '', deletedAt: '2026-09-15T09:32:00Z' }),
    )

    expect(await replyAction(user, confirmed)).toBeInTheDocument()
    expect(await replyAction(user, subject)).not.toBeInTheDocument()
  })

  it('none on a reply', async () => {
    const { user, confirmed, subject } = renderBeside(
      aMessage({ authorId: ADA, threadRootId: '0199a000-0000-7000-8000-0000000000aa' }),
    )

    expect(await replyAction(user, confirmed)).toBeInTheDocument()
    // Ada's own reply has a "⋯" (React, Edit, Delete): the menu opens, with no Reply in it.
    expect(within(subject).getByRole('button', { name: 'Message actions' })).toBeInTheDocument()
    expect(await replyAction(user, subject)).not.toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Edit' })).toBeInTheDocument()
  })

  it('without onOpenThread: no summary, no action', async () => {
    const rootWithReplies = aMessage({
      authorId: ADA,
      replyCount: 2,
      lastReplyAt: '2026-09-15T10:00:00Z',
    })
    const { user } = renderWithProviders(
      <>
        {row(rootWithReplies, vi.fn())}
        {row({ ...rootWithReplies, id: 'another-root' }, undefined)}
      </>,
    )
    const [withProp, withoutProp] = screen.getAllByRole('article')

    // The positive half: with the prop, both are there.
    expect(within(withProp).getByText(/2 replies/)).toBeInTheDocument()
    expect(await replyAction(user, withProp)).toBeInTheDocument()

    expect(within(withoutProp).queryByText(/2 replies/)).not.toBeInTheDocument()
    expect(await replyAction(user, withoutProp)).not.toBeInTheDocument()
    // Not null because there is no menu: the row has one, holding React, Edit, Delete.
    expect(screen.getByRole('menuitem', { name: 'Delete' })).toBeInTheDocument()
  })
})

describe('MessageItem — the reply summary', () => {
  it('"1 reply" and "2 replies" with the last time; nothing at 0', () => {
    renderWithProviders(
      <>
        {row(aMessage({ body: 'one', replyCount: 1, lastReplyAt: '2026-09-15T10:00:00Z' }), vi.fn())}
        {row(aMessage({ body: 'two', replyCount: 2, lastReplyAt: '2026-09-15T11:00:00Z' }), vi.fn())}
        {row(aMessage({ body: 'none', replyCount: 0, lastReplyAt: null }), vi.fn())}
      </>,
    )
    const [one, two, none] = screen.getAllByRole('article')

    const oneSummary = within(one).getByRole('button', { name: /^1 reply/ })
    expect(oneSummary.querySelector('time')).toHaveAttribute('dateTime', '2026-09-15T10:00:00Z')
    const twoSummary = within(two).getByRole('button', { name: /^2 replies/ })
    expect(twoSummary.querySelector('time')).toHaveAttribute('dateTime', '2026-09-15T11:00:00Z')
    expect(within(none).queryByRole('button', { name: /repl(y|ies)$/ })).not.toBeInTheDocument()
    expect(within(none).queryByText(/repl(y|ies)/)).not.toBeInTheDocument()
  })

  it('opens the thread when clicked', async () => {
    const onOpenThread = vi.fn()
    const { user } = renderWithProviders(
      row(aMessage({ replyCount: 3, lastReplyAt: '2026-09-15T10:00:00Z' }), onOpenThread),
    )

    await user.click(screen.getByRole('button', { name: /^3 replies/ }))

    expect(onOpenThread).toHaveBeenCalledOnce()
  })

  it('a deleted root shows its summary and it opens the thread', async () => {
    // R10: the summary is the only way into a deleted root's thread.
    const onOpenThread = vi.fn()
    const { user } = renderWithProviders(
      row(
        aMessage({
          authorId: ADA,
          body: '',
          deletedAt: '2026-09-15T09:32:00Z',
          replyCount: 2,
          lastReplyAt: '2026-09-15T10:00:00Z',
        }),
        onOpenThread,
      ),
    )

    expect(screen.getByText('This message was deleted.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /^2 replies/ }))

    expect(onOpenThread).toHaveBeenCalledOnce()
  })
})
