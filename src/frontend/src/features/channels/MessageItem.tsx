/**
 * One message: who said it, when, what they said, and what you may do to it.
 *
 * The author is a bare id on the wire — Messaging owns no user records
 * (Conventions §2) — so the name is resolved through `useWorkspaceMembers`,
 * the one directory every part of the UI shares. Someone who has left the
 * workspace renders as a shortened id rather than a blank, because a row with
 * no label in it looks like a bug.
 *
 * The timestamp renders through `<time dateTime>` in the browser's own locale,
 * with the hour cycle the user's clock preference asks for (register D28; none
 * set means the locale's own). The `dateTime` attribute is the machine-readable
 * half, and it is what the acceptance suite asserts on so the test does not
 * depend on the locale of whoever runs it.
 *
 * **Hiding a control is a courtesy, not authorization.** The server decides who
 * may edit and who may delete, and the integration tests are what prove it.
 * What this file decides is what to *offer*: an author edits their own words,
 * and an author or a channel admin deletes. Not the other way round — deleting
 * someone's message is moderation, rewriting it under their name is forgery, so
 * no role gets an edit control on somebody else's message.
 *
 * A deleted message renders its tombstone from `deletedAt`, never from the
 * empty `body`, carries no controls, and shows **no** edited marker even when
 * `editedAt` is set: "This message was deleted (edited)" is not something anyone
 * needs to read.
 */

import { type ReactNode, useState } from 'react'

import type { Message } from '../../lib/api/messaging'
import { formatTime, useClock } from '../settings/clock'
import { ThreadSummary } from '../threads/ThreadSummary'
import { MessageEditor } from './MessageEditor'
import { ReactionBar } from './ReactionBar'
import { ReactionPicker } from './ReactionPicker'
import { isPending } from './useMessages'

interface Props {
  message: Message
  authorName: string
  /** The signed-in user, so the row knows whether these are their own words. */
  userId: string
  /** The caller's role in this channel — `admin` may delete anyone's message. */
  myRole: string | null
  editError: unknown
  editPending: boolean
  onEdit: (body: string, version: number) => void
  onDelete: () => void
  /** Add or take back one reaction — the row does not know which, the cache does. */
  onToggleReaction: (emoji: string) => void
  /**
   * Open this message's thread. Optional because only the channel's list offers
   * it: the thread panel's own rows are the thread, so they pass nothing and show
   * neither the action nor the summary.
   */
  onOpenThread?: () => void
  /** The target of a jump from search, for the two seconds it is highlighted. */
  highlighted?: boolean
  /**
   * The message's files, drawn by `AttachmentList`. A slot rather than props
   * because fetching a URL needs the token and workspace, which the row has no
   * other use for; `MessageList` fills it when the message has any.
   */
  attachments?: ReactNode
}

export function MessageItem({
  message,
  authorName,
  userId,
  myRole,
  editError,
  editPending,
  onEdit,
  onDelete,
  onToggleReaction,
  onOpenThread,
  highlighted = false,
  attachments,
}: Props) {
  const [editing, setEditing] = useState(false)
  const clock = useClock()

  const deleted = message.deletedAt !== null
  // Sent, not yet confirmed. The `temp:` id *is* the marker — there is no
  // parallel map of in-flight sends, because that would be a second copy of the
  // message list.
  const pending = isPending(message)
  const isAuthor = message.authorId === userId
  const canEdit = !deleted && !pending && isAuthor
  const canDelete = !deleted && !pending && (isAuthor || myRole === 'admin')
  // Anyone who can see the message may react to it — reacting is talking, not
  // moderating. A tombstone takes none, and the server clears the ones it had.
  const canReact = !deleted && !pending
  // Threads are single-level: only a confirmed, live, top-level message takes a
  // reply. The *summary* below is not held to this — a deleted root keeps its
  // thread (R10), and the summary is the only way back into it.
  const canReply = onOpenThread !== undefined && !deleted && !pending && message.threadRootId === null

  function save(body: string) {
    // The version the cache holds; the server refuses with a 409 if the row has
    // moved on since it was read.
    onEdit(body, message.version)
    setEditing(false)
  }

  return (
    <article
      data-testid="message-item"
      data-message-id={message.id}
      data-pending={pending ? 'true' : 'false'}
      data-highlighted={highlighted ? 'true' : undefined}
      // The transition is always on, so dropping the highlight class is the fade.
      className={`group flex flex-col gap-0.5 px-6 py-2 transition-colors duration-700 ${pending ? 'opacity-50' : ''} ${highlighted ? 'bg-accent/15' : ''}`}
    >
      <div className="flex items-baseline gap-2">
        <span data-testid="message-author" className="text-sm font-medium text-ink">
          {authorName}
        </span>
        <time
          data-testid="message-time"
          dateTime={message.createdAt}
          className="text-xs text-ink-muted"
        >
          {formatTime(message.createdAt, clock)}
        </time>

        {!deleted && message.editedAt && (
          <span data-testid="message-edited" className="text-xs text-ink-muted">
            (edited)
          </span>
        )}

        <span className="ml-auto flex gap-2 opacity-0 group-hover:opacity-100 focus-within:opacity-100">
          {canReact && <ReactionPicker onPick={onToggleReaction} />}
          {canReply && (
            <button
              type="button"
              data-testid="thread-open"
              onClick={onOpenThread}
              className="text-xs text-ink-muted underline"
            >
              Reply in thread
            </button>
          )}
          {canEdit && (
            <button
              type="button"
              data-testid="message-edit"
              onClick={() => setEditing(true)}
              className="text-xs text-ink-muted underline"
            >
              Edit
            </button>
          )}
          {canDelete && (
            <button
              type="button"
              data-testid="message-delete"
              onClick={onDelete}
              className="text-xs text-danger underline"
            >
              Delete
            </button>
          )}
        </span>
      </div>

      {deleted ? (
        <p data-testid="message-deleted" className="text-sm text-ink-muted italic">
          This message was deleted.
        </p>
      ) : editing ? (
        <MessageEditor
          message={message}
          error={editError}
          pending={editPending}
          onSave={save}
          onCancel={() => setEditing(false)}
        />
      ) : (
        <p data-testid="message-body" className="text-sm whitespace-pre-wrap text-ink">
          {message.body}
        </p>
      )}

      {/* A tombstone shows no files, whatever the slot holds. */}
      {!deleted && attachments}

      {!deleted && <ReactionBar reactions={message.reactions} onToggle={onToggleReaction} />}

      {onOpenThread && (
        <ThreadSummary
          replyCount={message.replyCount}
          lastReplyAt={message.lastReplyAt}
          onOpen={onOpenThread}
        />
      )}
    </article>
  )
}
