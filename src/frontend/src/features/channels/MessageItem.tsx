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
 * Everything you can do to the message — react, reply, edit, delete — is behind
 * one always-visible "⋯" button (`MessageActions`), at every width, because a
 * touch screen has no hover. **What it offers is `offeredActions`' rule**, which
 * is a courtesy and not authorization: the server decides who may edit and who
 * may delete.
 *
 * A deleted message renders its tombstone from `deletedAt`, never from the
 * empty `body`, carries no controls, and shows **no** edited marker even when
 * `editedAt` is set: "This message was deleted (edited)" is not something anyone
 * needs to read.
 */

import { type ReactNode, useEffect, useRef, useState } from 'react'

import type { Message } from '../../lib/api/messaging'
import { formatTime, useClock } from '../settings/clock'
import { ThreadSummary } from '../threads/ThreadSummary'
import { offeredActions } from './actionRules'
import { MessageActions } from './MessageActions'
import { MessageEditor } from './MessageEditor'
import { ReactionBar } from './ReactionBar'
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
  const triggerRef = useRef<HTMLButtonElement>(null)
  const wasEditing = useRef(false)

  const deleted = message.deletedAt !== null
  // Sent, not yet confirmed. The `temp:` id *is* the marker — there is no
  // parallel map of in-flight sends, because that would be a second copy of the
  // message list.
  const pending = isPending(message)
  const actions = offeredActions(message, { userId, myRole, threads: onOpenThread !== undefined })

  // When editing ends — saved or cancelled — focus returns to "⋯", where it was
  // before Edit was chosen. Never on mount: only the true → false edge.
  useEffect(() => {
    if (wasEditing.current && !editing) triggerRef.current?.focus({ preventScroll: true })
    wasEditing.current = editing
  }, [editing])

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
      className={`flex flex-col gap-0.5 px-6 py-2 transition-colors duration-700 ${pending ? 'opacity-50' : ''} ${highlighted ? 'bg-accent/15' : ''}`}
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

        {actions.length > 0 && (
          <MessageActions
            actions={actions}
            onReact={onToggleReaction}
            onReply={() => onOpenThread?.()}
            onEdit={() => setEditing(true)}
            onDelete={onDelete}
            triggerRef={triggerRef}
          />
        )}
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
        <p data-testid="message-body" className="text-sm whitespace-pre-wrap text-ink [overflow-wrap:anywhere]">
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
