import { screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { Channel } from '../../lib/api/messaging'
import { messaging } from '../../test/api'
import { aChannel, WORKSPACE_ID } from '../../test/factories'
import { renderWithProviders } from '../../test/render'
import { ChannelHeader } from './ChannelHeader'
import { ChannelList } from './ChannelList'

describe('ChannelList', () => {
  it('links to every channel the server returns, in its order', async () => {
    const general = aChannel({ name: 'general' })
    const random = aChannel({ name: 'random' })
    messaging.get('/api/v1/channels', { items: [general, random], nextCursor: null })

    renderWithProviders(<ChannelList accessToken="token" workspaceId={WORKSPACE_ID} />)

    const links = await screen.findAllByRole('link')
    expect(links.map((link) => link.textContent?.replace('#', '').trim())).toEqual([
      'general',
      'random',
    ])
    expect(links[1]).toHaveAttribute('href', `/c/${random.id}`)
  })

  it('invites the first channel when there are none', async () => {
    messaging.get('/api/v1/channels', { items: [], nextCursor: null })

    renderWithProviders(<ChannelList accessToken="token" workspaceId={WORKSPACE_ID} />)

    expect(await screen.findByText('No channels yet. Create the first one.')).toBeInTheDocument()
  })

  it('drops a channel an admin archives, and leaves its page', async () => {
    const general = aChannel({ name: 'general' })
    const random = aChannel({ name: 'random', myRole: 'admin' })
    let channels: Channel[] = [general, random]
    messaging.get('/api/v1/channels', () => ({ items: channels, nextCursor: null }))
    messaging.delete('/api/v1/channels/{channel_id}', ({ params }) => {
      channels = channels.filter((c) => c.id !== params.channel_id)
      return { ...random, archivedAt: '2026-09-15T10:00:00Z' }
    })
    const { user, location } = renderWithProviders(
      <>
        <ChannelList accessToken="token" workspaceId={WORKSPACE_ID} />
        <ChannelHeader accessToken="token" workspaceId={WORKSPACE_ID} channel={random} />
      </>,
      { route: `/c/${random.id}` },
    )
    expect(await screen.findByRole('link', { name: 'random' })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Archive' }))
    const confirm = screen.getByText(/Nobody will be able to open it again/).parentElement
    await user.click(within(confirm as HTMLElement).getByRole('button', { name: 'Archive' }))

    await vi.waitFor(() =>
      expect(screen.queryByRole('link', { name: 'random' })).not.toBeInTheDocument(),
    )
    expect(screen.getByRole('link', { name: 'general' })).toBeInTheDocument()
    expect(location().pathname).toBe('/')
  })
})
