/**
 * PKCE for the browser half of the login (RFC 7636).
 *
 * The SPA generates a verifier, sends only its SHA-256 to `/auth/login/{provider}`,
 * and reveals the verifier at `/auth/token`. That is what makes the authorization
 * code safe to receive in a redirect URL: the code lands in the address bar and
 * in browser history, so on its own it must not be enough to obtain a session.
 *
 * The verifier has to outlive a full-page navigation to the identity provider
 * and back, so it cannot live in a variable — see `storage.ts`.
 */

const VERIFIER_BYTES = 32

/** base64url without padding, as every OAuth spec expects. */
function base64url(bytes: ArrayBuffer | Uint8Array): string {
  const view = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes)
  let binary = ''
  for (const byte of view) {
    binary += String.fromCharCode(byte)
  }
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

/** A fresh code verifier — 256 bits from the platform CSPRNG. */
export function createVerifier(): string {
  return base64url(crypto.getRandomValues(new Uint8Array(VERIFIER_BYTES)))
}

/** The S256 challenge derived from a verifier. */
export async function challengeFor(verifier: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier))
  return base64url(digest)
}
