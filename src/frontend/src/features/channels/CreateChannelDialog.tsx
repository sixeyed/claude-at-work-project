/**
 * Create a channel.
 *
 * The server owns the naming rules and this form does not restate them — a
 * regex here would be a second copy to drift, and the one that matters is the
 * one guarding the database. What the form does do is render what the server
 * says: `errors.name` against the field (doc 06 §7), `detail` in the banner for
 * anything without a field, such as the 409 on a duplicate name.
 */

import { useState, type FormEvent } from 'react'

import { ProblemError } from '../../lib/api/client'
import { useCreateChannel } from './useChannels'

interface Props {
  accessToken: string
  workspaceId: string | null
  onCreated: (channelId: string) => void
}

export function CreateChannelDialog({ accessToken, workspaceId, onCreated }: Props) {
  const [name, setName] = useState('')
  const create = useCreateChannel(accessToken, workspaceId)

  const problem = create.error instanceof ProblemError ? create.error : undefined
  const nameError = problem?.fieldError('name')
  // A duplicate name is a 409 with no `errors` map, so it has no field to sit
  // against — it belongs in the banner.
  const bannerError = problem && !nameError ? problem.message : undefined

  function submit(event: FormEvent) {
    event.preventDefault()
    create.mutate(
      { name },
      {
        onSuccess: (channel) => {
          setName('')
          onCreated(channel.id)
        },
      },
    )
  }

  return (
    <form onSubmit={submit} data-testid="create-channel-form" className="flex flex-col gap-2 p-3">
      <label htmlFor="channel-name" className="text-xs font-medium text-ink-muted uppercase">
        New channel
      </label>
      <div className="flex gap-2">
        <input
          id="channel-name"
          data-testid="create-channel-name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="general"
          autoComplete="off"
          className="min-w-0 flex-1 rounded border border-border bg-surface px-2 py-1 text-sm text-ink"
        />
        <button
          type="submit"
          data-testid="create-channel-submit"
          disabled={create.isPending}
          className="rounded bg-accent px-3 py-1 text-sm font-medium text-accent-ink disabled:opacity-60"
        >
          {create.isPending ? 'Creating…' : 'Create'}
        </button>
      </div>

      {nameError && (
        <p data-testid="create-channel-name-error" role="alert" className="text-sm text-danger">
          {nameError}
        </p>
      )}
      {bannerError && (
        <p
          data-testid="create-channel-error"
          role="alert"
          className="rounded bg-danger-surface px-2 py-1 text-sm text-danger"
        >
          {bannerError}
        </p>
      )}
    </form>
  )
}
