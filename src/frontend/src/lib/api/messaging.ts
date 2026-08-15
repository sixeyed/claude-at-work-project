/**
 * The Messaging service's REST surface (design doc 02 §3.1).
 *
 * The types are generated from the service's own OpenAPI document rather than
 * hand-written (register D23) — `npm run generate:api` regenerates
 * `src/types/messaging.ts` from `openapi/messaging.json`, which
 * `python -m messaging.openapi` produces without a running stack. A DTO copied
 * by hand is a DTO that drifts the first time a field is renamed.
 *
 * `openapi-fetch` returns `{ data, error }` rather than throwing. TanStack Query
 * wants a thrown error to mark a query failed, so each call converts once here
 * and nothing downstream sees the two-shaped result.
 */

import createClient from 'openapi-fetch'

import { ProblemError } from './client'
import type { components, paths } from '../../types/messaging'

export type Channel = components['schemas']['ChannelResponse']
export type ChannelPage = components['schemas']['ChannelListResponse']

const MESSAGING_URL: string = import.meta.env.VITE_MESSAGING_URL ?? 'http://localhost:8002'

const client = createClient<paths>({ baseUrl: MESSAGING_URL })

interface ProblemBody {
  title?: string
  detail?: string
  errors?: Record<string, string[]>
}

/**
 * `openapi-fetch` hands back the parsed error body, not the `Response`, so the
 * status comes from the caller. Anything unparsed is a service that failed
 * before it could describe itself.
 */
function problem(status: number, body: unknown): ProblemError {
  const parsed = (body ?? {}) as ProblemBody
  const title = parsed.title ?? 'Something went wrong.'
  return new ProblemError(status, parsed.detail ?? title, title, parsed.errors ?? {})
}

export async function listChannels(accessToken: string, cursor?: string): Promise<ChannelPage> {
  const { data, error, response } = await client.GET('/api/v1/channels', {
    headers: { Authorization: `Bearer ${accessToken}` },
    params: { query: cursor ? { cursor } : {} },
  })
  if (error !== undefined) throw problem(response.status, error)
  return data
}

export async function createChannel(
  accessToken: string,
  body: { name: string; topic?: string | null; kind?: string },
): Promise<Channel> {
  const { data, error, response } = await client.POST('/api/v1/channels', {
    headers: { Authorization: `Bearer ${accessToken}` },
    body: { kind: 'public', ...body },
  })
  if (error !== undefined) throw problem(response.status, error)
  return data
}

export async function getChannel(accessToken: string, channelId: string): Promise<Channel> {
  const { data, error, response } = await client.GET('/api/v1/channels/{channel_id}', {
    headers: { Authorization: `Bearer ${accessToken}` },
    params: { path: { channel_id: channelId } },
  })
  if (error !== undefined) throw problem(response.status, error)
  return data
}
