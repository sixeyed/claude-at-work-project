/**
 * The Auth service's HTTP surface, as the SPA uses it (design doc 01 §3).
 *
 * Every response on the platform that is not a 2xx is an RFC 7807 Problem
 * Details document (Conventions §4.2). The unwrapping now lives in
 * `lib/api/client.ts` so the Messaging client shares it — and so that the
 * `errors` map survives, which a form needs and this module used to discard.
 */

import { problemFrom } from '../api/client'

export { ProblemError } from '../api/client'

const AUTH_URL: string = import.meta.env.VITE_AUTH_URL ?? 'http://localhost:8001'

/**
 * What a sign-in returns. There is no refresh token here — it arrives as an
 * `HttpOnly` cookie this code cannot read (register D22), and the browser sends
 * it back on its own.
 */
export interface TokenPair {
  accessToken: string
  tokenType: string
  expiresIn: number
}

export interface Profile {
  id: string
  email: string
  displayName: string
  avatarAsset: string | null
}

export interface Workspace {
  id: string
  name: string
  role: string
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${AUTH_URL}${path}`, {
    ...init,
    // Without this the browser drops the refresh cookie on a cross-origin call,
    // and every renewal silently fails as though the session had expired.
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...init.headers },
  })

  if (!response.ok) {
    throw await problemFrom(response)
  }

  return response.status === 204 ? (undefined as T) : ((await response.json()) as T)
}

function authorized(accessToken: string): HeadersInit {
  return { Authorization: `Bearer ${accessToken}` }
}

/**
 * Where to send the browser to begin a login.
 *
 * A full-page navigation, not a fetch: the identity provider needs to show its
 * own login page on its own origin, and it will refuse to be framed.
 */
export function loginUrl(provider: string, codeChallenge: string): string {
  const query = new URLSearchParams({ codeChallenge, codeChallengeMethod: 'S256' })
  return `${AUTH_URL}/api/v1/auth/login/${provider}?${query}`
}

export function exchangeCode(code: string, codeVerifier: string): Promise<TokenPair> {
  return request<TokenPair>('/api/v1/auth/token', {
    method: 'POST',
    body: JSON.stringify({ grantType: 'authorization_code', code, codeVerifier }),
  })
}

/** Renew the session the cookie identifies. No argument — there is nothing to pass. */
export function refresh(): Promise<TokenPair> {
  return request<TokenPair>('/api/v1/auth/refresh', { method: 'POST' })
}

export function switchWorkspace(workspaceId: string): Promise<TokenPair> {
  return request<TokenPair>('/api/v1/auth/switch-workspace', {
    method: 'POST',
    body: JSON.stringify({ workspaceId }),
  })
}

export function logout(accessToken: string): Promise<void> {
  return request<void>('/api/v1/auth/logout', {
    method: 'POST',
    headers: authorized(accessToken),
  })
}

export function me(accessToken: string): Promise<Profile> {
  return request<Profile>('/api/v1/users/me', { headers: authorized(accessToken) })
}

export function workspaces(accessToken: string): Promise<{ items: Workspace[] }> {
  return request<{ items: Workspace[] }>('/api/v1/workspaces', { headers: authorized(accessToken) })
}
