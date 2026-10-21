/**
 * Settings: your display name, and the first per-user preference, the clock
 * (issue gh-5; register D28, D46).
 *
 * **Both sections read from the server on every visit.** The Profile form renders
 * only once *this* visit's read has succeeded (`isFetchedAfterMount`), because a
 * field takes its value once: a profile cached by an earlier visit would otherwise
 * prefill the field with a name that may since have changed. A failed read shows
 * an error and no form, rather than a form that would save over a name it never
 * saw.
 *
 * **Save is a convenience, not the rule.** It is disabled when the name is
 * unchanged, empty after trimming, or over 100 code points — the cases the
 * browser can see without asking. Everything else goes to the server, whose answer
 * (400 with `errors.displayName`, or 409 "That name is already taken.") renders on
 * the field. The full rule lives once, in Auth; JS `trim()` and Python `strip()`
 * differ on a few code points, which can only move a button, never what is stored.
 *
 * The clock is chosen with radios and saved at once; see `useSetClock` for how
 * saves are ordered and rolled back.
 */

import { useState } from 'react'
import { Link } from 'react-router-dom'

import { type Clock, type Profile } from '../../lib/auth/api'
import { ProblemError } from '../../lib/api/client'
import { useChatStore } from '../../stores/chat'
import { usePreferences, useSetClock } from './usePreferences'
import { useMyProfile, useRenameMe } from './useProfile'

interface Props {
  accessToken: string
  userId: string
}

const MAX_NAME_LENGTH = 100

/** The message to put on a field: the field's own, else the problem's. */
function messageFor(error: Error, field: string): string {
  return (error instanceof ProblemError ? error.fieldError(field) : undefined) ?? error.message
}

function ProfileSection({ accessToken, profile }: { accessToken: string; profile: Profile }) {
  const rename = useRenameMe(accessToken, profile.id)
  const [value, setValue] = useState(profile.displayName)
  const [saved, setSaved] = useState(false)

  const candidate = value.trim().normalize('NFC')
  const cannotSave =
    rename.isPending ||
    candidate === profile.displayName ||
    candidate === '' ||
    [...candidate].length > MAX_NAME_LENGTH

  function save() {
    rename.mutate(value, {
      onSuccess: (stored) => {
        // The server trims and composes: show the stored form back.
        setValue(stored.displayName)
        setSaved(true)
      },
    })
  }

  return (
    <form
      className="flex flex-col gap-2"
      onSubmit={(event) => {
        event.preventDefault()
        if (!cannotSave) save()
      }}
    >
      <label htmlFor="settings-display-name" className="text-sm font-medium text-ink">
        Display name
      </label>
      <input
        id="settings-display-name"
        data-testid="settings-display-name-input"
        type="text"
        value={value}
        onChange={(event) => {
          setValue(event.target.value)
          setSaved(false)
          rename.reset()
        }}
        aria-invalid={rename.isError}
        className="rounded border border-border bg-surface px-3 py-2 text-ink"
      />
      {rename.isError && (
        <p role="alert" className="text-sm text-danger">
          {messageFor(rename.error, 'displayName')}
        </p>
      )}
      <div className="flex items-center gap-3">
        <button
          type="submit"
          data-testid="settings-display-name-save"
          disabled={cannotSave}
          className="rounded bg-accent px-4 py-2 font-medium text-accent-ink disabled:opacity-50"
        >
          Save
        </button>
        {saved && (
          <p role="status" data-testid="settings-saved" className="text-sm text-ink-muted">
            Saved
          </p>
        )}
      </div>
    </form>
  )
}

const CLOCK_CHOICES: { label: string; value: Clock | null }[] = [
  { label: 'Automatic', value: null },
  { label: '12-hour', value: '12h' },
  { label: '24-hour', value: '24h' },
]

function PreferencesSection({ accessToken, userId }: Props) {
  const preferences = usePreferences(accessToken, userId, { refetchOnMount: 'always' })
  const setClock = useSetClock(accessToken, userId)
  const chosen = preferences.data?.clock ?? null

  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="text-sm font-medium text-ink">Clock</legend>
      {CLOCK_CHOICES.map((choice) => (
        <label key={choice.label} className="flex items-center gap-2 text-sm text-ink">
          <input
            type="radio"
            name="clock"
            checked={chosen === choice.value}
            onChange={() => setClock.mutate(choice.value)}
          />
          {choice.label}
        </label>
      ))}
      {setClock.isError && (
        <p role="alert" className="text-sm text-danger">
          {setClock.error.message}
        </p>
      )}
    </fieldset>
  )
}

export function SettingsPage({ accessToken, userId }: Props) {
  const profile = useMyProfile(accessToken, userId)
  const lastChannelId = useChatStore((state) => state.lastChannelId)

  return (
    <div data-testid="settings-page" className="flex max-w-xl flex-col gap-8 p-6">
      <div className="flex items-baseline justify-between">
        <h1 className="text-xl font-semibold text-ink">Settings</h1>
        <Link
          to={lastChannelId ? `/c/${lastChannelId}` : '/'}
          data-testid="back-to-chat"
          className="text-sm text-accent underline"
        >
          Back to chat
        </Link>
      </div>

      <section aria-labelledby="settings-profile" className="flex flex-col gap-3">
        <h2 id="settings-profile" className="text-lg font-medium text-ink">
          Profile
        </h2>
        {profile.isError ? (
          <p role="alert" className="text-sm text-danger">
            Couldn’t load your profile.
          </p>
        ) : profile.isSuccess && profile.isFetchedAfterMount ? (
          <ProfileSection accessToken={accessToken} profile={profile.data} />
        ) : (
          <p className="text-sm text-ink-muted">Loading…</p>
        )}
      </section>

      <section aria-labelledby="settings-preferences" className="flex flex-col gap-3">
        <h2 id="settings-preferences" className="text-lg font-medium text-ink">
          Preferences
        </h2>
        <PreferencesSection accessToken={accessToken} userId={userId} />
      </section>
    </div>
  )
}
