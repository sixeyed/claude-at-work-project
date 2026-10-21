# Change your display name, with unique names and a preferences page

## Summary

A signed-in user can change their own display name on a new Settings page. Display names become unique across all of CollabHub, so nobody can pass themselves off as someone else. The same page holds the first per-user preference, a 12/24-hour clock, which settles where preferences live (register D28).

## Services touched

**Auth and the SPA.** Read `docs/design/01-auth-service.md` §3 (endpoints) and §4 (tables), `docs/design/06-frontend-spa.md` §3, §5.2 (*Names*) and §9, and `docs/design/00-platform-conventions.md` §5.1–§5.2. Messaging and the Worker are not changed: no service but Auth stores a name.

## What exists already

- `users.display_name text NOT NULL`, with no length limit, no uniqueness and no index (`auth/models.py:43`, migration `0001_initial_schema.py:33`).
- A name is created only in `identities.provision_user` (`identities.py:85-105`), on a first sign-in, from the IdP's `name` claim, else `preferred_username`, else the email's local part (`oidc.py:248-252`). The same call names the user's own workspace `"{display_name}'s Workspace"`. `link_identity` never touches the name of an existing user, so a later sign-in never overwrites it.
- `PATCH /api/v1/users/me` (`routers/users.py:39-77`) takes `UpdateUserRequest {displayName: 1..100, avatarAsset}`, applies only the fields sent, and returns `UserResponse`. It does not trim, so `"   "` passes. Nothing in the SPA calls it. `GET /api/v1/users/me` and `GET /api/v1/users/{id}` (shared-workspace only, else 404) exist.
- The access token carries a `name` claim from `user.display_name` (`sessions.py:51-57`); `/auth/refresh` re-reads the user. Nothing in the SPA reads `name`.
- The SPA's own name: `Session.profile` in `lib/auth/session.ts`, re-read only in `adopt()` (sign-in, renewal, workspace switch), shown once as `<p data-testid="current-user">` in `WorkspaceSwitcher.tsx:26`. There is no settings page, user menu or profile UI.
- Everyone's name elsewhere — message authors, thread replies, DMs, member panel, typing, search — comes from `useWorkspaceMembers` (`directoryKeys.members(ws)`, `staleTime` 5 minutes, refetched on focus, reconnect, mount and an unknown id; commit `a146ca3`). Doc 06 §5.2 says "Renames are not covered".
- Auth's client types are hand-typed in `src/frontend/src/lib/auth/api.ts` (`Profile`, `me`, `workspaceMembers`); Auth has no `openapi` module.
- Times are formatted with the browser's locale in three places: `MessageItem.tsx:69`, `ThreadSummary.tsx:17`, `SearchResult.tsx:23`.
- The nearest templates: channel rename (`ChannelHeader.tsx` + `useRenameChannel`) for an edit form with Problem Details errors; issue 7 (`a146ca3`) for the directory.

## Requirements

1. **Rename yourself.** A signed-in user changes their own display name, and only their own, from the Profile section of `/settings`. The name is trimmed of Unicode whitespace (Python `str.strip()`) and normalised to NFC, and stored that way; after that it is 1–100 characters and holds no character that is in Unicode general category Cc, Cf, Cs, Co, Cn, Zl or Zp, or that has the `Default_Ignorable_Code_Point` property. Refused: `"Grace\u200B"` (zero-width space, Cf), `"Grace\u3164"` (Hangul filler, default-ignorable), `"Gr\u034Face"` (combining grapheme joiner, default-ignorable), `"Grace\^G"` (Cc), `"\u00A0"` (empty after trimming). Accepted: `"José"` typed either precomposed or as `e` + U+0301 (both stored as the precomposed form), `"Zoë"`, `"李小龍"`, `"O'Brien"`, `"Ada  Lovelace"` (inner spaces kept). An invalid name is refused with a 400 and `errors.displayName`; nothing changes. Saving the name you already have succeeds and changes nothing.
2. **Unique everywhere.** No two accounts hold the same display name, compared on the stored form (trimmed, NFC) ignoring case — the application and the database compare the same way, so a name one accepts the other never refuses as a duplicate, or the reverse — across every workspace and including deleted accounts. A rename to a taken name is refused with a 409, `errors.displayName` "That name is already taken.", naming nobody; nothing changes. Changing only the capitals of your own name is allowed. `"josé"` is taken by `"José"` whichever way either was typed.
3. **First sign-in.** An account created from an IdP name that is taken gets the first free name of `X 2`, `X 3`, …; its own workspace is named from that result. Sign-in never refuses over a name and never overwrites an existing user's name.
4. **Existing duplicates.** The migration that makes names unique first trims and NFC-normalises every stored name with the same code as Req 1, then renames every duplicate except the oldest account (`created_at`), using Req 3's suffix rule. This is a one-way data change.
5. **Who sees a rename, when.** The renamer's own tab shows the new name at once — the sidebar's `current-user` and the author of their own messages. Everyone else, and the renamer's other tabs and devices, see it on their next member-directory refetch. No broadcast is added.
6. **Preferences store (D28).** Auth owns per-user preferences: one row per user, global, not per workspace. `GET /api/v1/users/me/preferences` returns the stored keys, or `{}` for a user with none; reading never creates a row. `PATCH` merges the keys sent; `null` removes a key; an unknown key or a bad value is a 400 with `errors.<key>`, and nothing changes. A deleted account gets a 404, as on `/users/me`.
7. **The clock.** One preference, `clock`: `"12h"`, `"24h"`, or absent (Automatic — the browser's locale, as today). It applies to every message time, every thread-summary time and every search-result time. Choosing it saves at once and re-renders the tab's times; a failed save puts the previous choice back and shows the error.
8. **The page.** `/settings` has a Profile section (display name, prefilled, with Save — disabled while the value is unchanged or invalid; a "Saved" confirmation after) and a Preferences section (the clock as Automatic / 12-hour / 24-hour). It is reached by clicking `current-user`, has a "Back to chat" link to the last channel, reads the profile and preferences from the server on every visit, and works on a direct load or a reload.

## Where the rules meet

- **Uniqueness and concurrency (Req 2, Req 1):** Grace and Alan save "Sam" at the same instant — exactly one succeeds, the other gets the 409. The database never holds two.
- **Uniqueness and first sign-in (Req 2, Req 3):** a rename to "X" racing a first sign-in named "X" — one holds "X"; a refused sign-up name falls to the next suffix, never to a failed sign-in.
- **A rename and the user's own view (Req 5, Req 1):** the success updates both the session `profile` and the member-directory cache, so the sidebar and their own message authors never disagree.
- **A rename and the token (Req 5):** the `name` claim, and so `/auth/userinfo`, keeps the old name until the next refresh (≤15 minutes). Nothing in the SPA reads it; this issue leaves it.
- **A rename and the user's workspace:** "ada's Workspace" keeps its name. A workspace's name is not its owner's.
- **The clock and cached lists (Req 7):** messages already in the cache re-render with the new format; nothing refetches.
- **Two tabs and preferences (Req 6):** tabs setting different keys don't lose each other's change; on the same key the last write wins.

## Paths each rule holds on

| Path | What must be true |
|---|---|
| Direct load or reload of `/settings` | the page renders from the server's profile and preferences, not a cached copy |
| `/settings` while signed out | sign-in, then back on `/settings` |
| Leaving `/settings` mid-save (unmount) | a successful response still updates the session profile and the directory cache |
| Leaving with an unsaved edit | the edit is dropped, with no warning |
| Workspace switch while on `/settings` | nothing changes — the name and preferences are per user |
| A second tab or device of the renamer | like anyone else: the new name and the clock on its next refetch |
| Grace, looking at Ada's messages, when Ada renames | the old name until her directory refetches (focus, reconnect, mount, or after 5 minutes) |
| A deleted account | its name stays taken; its preferences routes return 404 |

## What this assumes — check before building on it

- **A unique index on the lower-cased stored name is enough** for Req 2 and its race, once the stored names are trimmed and normalised. Postgres `lower()` is not full Unicode case folding; the plan says whether that matters.
- **`provision_user` is the only place an account's name is created** and `link_identity` the only caller — checked, but the plan confirms nothing else inserts into `users`.
- **An explicit `displayName: null` is a 400 today.** The two reports behind this issue disagree on 400 or 422; the plan checks the code and keeps what it does.
- **The SPA's sign-in returns to the route it started from.** If it doesn't for `/settings`, the plan says so rather than building it silently.
- **`toLocale*String` with `hour12` / `hourCycle`** gives 12- or 24-hour output in every locale the suite runs in.

## Timing

There is no throttle or window. The orderings that matter:

```
t0  Grace PATCH "Sam"  |  Alan PATCH "Sam"     → both in flight
t1  one commits        → 200, the new name
t2  the other          → 409 "That name is already taken."; their name unchanged

t0  Ada saves "Ada L"  → 200; her sidebar and her own messages show "Ada L"
t1  Grace, same channel → still "ada" (directory cached, < 5 min)
t2  Grace focuses the window or reconnects → directory refetch → "Ada L"

t0  Grace chooses 24-hour → her times re-render as 24-hour at once
t1  the PATCH fails       → back to her previous choice, error shown
```

## Decided already

1. Scope is Req 1–8. Everything in *Not in this issue* stays out.
2. A user renames only themselves — no admin rename.
3. One name per user, global — not per workspace.
4. **Names are unique across all of CollabHub (new register D46).** This crosses the tenancy convention on purpose: a 409 tells a user that a name exists in some workspace they can't see. Revealing that a name exists was judged better than allowing impersonation. The response names nobody and no workspace.
5. Lookalike characters (TR39 confusables, e.g. Cyrillic "А") are a known gap; only case, normalisation and the characters Req 1 lists are handled. Characters Unicode counts as visible symbols stay allowed even where they render blank (U+2800 Braille blank). Refusing every default-ignorable character also refuses the zero-width joiner and non-joiner that some Persian and Indic names and emoji sequences use — accepted, for a name that can't hide characters.
6. No live broadcast of a rename; doc 06's "Renames are not covered" stays true for everyone but the renamer's own tab.
7. **D28 is decided here, 🟢:** Auth owns preferences in a `user_preferences` table (`user_id`, `prefs jsonb`, `version`, `updated_at`), per user, with a server-validated set of keys; the SPA holds them in a TanStack query, never Zustand (D24). The display name stays on `users` — profile, not a preference.
8. The clock is the one preference. A dark theme is not (D26 is light-only), nor notifications (D18 🔴).
9. Both PATCH routes stay on `require_user` and fail open when R1 is down — neither is in Conventions §5.2's sensitive set.
10. Auth's new client calls are hand-typed in `lib/auth/api.ts` (`updateMe`, `preferences`, `updatePreferences`): generating Auth's types is its own change.
11. No display name is ever written to a log (CH008).

Left to the plan, on purpose: how the uniqueness is enforced and the race made safe, the migration's shape, the `/settings` route and component layout, how the SPA writes the session profile and directory cache on success, and how the clock reaches the three formatters.

## Tests

- **pytest below the journey**: trim, NFC and validation — every example Req 1 gives, both sides; the 409 and its case-insensitivity, including names that collide only after NFC; changing your own capitals; a deleted account's name stays taken; the concurrent rename; first sign-in suffixing, including two at once; the duplicate-renaming migration, including duplicates that appear only once names are normalised; preferences GET/PATCH — merge, `null`, unknown key, bad value, `{}` with no row, 404 for a deleted account.
- **Vitest**: the Profile form (disabled states, 400 and 409 shown on the field, "Saved"); the session profile and directory both updated on success; the clock applied in all three formatters; the clock's revert on a failed save.
- **One BDD journey**: Alan renames himself to "Alan Turing" on Settings; Grace, after a reload, sees "Alan Turing" on Alan's message. No BDD test uses Alan, so his name is not restored: Auth's tables survive between scenarios, and renaming to the name he already has is a no-op, so a `KEEP_STACK` rerun still passes. The harness gains an `alan` context and page fixture beside `ada` and `grace`.

## Record in this slice

- Register: **D28** 🟢 with the decision above; a new **D46** for global unique display names, with the leak it accepts.
- ADRs: one for D28 (preferences in Auth, per user, validated keys), one for D46 (global uniqueness over tenancy).
- Doc 01: §3 the preferences routes and the 409 on `PATCH /users/me`; §4 the `user_preferences` table and the uniqueness; the first-sign-in suffix rule.
- Doc 06: §3 the settings feature; §5.2's *Names* note — the renamer's own view updates at once; §9's D28 paragraph.
- Conventions doc (`docs/design/00-platform-conventions.md`): §5.4 *Workspace scoping* gains the D46 exception — a display-name 409 may reveal that a name exists in another workspace, and names nobody and no workspace. Reviewers read that exception as decided, not as a leak.

## Not in this issue

- Renaming another user, or a workspace.
- Live push of a rename to other users.
- Lookalike-character detection.
- Any preference but `clock`; a theme; notification settings.
- Generating Auth's OpenAPI types.
- An avatar editor (`avatarAsset` stays as it is).

## Acceptance — on the branch's preview

With Ada, Grace and Alan in three browsers. Each check fails on `main`, which has no `/settings` page and no uniqueness. Each uses its own user, and none needs a fresh preview:

- **Ada** renames herself to `ada-<run id>`: her sidebar and her own messages show it at once. Grace, after a reload, sees it on Ada's message. Ada is renamed back to "ada" at the end.
- **Alan** tries "GRACE" (Grace's name is never changed by any check): he reads "That name is already taken." and his name is unchanged; the 409's body names no user and no workspace.
- **Grace** chooses 24-hour: a message sent after noon shows a 24-hour time; she chooses Automatic again at the end.

The first-sign-in suffix can't be checked on the preview — every Dex user's name is distinct — so it is proven by integration tests only.

## References

- `docs/design/01-auth-service.md` §3, §4
- `docs/design/06-frontend-spa.md` §3, §5.2, §9
- `docs/design/00-platform-conventions.md` §5.1, §5.2
- `docs/design/07-open-decisions-register.md` D2, D24, D26, D28
- Commit `a146ca3` (issue 7) — the member directory and its refetches
- `ChannelHeader.tsx` / `useRenameChannel` — the edit-form template
