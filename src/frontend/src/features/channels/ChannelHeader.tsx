/**
 * The open channel's name, topic and — for an admin — its controls.
 *
 * Extracted from the inline `<header>` `ChannelView` used to carry, because
 * this is where the authority rule becomes visible: **the rename form and the
 * archive button render only when `myRole === 'admin'`.** The server refuses a
 * non-admin write with a 403 regardless, so this is not the guard; it is the
 * reason the Gherkin can assert "a member is not offered the controls" rather
 * than trying to click one that is not there.
 *
 * Archiving asks first, and the wording says what it costs. Every read in the
 * service filters archived channels out, so there is no un-archive and no
 * "archived" view to find it in again — a control that irreversible should not
 * be one click. The confirmation is an inline button rather than
 * `window.confirm`, which would block the page and take the browser tests with
 * it.
 */

import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'

import { ProblemBanner } from '../../components/ProblemBanner'
import { ProblemError } from '../../lib/api/client'
import type { Channel } from '../../lib/api/messaging'
import { useArchiveChannel, useRenameChannel } from './useChannels'

interface Props {
  accessToken: string
  workspaceId: string | null
  channel: Channel
}

export function ChannelHeader({ accessToken, workspaceId, channel }: Props) {
  const navigate = useNavigate()
  const [renaming, setRenaming] = useState(false)
  const [name, setName] = useState(channel.name)
  const [confirmingArchive, setConfirmingArchive] = useState(false)

  const rename = useRenameChannel(accessToken, workspaceId, channel.id)
  const archive = useArchiveChannel(accessToken, workspaceId, channel.id)

  const isAdmin = channel.myRole === 'admin'
  const problem = rename.error instanceof ProblemError ? rename.error : undefined
  const nameError = problem?.fieldError('name')

  function submitRename(event: FormEvent) {
    event.preventDefault()
    // `version` is the one the cache holds; the server refuses the write with a
    // 409 if the row has moved on since it was read.
    rename.mutate(
      { version: channel.version, name },
      { onSuccess: () => setRenaming(false) },
    )
  }

  return (
    <header className="flex flex-col gap-2 border-b border-border px-6 py-4">
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <h2 data-testid="channel-header-name" className="text-lg font-semibold text-ink">
            <span aria-hidden="true" className="opacity-50">
              #
            </span>{' '}
            {channel.name}
          </h2>
          {channel.topic && <p className="text-sm text-ink-muted">{channel.topic}</p>}
        </div>

        {isAdmin && (
          <div data-testid="channel-controls" className="flex shrink-0 gap-2">
            <button
              type="button"
              data-testid="channel-rename-open"
              onClick={() => {
                setName(channel.name)
                setRenaming((open) => !open)
              }}
              className="rounded border border-border px-2 py-1 text-xs text-ink"
            >
              Rename
            </button>
            <button
              type="button"
              data-testid="channel-archive"
              onClick={() => setConfirmingArchive(true)}
              className="rounded border border-border px-2 py-1 text-xs text-danger"
            >
              Archive
            </button>
          </div>
        )}
      </div>

      {isAdmin && renaming && (
        <form onSubmit={submitRename} data-testid="channel-rename-form" className="flex gap-2">
          <input
            data-testid="channel-rename-input"
            value={name}
            onChange={(event) => setName(event.target.value)}
            aria-label="Channel name"
            autoComplete="off"
            className="min-w-0 flex-1 rounded border border-border bg-surface px-2 py-1 text-sm text-ink"
          />
          <button
            type="submit"
            data-testid="channel-rename-submit"
            disabled={rename.isPending}
            className="rounded bg-accent px-3 py-1 text-sm font-medium text-accent-ink disabled:opacity-60"
          >
            {rename.isPending ? 'Saving…' : 'Save'}
          </button>
        </form>
      )}

      {nameError && (
        <p data-testid="channel-rename-error" role="alert" className="text-sm text-danger">
          {nameError}
        </p>
      )}
      {!nameError && <ProblemBanner error={rename.error ?? archive.error} />}

      {isAdmin && confirmingArchive && (
        <div data-testid="channel-archive-confirm-panel" className="flex items-center gap-3">
          <p className="text-sm text-ink">
            Archive #{channel.name}? Nobody will be able to open it again.
          </p>
          <button
            type="button"
            data-testid="channel-archive-confirm"
            disabled={archive.isPending}
            onClick={() =>
              archive.mutate(undefined, {
                // The channel this route points at is now invisible to the
                // server, so staying here would render its 404.
                onSuccess: () => navigate('/'),
              })
            }
            className="rounded bg-danger px-3 py-1 text-sm font-medium text-accent-ink disabled:opacity-60"
          >
            {archive.isPending ? 'Archiving…' : 'Archive'}
          </button>
          <button
            type="button"
            data-testid="channel-archive-cancel"
            onClick={() => setConfirmingArchive(false)}
            className="text-sm text-ink-muted underline"
          >
            Cancel
          </button>
        </div>
      )}
    </header>
  )
}
