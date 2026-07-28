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
 */

const VERIFIER_KEY = 'collabhub.pkceVerifier'

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
