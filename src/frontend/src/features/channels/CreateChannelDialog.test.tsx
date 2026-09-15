/**
 * The dialog restates none of the naming rules — the server owns them — so what
 * is tested here is that each rule's reason reaches the user where they will
 * read it, and that a created channel is where the user lands. The rules
 * themselves are unit-tested in Messaging's `test_channel_rules.py`.
 */

import { screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { Channel } from '../../lib/api/messaging'
import { messaging, requests } from '../../test/api'
import { aChannel, aSession, WORKSPACE_ID } from '../../test/factories'
import { renderWithProviders } from '../../test/render'
import { ChatLayout } from './ChatLayout'
import { CreateChannelDialog } from './CreateChannelDialog'

function renderDialog() {
  const onCreated = vi.fn()
  const view = renderWithProviders(
    <CreateChannelDialog accessToken="token" workspaceId={WORKSPACE_ID} onCreated={onCreated} />,
  )
  return { ...view, onCreated }
}

describe('CreateChannelDialog', () => {
  it.each([
    ['a blank name', '', 'A channel name is required.'],
    ['a name that is too short', 'ab', 'A channel name must be at least 3 characters.'],
    ['a name over 80 characters', 'a'.repeat(81), 'A channel name must be 80 characters or fewer.'],
    ['a name starting with a digit', '1password', 'A channel name must start with a letter.'],
    ['a name starting with a hyphen', '-general', 'A channel name must start with a letter.'],
    [
      'a name with a space',
      'dev team',
      'A channel name can only use letters, numbers and hyphens.',
    ],
    [
      'a name with an underscore',
      'dev_team',
      'A channel name can only use letters, numbers and hyphens.',
    ],
    [
      'a name with an accent',
      'général',
      'A channel name can only use letters, numbers and hyphens.',
    ],
  ])('shows the server’s reason for %s against the name field', async (_, typed, reason) => {
    messaging.problem('post', '/api/v1/channels', 400, {
      title: 'Validation error',
      detail: reason,
      errors: { name: [reason] },
    })
    const { user, onCreated } = renderDialog()

    if (typed) await user.type(screen.getByLabelText('New channel'), typed)
    await user.click(screen.getByRole('button', { name: 'Create' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(reason)
    // Sent as typed: the form does not pre-judge a name the server would take.
    expect(requests().map((r) => r.body)).toEqual([{ name: typed, kind: 'public' }])
    expect(onCreated).not.toHaveBeenCalled()
  })

  it('shows a name already in use, whatever its case, in the banner', async () => {
    messaging.problem('post', '/api/v1/channels', 409, {
      title: 'Conflict',
      detail: 'A channel with that name already exists in this workspace.',
    })
    const { user, onCreated } = renderDialog()

    await user.type(screen.getByLabelText('New channel'), 'GENERAL')
    await user.click(screen.getByRole('button', { name: 'Create' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'A channel with that name already exists in this workspace.',
    )
    expect(onCreated).not.toHaveBeenCalled()
  })

  it('asks for a private channel when one is chosen', async () => {
    const created = aChannel({ name: 'secret-plans', kind: 'private' })
    messaging.post('/api/v1/channels', created)
    const { user, onCreated } = renderDialog()

    await user.selectOptions(screen.getByLabelText('Channel visibility'), 'private')
    await user.type(screen.getByLabelText('New channel'), 'secret-plans')
    await user.click(screen.getByRole('button', { name: 'Create' }))

    await vi.waitFor(() => expect(onCreated).toHaveBeenCalledWith(created.id))
    expect(requests().find((r) => r.method === 'POST')?.body).toEqual({
      name: 'secret-plans',
      kind: 'private',
    })
  })
})

describe('creating a channel from the chat shell', () => {
  it.each(['general', 'team-42', 'Design-Review'])(
    'creates "%s" and lands the user in it',
    async (name) => {
      const channels: Channel[] = []
      messaging.get('/api/v1/channels', () => ({ items: [...channels], nextCursor: null }))
      messaging.post('/api/v1/channels', ({ body }) => {
        const created = aChannel({ name: body.name, kind: body.kind, myRole: 'admin' })
        channels.push(created)
        return created
      })
      const { user, location } = renderWithProviders(
        <ChatLayout current={aSession()}>
          <p>Pick a channel, or create one.</p>
        </ChatLayout>,
      )

      await user.type(screen.getByLabelText('New channel'), name)
      await user.click(screen.getByRole('button', { name: 'Create' }))

      const link = await screen.findByRole('link', { name })
      await vi.waitFor(() => expect(location().pathname).toBe(`/c/${channels[0].id}`))
      expect(link).toHaveAttribute('href', `/c/${channels[0].id}`)
      expect(screen.getByLabelText('New channel')).toHaveValue('')
      expect(within(screen.getByRole('list')).getAllByRole('link')).toHaveLength(1)
    },
  )
})
