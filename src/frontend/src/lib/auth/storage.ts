/**
 * The one secret the browser tab has to keep. **Register D22 is settled.**
 *
 * D22 — "refresh-token storage: HttpOnly cookie vs. in-app secure storage" — was
 * decided on 2026-07-28 in favour of the cookie. So the refresh token is *not*
 * here, and cannot be: it is set by the Auth service with `HttpOnly`, which
 * means no code in this application can read it, including this file. The
 * browser attaches it to `/api/v1/auth` requests and that is the whole of the
 * SPA's involvement.
 *
 * What is left:
 *
 * - **The access token** lives in a variable in `session.ts` and dies with the
 *   tab. Short-lived and re-obtainable, so persisting it would add exposure and
 *   buy nothing.
 * - **The PKCE verifier** is here, in `sessionStorage`, because it has to
 *   survive a full-page redirect to the identity provider and back — a variable
 *   cannot. It is readable by any script on the origin, which is acceptable in a
 *   way the refresh token was not: it is single-use, lives for the seconds
 *   between leaving and returning, is useless without the matching authorization
 *   code, and is deleted before that code is spent.
 * - **The return path** is a second `sessionStorage` entry for the same reason: it
 *   is the route a signed-out visitor asked for, and it too must survive the
 *   redirect. Not a secret, but untrusted on the way back — see `isSafeReturnPath`.
 */

const VERIFIER_KEY = 'collabhub.pkceVerifier'
const RETURN_KEY = 'collabhub.returnTo'

function read(key: string): string | null {
  try {
    return window.sessionStorage.getItem(key)
  } catch {
    // Storage can throw in private modes and sandboxed frames. A sign-in that
    // cannot be resumed is better than a page that will not render.
    return null
  }
}

function write(key: string, value: string): void {
  try {
    window.sessionStorage.setItem(key, value)
  } catch {
    /* see read() */
  }
}

function clear(key: string): void {
  try {
    window.sessionStorage.removeItem(key)
  } catch {
    /* see read() */
  }
}

/**
 * The PKCE verifier, held only between leaving for the provider and coming back.
 * Cleared as soon as it is spent — it is single-use, and a verifier left behind
 * is one that outlives the code it protects.
 */
export const pkceVerifier = {
  read: () => read(VERIFIER_KEY),
  write: (verifier: string) => write(VERIFIER_KEY, verifier),
  clear: () => clear(VERIFIER_KEY),
}

/**
 * Whether `path` is somewhere sign-in may send the browser back to.
 *
 * The path comes from `sessionStorage`, which any script on the origin can write,
 * and ends up in a navigation — so only a same-origin path qualifies. `//host` and
 * `/\host` are protocol-relative to a browser, and `/sign-in` and `/auth/…` would
 * loop straight back into the flow that just finished.
 */
export function isSafeReturnPath(path: string): boolean {
  if (!path.startsWith('/') || path.startsWith('//') || path.startsWith('/\\')) return false
  return !path.startsWith('/sign-in') && !path.startsWith('/auth/')
}

/**
 * The route a signed-out visitor was heading for, held across the same redirect
 * the PKCE verifier survives. A path only — no token, no secret — and read once.
 */
export const returnPath = {
  read: () => read(RETURN_KEY),
  write: (path: string) => write(RETURN_KEY, path),
  clear: () => clear(RETURN_KEY),
}
