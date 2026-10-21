# Per-user preferences live in the Auth service

- **Status:** Accepted
- **Date:** 2026-10-21

## Context

Nothing in CollabHub stored a per-user choice. The palette is light-only, times render in the
browser's locale, and a theme, a locale or notification settings (D18) all needed the same missing
thing: a place to put them (register D28, open since 2026-08-15). Issue gh-5 needs the first one — a
12/24-hour clock — and so forces the decision.

## Decision

Auth owns preferences. A table `user_preferences(user_id, prefs jsonb, version, updated_at)` holds
one row per user, created by the first write; reading never creates it. They belong to the user, not
a workspace, so the same answer holds in every workspace they join.

`GET /api/v1/users/me/preferences` returns the stored keys the API knows (`{}` when none);
`PATCH` merges the keys it carries and a `null` removes one. Keys are validated by the API
(`extra="forbid"`), not by the database, so adding a preference is one more validated key and no
migration. The merge is a single `INSERT … ON CONFLICT DO UPDATE` under the row lock: two tabs
changing different keys both survive, and two first writes cannot collide. Both routes use
`require_user` and fail open when R1 is unreachable — they are not in Conventions §5.2's set.

The SPA holds preferences in TanStack Query only (D24). The display name stays on `users`. The first
preference is `clock`: `12h`, `24h`, or absent meaning the browser's locale.

## Consequences

- A theme, locale or notification setting is one more key and one more control; the table does not
  change.
- Preferences are not in the token, so a change shows on the next read; the SPA refetches on focus
  and on every visit to Settings.
- A row may hold keys the API no longer offers; they survive a merge and are left out of the
  response.

## Alternatives considered

- **A `preferences jsonb` column on `users`** — one fewer table, but every profile write and read
  would carry it, and `users` rows are rewritten by renames and avatar changes. A separate row keeps
  the two lifecycles apart.
- **A separate service** — more deployment for one small table, and every service already trusts Auth.
- **Putting them in the access token** — would go stale for up to its fifteen-minute life after a
  change, and tokens are for authorization.
