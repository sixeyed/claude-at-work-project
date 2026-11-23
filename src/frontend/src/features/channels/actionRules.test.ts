/**
 * What a message row offers (gh-8 Req 1). Hiding a control is a courtesy, not
 * authorization — the server's `check_editable` / `check_deletable` decide — so
 * these are about the offer, one input flipped at a time with the others held true.
 */

import { describe, expect, it } from 'vitest'

import { aMessage } from '../../test/factories'
import { offeredActions } from './actionRules'

const ADA = 'user-ada'
const GRACE = 'user-grace'

const asAda = { userId: ADA, myRole: 'member' as string | null, threads: true }

describe('offeredActions', () => {
  it('your own confirmed message offers react, reply, edit, delete — in that order', () => {
    expect(offeredActions(aMessage({ authorId: ADA }), asAda)).toEqual([
      'react',
      'reply',
      'edit',
      'delete',
    ])
  })

  it('someone else’s message offers react and reply only', () => {
    expect(offeredActions(aMessage({ authorId: GRACE }), asAda)).toEqual(['react', 'reply'])
  })

  it('a channel admin gets delete, never edit, on someone else’s message', () => {
    expect(offeredActions(aMessage({ authorId: GRACE }), { ...asAda, myRole: 'admin' })).toEqual([
      'react',
      'reply',
      'delete',
    ])
  })

  it('with threads off — a thread panel row — there is no reply; the same message with threads on has one', () => {
    const message = aMessage({ authorId: ADA })

    expect(offeredActions(message, asAda)).toContain('reply')
    expect(offeredActions(message, { ...asAda, threads: false })).toEqual([
      'react',
      'edit',
      'delete',
    ])
  })

  it('a reply in a thread offers no reply even with threads on', () => {
    const topLevel = aMessage({ authorId: ADA, threadRootId: null })
    const inThread = aMessage({ authorId: ADA, threadRootId: 'a-root' })

    expect(offeredActions(topLevel, asAda)).toContain('reply')
    expect(offeredActions(inThread, asAda)).toEqual(['react', 'edit', 'delete'])
  })

  it('a pending message offers nothing, even to its admin author with threads on', () => {
    const confirmed = aMessage({ authorId: ADA })
    const pending = aMessage({ id: 'temp:1234', authorId: ADA })
    const admin = { ...asAda, myRole: 'admin' as string | null }

    expect(offeredActions(confirmed, admin)).toHaveLength(4)
    expect(offeredActions(pending, admin)).toEqual([])
  })

  it('a deleted message offers nothing, even to its admin author with threads on', () => {
    const live = aMessage({ authorId: ADA })
    const tombstone = aMessage({ authorId: ADA, body: '', deletedAt: '2026-09-15T09:32:00Z' })
    const admin = { ...asAda, myRole: 'admin' as string | null }

    expect(offeredActions(live, admin)).toHaveLength(4)
    expect(offeredActions(tombstone, admin)).toEqual([])
  })
})
