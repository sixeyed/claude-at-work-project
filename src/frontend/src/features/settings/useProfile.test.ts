/**
 * What a successful rename writes, and what it must not lose to (issue Req 5;
 * plan Decisions 30, 30a).
 *
 * The session is the real store, signed in as Ada; Auth is stubbed at the network
 * edge. A cached directory is made the real way — `useWorkspaceMembers` mounted for
 * the workspace, and unmounted for an inactive one — never by `setQueryData` alone:
 * a query with no `queryFn` cannot be refetched, so the refetch a rename owes would
 * never go out. Query keys are written as literals, the keys the plan names.
 *
 * The held-read tests are the point. A directory or profile read that was answered
 * before the commit and lands after the rename carries the old name; writing the
 * caches alone loses to it, and so does invalidating alone. Each read in flight is
 * held, and the next one too, so "the cancelled answer was discarded" is looked at
 * while the refetch is still outstanding.
 */

import type { QueryClient } from '@tanstack/react-query'
import { act } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Profile, TokenPair, WorkspaceMember } from '../../lib/auth/api'
import * as session from '../../lib/auth/session'
import { auth, requests } from '../../test/api'
import { scriptDirectory, settleDirectory } from '../../test/directory'
import { aWorkspaceMember } from '../../test/factories'
import { createTestQueryClient, renderHookWithProviders } from '../../test/render'
import { directoryKeys, useWorkspaceMembers } from '../channels/useWorkspaceMembers'
import { applyRename, useMyProfile, useRenameMe } from './useProfile'

const WS_A = '0199a000-0000-7000-8000-00000000aaa0'
const WS_B = '0199a000-0000-7000-8000-00000000bbb0'
const ADA = 'user-ada'
const GRACE = 'user-grace'

const PROFILE: Profile = {
  id: ADA,
  email: 'ada@collabhub.dev',
  displayName: 'Ada Lovelace',
  avatarAsset: null,
}
const RENAMED: Profile = { ...PROFILE, displayName: 'Ada New' }

const adaOld = aWorkspaceMember({ id: ADA, displayName: 'Ada Lovelace' })
const adaNew = aWorkspaceMember({ id: ADA, displayName: 'Ada New' })
const grace = aWorkspaceMember({ id: GRACE, displayName: 'Grace Hopper' })
const bob = aWorkspaceMember({ id: 'user-bob', displayName: 'Bob Barker' })

function tokenFor(workspaceId: string): string {
  const payload = btoa(JSON.stringify({ wsp: workspaceId }))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
  return `header.${payload}.signature`
}
const PAIR: TokenPair = { accessToken: tokenFor(WS_A), tokenType: 'Bearer', expiresIn: 900 }

function deferred<T = void>() {
  let release!: (value: T) => void
  const promise = new Promise<T>((resolve) => {
    release = resolve
  })
  return { promise, release }
}

/** A macrotask or two, so anything a build would start on its own has started. */
const pause = () => act(() => new Promise<void>((resolve) => setTimeout(resolve, 25)))

beforeEach(async () => {
  auth.refresh(PAIR)
  auth.me(PROFILE)
  auth.workspaces([{ id: WS_A, name: 'Home', role: 'owner' }])
  await session.restore()
})

function sessionName(): string | undefined {
  const state = session.snapshot()
  return state.status === 'signedIn' ? state.session.profile.displayName : undefined
}

function nameIn(queryClient: QueryClient, workspace: string, userId: string): string | undefined {
  const members = queryClient.getQueryData<WorkspaceMember[]>(directoryKeys.members(workspace))
  return members?.find((m) => m.user.id === userId)?.user.displayName
}

/** Mount the directory for `workspace` until it has loaded; leave it mounted or not. */
async function cachedDirectory(queryClient: QueryClient, workspace: string, keepMounted: boolean) {
  const view = renderHookWithProviders(() => useWorkspaceMembers('token', workspace), {
    queryClient,
  })
  await vi.waitFor(() =>
    expect(queryClient.getQueryData(directoryKeys.members(workspace))).toBeDefined(),
  )
  await settleDirectory(queryClient, workspace)
  if (!keepMounted) view.unmount()
  return view
}

const renameRequests = () =>
  requests().filter((r) => r.method === 'PATCH' && r.url.pathname === '/api/v1/users/me')
const profileReads = () =>
  requests().filter((r) => r.method === 'GET' && r.url.pathname === '/api/v1/users/me')

describe('applyRename', () => {
  it('updates the session and every cached directory', async () => {
    const queryClient = createTestQueryClient()
    const script = scriptDirectory({ [WS_A]: [adaOld, grace], [WS_B]: [adaOld, bob] })
    await cachedDirectory(queryClient, WS_A, true)
    await cachedDirectory(queryClient, WS_B, false)
    // The server has committed the rename, so the refetch it owes answers the new name.
    script.now[WS_A] = [adaNew, grace]
    script.now[WS_B] = [adaNew, bob]

    act(() => applyRename(queryClient, RENAMED))

    // At once: no refetch can have landed yet, so this is the write, not the re-read.
    expect(sessionName()).toBe('Ada New')
    expect(nameIn(queryClient, WS_A, ADA)).toBe('Ada New')
    expect(nameIn(queryClient, WS_B, ADA)).toBe('Ada New')
    expect(nameIn(queryClient, WS_A, GRACE)).toBe('Grace Hopper')
    expect(nameIn(queryClient, WS_B, 'user-bob')).toBe('Bob Barker')
    expect(queryClient.getQueryData(['me', ADA])).toEqual(RENAMED)

    // And every cached directory, the unmounted one included, is read again.
    await vi.waitFor(() => {
      expect(script.requests(WS_A)).toHaveLength(2)
      expect(script.requests(WS_B)).toHaveLength(2)
    })
    await settleDirectory(queryClient, WS_A)
    await settleDirectory(queryClient, WS_B)
    expect(nameIn(queryClient, WS_A, ADA)).toBe('Ada New')
    expect(nameIn(queryClient, WS_B, ADA)).toBe('Ada New')
  })

  it('leaves another user’s session alone', () => {
    const queryClient = createTestQueryClient()

    act(() => applyRename(queryClient, { ...PROFILE, id: GRACE, displayName: 'Gracie' }))

    expect(sessionName()).toBe('Ada Lovelace')
  })

  it('lands after the form that started it has unmounted', async () => {
    const queryClient = createTestQueryClient()
    const script = scriptDirectory({ [WS_A]: [adaOld, grace] })
    await cachedDirectory(queryClient, WS_A, true)
    const held = deferred()
    auth.updateMe(async () => {
      await held.promise
      return RENAMED
    })
    const form = renderHookWithProviders(() => useRenameMe('token', ADA), { queryClient })
    const mutate = form.result.current.mutate

    act(() => mutate('Ada New'))
    await vi.waitFor(() => expect(renameRequests()).toHaveLength(1))
    expect(renameRequests()[0].body).toEqual({ displayName: 'Ada New' })
    form.unmount()
    script.now[WS_A] = [adaNew, grace]
    held.release()

    await vi.waitFor(() => expect(sessionName()).toBe('Ada New'))
    expect(nameIn(queryClient, WS_A, ADA)).toBe('Ada New')
    expect(queryClient.getQueryData(['me', ADA])).toEqual(RENAMED)
  })
})

describe('a rename racing a read already in flight', () => {
  it('a directory read answered before the rename can’t put the old name back', async () => {
    const queryClient = createTestQueryClient()
    const script = scriptDirectory({ [WS_A]: [adaOld, grace] })
    await cachedDirectory(queryClient, WS_A, true)
    const second = script.hold(WS_A, 2)
    const third = script.hold(WS_A, 3)
    act(() => {
      void queryClient.invalidateQueries({ queryKey: directoryKeys.members(WS_A) })
    })
    await vi.waitFor(() => expect(script.requests(WS_A)).toHaveLength(2))

    act(() => applyRename(queryClient, RENAMED))
    expect(nameIn(queryClient, WS_A, ADA)).toBe('Ada New')
    // The refetch the rename starts has gone out, beside the stale one.
    await vi.waitFor(() => expect(script.requests(WS_A)).toHaveLength(3))

    await second.release([adaOld, grace])
    await pause()
    // The stale answer landed, and the refetch is still outstanding: it must not show.
    expect(nameIn(queryClient, WS_A, ADA)).toBe('Ada New')

    await third.release([adaNew, grace])
    await settleDirectory(queryClient, WS_A)
    expect(nameIn(queryClient, WS_A, ADA)).toBe('Ada New')
    expect(script.requests(WS_A)).toHaveLength(3)
  })

  it('a directory read started after the rename lands as the server says', async () => {
    const queryClient = createTestQueryClient()
    const newer = aWorkspaceMember({ id: ADA, displayName: 'Ada Newer' })
    const script = scriptDirectory({ [WS_A]: [adaOld, grace] })
    await cachedDirectory(queryClient, WS_A, true)
    // Someone renamed Ada again between the commit and the refetch.
    script.answer(WS_A, 2, [newer, grace])

    act(() => applyRename(queryClient, RENAMED))
    expect(nameIn(queryClient, WS_A, ADA)).toBe('Ada New')

    await vi.waitFor(() => expect(nameIn(queryClient, WS_A, ADA)).toBe('Ada Newer'))
  })

  it('a first directory load in flight is restarted', async () => {
    const queryClient = createTestQueryClient()
    const script = scriptDirectory({ [WS_A]: [adaOld, grace] })
    const first = script.hold(WS_A, 1)
    const second = script.hold(WS_A, 2)
    renderHookWithProviders(() => useWorkspaceMembers('token', WS_A), { queryClient })
    await vi.waitFor(() => expect(script.requests(WS_A)).toHaveLength(1))
    expect(queryClient.getQueryData(directoryKeys.members(WS_A))).toBeUndefined()

    // No data to write the name into: the updater is handed `undefined` and must cope.
    act(() => applyRename(queryClient, RENAMED))
    await vi.waitFor(() => expect(script.requests(WS_A)).toHaveLength(2))

    await first.release([adaOld, grace])
    await pause()
    // The first read was cancelled, so its old name never becomes the directory.
    expect(queryClient.getQueryData(directoryKeys.members(WS_A))).toBeUndefined()

    await second.release([adaNew, grace])
    await vi.waitFor(() => expect(nameIn(queryClient, WS_A, ADA)).toBe('Ada New'))
  })

  it('a profile read in flight can’t undo the rename', async () => {
    const queryClient = createTestQueryClient()
    const second = deferred<Profile>()
    auth.meBy((call) => (call === 1 ? PROFILE : call === 2 ? second.promise : RENAMED))
    const before = profileReads().length
    const view = renderHookWithProviders(() => useMyProfile('token', ADA), { queryClient })
    await vi.waitFor(() => expect(view.result.current.data?.displayName).toBe('Ada Lovelace'))
    act(() => {
      void queryClient.invalidateQueries({ queryKey: ['me', ADA] })
    })
    await vi.waitFor(() => expect(profileReads()).toHaveLength(before + 2))

    act(() => applyRename(queryClient, RENAMED))
    expect(queryClient.getQueryData<Profile>(['me', ADA])?.displayName).toBe('Ada New')
    await act(async () => {
      second.release(PROFILE)
    })
    await pause()

    expect(queryClient.getQueryData<Profile>(['me', ADA])?.displayName).toBe('Ada New')
    expect(view.result.current.data?.displayName).toBe('Ada New')
  })
})
