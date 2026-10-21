/**
 * The Settings page on its own (issue Req 1, 7, 8; plan Decisions 24, 28, 29).
 *
 * The page is mounted directly, with a fresh `QueryClient`, against Auth stubbed at
 * the network edge. The real session store is signed in as "Ada Lovelace", so a
 * test can show the field is filled from the server's read and not from it.
 *
 * Preferences are served by a small stateful stand-in (`prefsServer`): a PATCH that
 * succeeds changes what the next GET answers, as the real service would. Where a
 * test looks at what the screen shows *between* a failure and the re-read it owes,
 * the reads are gated (`gateReads`) so the answer comes from the cache and not from
 * a refetch that happens to land first.
 */

import { act, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Preferences, Profile, TokenPair } from '../../lib/auth/api'
import * as session from '../../lib/auth/session'
import { auth, Refused, requests } from '../../test/api'
import { createTestQueryClient, renderWithProviders } from '../../test/render'
import { SettingsPage } from './SettingsPage'

const USER = 'user-ada'
const WORKSPACE = '0199a000-0000-7000-8000-0000000000a1'

const PROFILE: Profile = {
  id: USER,
  email: 'ada@collabhub.dev',
  displayName: 'Ada Lovelace',
  avatarAsset: null,
}
const SERVER_PROFILE: Profile = { ...PROFILE, displayName: 'Ada Server' }
const TAKEN = 'That name is already taken.'
const INVISIBLE = 'A display name can’t contain invisible or control characters.'

function tokenFor(workspaceId: string): string {
  const payload = btoa(JSON.stringify({ wsp: workspaceId }))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
  return `header.${payload}.signature`
}
const PAIR: TokenPair = { accessToken: tokenFor(WORKSPACE), tokenType: 'Bearer', expiresIn: 900 }

function deferred<T = void>() {
  let release!: (value: T) => void
  const promise = new Promise<T>((resolve) => {
    release = resolve
  })
  return { promise, release }
}

const pause = () => act(() => new Promise<void>((resolve) => setTimeout(resolve, 25)))
const release = <T,>(held: { release: (value: T) => void }, value: T) =>
  act(async () => held.release(value))

beforeEach(async () => {
  auth.refresh(PAIR)
  auth.me(PROFILE)
  auth.workspaces([{ id: WORKSPACE, name: 'Home', role: 'owner' }])
  await session.restore()
})

function sessionName(): string | undefined {
  const state = session.snapshot()
  return state.status === 'signedIn' ? state.session.profile.displayName : undefined
}

/**
 * What the Auth service holds for Ada's preferences. `accept` answers a PATCH the
 * way the service does; `gateReads` holds every GET from now on until released.
 */
function prefsServer(initial: Preferences = {}) {
  const state = { stored: initial, gate: null as Promise<void> | null }
  auth.preferences(async () => {
    await state.gate
    return { ...state.stored }
  })
  return {
    state,
    accept(body: { clock: '12h' | '24h' | null }): Preferences {
      state.stored = body.clock === null ? {} : { clock: body.clock }
      return { ...state.stored }
    },
    gateReads() {
      const gate = deferred()
      state.gate = gate.promise
      return () => gate.release()
    },
  }
}

const preferenceRequests = () =>
  requests().filter(
    (r) => r.method === 'PATCH' && r.url.pathname === '/api/v1/users/me/preferences',
  )
const profileReads = () =>
  requests().filter((r) => r.method === 'GET' && r.url.pathname === '/api/v1/users/me')
const renames = () =>
  requests().filter((r) => r.method === 'PATCH' && r.url.pathname === '/api/v1/users/me')

function renderPage(queryClient = createTestQueryClient()) {
  return { ...renderWithProviders(<SettingsPage accessToken="token" userId={USER} />, { queryClient }), queryClient }
}

const nameField = () => screen.findByRole('textbox', { name: 'Display name' })
const saveButton = () => screen.getByRole('button', { name: 'Save' })
const radio = (name: string) => screen.getByRole('radio', { name })

/** A page whose profile read has landed, with the field in hand. */
async function openedPage(prefs: Preferences = {}) {
  auth.me(SERVER_PROFILE)
  const server = prefsServer(prefs)
  const view = renderPage()
  const input = await nameField()
  return { ...view, server, input }
}

describe('the Profile section', () => {
  it('prefills from the server, not the session', async () => {
    auth.me(SERVER_PROFILE)
    prefsServer()

    renderPage()

    expect(await nameField()).toHaveValue('Ada Server')
    expect(sessionName()).toBe('Ada Lovelace')
  })

  it('waits for this visit’s read, not a cached profile', async () => {
    const read = deferred<Profile>()
    auth.meBy(() => read.promise)
    prefsServer()
    const queryClient = createTestQueryClient()
    queryClient.setQueryData(['me', USER], { ...PROFILE, displayName: 'Ada Cached' })
    const before = profileReads().length

    renderPage(queryClient)

    await screen.findByRole('heading', { name: 'Settings' })
    await vi.waitFor(() => expect(profileReads()).toHaveLength(before + 1))
    await pause()
    expect(screen.queryByRole('textbox', { name: 'Display name' })).not.toBeInTheDocument()
    expect(screen.queryByDisplayValue('Ada Cached')).not.toBeInTheDocument()

    await release(read, SERVER_PROFILE)
    expect(await nameField()).toHaveValue('Ada Server')
  })

  it('shows an error and no form when the profile read fails', async () => {
    auth.problem('get', '/api/v1/users/me', 500, { title: 'Internal error' })
    prefsServer()

    renderPage()

    expect(await screen.findByRole('alert')).toHaveTextContent(/load your profile/i)
    expect(screen.queryByRole('textbox', { name: 'Display name' })).not.toBeInTheDocument()
  })

  it('disables Save while the value is unchanged, including after spaces', async () => {
    const { user, input } = await openedPage()
    expect(saveButton()).toBeDisabled()

    await user.type(input, '  ')
    expect(saveButton()).toBeDisabled()

    await user.type(input, 'x')
    expect(saveButton()).toBeEnabled()
  })

  it('enables Save for a change of capitals only', async () => {
    const { user, input } = await openedPage()

    await user.clear(input)
    await user.type(input, 'ADA SERVER')

    expect(saveButton()).toBeEnabled()
  })

  it('disables Save when the name is empty after trimming', async () => {
    const { user, input } = await openedPage()

    await user.clear(input)
    expect(saveButton()).toBeDisabled()
    await user.type(input, '   ')
    expect(saveButton()).toBeDisabled()

    await user.type(input, 'x')
    expect(saveButton()).toBeEnabled()
  })

  it('counts code points: 100 emoji enable Save, 101 disable it', async () => {
    const { user, input } = await openedPage()
    const emoji = String.fromCodePoint(0x1f600)

    await user.clear(input)
    await user.paste(emoji.repeat(100))
    expect(saveButton()).toBeEnabled()

    await user.clear(input)
    await user.paste(emoji.repeat(101))
    expect(saveButton()).toBeDisabled()
  })

  it('sends the name as typed and shows the stored form back', async () => {
    const { user, input } = await openedPage()
    auth.updateMe((body) => ({ ...SERVER_PROFILE, displayName: body.displayName.trim() }))

    await user.clear(input)
    await user.type(input, '  Ada L  ')
    await user.click(saveButton())

    await vi.waitFor(() => expect(renames()).toHaveLength(1))
    expect(renames()[0].body).toEqual({ displayName: '  Ada L  ' })
    await vi.waitFor(() => expect(input).toHaveValue('Ada L'))
  })

  it('keeps Save disabled while a save is in flight', async () => {
    const { user, input } = await openedPage()
    const held = deferred<Profile>()
    auth.updateMe(() => held.promise)
    await user.clear(input)
    await user.type(input, 'Ada L')
    expect(saveButton()).toBeEnabled()

    await user.click(saveButton())
    await vi.waitFor(() => expect(renames()).toHaveLength(1))

    expect(saveButton()).toBeDisabled()
    await release(held, { ...SERVER_PROFILE, displayName: 'Ada L' })
    await vi.waitFor(() => expect(screen.getByText('Saved')).toBeInTheDocument())
  })

  it('shows a 400 on the field and writes no cache', async () => {
    const { user, input, queryClient } = await openedPage()
    queryClient.setQueryData(['workspace-members', WORKSPACE], [{ marker: 'untouched' }])
    auth.updateMe(
      () =>
        new Refused(400, {
          title: 'Validation error',
          detail: INVISIBLE,
          errors: { displayName: [INVISIBLE] },
        }),
    )

    await user.clear(input)
    await user.type(input, 'Gr')
    await user.click(saveButton())

    expect(await screen.findByRole('alert')).toHaveTextContent(INVISIBLE)
    expect(sessionName()).toBe('Ada Lovelace')
    expect(queryClient.getQueryData<Profile>(['me', USER])?.displayName).toBe('Ada Server')
    expect(queryClient.getQueryData(['workspace-members', WORKSPACE])).toEqual([
      { marker: 'untouched' },
    ])
    expect(screen.queryByText('Saved')).not.toBeInTheDocument()
  })

  it('shows a 409 as “That name is already taken.” on the field', async () => {
    const { user, input } = await openedPage()
    auth.updateMe(
      () =>
        new Refused(409, {
          title: 'Conflict',
          detail: TAKEN,
          errors: { displayName: [TAKEN] },
        }),
    )

    await user.clear(input)
    await user.type(input, 'grace')
    await user.click(saveButton())

    expect(await screen.findByRole('alert')).toHaveTextContent(TAKEN)
    expect(input).toHaveValue('grace')
  })

  it('says Saved after a success, and stops saying it on the next edit', async () => {
    const { user, input } = await openedPage()
    auth.updateMe((body) => ({ ...SERVER_PROFILE, displayName: body.displayName }))
    expect(screen.queryByText('Saved')).not.toBeInTheDocument()

    await user.clear(input)
    await user.type(input, 'Ada L')
    await user.click(saveButton())
    expect(await screen.findByText('Saved')).toBeInTheDocument()

    await user.type(input, '!')
    expect(screen.queryByText('Saved')).not.toBeInTheDocument()
  })
})

describe('the Preferences section', () => {
  it('checks the stored clock, and Automatic when there is none', async () => {
    prefsServer({ clock: '12h' })
    auth.me(SERVER_PROFILE)
    const first = renderPage()
    await first.findByRole('radio', { name: '12-hour' })
    await vi.waitFor(() => expect(radio('12-hour')).toBeChecked())
    expect(radio('Automatic')).not.toBeChecked()
    expect(radio('24-hour')).not.toBeChecked()
    first.unmount()

    prefsServer({})
    renderPage()

    await vi.waitFor(() => expect(radio('Automatic')).toBeChecked())
    expect(radio('12-hour')).not.toBeChecked()
  })

  it('sends {clock:"24h"} at once when 24-hour is chosen', async () => {
    const { user, server } = await openedPage({})
    const held = deferred<Preferences>()
    auth.updatePreferences(() => held.promise)

    await user.click(radio('24-hour'))

    await vi.waitFor(() => expect(preferenceRequests()).toHaveLength(1))
    expect(preferenceRequests()[0].body).toEqual({ clock: '24h' })
    expect(radio('24-hour')).toBeChecked()
    await release(held, server.accept({ clock: '24h' }))
    expect(radio('24-hour')).toBeChecked()
  })

  it('sends {clock:null} when Automatic is chosen', async () => {
    const { user } = await openedPage({ clock: '24h' })
    await vi.waitFor(() => expect(radio('24-hour')).toBeChecked())
    const held = deferred<Preferences>()
    auth.updatePreferences(() => held.promise)

    await user.click(radio('Automatic'))

    await vi.waitFor(() => expect(preferenceRequests()).toHaveLength(1))
    expect(preferenceRequests()[0].body).toEqual({ clock: null })
    expect(radio('Automatic')).toBeChecked()
    await release(held, {})
  })

  it('puts the previous choice back and shows the error when a save fails', async () => {
    const { user } = await openedPage({ clock: '12h' })
    await vi.waitFor(() => expect(radio('12-hour')).toBeChecked())
    const held = deferred()
    auth.updatePreferences(async () => {
      await held.promise
      return new Refused(500, { title: 'Internal error', detail: 'Could not save that.' })
    })

    await user.click(radio('24-hour'))
    await vi.waitFor(() => expect(preferenceRequests()).toHaveLength(1))
    expect(radio('24-hour')).toBeChecked()
    await release(held, undefined)

    await vi.waitFor(() => expect(radio('12-hour')).toBeChecked())
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not save that.')
  })

  it('keeps a later choice when an earlier save fails', async () => {
    const { user, server } = await openedPage({ clock: '12h' })
    await vi.waitFor(() => expect(radio('12-hour')).toBeChecked())
    const first = deferred()
    const second = deferred()
    let calls = 0
    auth.updatePreferences(async (body) => {
      calls += 1
      if (calls === 1) {
        await first.promise
        return new Refused(500, { title: 'Internal error', detail: 'Could not save that.' })
      }
      await second.promise
      return server.accept(body)
    })
    const ungate = server.gateReads()

    await user.click(radio('24-hour'))
    await vi.waitFor(() => expect(preferenceRequests()).toHaveLength(1))
    await user.click(radio('Automatic'))
    expect(radio('Automatic')).toBeChecked()

    await release(first, undefined)
    await vi.waitFor(() => expect(preferenceRequests()).toHaveLength(2))
    // The first save failed; the choice made after it is still the one on screen.
    // TanStack notifies observers on a timeout, so give a wrong rollback time to reach the DOM.
    await pause()
    expect(radio('Automatic')).toBeChecked()
    expect(radio('12-hour')).not.toBeChecked()

    await release(second, undefined)
    await pause()
    ungate()
    await vi.waitFor(() => expect(radio('Automatic')).toBeChecked())
    expect(server.state.stored).toEqual({})
  })

  it('goes back to the earlier choice when a later save fails after an earlier success', async () => {
    const { user, server } = await openedPage({})
    let calls = 0
    const failing = deferred()
    auth.updatePreferences(async (body) => {
      calls += 1
      if (calls === 1) return server.accept(body)
      await failing.promise
      return new Refused(500, { title: 'Internal error', detail: 'Could not save that.' })
    })
    const ungate = server.gateReads()

    await user.click(radio('24-hour'))
    await vi.waitFor(() => expect(preferenceRequests()).toHaveLength(1))
    await pause()
    await user.click(radio('12-hour'))
    await vi.waitFor(() => expect(preferenceRequests()).toHaveLength(2))
    expect(radio('12-hour')).toBeChecked()
    await release(failing, undefined)

    // Not Automatic, the choice the page opened with: the one the first save made.
    await vi.waitFor(() => expect(radio('24-hour')).toBeChecked())
    expect(radio('Automatic')).not.toBeChecked()
    ungate()
  })

  it('re-reads the clock from the server when both saves fail', async () => {
    const { user, server } = await openedPage({ clock: '12h' })
    await vi.waitFor(() => expect(radio('12-hour')).toBeChecked())
    const first = deferred()
    const second = deferred()
    let calls = 0
    auth.updatePreferences(async () => {
      calls += 1
      await (calls === 1 ? first.promise : second.promise)
      return new Refused(500, { title: 'Internal error', detail: 'Could not save that.' })
    })

    await user.click(radio('24-hour'))
    await vi.waitFor(() => expect(preferenceRequests()).toHaveLength(1))
    await user.click(radio('Automatic'))
    await release(first, undefined)
    await vi.waitFor(() => expect(preferenceRequests()).toHaveLength(2))
    // Another tab changed it meanwhile: the truth is neither 12-hour nor Automatic.
    server.state.stored = { clock: '24h' }
    await release(second, undefined)

    await vi.waitFor(() => expect(radio('24-hour')).toBeChecked())
    expect(radio('12-hour')).not.toBeChecked()
  })

  it('does not send the second choice before the first has answered', async () => {
    const { user, server } = await openedPage({})
    const first = deferred<Preferences>()
    let calls = 0
    auth.updatePreferences((body) => {
      calls += 1
      return calls === 1 ? first.promise : server.accept(body)
    })

    await user.click(radio('24-hour'))
    await vi.waitFor(() => expect(preferenceRequests()).toHaveLength(1))
    await user.click(radio('12-hour'))
    expect(radio('12-hour')).toBeChecked()
    await pause()
    expect(preferenceRequests()).toHaveLength(1)

    await release(first, server.accept({ clock: '24h' }))
    await vi.waitFor(() => expect(preferenceRequests()).toHaveLength(2))
    expect(preferenceRequests()[1].body).toEqual({ clock: '12h' })
  })
})
