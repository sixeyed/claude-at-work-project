/**
 * What happens to pending uploads when the shell goes away (issue 4 R15,
 * decision 37): a workspace switch clears every channel's chips and aborts what
 * is uploading, and so does leaving (sign-out unmounts the shell).
 *
 * A token is scoped to one workspace, so an upload started under the old one must
 * not carry on, and a chip from the old workspace must not be offered in the new.
 * A reload loses chips by itself — they are in memory — so there is nothing to test
 * for that. Same setup as `ChatLayout.test.tsx`; a new file because this one
 * imports modules that do not exist yet.
 */

import { screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Profile, TokenPair, Workspace } from '../../lib/auth/api'
import * as session from '../../lib/auth/session'
import { useSession } from '../../lib/auth/useSession'
import { useAttachmentStore } from '../../stores/attachments'
import { asset, auth, messaging, requests } from '../../test/api'
import { aChannel, aChip } from '../../test/factories'
import { renderWithProviders } from '../../test/render'
import { addFiles, cancelAll } from '../attachments/uploads'
import { ChatLayout } from './ChatLayout'

const HOME = '0199a000-0000-7000-8000-0000000000a1'
const AWAY = '0199a000-0000-7000-8000-0000000000a2'

const PROFILE: Profile = {
  id: 'user-ada',
  email: 'ada@collabhub.dev',
  displayName: 'Ada Lovelace',
  avatarAsset: null,
}
const WORKSPACES: Workspace[] = [
  { id: HOME, name: 'Home', role: 'owner' },
  { id: AWAY, name: 'Away', role: 'member' },
]

function tokenFor(workspaceId: string): string {
  const payload = btoa(JSON.stringify({ wsp: workspaceId }))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
  return `header.${payload}.signature`
}

function pair(workspaceId: string): TokenPair {
  return { accessToken: tokenFor(workspaceId), tokenType: 'Bearer', expiresIn: 900 }
}

function SignedInShell() {
  const state = useSession()
  if (state.status !== 'signedIn') return null
  return (
    <ChatLayout current={state.session}>
      <p>content</p>
    </ChatLayout>
  )
}

const home = aChannel({ name: 'general' })
const GENERAL = home.id
const OTHER = 'channel-other'
const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms))
const chips = () => useAttachmentStore.getState().chips
const confirms = () => requests().filter((r) => r.url.pathname.endsWith('/confirm'))

function deferred() {
  let release!: () => void
  const promise = new Promise<void>((resolve) => {
    release = resolve
  })
  return { promise, release }
}

beforeEach(async () => {
  auth.me(PROFILE)
  auth.workspaces(WORKSPACES)
  auth.preferences({})
  auth.refresh(pair(HOME))
  await session.restore()
  auth.switchWorkspace(pair(AWAY))
  messaging.get('/api/v1/channels', () => ({ items: [home], nextCursor: null }))
})

afterEach(() => {
  cancelAll()
  useAttachmentStore.getState().reset()
})

/** One chip already ready in another channel, and one file still uploading in this one. */
async function startUploads(gate: Promise<unknown>) {
  asset.acceptUploads({ hold: { put: gate } })
  useAttachmentStore.getState().add(OTHER, aChip({ fileName: 'ready.png' }))
  addFiles(GENERAL, [new File(['x'.repeat(10)], 'uploading.png', { type: 'image/png' })], () =>
    tokenFor(HOME),
  )
  await vi.waitFor(() =>
    expect(requests().some((r) => r.method === 'PUT' && r.url.pathname.includes('uploading'))).toBe(
      true,
    ),
  )
}

describe('ChatLayout — pending uploads', () => {
  it('clears every channel’s chips and stops the upload on a workspace switch', async () => {
    const gate = deferred()
    const { user } = renderWithProviders(<SignedInShell />)
    await screen.findByRole('link', { name: 'general' })
    await startUploads(gate.promise)
    // The positive half of "cleared": both chips are there before the switch.
    expect(Object.keys(chips()).sort()).toEqual([GENERAL, OTHER].sort())

    await user.click(screen.getByRole('button', { name: 'Away' }))

    await vi.waitFor(() => expect(chips()).toEqual({}))
    gate.release()
    await sleep(150)
    // The upload that was in flight neither confirmed nor wrote its chip back.
    expect(confirms()).toEqual([])
    expect(chips()).toEqual({})
  })

  it('does the same when the shell unmounts, as it does on sign-out', async () => {
    const gate = deferred()
    const { unmount } = renderWithProviders(<SignedInShell />)
    await screen.findByRole('link', { name: 'general' })
    await startUploads(gate.promise)
    expect(Object.keys(chips())).toHaveLength(2)

    unmount()

    expect(chips()).toEqual({})
    gate.release()
    await sleep(150)
    expect(confirms()).toEqual([])
    expect(chips()).toEqual({})
  })

  it('lets the same upload finish when nothing switches or unmounts', async () => {
    const gate = deferred()
    renderWithProviders(<SignedInShell />)
    await screen.findByRole('link', { name: 'general' })
    await startUploads(gate.promise)

    gate.release()

    await vi.waitFor(() => expect(chips()[GENERAL]?.[0]?.status).toBe('ready'))
    expect(confirms()).toHaveLength(1)
    expect(chips()[OTHER]).toHaveLength(1)
  })
})
