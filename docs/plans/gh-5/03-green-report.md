# Green — gh-5, round 1

Display names are now validated, trimmed, NFC-normalised and unique across CollabHub (key column +
unique index, migration `0002`), a `/settings` page renames you and holds a 12/24-hour clock stored by
Auth, and the three time formatters follow it. Every unit, integration and end-to-end test is green,
lint, typecheck and the build are clean, and the journey passed on its first run.

## Baseline
I did not take a separate pre-build run of the red set: the Python and Vitest files were read against
the red report and built task by task, each layer rerun after its task. The first runs after building
were already green, so no test failed differently from `02-red-tests.md`. Counts the plan expects:
unit baseline 1871 (auth 59, frontend 503) — now 1993 (frontend 568 = 503 + 65 new). Deviation from the
instructions: no literal pre-build baseline run; the red report's *Observed red* was taken as given.

## Built
| Task | Files | Tests now | Notes |
|---|---|---|---|
| 5 rules, key, migration | `auth/names.py`, `models.py`, `alembic/versions/0002_…`, `migrations.py` | `test_names.py`, `test_name_migration.py`, `test_schema.py` green (126 with the rest of unit) | `upgrade_to(dsn, revision)`; `upgrade_to_head` delegates |
| 6 routes | `identities.py`, `routers/users.py`, `schemas.py`, `preferences.py`, `routers/preferences.py`, `main.py` | whole Auth suite 287 passed, races included | `provision_user` inserts in a SAVEPOINT; `update_me` maps the index conflict at commit |
| 7 SPA | `lib/auth/{api,session,storage}.ts`, `App.tsx`, `WorkspaceSwitcher.tsx`, `ChatLayout.tsx`, `stores/chat.ts`, `features/settings/{clock,usePreferences,useProfile}.ts`, `SettingsPage.tsx`, `MessageItem.tsx`, `ThreadSummary.tsx`, `SearchResult.tsx` | Vitest 568 passed (56 files), typecheck clean | |
| 8 record | register D28 → 🟢, new D46; ADRs `261021-user-preferences-in-auth`, `261021-display-names-unique-across-collabhub`; docs 00 §5.4, 01 §3–4, 06 §3–5.2–9; `api.http`; frontend README | lint only | sweep below |

## What ran
- `uv run pytest src/services/auth -q` → 287 passed (before the full run).
- `npm --prefix src/frontend run typecheck` → clean. `… test` → 56 files, **568 passed**. `… run lint` → clean.
  `… run build` → built.
- `scripts/test.sh lint unit integration` → **passed**; Unit 1993 passed, Integration 627 passed (a first
  run stopped at lint on CH009 in `routers/users.py`; fixed by putting the `select` directly under its
  waiver, then rerun whole).
- `scripts/test.sh e2e` → **passed**, 25 scenarios, 0 failed — including `display_names.feature`
  on its first run. The committed `docs/test-report.md` shows this last run.
- `python3 .claude/hooks/checks/conventions.py` over the changed Auth files → clean (the one CH009 waiver is
  on `routers/users.py` and `identities.py`). `.claude/hooks/security.sh` → "Security pass clean"
  (it prints `mktemp: too few X's` noise for gitleaks/semgrep in this sandbox).
- Sweep: `grep D28` in `src` and `docs/design` — every hit says the new state (README, the five SPA
  comments); "Renames are not covered" in doc 06 reworded to "not pushed to other people".
  `display_name` writes in `auth/auth` all go through the `User` model (validator) or migration 0002.

## Beyond the tests
- Doc-comments for the why: `names.py` (key vs `lower()`, the Unicode 15.0 table), `models.py` validator,
  `0002` docstring (imports `auth.names` and what that costs; one-way), `useProfile.ts`
  (cancel → write → re-read, own `onSuccess`), `usePreferences.ts` (ordering, rollback), `SettingsPage.tsx`
  (fresh read, Save as a convenience), `storage.ts` (untrusted return path), `session.ts` (`updateProfile`
  guard).
- The 409 carries no id, email or workspace (`_name_taken` in `routers/users.py`).
- `PATCH` that carries nothing writes nothing; both preference routes `require_user` (fail open).
- The D46 exception recorded in Conventions §5.4; doc 06 §4 records the second `sessionStorage` entry.
- No log call mentions a display name (none added).

## Departures from the plan
All in the plan's *Found while building*. In short: `useSetClock` writes/re-reads only when no other save
is queued; `UpdatePreferencesRequest` has its own config; `update_me` pre-checks and maps only
`uq_users_display_name_key`; `PATCH {}` writes nothing; `takeReturnPath` revalidates; clock radios are never
disabled while loading.

## Picked up from earlier reviews
- test-reviewer 1/2, "unique-index conflict can surface at `commit()`": `update_me` catches
  `IntegrityError` around `commit()` (the race tests pass).
- test-reviewer 1/2, "rollback in `onSettled` should also pass": I used `onError`; not tried otherwise.
- plan-reviewer 1/2, ADR should say case folding is wider than `lower()`: said in the D46 ADR and register.
- plan-reviewer 2, `isFetchedAfterMount` turns true on `setQueryData`: left as the plan says, harmless.
- Assumed decisions 14–17a, 20, 24–27 are built as written; for the human to read.

## Left for the human
- The plan's by-hand "first real run" (`docker compose up -d --build`): rename Ada and watch the sidebar and
  messages; from Alan's browser try Grace's name in capitals and read the 409 body; 24-hour on a message, a
  thread summary and a search result; reload `/settings`; open it signed out and check sign-in returns you
  to `/settings`.
- Confusables and `name` claim staleness (≤15 min) are out of scope as the plan says.
- Run `scripts/deploy.sh` migrations: `0002` renames existing duplicate names one-way.
