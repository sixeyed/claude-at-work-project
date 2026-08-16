/**
 * Editing a message in place.
 *
 * Seeded from the current body rather than starting empty, because an edit is a
 * correction and almost never a rewrite. Enter saves and Shift+Enter breaks a
 * line, matching the composer — two boxes in the same column behaving
 * differently would be its own bug report.
 *
 * The two error shapes are split the way every form on this platform splits
 * them: `errors.body` goes against the input, and anything without a field goes
 * in the banner. The 409 from a version conflict is the case that makes this
 * worth doing — it has no `errors` map, and rendering it against the textarea
 * would say "this text is wrong" about text that is fine.
 */

import { useState, type FormEvent, type KeyboardEvent } from 'react'

import { ProblemError } from '../../lib/api/client'
import type { Message } from '../../lib/api/messaging'

interface Props {
  message: Message
  error: unknown
  pending: boolean
  onSave: (body: string) => void
  onCancel: () => void
}

export function MessageEditor({ message, error, pending, onSave, onCancel }: Props) {
  const [body, setBody] = useState(message.body)

  const problem = error instanceof ProblemError ? error : undefined
  const bodyError = problem?.fieldError('body')
  const bannerError = problem && !bodyError ? problem.message : undefined

  function submit(event?: FormEvent) {
    event?.preventDefault()
    onSave(body)
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submit()
    }
    if (event.key === 'Escape') onCancel()
  }

  return (
    <form onSubmit={submit} data-testid="message-editor" className="flex flex-col gap-1">
      <textarea
        data-testid="message-editor-input"
        value={body}
        onChange={(event) => setBody(event.target.value)}
        onKeyDown={onKeyDown}
        rows={2}
        aria-label="Edit message"
        autoFocus
        className="w-full resize-none rounded border border-border bg-surface px-2 py-1 text-sm text-ink"
      />
      <div className="flex items-center gap-2">
        <button
          type="submit"
          data-testid="message-editor-save"
          disabled={pending}
          className="rounded bg-accent px-3 py-1 text-xs font-medium text-accent-ink disabled:opacity-60"
        >
          {pending ? 'Saving…' : 'Save'}
        </button>
        <button
          type="button"
          data-testid="message-editor-cancel"
          onClick={onCancel}
          className="text-xs text-ink-muted underline"
        >
          Cancel
        </button>
      </div>

      {bodyError && (
        <p data-testid="message-editor-error" role="alert" className="text-sm text-danger">
          {bodyError}
        </p>
      )}
      {bannerError && (
        <p
          data-testid="message-editor-error"
          role="alert"
          className="rounded bg-danger-surface px-2 py-1 text-sm text-danger"
        >
          {bannerError}
        </p>
      )}
    </form>
  )
}
