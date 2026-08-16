/**
 * One message: who said it, when, what they said, and what you may do to it.
 *
 * The author is a bare id on the wire — Messaging owns no user records
 * (Conventions §2) — so the name is resolved through `useWorkspaceMembers`,
 * the one directory every part of the UI shares. Someone who has left the
 * workspace renders as a shortened id rather than a blank, because a row with
 * no label in it looks like a bug.
 *
 * The timestamp renders through `<time dateTime>` with the browser's own
 * locale formatting, and **not** a stored preference: there is no
 * user-preferences feature anywhere in the design (register D28 🔴), which is
 * the same reason the palette is light-only. The `dateTime` attribute is the
 * machine-readable half, and it is what the acceptance suite asserts on so the
 * test does not depend on the locale of whoever runs it.
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

import { useState } from 'react'

import type { Message } from '../../lib/api/messaging'
import { MessageEditor } from './MessageEditor'
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
}

function timeOfDay(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
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
}: Props) {
  const [editing, setEditing] = useState(false)

  const deleted = message.deletedAt !== null
  // Sent, not yet confirmed. The `temp:` id *is* the marker — there is no
  // parallel map of in-flight sends, because that would be a second copy of the
  // message list.
  const pending = isPending(message)
  const isAuthor = message.authorId === userId
  const canEdit = !deleted && !pending && isAuthor
  const canDelete = !deleted && !pending && (isAuthor || myRole === 'admin')

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
      className={`group flex flex-col gap-0.5 px-6 py-2 ${pending ? 'opacity-50' : ''}`}
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
          {timeOfDay(message.createdAt)}
        </time>

        {!deleted && message.editedAt && (
          <span data-testid="message-edited" className="text-xs text-ink-muted">
            (edited)
          </span>
        )}

        <span className="ml-auto flex gap-2 opacity-0 group-hover:opacity-100 focus-within:opacity-100">
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
    </article>
  )
}
