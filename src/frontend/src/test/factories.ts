/**
 * Server-shaped values for tests, typed from the generated schema (D23).
 *
 * Every field is filled, so a factory built value is exactly what the API
 * could send, and a test names only the fields its behaviour depends on.
 * Ids are fresh per call so two factory values never collide by accident.
 */

import type { Channel, Message, MessagePage } from '../lib/api/messaging'
import type { WorkspaceMember } from '../lib/auth/api'
import type { Session } from '../lib/auth/session'

const AT = '2026-09-15T09:00:00Z'

export const WORKSPACE_ID = '0199a000-0000-7000-8000-0000000000f0'

function id(): string {
  return crypto.randomUUID()
}

export function aChannel(overrides: Partial<Channel> = {}): Channel {
  return {
    id: id(),
    name: 'general',
    topic: null,
    kind: 'public',
    createdBy: id(),
    createdAt: AT,
    updatedAt: AT,
    archivedAt: null,
    version: 0,
    myRole: null,
    lastReadId: null,
    unreadCount: 0,
    ...overrides,
  }
}

export function aMessage(overrides: Partial<Message> = {}): Message {
  return {
    id: id(),
    channelId: id(),
    authorId: id(),
    threadRootId: null,
    body: 'hello',
    attachments: [],
    createdAt: AT,
    editedAt: null,
    deletedAt: null,
    version: 0,
    ...overrides,
  }
}

/** One page of history, newest first — the wire order. */
export function aMessagePage(items: Message[], nextCursor: string | null = null): MessagePage {
  return { items, nextCursor }
}

export function aWorkspaceMember(
  overrides: { id?: string; displayName?: string; role?: string } = {},
): WorkspaceMember {
  const userId = overrides.id ?? id()
  const displayName = overrides.displayName ?? 'Ada Lovelace'
  return {
    user: {
      id: userId,
      email: `${displayName.split(' ')[0].toLowerCase()}@collabhub.dev`,
      displayName,
      avatarAsset: null,
    },
    role: overrides.role ?? 'member',
    joinedAt: AT,
  }
}

export function aSession(overrides: Partial<Session> = {}): Session {
  return {
    accessToken: 'test-token',
    profile: {
      id: id(),
      email: 'ada@collabhub.dev',
      displayName: 'Ada Lovelace',
      avatarAsset: null,
    },
    workspaces: [{ id: WORKSPACE_ID, name: 'CollabHub', role: 'owner' }],
    activeWorkspaceId: WORKSPACE_ID,
    ...overrides,
  }
}
