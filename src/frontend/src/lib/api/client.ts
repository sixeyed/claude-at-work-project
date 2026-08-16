/**
 * RFC 7807 Problem Details, unwrapped once for the whole app (Conventions §4.2).
 *
 * Every non-2xx on this platform is a problem document, so no call site should
 * be parsing one. What matters is that the parsing keeps `errors`: doc 06 §7
 * requires the field-level messages to render on a form, and a client that only
 * kept `detail` would leave "A channel name must start with a letter" with
 * nowhere to go but a banner.
 */

/** A failure a CollabHub service described in a Problem Details body. */
export class ProblemError extends Error {
  readonly status: number
  readonly title: string
  /** Field name → messages. Present on 400s; empty otherwise. */
  readonly errors: Record<string, string[]>

  constructor(status: number, message: string, title: string, errors: Record<string, string[]>) {
    super(message)
    this.name = 'ProblemError'
    this.status = status
    this.title = title
    this.errors = errors
  }

  /** The first message for a field, for rendering next to the input. */
  fieldError(field: string): string | undefined {
    return this.errors[field]?.[0]
  }
}

interface ProblemBody {
  title?: string
  detail?: string
  errors?: Record<string, string[]>
}

/**
 * Turn a failed response into a `ProblemError`.
 *
 * A service that is down or behind a broken proxy will not return a problem
 * document at all, so the body is parsed defensively and falls back to the
 * status text — an error with no message is worse than a vague one.
 */
export async function problemFrom(response: Response): Promise<ProblemError> {
  const body = (await response.json().catch(() => null)) as ProblemBody | null
  const title = body?.title ?? response.statusText
  return new ProblemError(
    response.status,
    body?.detail ?? title ?? 'Something went wrong.',
    title,
    body?.errors ?? {},
  )
}

/**
 * Build a `ProblemError` from an already-parsed problem body.
 *
 * `problemFrom` above takes a `Response`; this takes the document on its own,
 * because two callers have one but not the other: `openapi-fetch` hands back the
 * parsed error body rather than the response, and a Socket.IO acknowledgement
 * has no response at all. The server sends the same RFC 7807 document either
 * way, so one parser is enough — which is the whole reason the socket ack
 * carries a problem document rather than an error shape of its own.
 */
export function problemFromBody(status: number, body: unknown): ProblemError {
  const parsed = (body ?? {}) as ProblemBody
  const title = parsed.title ?? 'Something went wrong.'
  return new ProblemError(status, parsed.detail ?? title, title, parsed.errors ?? {})
}

/** Turn a thrown value into something safe to show a user. */
export function describeError(caught: unknown): string {
  return caught instanceof Error ? caught.message : 'Something went wrong.'
}

export function bearer(accessToken: string): Record<string, string> {
  return { Authorization: `Bearer ${accessToken}` }
}
