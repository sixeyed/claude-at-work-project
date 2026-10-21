# Red tests — gh-5, round 1

BDD outside-in, as the plan recommends: one journey (`display_names.feature`), and everything under it
at the lowest layer that proves it. Test files written or changed on the Python side and the SPA, plus
the journey. **Python:** 36 new integration tests fail as planned and 7 new ones pass by design (below);
the unit file (`test_names.py`) and the migration file (5) cannot load until `auth.names` and
`upgrade_to` exist, which is right since every test in them needs the module. **Vitest:** 22 new tests fail
for the planned reasons, 5 new guards pass, and 4 new files cannot load until the feature's modules exist.
All 49 existing tests in the six files I changed still pass. Nothing was run against an implementation: no
production code exists yet, so the held-read and race tests have been checked by reading the installed
TanStack/MSW source, not by passing — the test-reviewer's sketch is their first green.

## Baseline
| File(s) changed | Before | After |
|---|---|---|
| `test_schema.py` + `test_r1_unreachable.py` | 8 passed | 8 existing pass; 2 new fail (`DID NOT RAISE`, preferences 404) |
| `App.test.tsx`, `ChatLayout.test.tsx`, `ChatLayout.attachments.test.tsx`, `CreateChannelDialog.test.tsx`, `session.test.ts`, `chat.test.ts` | 49 passed (6 files) | 49 existing pass; 22 new fail, 5 new pass |

`test/api.ts` (shared helper) changed too; every file that uses it still loads.

## Tests
Python = `src/services/auth/tests/…`; SPA = `src/frontend/src/…`. "Plan" is the plan's task. Observed = first
line of the failure, copied.

| File · test | Layer | Plan | Proves | Observed red | Match |
|---|---|---|---|---|---|
| `unit/test_names.py` (all cases) | unit | T1 | trim/NFC, refusals, ranges, key, suffixes, `provisional`, `dedupe`, `User` key | `ImportError: cannot import name 'names' from 'auth'` | yes (plan says `ModuleNotFoundError`; the package exists, the submodule doesn't) |
| `test_display_names.py::test_a_name_is_stored_trimmed_and_composed` | integ | T2 | trim + NFC stored | `AssertionError: assert '  José  ' == 'José'` | yes |
| `…::test_a_refused_name_is_400…[5 params]` | integ | T2 | 400 + exact message per example, name unchanged | `assert 200 == 400` ×5 | yes |
| `…::test_every_accepted_example_is_stored[decomposed]` | integ | T2 | NFC on the way in | `assert 'José' == 'Jos\xe9'`; the other 5 pass (positive side) | yes |
| `…::test_a_100_character_name_with_spaces_is_kept_and_101_refused` | integ | T2 | limit on stored form | 400 body: validation error on the 102-char padded name | yes |
| `…::test_saving_the_name_you_have_changes_nothing` | integ | T2 | re-save writes nothing; a real rename does | `assert 2 == 0` (version bumped) | yes |
| `…::test_a_taken_name_is_409_naming_nobody` · `…_changes_nothing_else_in_the_request` · `…_normal_form_collide` · `…_own_capitals…` · `…_deleted_accounts_name…` | integ | T2 | 409 body, avatar untouched, NFC collisions, own capitals vs another user, deleted holder | `assert 200 == 409` (normal-form: `AssertionError: josé`) | yes |
| `…::test_two_renames_to_one_name_at_once_one_wins` | integ | T2 | one 200, one 409, one row | `assert [200, 200] == [200, 409]` | yes |
| `…::test_a_rename_racing_an_uncommitted_first_sign_in` (commit) · `…_waits_out_…_rolls_back` | integ | T2 | rename waits on an open sign-in, then 409 / 200 | commit: 200 body where 409 expected; rollback: `Grace's rename never waited on the open sign-in` | yes / extra (see Departures) |
| `…::test_a_first_sign_in_racing_an_uncommitted_rename` (commit) · `…_takes_the_name_when_the_rename_rolls_back` | integ | T2 | mirror race | `assert 'Sam' == 'Sam 2'`; rollback: `the first sign-in never waited on the open rename` | yes / extra |
| `…::test_two_first_sign_ins_with_one_name_both_succeed` | integ | T2 | gathered sign-ups | `assert {'Sam'} == {'Sam', 'Sam 2'}` | yes |
| `…::test_a_first_sign_in_with_a_taken_name_takes_the_next_suffix` | integ | T2 | `ada 3`, workspace `ada 3's Workspace` | `assert 'ada' == 'ada 3'` | yes |
| `…::test_an_unusable_idp_name_still_signs_in` | integ | T2 | repair to `zed` | `assert '​' == 'zed'` | yes |
| `…::test_a_sign_in_never_overwrites…` · `…_rename_leaves_the_workspace_name_alone` | integ | T2 | **green by design** (Req 3 last clause; row 5) | pass | as planned |
| `test_preferences.py` (12 tests, 14 cases) | integ | T2 | GET/PATCH, merge, null, 400s, empty patch, upsert race, per-user, 404 + detail, 401 | `assert 404 == 200` (or `404 == 401`); merge seed: `UndefinedTableError: relation "user_preferences" does not exist` | yes |
| `test_name_migration.py` (5 tests) | integ | T2 | normalise, dedupe (deleted counts), newer unique name kept, versions, index | `ImportError: cannot import name 'upgrade_to' from 'auth.migrations'` | yes |
| `test_schema.py::test_display_names_are_unique_ignoring_case_and_form` | integ | T2 | index on the key | `Failed: DID NOT RAISE IntegrityError` | yes |
| `test_r1_unreachable.py::test_profile_and_preference_edits_fail_open…` | integ | T2 | both PATCHes 200 with R1 down | preferences PATCH is a 404 | yes |
| `settings/clock.test.ts` (6) · `clockApplied.test.tsx` (5) | Vitest | T3 | options, 13:05 / 00:05 / never 24:05, three formatters, no-clock unchanged | `Failed to resolve import "./clock"` | yes |
| `settings/useProfile.test.ts` (7) | Vitest | T3 | `applyRename`, unmount mid-save, 4 held-read races | `Failed to resolve import "./useProfile"` | yes |
| `settings/SettingsPage.test.tsx` (20) | Vitest | T3 | form states, errors, Saved, clock save/revert/serialise | `Failed to resolve import "./SettingsPage"` | yes |
| `App.settings.test.tsx` (13) | Vitest | T3 | routes + Paths rows | `Unable to find … link "Ada Lovelace"` (name is a `<p>` today) ×6; `Unable to find role="textbox"` ×2; `Unable to find role="button" and name "Sign in"` (route → "No such page."); `Unable to find role="heading" … "Settings"` (callback lands `/`); `Unable to find an element with the text: 13:05` ×2; `expected undefined to be '0199…c001'` | yes |
| `session.test.ts` +7 (`signIn` safe path; `takeReturnPath` ×2; `updateProfile` ×4) | Vitest | T3 | return path, `updateProfile`, 30b both orders | `expected null to be '/settings'`; `session.takeReturnPath is not a function`; `session.updateProfile is not a function` | yes |
| `session.test.ts` unsafe path ×5 | Vitest | T3 | an unsafe path is not stored, sign-in still proceeds | **pass at red** — guard; positive half is the safe-path test above, and it fails a build that stores any path | guard |
| `chat.test.ts` +2 | Vitest | T3 | `lastChannelId`, `clearLastChannel` | `expected undefined to be null`; `clearLastChannel is not a function` | yes |
| `tests/bdd/features/display_names.feature` | BDD | T4 | the journey | cannot run here — see BDD | n/a |

## Types
`npm --prefix src/frontend run typecheck`: 30 errors, all of the planned kinds and nothing else.
- `Clock`, `Preferences` not exported from `lib/auth/api` — `test/api.ts`, `App.settings.test.tsx`,
  `SettingsPage.test.tsx` (Task 7).
- `Cannot find module './clock'` / `'./useProfile'` / `'./SettingsPage'` (Task 7).
- `session.updateProfile`, `session.takeReturnPath` missing; `signIn` takes 0–1 arguments (Task 7).
- `lastChannelId`, `clearLastChannel` missing on `ChatState` (Task 7).
- Five `TS7006 'body' implicitly has an 'any' type` — the callbacks to `auth.updatePreferences`, whose body type
  is `{ clock: Clock | null }` and so unresolved until `Clock` exists. They go with it.

## BDD
- `uv run pytest tests/bdd --collect-only -q`: 25 collected, including
  `test_display_name_steps.py::test_grace_sees_the_name_alan_chose_on_his_message`; no collection error.
- `uv run pytest tests/bdd --generate-missing --feature tests/bdd/features`: prints nothing — every step binds.
  (The plan expected four missing steps; the steps module is part of Task 4, so they exist.)
- Expected red at e2e: `When Alan changes his display name to "Alan Turing" in Settings` stops at
  `ChatPage.open_settings` — `current-user` is a `<p>`, so the click does nothing and
  `expect(settings-page).to_be_visible()` times out. After Task 7 it needs `settings-page`,
  `settings-display-name-input`, `settings-display-name-save`, `settings-saved` and `current-user` as a link
  that keeps its test id. `Then Alan sees … as his name` waits on `current-user` text. The last `Then` reads
  Grace's window after a fresh load: only a server-side rename plus a directory refetch can satisfy it.

## Departures from the plan
- **Extra tests (kept):** `test_the_migration_creates_the_preferences_table`; `test_a_refused_rename_changes_nothing_else_in_the_request` (a 409 leaves the avatar sent beside it); `test_check_works_on_an_already_normalised_name`, `test_the_outside_neighbours_the_table_is_tested_against_exist` (guard: enough allowed neighbours exist for the range test to check anything), `test_dedupe_leaves_distinct_names_as_they_are`; SettingsPage `keeps Save disabled while a save is in flight` (Decision 24's last clause); `session.test.ts` `takeReturnPath gives / when nothing was remembered`.
- **Race tests split:** each "racing" test is two tests (holder commits / holder rolls back), so each half names its own wrong build. The rollback halves also fail at red — on `never waited`, not on a status — because with no index nothing blocks. The plan said only the commit half fails. Both are right: a rollback half that passed at red would prove nothing.
- **`test/api.ts`:** `auth.updateMe`, `auth.preferences`, `auth.updatePreferences`, `auth.meBy` as planned, plus `Refused` — a reply function may return `new Refused(status, problem)` to answer with a problem after being held, which a failure sequence ("first save fails after the second is queued") needs and `auth.problem` cannot give. `auth.preferences` also takes a function, asked on every GET, so a stateful fake server and a gate on reads are possible.
- **Special characters** are built with `chr()` or `\x` escapes. The authoring tool decodes `\uXXXX` in file content into raw characters, which ruff rightly rejects (`RUF001`), so no invisible character is typed anywhere.
- **`SettingsPage.test.tsx` gates reads** (`gateReads`) in two tests, so the screen's state between a failed save and its re-read comes from the cache, not from whichever refetch lands first. This pins Decision 29's snapshot rollback: a build that only invalidates and waits for the re-read fails `a later failure after an earlier success returns to the earlier choice`. Plan-conformant; stated so it isn't a surprise.
- **`App.settings.test.tsx`:** the workspace-switch Back-to-chat case sets the active channel through the store and switches with `session.changeWorkspace`, rather than navigating a real `ChannelView` across the switch; the plain "last channel" case does use a real `ChannelView`.

## Picked up from earlier reviews
- plan-reviewer-2, *Left for later stages*, `a first directory load in flight is restarted`: the test mounts the
  directory with call 1 held and no data, runs `applyRename` (the updater is handed `undefined`), asserts the cache is
  still empty after call 1's stale answer lands, then lands call 2. It fails a build whose updater dereferences
  `undefined`, one that never refetches, and one that lets the cancelled read land.
- plan-reviewer-1/2 minor items about assumed decisions (14–17a, 20, 24–27) are the human's; the tests follow them as written.

## For the code-writer
- `Preferences`/`Clock` must be exported from `lib/auth/api.ts` — `test/api.ts` imports them as types.
- `useMyProfile` returns the `useQuery` result (tests read `.data`); `useRenameMe().mutate(displayName: string)`.
- `applyRename` is **synchronous** up to the point of `invalidateQueries`: the tests check the session and every cached
  directory immediately after `act(() => applyRename(…))`, before any refetch can land.
- A held directory read is cancelled, not merely outdated: tests hold the stale read *and* the refetch and look at the cache between.
- Save is disabled in flight; the profile form is absent until this visit's read has succeeded; the failed-read alert text matches `/load your profile/i`.
- Labels: radios `Automatic` / `12-hour` / `24-hour` inside a group named by the legend `Clock`; `Display name` textbox; `Save` button; `Saved` as visible text; `Back to chat` link whose `href` is `/c/{lastChannelId}` or `/`.
- Queries use the literal keys `['me', id]`, `['user-preferences', id]`, `['workspace-members', ws]`. `App.settings.test.tsx` writes `['user-preferences', 'user-ada']` directly.
- The clock refetch on focus is the default `refetchOnWindowFocus` through a hidden→visible change; `usePreferences` must not set a long `staleTime`.
- Special-case: `ChatLayout` workspace-effect cleanup calls `clearLastChannel()`; a test asserts `lastChannelId` is `null` after a switch.
- `provision_user` is called directly by Auth tests with `(session, email=…, display_name=…, demo_workspace_name=None)`; it must flush the user inside the call (the race tests hold the transaction open after it returns).
- Auth tests read `users.display_name_key`, `user_preferences(user_id, prefs, version, updated_at)` and the constraint name `uq_users_display_name_key`.
