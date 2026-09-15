import { screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { Channel, ChannelPage } from '../../lib/api/messaging'
import { messaging, requests } from '../../test/api'
import { aChannel, WORKSPACE_ID } from '../../test/factories'
import { createTestQueryClient, renderWithProviders } from '../../test/render'
import { ChannelHeader } from './ChannelHeader'
import { channelKeys } from './useChannels'

function renderHeader(channel: Channel) {
  const queryClient = createTestQueryClient()
  queryClient.setQueryData<ChannelPage>(channelKeys.list(WORKSPACE_ID), {
    items: [channel],
    nextCursor: null,
  })
  queryClient.setQueryData<Channel>(channelKeys.detail(WORKSPACE_ID, channel.id), channel)
  const view = renderWithProviders(
    <ChannelHeader accessToken="token" workspaceId={WORKSPACE_ID} channel={channel} />,
    { queryClient, route: `/c/${channel.id}` },
  )
  return { ...view, queryClient }
}

describe('ChannelHeader', () => {
  it('lets a channel admin rename the channel', async () => {
    const channel = aChannel({ name: 'general', myRole: 'admin', version: 3 })
    messaging.patch('/api/v1/channels/{channel_id}', ({ body }) => ({
      ...channel,
      name: body.name ?? channel.name,
      version: 4,
    }))
    const { user, queryClient } = renderHeader(channel)

    await user.click(screen.getByRole('button', { name: 'Rename' }))
    const input = screen.getByRole('textbox', { name: 'Channel name' })
    expect(input).toHaveValue('general')
    await user.clear(input)
    await user.type(input, 'general-chat')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    // The form closes, and both places that show the name are told to refetch.
    await vi.waitFor(() =>
      expect(screen.queryByRole('textbox', { name: 'Channel name' })).not.toBeInTheDocument(),
    )
    expect(requests().map((r) => r.body)).toEqual([{ version: 3, name: 'general-chat' }])
    expect(queryClient.getQueryState(channelKeys.list(WORKSPACE_ID))?.isInvalidated).toBe(true)
    expect(
      queryClient.getQueryState(channelKeys.detail(WORKSPACE_ID, channel.id))?.isInvalidated,
    ).toBe(true)
  })

  it('shows a refused name against the rename field', async () => {
    const channel = aChannel({ name: 'general', myRole: 'admin' })
    messaging.problem('patch', '/api/v1/channels/{channel_id}', 400, {
      title: 'Validation error',
      detail: 'A channel name must start with a letter.',
      errors: { name: ['A channel name must start with a letter.'] },
    })
    const { user } = renderHeader(channel)

    await user.click(screen.getByRole('button', { name: 'Rename' }))
    const input = screen.getByRole('textbox', { name: 'Channel name' })
    await user.clear(input)
    await user.type(input, '1general')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'A channel name must start with a letter.',
    )
    expect(input).toBeInTheDocument()
  })

  it('asks before archiving, and a cancel sends nothing', async () => {
    const channel = aChannel({ name: 'general', myRole: 'admin' })
    const { user } = renderHeader(channel)

    await user.click(screen.getByRole('button', { name: 'Archive' }))
    expect(screen.getByText('Archive #general? Nobody will be able to open it again.')).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(screen.queryByText(/Nobody will be able to open it again/)).not.toBeInTheDocument()
    expect(requests()).toEqual([])
  })

  it.each([
    ['a member', 'member'],
    ['someone who never joined', null],
  ])('offers %s no channel controls', (_, myRole) => {
    renderHeader(aChannel({ name: 'general', myRole }))

    expect(screen.getByRole('heading', { name: /general/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Rename' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Archive' })).not.toBeInTheDocument()
  })
})
