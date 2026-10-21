/**
 * The signed-in session: the one place that holds tokens and renews them.
 *
 * A plain module-level store rather than a state library, because register D24
 * (Zustand vs. Redux Toolkit) is still open and this is not the code that
 * should decide it. `subscribe`/`snapshot` is the shape React's
 * `useSyncExternalStore` wants, so whichever library wins can replace this file
 * without touching a component.
 *
 * `sessionStorage` holds two entries across the sign-in redirect, both in
 * `storage.ts`: the PKCE verifier and the route the visitor was heading for.
 *
 * Two things are deliberate:
 *
 * - **The access token never leaves memory**, and the refresh token never enters
 *   it: it is an `HttpOnly` cookie this code cannot read (register D22). Nothing
 *   here passes a refresh token anywhere, because nothing here has one.
 * - **Renewal happens ahead of expiry**, not on a 401. Waiting for a failure
 *   means every component needs retry logic; renewing early means they only
 *   ever see a valid token.
 */

import * as api from './api'
import { isSafeReturnPath, pkceVerifier, returnPath } from './storage'
import { challengeFor, createVerifier } from './pkce'

/** Renew this long before expiry, so a slow request cannot straddle it. */
const RENEW_MARGIN_SECONDS = 60

export interface Session {
  accessToken: string
  profile: api.Profile
  workspaces: api.Workspace[]
  /** The workspace this token is scoped to — its `wsp` claim (Conventions §5.4). */
  activeWorkspaceId: string | null
}

/**
 * Read a claim out of the access token for display.
 *
 * Deliberately *not* verification: the browser holds no public key and could not
 * meaningfully check a signature it also received. Services verify tokens
 * (Conventions §5.1); the SPA only needs to know which workspace it is in so it
 * can show the switcher correctly. Nothing here may gate access to anything.
 */
function claim(accessToken: string, name: string): string | null {
  try {
    const payload = accessToken.split('.')[1]
    const decoded = atob(payload.replace(/-/g, '+').replace(/_/g, '/'))
    return (JSON.parse(decoded) as Record<string, unknown>)[name] as string | null
  } catch {
    return null
  }
}

export type State =
  | { status: 'loading' }
  | { status: 'signedOut'; error?: string }
  | { status: 'signedIn'; session: Session }

let state: State = { status: 'loading' }
let renewalTimer: ReturnType<typeof setTimeout> | undefined
const listeners = new Set<() => void>()

function set(next: State): void {
  state = next
  for (const listener of listeners) listener()
}

export function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function snapshot(): State {
  return state
}

/** Counts `updateProfile` calls, so `adopt` can tell a rename landed during its reads. */
let profileUpdates = 0

/**
 * Replace the signed-in user's profile with a newer one, e.g. after a rename.
 *
 * A no-op unless signed in as `profile.id`. It also outlives an `adopt()` whose
 * reads began earlier (see there): otherwise a renewal or switch answered before
 * the rename would put the old name back in the sidebar for up to a renewal.
 */
export function updateProfile(profile: api.Profile): void {
  if (state.status !== 'signedIn' || state.session.profile.id !== profile.id) return

  profileUpdates += 1
  set({ status: 'signedIn', session: { ...state.session, profile } })
}

async function adopt(pair: api.TokenPair): Promise<void> {
  // Nothing to store: the refresh cookie was set by the response that carried
  // this access token, and the browser will send it back unprompted.
  const updatesBefore = profileUpdates
  const [read, workspaceList] = await Promise.all([
    api.me(pair.accessToken),
    api.workspaces(pair.accessToken),
  ])

  // A profile read answered before a rename that landed meanwhile carries the old
  // name: keep the session's. A read begun after the rename is adopted as it is, so
  // this can't freeze a name.
  const current = state
  const renamedMeanwhile =
    updatesBefore !== profileUpdates &&
    current.status === 'signedIn' &&
    current.session.profile.id === read.id
  const profile = renamedMeanwhile ? current.session.profile : read

  set({
    status: 'signedIn',
    session: {
      accessToken: pair.accessToken,
      profile,
      workspaces: workspaceList.items,
      activeWorkspaceId: claim(pair.accessToken, 'wsp'),
    },
  })
  scheduleRenewal(pair.expiresIn)
}

function scheduleRenewal(expiresIn: number): void {
  clearTimeout(renewalTimer)
  const delay = Math.max(expiresIn - RENEW_MARGIN_SECONDS, 1) * 1000
  renewalTimer = setTimeout(() => void renew(), delay)
}

/**
 * The request spending the refresh cookie right now, if any.
 *
 * Rotation spends a cookie the moment it is used, so a second request carrying
 * the same one is a replay, and the server answers a replay by revoking the whole
 * session. StrictMode's double restore or a timer firing mid-restore would do
 * exactly that, so only one request may hold the cookie at a time. This is one
 * tab's guard — two tabs still share a cookie and nothing coordinates them.
 */
let spending: Promise<void> | undefined

/** Hold the cookie for `exchange`, releasing it however that settles. */
function spend(exchange: () => Promise<void>): Promise<void> {
  const settled = exchange().finally(() => {
    if (spending === settled) spending = undefined
  })
  spending = settled
  return settled
}

function renew(): Promise<void> {
  // Whatever already holds the cookie — a renewal or a switch — leaves a fresh
  // token behind, which is all a renewal wants. Join it rather than replay.
  return (
    spending ??
    spend(async () => {
      try {
        await adopt(await api.refresh())
      } catch {
        // Rotation means a refresh token is spent the moment it is used. A failure
        // here is not retryable with the same cookie, so the only honest outcome is
        // to sign out rather than loop.
        signedOut()
      }
    })
  )
}

function signedOut(error?: string): void {
  clearTimeout(renewalTimer)
  // The cookie is cleared by the server on /auth/logout; there is nothing to
  // clear here, and a stale one simply fails the next renewal.
  set({ status: 'signedOut', error })
}

/**
 * Resume a session on page load, if there is one to resume.
 *
 * Called once at startup. The SPA cannot see the refresh cookie, so it cannot
 * know in advance whether a session exists — it simply attempts a renewal and
 * lets the answer decide. A 401 here is a first visit, not an error.
 */
export async function restore(): Promise<void> {
  await renew()
}

/**
 * Begin a login. Navigates away, so nothing after this runs.
 *
 * `returnTo` is the route the visitor was heading for; it is remembered across the
 * redirect only if it is a safe same-origin path, and any earlier one is dropped.
 */
export async function signIn(provider = 'dex', returnTo?: string): Promise<void> {
  const verifier = createVerifier()
  pkceVerifier.write(verifier)
  if (returnTo !== undefined && isSafeReturnPath(returnTo)) returnPath.write(returnTo)
  else returnPath.clear()
  window.location.assign(api.loginUrl(provider, await challengeFor(verifier)))
}

/** The route to land on after sign-in: the one remembered, once, else `/`. */
export function takeReturnPath(): string {
  const path = returnPath.read()
  returnPath.clear()
  return path !== null && isSafeReturnPath(path) ? path : '/'
}

/**
 * Finish a login from the query string the Auth service redirected back with.
 *
 * Returns whether a sign-in was completed, so the callback route can tell "the
 * user landed here mid-login" from "someone opened this URL directly".
 */
export async function completeSignIn(query: URLSearchParams): Promise<boolean> {
  const error = query.get('error')
  if (error) {
    pkceVerifier.clear()
    signedOut(describe(error))
    return false
  }

  const code = query.get('code')
  const verifier = pkceVerifier.read()
  if (!code || !verifier) {
    signedOut(code ? 'This sign-in was started in another tab.' : undefined)
    return false
  }

  // Single-use: clear before spending, so a re-render or a page refresh cannot
  // replay the exchange.
  pkceVerifier.clear()

  try {
    await adopt(await api.exchangeCode(code, verifier))
    return true
  } catch (caught) {
    signedOut(caught instanceof Error ? caught.message : 'Sign-in failed.')
    return false
  }
}

export async function changeWorkspace(workspaceId: string): Promise<void> {
  // Switching rotates the cookie just as renewal does, but it cannot join a
  // renewal — that would leave the user in the old workspace — so it waits its
  // turn. The loop re-checks, because another caller may take the cookie in the
  // moment this one wakes.
  while (spending) await spending
  await spend(async () => {
    try {
      await adopt(await api.switchWorkspace(workspaceId))
    } catch (caught) {
      signedOut(caught instanceof Error ? caught.message : undefined)
    }
  })
}

export async function signOut(): Promise<void> {
  const current = state
  if (current.status === 'signedIn') {
    // Best effort: the local session ends either way, and a failed revocation
    // must not leave the user apparently still signed in. The server clears the
    // cookie on the way through — this code could not.
    await api.logout(current.session.accessToken).catch(() => undefined)
  }
  signedOut()
}

/** Turn the error codes `/auth/callback` forwards into something readable. */
function describe(code: string): string {
  switch (code) {
    case 'access_denied':
      return 'Sign-in was declined at the identity provider.'
    case 'invalid_state':
      return 'That sign-in link has expired. Please try again.'
    case 'email_not_verified':
      return 'Your identity provider has not verified this email address.'
    case 'temporarily_unavailable':
      return 'Sign-in is temporarily unavailable. Please try again shortly.'
    case 'no_workspace':
      return 'This account does not belong to any workspace.'
    default:
      return `Sign-in failed (${code}).`
  }
}
