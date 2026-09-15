/**
 * The composer checks nothing itself (doc 06 §8): a blank or over-long message
 * goes to the server, comes back refused, and is rolled back with the reason
 * shown. The body rules are unit-tested in Messaging's `test_message_body.py`.
 */

import { act, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { useChatStore } from '../../stores/chat'
import { auth } from '../../test/api'
import { aWorkspaceMember, WORKSPACE_ID } from '../../test/factories'
import { renderWithProviders } from '../../test/render'
import { FakeSocket } from '../../test/socket'
import { MessageComposer } from './MessageComposer'

const CHANNEL = 'channel-general'
const ADA = 'user-ada'
const GRACE = 'user-grace'

function refusal(reason: string) {
  return {
    ok: false,
    problem: { status: 400, title: 'Validation error', detail: reason, errors: { body: [reason] } },
  }
}

function renderComposer({ connected = true } = {}) {
  auth.members([
    aWorkspaceMember({ id: ADA, displayName: 'Ada Lovelace' }),
    aWorkspaceMember({ id: GRACE, displayName: 'Grace Hopper' }),
  ])
  useChatStore.getState().setConnectionStatus(connected ? 'connected' : 'disconnected')
  const socket = new FakeSocket('token')
  const view = renderWithProviders(
    <MessageComposer
      accessToken="token"
      workspaceId={WORKSPACE_ID}
      channelId={CHANNEL}
      channelName="general"
      userId={ADA}
    />,
    { socket },
  )
  return { ...view, socket, input: screen.getByRole('textbox', { name: 'Message #general' }) }
}

const sends = (socket: FakeSocket) => socket.emitted.filter((e) => e.event === 'send_message')

describe('MessageComposer', () => {
  it('sends nothing when the box is empty', async () => {
    const { user, socket, input } = renderComposer()

    await user.click(input)
    await user.keyboard('{Enter}')

    expect(sends(socket)).toEqual([])
  })

  it('does not keep a message of nothing but spaces, and says why', async () => {
    const { user, socket, input } = renderComposer()
    socket.onEmit('send_message', () => refusal('A message cannot be empty.'))

    await user.type(input, '   {Enter}')

    expect(await screen.findByRole('alert')).toHaveTextContent('A message cannot be empty.')
    expect(input).toHaveValue('   ')
  })

  it('rejects a message over 8000 characters with the reason, and keeps the text', async () => {
    const { user, socket, input } = renderComposer()
    socket.onEmit('send_message', () => refusal('A message must be 8000 characters or fewer.'))
    const long = 'a'.repeat(8001)

    await user.click(input)
    await user.paste(long)
    await user.keyboard('{Enter}')

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'A message must be 8000 characters or fewer.',
    )
    // No client-side limit: the whole text went to the server.
    expect(sends(socket)).toEqual([
      { event: 'send_message', args: [{ channelId: CHANNEL, body: long }] },
    ])
    expect(input).toHaveValue(long)
  })

  it('empties the box the moment a message is sent', async () => {
    const { user, socket, input } = renderComposer()
    socket.onEmit('send_message', () => new Promise(() => undefined))

    await user.type(input, 'lunch is at one{Enter}')

    expect(input).toHaveValue('')
    expect(sends(socket)).toHaveLength(1)
  })

  it('breaks a line on Shift+Enter instead of sending', async () => {
    const { user, socket, input } = renderComposer()

    await user.type(input, 'first{Shift>}{Enter}{/Shift}second')

    expect(input).toHaveValue('first\nsecond')
    expect(sends(socket)).toEqual([])
  })

  it('is disabled, and says so, while the connection is down', () => {
    const { input } = renderComposer({ connected: false })

    expect(input).toBeDisabled()
    expect(
      screen.getByText('Not connected — messages cannot be sent until the connection is back.'),
    ).toBeInTheDocument()
  })

  it('shows who is typing, by name', async () => {
    const { socket } = renderComposer()

    act(() => socket.serverEmit('user_typing', { channelId: CHANNEL, userId: GRACE }))

    expect(await screen.findByText('Grace Hopper is typing…')).toBeInTheDocument()
  })
})
