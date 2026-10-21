/**
 * The three places a time is shown follow the clock preference (issue Req 7).
 *
 * A file of its own, importing `./clock`, so that while the module is missing the
 * load failure hides no existing test of `MessageItem`, `ThreadSummary` or
 * `SearchResult`. Each is rendered inside `ClockContext.Provider`, 24-hour then
 * 12-hour on the same instant, so a formatter that ignores the context shows the
 * same text twice and fails one of the two. The instant is built in local time.
 */

import { screen } from '@testing-library/react'
import type { ReactElement } from 'react'
import { describe, expect, it, vi } from 'vitest'

import { aChannel, aMessage } from '../../test/factories'
import { renderWithProviders } from '../../test/render'
import { MessageItem } from '../channels/MessageItem'
import { SearchResult } from '../search/SearchResult'
import { ThreadSummary } from '../threads/ThreadSummary'
import { ClockContext } from './clock'

const afternoon = new Date(2026, 8, 15, 13, 5).toISOString()

function item(): ReactElement {
  return (
    <MessageItem
      message={aMessage({ authorId: 'user-ada', createdAt: afternoon })}
      authorName="Ada Lovelace"
      userId="user-ada"
      myRole={null}
      editError={undefined}
      editPending={false}
      onEdit={vi.fn()}
      onDelete={vi.fn()}
      onToggleReaction={vi.fn()}
    />
  )
}

function summary(): ReactElement {
  return <ThreadSummary replyCount={2} lastReplyAt={afternoon} onOpen={vi.fn()} />
}

function hit(): ReactElement {
  const message = aMessage({ channelId: aChannel().id, createdAt: afternoon })
  return <SearchResult message={message} channelTitle="#general" authorName="Ada Lovelace" />
}

const inClock = (clock: '12h' | '24h' | undefined, ui: ReactElement) => (
  <ClockContext.Provider value={clock}>{ui}</ClockContext.Provider>
)

describe.each([
  ['MessageItem’s time', item, { twentyFour: '13:05', twelve: /^0?1:05/ }],
  ['ThreadSummary’s last reply', summary, { twentyFour: '13:05', twelve: /^0?1:05/ }],
  ['SearchResult’s date and time', hit, { twentyFour: /13:05/, twelve: /\b0?1:05/ }],
])('%s', (_name, build, expected) => {
  it('follows the clock', () => {
    const { rerender, container } = renderWithProviders(inClock('24h', build()))
    const time = () => container.querySelector('time')?.textContent ?? ''

    expect(time()).toMatch(expected.twentyFour)
    expect(time()).not.toMatch(/\b(AM|PM)\b/i)

    rerender(inClock('12h', build()))
    expect(time()).toMatch(expected.twelve)
    expect(time()).not.toContain('13:05')
  })
})

describe('with no clock', () => {
  it('formats each exactly as before', () => {
    const date = new Date(afternoon)
    const bare = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    const full = date.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })

    const first = renderWithProviders(item())
    expect(screen.getByText(bare).tagName).toBe('TIME')
    first.unmount()

    const second = renderWithProviders(summary())
    expect(screen.getByText(bare).tagName).toBe('TIME')
    second.unmount()

    renderWithProviders(hit())
    expect(screen.getByText(full).tagName).toBe('TIME')
  })

  it('formats the same when the provider says Automatic explicitly', () => {
    const bare = new Date(afternoon).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

    renderWithProviders(inClock(undefined, item()))

    expect(screen.getByText(bare).tagName).toBe('TIME')
  })
})
