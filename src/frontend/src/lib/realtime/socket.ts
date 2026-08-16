/**
 * The Socket.IO connection to the Messaging service (doc 02 §3.2).
 *
 * One function, because there is exactly one decision to get right here and it
 * is easy to get wrong: **`/messaging` is a namespace, not a path.**
 * socket.io-client parses a trailing path on the URL as the namespace to join,
 * which is what the server registered its handlers under. Setting `path:
 * '/messaging'` instead — the other option the API offers — points engine.io at
 * a URL the server does not serve, and the symptom is a handshake that 404s
 * with no mention of namespaces anywhere.
 *
 * The token travels in the handshake `auth` payload rather than the query
 * string. Conventions §6 allows both, and the query string is the fallback
 * because it ends up in access logs.
 *
 * `withCredentials` stays off: the refresh cookie is scoped to `/api/v1/auth`
 * (Conventions §5.1), so it would not be sent anyway, and the handshake carries
 * its own bearer token.
 */

import { io, type Socket } from 'socket.io-client'

const MESSAGING_URL: string = import.meta.env.VITE_MESSAGING_URL ?? 'http://localhost:8002'

export function connect(accessToken: string): Socket {
  return io(`${MESSAGING_URL}/messaging`, {
    auth: { token: accessToken },
    transports: ['websocket', 'polling'],
  })
}

export type { Socket }
