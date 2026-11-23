/**
 * What a message row offers — the one place the `can*` rules live.
 *
 * **Hiding a control is a courtesy, not authorization.** The server decides who
 * may edit and who may delete, and the integration tests are what prove it.
 * What this decides is what to *offer*: an author edits their own words, and an
 * author or a channel admin deletes. Not the other way round — deleting
 * someone's message is moderation, rewriting it under their name is forgery, so
 * no role gets an edit control on somebody else's message.
 */

import type { Message } from '../../lib/api/messaging'
import { isPending } from './useMessages'

export type MessageAction = 'react' | 'reply' | 'edit' | 'delete'

export interface Viewer {
  userId: string
  /** The caller's role in this channel — `admin` may delete anyone's message. */
  myRole: string | null
  /** The row can open a thread — `MessageItem` got `onOpenThread`. */
  threads: boolean
}

/**
 * The actions this message allows this viewer, in this order always: react,
 * reply, edit, delete. Empty for a pending or deleted message.
 */
export function offeredActions(message: Message, viewer: Viewer): MessageAction[] {
  // A tombstone takes none, and the server clears the reactions it had. A pending
  // message (the `temp:` id *is* the marker) is not yet something the server knows.
  if (message.deletedAt !== null || isPending(message)) return []

  const isAuthor = message.authorId === viewer.userId
  const actions: MessageAction[] = ['react']
  // Threads are single-level: only a confirmed, live, top-level message takes a
  // reply. The thread *summary* is not held to this — a deleted root keeps its
  // thread, and the summary is the only way back into it.
  if (viewer.threads && message.threadRootId === null) actions.push('reply')
  if (isAuthor) actions.push('edit')
  if (isAuthor || viewer.myRole === 'admin') actions.push('delete')
  return actions
}
