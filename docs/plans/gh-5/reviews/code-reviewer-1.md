# Code review — gh-5, round 1: approved

The build does what the plan says, at every task. Everything the plan's verification names is green,
and I reran it: the e2e journey shows as passed in the committed evidence. The record is written. Of 13
mutants, 10 were caught. The three that survived are behaviour I walked through the real code and found
right. Three minor findings are left for the human; none blocks.

## Expectations                 (round 1 — written before the code was opened)

I read the issue, the plan, the red report, the test reviews and the pre-writer sources (`56fb009`) of
`routers/users.py`, `identities.py`, `schemas.py`, `session.ts`, `storage.ts`, `App.tsx`,
`ChatLayout.tsx`, `chat.ts`, `WorkspaceSwitcher.tsx` and `MessageItem.tsx`. One honest caveat: the plan
file carries *Found while building* in the same file, and I read the plan whole, so I saw its list of
departures (the `isMutating` gate, `UpdatePreferencesRequest` config, the `update_me` pre-check, `{}`
writes nothing, `takeReturnPath` re-check, radios never disabled). I hadn't opened any code.

### Task 5 — names, key, migration
- **Not pinned:** the migration docstring saying it imports `auth.names` and what that costs (Decision 31).
  Downgrade dropping the table, then the index, then the column. Bound SQL everywhere (CH006). Keys set on
  rows whose names didn't change.
- **Takes for granted:** that `@validates` fires for constructor kwargs (SQLAlchemy's default `__init__`
  does `setattr`), so `User(display_name=…)` in `provision_user` sets the key. The migration runs raw SQL,
  so it has to compute the key itself with `names.name_key` on the *final* name, not on the stored one.
- **Could go wrong:** a key computed before dedupe/repair. A deleted row left out of the SELECT. A `version`
  bump on unchanged rows (too much), or none on renamed rows (too little).
- **Plausible wrong build:** `name_key` as `casefold()` without NFC/NFD. The unit tests pin `Straße`/`José`.

### Task 6 — routes
- **Not pinned:** that `update_me` stops on a refused name before touching `avatar_asset` (a 409 test pins the
  avatar; does a 400?). That the 409 mapping fires only for `uq_users_display_name_key`. The CH009 waiver's
  wording on the deleted-rows lookup. No display name in any log call.
- **Takes for granted:** the pre-check excludes the caller's own row. Otherwise changing your own capitals is a
  409 (pinned). That `ProblemException` can carry `errors` on a 409 — check `shared`. That the
  `IntegrityError` can surface at `commit()` and not only at flush (test-reviewer's left-for-later). That
  `provision_user` flushes inside its SAVEPOINT, so the outer transaction survives a conflict. The workspace
  is named from the name stored, not the IdP name.
- **Could go wrong:** in `provision_user`, a re-check that reads `taken` with deleted rows filtered, which
  differs from the index and loops or re-raises wrongly. An email race (same email twice) that loops forever
  instead of re-raising. A merge SQL whose `- :removed` binds a list asyncpg can't type as `text[]`. A GET
  that inserts a row (pinned). A PATCH for a deleted account that writes before the 404 check. A response that
  leaks a stored unknown key.
- **Plausible wrong build:** `except IntegrityError` mapping every integrity error to 409. No test, so I read
  for it.

### Task 7 — SPA
- **Not pinned:**
  - The `session.ts` module docstring naming the second sessionStorage entry.
  - The D28 comments in the three formatters.
  - `isSafeReturnPath` refusing `/auth/…`. The test params cover `//`, `https:`, `/\` and `/sign-in` only.
  - `adopt()`'s guard checking that the read is the *same user's*.
  - `Callback` on failure going to `/sign-in`.
- **Takes for granted:** that `ChatLayout` is **not remounted** when you navigate `/c/x` → `/settings`. Each
  route has its own `<Protected>`, and React reuses a fiber only by type and position. If it remounted, the
  workspace effect's cleanup would run `clearLastChannel()` on every navigation and "Back to chat" would
  always go to `/`. The App test with a real `ChannelView` should hold this. That `onMutate` runs at once even
  for a scoped mutation that is queued, so a later choice's optimistic value is already in the cache when an
  earlier save fails. That `useWorkspaceMembers`' data shape (plain or infinite pages) is what
  `applyRename`'s updater walks, including `undefined` for a load with no data.
- **Could go wrong:**
  - **`useSetClock`'s "alone" test (`isMutating`).** If it counts *every* mutation in the client, not just
    the preferences scope, then a rename in flight, or any other mutation such as sending a message, makes
    a lone failed clock save skip its rollback and its re-read. The radio then shows a choice the server
    refused, against Req 7 "a failed save puts the previous choice back". The two directions:
    - too little: no rollback while some unrelated mutation is pending;
    - too much: a rollback that undoes a later choice.
  - `applyRename` writing before cancelling, or never re-reading.
  - `updateProfile` bumping the counter when it is a no-op.
  - The Save comparison against the *initial* value instead of the current server profile, so Save stays
    enabled after a success.
  - The form re-keyed on the access token, which would reset the field on a workspace switch or a renewal.
  - The clock query's key including the workspace.
- **Plausible wrong builds:**
  - `applyRename` in `mutate(…, {onSuccess})`. The unmount test catches it.
  - Dropping the `isFetchedAfterMount` gate. Caught.
  - `hour12` in place of `hourCycle`. Caught by the exact-object tests.

### Task 8 — the record
- Register D28 🟢 "built 2026-10-21". A new D46 row: `display_name_key`, deleted accounts included, the
  leak it accepts, and that the 409 names nobody.
- Two ADRs. D46's covers key-over-`lower()` and that full case folding is wider than `lower()`.
- Doc 01 §3 and §4.
- Doc 06 §3, §4 (the return path), §5.2 (renamer's own tab), §9.
- Conventions §5.4 exception. `api.http`.
- A sweep that leaves no stale "D28 open" or "Renames are not covered" without its qualifier.
- Every changed file in the file map or a departure. `src/frontend/README.md` changed and isn't in the map.
  Check it.

### Task 9
- e2e journey `display_names` passed in `build/test-results/e2e.xml`. `docs/test-report.md` is at this
  revision with lint, unit and integration counts matching the report.

## What ran

**Commands:**
- `npm --prefix src/frontend test` → 56 files, **568 passed**.
- `npm --prefix src/frontend run typecheck` → clean.
- `npm --prefix src/frontend run lint` → clean.
- `npm --prefix src/frontend run build` → built (408.71 kB JS).
- `uv run pytest src/services/auth/tests/unit` → **116 passed**.
- `uv run ruff check src/services/auth` → all checks passed.
- `uv run pytest` over the feature's Auth integration files → **51 passed**: `test_display_names`,
  `test_preferences`, `test_name_migration`, `test_schema`.
- `python3 .claude/hooks/checks/conventions.py` over the 10 changed or new Auth files → no findings.
- `git diff --stat 56fb009 HEAD` over every test path → nothing. No test, helper or fixture changed.

**Evidence for `scripts/test.sh`:** `docs/test-report.md` is at `56fb009602cc-dirty`. That is the parent
of the code-writer's commit plus its changes, so it is this tree. Lint passed, Unit 1993, Integration
627, End-to-end 25/0, all matching the green report's *What ran*. `build/test-results/e2e.xml` names
`test_grace_sees_the_name_alan_chose_on_his_message` and holds no `<failure`.

**Mutants (sketch).** Each was reverted before the next.

| # | File · change | Tests run | Result |
|---|---|---|---|
| 1 | `useProfile.ts` · no `cancelQueries` on directories | `useProfile.test.ts` | caught (`a first directory load in flight is restarted`) |
| 2 | `useProfile.ts` · no `invalidateQueries` | same | caught (4 tests) |
| 3 | `session.ts` · `adopt()` guard drops the same-user check | `session.test.ts`, `App.settings.test.tsx`, `App.test.tsx` | **survived** |
| 4 | `storage.ts` · `isSafeReturnPath` allows `/auth/` | `session.test.ts`, `App.settings.test.tsx` | caught |
| 5 | `session.ts` · `adopt()` guard removed | `session.test.ts` | caught (`outlives a switch whose profile read began before it`) |
| 6 | `usePreferences.ts` · rollback unconditional | `SettingsPage.test.tsx` | caught (`keeps a later choice…`) |
| 7 | `usePreferences.ts` · `aloneInQueue` always true | `SettingsPage.test.tsx`, `App.settings.test.tsx` | **survived** |
| 8 | `ChatLayout.tsx` · no `clearLastChannel()` | `App.settings.test.tsx`, `ChatLayout.test.tsx` | caught |
| 9 | `SettingsPage.tsx` · Save compares to the first value, not the cached profile | `SettingsPage.test.tsx`, `App.settings.test.tsx` | **survived**. The first run had one failure in a callback test this change can't reach; the rerun passed 33/33. See *Left for the human* |
| 10 | `SettingsPage.tsx` · no `isFetchedAfterMount` gate | same | caught (2) |
| 11 | `ChatLayout.tsx` · clock context never provided | `App.settings.test.tsx` | caught (2) |
| P1 | `routers/users.py` · pre-check doesn't exclude the caller's own row | `test_display_names.py` | caught (`…own_capitals…`, 409 ≠ 200) |
| P2 | `identities.py` · on `IntegrityError` always try the next candidate, never re-raise | all Auth integration (171) | **survived** |

**Library behaviour I checked:** in `query-core/build/modern/query.js:375-389`, a failed background
refetch sets `status: "error"` and keeps the data. This is behind Finding 2.

## Conformance

| Plan task or decision | Code | Outcome |
|---|---|---|
| T5: `names.py` to the interface; `_DEFAULT_IGNORABLE` table as given | `auth/names.py` | as planned |
| T5 / D12: `display_name_key`, `@validates`, unique index | `models.py:41-71` | as planned |
| T5: `UserPreferences` | `models.py:74-92` | as planned |
| T5 / D17, 17a, 31: migration 0002 | `0002_unique_display_names.py` | as planned. Reads every row, deleted included; repairs, then dedupes, reserving first; bumps `version` only on renamed rows; sets the key on the rest; NOT NULL, then the index, then the table; the docstring states the `auth.names` cost; the downgrade is as planned |
| T5: `upgrade_to`, `upgrade_to_head` delegates | `migrations.py` | as planned |
| T6 / D18, 19: `update_me` — null 400, `clean`, no-op re-save, 409 body | `routers/users.py` | departed, with a reason: a pre-check, plus a commit-time mapping only for `uq_users_display_name_key`. `{}` writes nothing. Both recorded |
| T6 / D13: `provision_user` SAVEPOINT, next suffix only if the key is taken, else re-raise | `identities.py:88-118` | as planned. The workspace is named from `user.display_name` |
| T6 / D20, 21: preferences read and merge, qualified upsert, `{}` writes nothing | `preferences.py`, `routers/preferences.py` | as planned |
| T6: `UpdatePreferencesRequest` `extra="forbid"` | `schemas.py` | departed, with a reason (its own `model_config`). Same effect |
| T6: both PATCHes on `require_user`; 404 detail for a deleted account | routers | as planned |
| T7 / D25: return path in `Protected`, `SignIn`, `Callback`, storage | `App.tsx`, `session.ts`, `storage.ts` | as planned. `takeReturnPath` re-validates (recorded) |
| T7 / D30b: `updateProfile` and the `adopt()` guard | `session.ts:79-113` | as planned |
| T7 / D26: `lastChannelId`, `clearLastChannel` in the workspace cleanup | `chat.ts`, `ChatLayout.tsx` | as planned |
| T7 / D22, 23: `ClockContext` from `usePreferences`; `hourCycle` h12/h23; three formatters | `clock.ts`, `ChatLayout.tsx`, the three leaves | as planned |
| T7 / D28: `refetchOnMount: 'always'`, `isFetchedAfterMount` gate, failed-read alert | `SettingsPage.tsx`, `useProfile.ts` | as planned |
| T7 / D29: scoped, serialised clock writes; snapshot rollback only on its own value; invalidate | `usePreferences.ts` | departed, with a reason: write and re-read only when alone. Recorded, but the test it names doesn't pin it (Finding 1) |
| T7 / D30, 30a: `applyRename` from the hook's own `onSuccess`; cancel → write → invalidate `'all'` | `useProfile.ts` | as planned |
| T7: `current-user` becomes a `Link` to `/settings`; markup and labels | `WorkspaceSwitcher.tsx`, `SettingsPage.tsx` | as planned |
| T8: register, ADRs, docs 00, 01, 06, `api.http`, sweep | docs | as planned. The README was swept as well (see *Checked and sound*). One stale cell (Finding 3) |
| T9: lint, unit, integration, e2e | `docs/test-report.md`, `e2e.xml` | done. The by-hand first run is left for the human, as the report says |

## Findings

### 1. *Found while building* says the `useSetClock` "alone" gate is pinned by two tests; it isn't — minor
**Where:** `01-implementation-plan.md` *Found while building*, first bullet; `usePreferences.ts:51`.
**Checked:** mutant 7. With `aloneInQueue` always true, `SettingsPage.test.tsx` and `App.settings.test.tsx`
still pass 33/33, `keeps a later choice when an earlier save fails` included.

The behaviour itself is sound by reading. The gate only skips an intermediate cache write or re-read
while a later save is queued, and that later save's own settle writes or re-reads. The end state is the
server's either way; without the gate the screen can flicker. But the record names a test that holds it,
and none does. It should say "no test", with that reason.

### 2. A failed background read of the profile replaces an open form, and the typed edit is lost — minor
**Where:** `SettingsPage.tsx:169-177`.
**Checked:** reading, and `query.js:375-389` as above.

`useMyProfile` has `staleTime: 0`, so a window focus refetches it. If that refetch fails after its
retries, `status` becomes `error` while `data` is kept. `profile.isError` then wins, and
`ProfileSection` unmounts with whatever the user had typed. Decision 28 says only "a failed read shows
an error and no form", and the code follows it literally. The narrower reading would show the alert
only when no read has succeeded this visit, for example `isError && !isFetchedAfterMount`, or check
`isSuccess` first. It needs focus plus a failing network for all retries, so it is minor.

### 3. Register D28's question cell still says "no feature for them exists at all" — minor
**Where:** `docs/design/07-open-decisions-register.md:168`.
**Checked:** reading. The status column is right (🟢, built 2026-10-21). The question text beside it
still states the old fact in bold. One phrase to change.

## Unpinned

- **Mutant 3, `adopt()`'s same-user check.** Survived. Reading says it is unreachable today. Another
  user's profile only arrives through `completeSignIn`, which starts from `signedOut`. There,
  `updateProfile` returns before bumping `profileUpdates`, so `renamedMeanwhile` can't be true for a
  different user. Only reading protects it.
- **Mutant 7, the "alone" gate.** See Finding 1. I walked through A-fails-while-B-queued,
  A-succeeds-while-B-queued, and both-fail. Each ends on the server's answer.
- **Mutant 9, Save compares to the cached profile, not the first value.** After a successful rename,
  `applyRename` sets `['me', id]`. That is the key `useMyProfile` reads (`profileKeys.me(userId)`),
  so `profile.displayName` becomes the stored name and Save disables. No test asserts Save is disabled
  after a success.
- **Mutant P2, `provision_user` re-raising.** No test drives two first sign-ins for one email. The code
  re-raises when the candidate's key isn't taken (`identities.py:113-116`), as Decision 13 says. The
  mutant would loop forever on that race.
- **The `update_me` 409 mapping only for `uq_users_display_name_key`.** No test raises another integrity
  error here. Reading shows `str(conflict.orig)` from asyncpg carries the constraint name. The
  concurrent-rename test proves the positive side.

## Left for the human

- **Findings 1–3** above. Each is one edit: the record's "pinned by" line; the Profile section's error
  condition; the register's question cell.
- **Possibly flaky:** `App.settings.test.tsx › returns to the remembered route from the callback, once`
  failed once in my sketch under mutant 9, which can't reach it. It passed on the immediate rerun, in the
  full suite, and in a rerun of that file in the real tree. Worth watching in CI.
- **First real run** (the plan's Task 9 by-hand checks, not run by any stage):
  - rename Ada and watch the sidebar and her messages;
  - try `GRACE` from Alan's browser and read the 409 body;
  - check 24-hour on a message, a thread summary and a search result;
  - reload `/settings`, and open it signed out.
- **Before deploying:** migration `0002` renames existing duplicate names, one-way.
- **Assumed decisions to read:** 14–17a, 20, 24–27, as the earlier reviews list. The code builds each as
  written.

## Checked and sound

- Mutants 1, 2, 4, 5, 6, 8, 10, 11 and P1 were caught.
- The `isMutating` filter is by `mutationKey`, so a rename in flight doesn't stop a clock rollback. I had
  flagged that as a risk in *Expectations*.
- `ChatLayout` persists across routes. The real-`ChannelView` Back-to-chat test passes, and mutant 8
  shows the cleanup runs on a switch.
- `applyRename`'s updater handles `undefined`. The directory data is a plain `WorkspaceMember[]`
  (`useWorkspaceMembers.ts`), and `['workspace-members', null]` is disabled, so it isn't refetched.
- Conventions:
  - CH001: the row is the token's `sub`.
  - CH006: bound SQL, including `CAST(:removed AS text[])` and in the migration.
  - CH008: no display name in a log call.
  - CH009: waived on both deleted-inclusive lookups, with the D46 reason.
  - No suppression comment without a reason.
  - camelCase on the wire; UTC `now()`.
- Doc 01 §3–4, doc 06 §3, §4, §5.2 and §9, Conventions §5.4, both ADRs, D46 and `api.http` all describe
  the code as built. The D46 ADR records `ß`/`SS` and key-over-`lower()`.
- `src/frontend/README.md` sits outside the file map. It is the Task 8 sweep's fix of a stale "D28 🔴",
  and the green report's Built table names it.
- The report matches the tree. Every *Left for later stages* item from the test review is answered:
  commit-time conflict, `onError` rollback, and the e2e first run.
