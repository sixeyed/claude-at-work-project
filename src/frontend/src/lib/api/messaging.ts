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

import { problemFromBody, type ProblemError } from './client'
import type { components, paths } from '../../types/messaging'

export type Channel = components['schemas']['ChannelResponse']
export type ChannelPage = components['schemas']['ChannelListResponse']
export type ChannelKind = 'public' | 'private'
export type ChannelMember = components['schemas']['ChannelMemberResponse']
export type ChannelMemberPage = components['schemas']['ChannelMemberListResponse']
export type ChannelMemberRole = components['schemas']['AddChannelMemberRequest']['role']
export type Message = components['schemas']['MessageResponse']
export type MessagePage = components['schemas']['MessageListResponse']

const MESSAGING_URL: string = import.meta.env.VITE_MESSAGING_URL ?? 'http://localhost:8002'

const client = createClient<paths>({ baseUrl: MESSAGING_URL })

/**
 * `openapi-fetch` hands back the parsed error body, not the `Response`, so the
 * status comes from the caller. The builder itself lives in `client.ts`,
 * because a Socket.IO acknowledgement needs the same one and has no `Response`
 * either.
 */
function problem(status: number, body: unknown): ProblemError {
  return problemFromBody(status, body)
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
  body: { name: string; topic?: string | null; kind: ChannelKind },
): Promise<Channel> {
  const { data, error, response } = await client.POST('/api/v1/channels', {
    headers: { Authorization: `Bearer ${accessToken}` },
    body,
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

/**
 * Rename a channel, or set its topic.
 *
 * `version` is the version the caller last read and is required: the server
 * refuses the write with a 409 if the row has moved on since. Sending an absent
 * `topic` leaves the topic alone; sending `null` clears it.
 */
export async function updateChannel(
  accessToken: string,
  channelId: string,
  body: { version: number; name?: string; topic?: string | null },
): Promise<Channel> {
  const { data, error, response } = await client.PATCH('/api/v1/channels/{channel_id}', {
    headers: { Authorization: `Bearer ${accessToken}` },
    params: { path: { channel_id: channelId } },
    body,
  })
  if (error !== undefined) throw problem(response.status, error)
  return data
}

/** Archive a channel. One-way — nothing in this API brings it back. */
export async function archiveChannel(accessToken: string, channelId: string): Promise<Channel> {
  const { data, error, response } = await client.DELETE('/api/v1/channels/{channel_id}', {
    headers: { Authorization: `Bearer ${accessToken}` },
    params: { path: { channel_id: channelId } },
  })
  if (error !== undefined) throw problem(response.status, error)
  return data
}

export async function listChannelMembers(
  accessToken: string,
  channelId: string,
  cursor?: string,
): Promise<ChannelMemberPage> {
  const { data, error, response } = await client.GET('/api/v1/channels/{channel_id}/members', {
    headers: { Authorization: `Bearer ${accessToken}` },
    params: { path: { channel_id: channelId }, query: cursor ? { cursor } : {} },
  })
  if (error !== undefined) throw problem(response.status, error)
  return data
}

/**
 * `role` is sent explicitly rather than left to the server's default. The
 * generated type treats a property with a `default` as always present, and
 * spelling it out here is cheaper than arguing with the generator — the value
 * is the same one the server would have picked.
 */
export async function addChannelMember(
  accessToken: string,
  channelId: string,
  body: { userId: string; role?: ChannelMemberRole },
): Promise<ChannelMember> {
  const { data, error, response } = await client.POST('/api/v1/channels/{channel_id}/members', {
    headers: { Authorization: `Bearer ${accessToken}` },
    params: { path: { channel_id: channelId } },
    body: { role: 'member', ...body },
  })
  if (error !== undefined) throw problem(response.status, error)
  return data
}

export async function removeChannelMember(
  accessToken: string,
  channelId: string,
  userId: string,
): Promise<void> {
  const { error, response } = await client.DELETE(
    '/api/v1/channels/{channel_id}/members/{user_id}',
    {
      headers: { Authorization: `Bearer ${accessToken}` },
      params: { path: { channel_id: channelId, user_id: userId } },
    },
  )
  if (error !== undefined) throw problem(response.status, error)
}

/**
 * A page of history, newest first.
 *
 * Newest-first is the wire order, matching the index the query walks. The SPA
 * reverses once on the way to the DOM, in `useMessages`'s `select` — not here,
 * because a second flip somewhere else is how a list ends up in the right order
 * by accident and the wrong order after the next change.
 */
export async function listMessages(
  accessToken: string,
  channelId: string,
  cursor?: string,
): Promise<MessagePage> {
  const { data, error, response } = await client.GET('/api/v1/channels/{channel_id}/messages', {
    headers: { Authorization: `Bearer ${accessToken}` },
    params: { path: { channel_id: channelId }, query: cursor ? { cursor } : {} },
  })
  if (error !== undefined) throw problem(response.status, error)
  return data
}

export async function sendMessage(
  accessToken: string,
  channelId: string,
  body: string,
): Promise<Message> {
  const { data, error, response } = await client.POST('/api/v1/channels/{channel_id}/messages', {
    headers: { Authorization: `Bearer ${accessToken}` },
    params: { path: { channel_id: channelId } },
    body: { body },
  })
  if (error !== undefined) throw problem(response.status, error)
  return data
}

export async function getMessage(accessToken: string, messageId: string): Promise<Message> {
  const { data, error, response } = await client.GET('/api/v1/messages/{message_id}', {
    headers: { Authorization: `Bearer ${accessToken}` },
    params: { path: { message_id: messageId } },
  })
  if (error !== undefined) throw problem(response.status, error)
  return data
}

/**
 * Rewrite a message.
 *
 * `version` is a precondition, not a field being assigned — the server refuses
 * with a 409 if the row moved on since the caller read it. Both fields are
 * required: there is only one editable field on a message, so there is no
 * "leave this one alone" case to express.
 */
export async function editMessage(
  accessToken: string,
  messageId: string,
  body: { body: string; version: number },
): Promise<Message> {
  const { data, error, response } = await client.PATCH('/api/v1/messages/{message_id}', {
    headers: { Authorization: `Bearer ${accessToken}` },
    params: { path: { message_id: messageId } },
    body,
  })
  if (error !== undefined) throw problem(response.status, error)
  return data
}

/**
 * Delete a message, and get the tombstone back.
 *
 * Deliberately not a 204. The row stays in the history with an empty body and
 * `deletedAt` set, and the client has to draw it — so the server returns what
 * to draw rather than making the client refetch a page it already holds.
 */
export async function deleteMessage(accessToken: string, messageId: string): Promise<Message> {
  const { data, error, response } = await client.DELETE('/api/v1/messages/{message_id}', {
    headers: { Authorization: `Bearer ${accessToken}` },
    params: { path: { message_id: messageId } },
  })
  if (error !== undefined) throw problem(response.status, error)
  return data
}
