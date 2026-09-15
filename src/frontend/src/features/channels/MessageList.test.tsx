import { fireEvent, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { auth, messaging, requests } from '../../test/api'
import { aMessage, aMessagePage, aWorkspaceMember, WORKSPACE_ID } from '../../test/factories'
import { renderWithProviders } from '../../test/render'
import { MessageList } from './MessageList'

const CHANNEL = 'channel-general'
const ADA = 'user-ada'

const oldest = aMessage({ channelId: CHANNEL, authorId: ADA, body: 'the first message' })
const middle = aMessage({ channelId: CHANNEL, authorId: ADA, body: 'the second message' })
const newest = aMessage({ channelId: CHANNEL, authorId: ADA, body: 'the latest message' })

/** Two pages, newest first on the wire, the way Messaging serves them. */
function stubHistory() {
  messaging.get('/api/v1/channels/{channel_id}/messages', ({ request }) =>
    new URL(request.url).searchParams.get('cursor') === 'older'
      ? aMessagePage([oldest])
      : aMessagePage([newest, middle], 'older'),
  )
}

function renderList() {
  auth.members([aWorkspaceMember({ id: ADA, displayName: 'Ada Lovelace' })])
  return renderWithProviders(
    <MessageList
      accessToken="token"
      workspaceId={WORKSPACE_ID}
      channelId={CHANNEL}
      userId={ADA}
      myRole={null}
    />,
  )
}

const shownBodies = () =>
  screen.getAllByRole('article').map((article) => article.querySelector('p')?.textContent)

const historyRequests = () => requests().filter((r) => r.url.pathname.endsWith('/messages'))

describe('MessageList', () => {
  it('shows the newest page oldest-first, as a conversation reads', async () => {
    stubHistory()
    renderList()

    await screen.findByText('the latest message')

    expect(shownBodies()).toEqual(['the second message', 'the latest message'])
    expect(screen.queryByText('the first message')).not.toBeInTheDocument()
  })

  it('loads older messages above the rest when the top of the history is reached', async () => {
    stubHistory()
    renderList()
    await screen.findByText('the latest message')

    // jsdom has no layout, so scrollTop is 0: the scroller is at the top.
    fireEvent.scroll(screen.getAllByRole('article')[0].parentElement as HTMLElement)

    expect(await screen.findByText('the first message')).toBeInTheDocument()
    expect(shownBodies()).toEqual([
      'the first message',
      'the second message',
      'the latest message',
    ])
    expect(historyRequests().map((r) => r.url.searchParams.get('cursor'))).toEqual([
      null,
      'older',
    ])
  })

  it('asks for nothing more once the oldest page is in', async () => {
    stubHistory()
    renderList()
    await screen.findByText('the latest message')
    const scroller = screen.getAllByRole('article')[0].parentElement as HTMLElement
    fireEvent.scroll(scroller)
    await screen.findByText('the first message')

    fireEvent.scroll(scroller)

    expect(historyRequests()).toHaveLength(2)
  })

  it('invites the first message in an empty channel', async () => {
    messaging.get('/api/v1/channels/{channel_id}/messages', aMessagePage([]))
    renderList()

    expect(await screen.findByText('Nothing here yet. Say something.')).toBeInTheDocument()
  })
})
