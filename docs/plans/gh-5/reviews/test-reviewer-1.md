# Test review — gh-5, round 1: changes_requested

The red is real and well aimed: 36 of 36 new Auth integration tests, the Python unit file, the migration file and 22 of
22 new Vitest tests fail for the planned reasons, and a correct sketch turns every Vitest test green (568/568). One
major finding: `SettingsPage.test.tsx › keeps a later choice when an earlier save fails` — the test that claims to pin
Decision 29 — passes against a build that rolls back unconditionally, so the "a failed save must not undo a later
choice" clause is unpinned. It is a one-line fix in the test.

## Expectations

Written before opening the red report or any test file.

**Name rules (`test_names.py`).** Today `auth.names` does not exist: every test fails at collection with
`ModuleNotFoundError: No module named 'auth.names'` — right, as every test needs it. Vacuous versions: a
refused-example list that only checks "raises" not the message; default-ignorable ranges tested at one end only,
or with a neighbour that another rule (Cn/Cf) also refuses; length tested only at 100/101 without surrounding
spaces or with astral characters (UTF-16 vs code points); `name_key` tested only on ASCII case (a `lower()` build
passes; ß/SS and NFD/NFC are the discriminators); `dedupe` fixtures where age order and "reserve first" coincide
(the plan's Sam / sam / Sam 2 case); a created_at tie not actually tied. Wrong build: suffix by age without
reserving; `lower()` key; `str.strip()` vs `.strip(" ")`.

**Routes (`test_display_names.py`).** Red: assertion failures on the old route (200 where 400/409 expected). Vacuous:
a 409 test that doesn't assert the exact body or that Ada's name is unchanged *via GET*; "capitals only" with no
other-user half; "no write" checked without comparing `version`/`updated_at`; races that run in one order or never
wait (the `pg_stat_activity` poll); deleted-account 409 passing because of an earlier guard. Wrong build: unique index
on `lower(display_name)` instead of key; check-then-insert only; rename that 500s on IntegrityError.

**Preferences (`test_preferences.py`).** Red: 404. A 404 passes any "can't see it" test, so the deleted-account and
401 tests must assert `detail`/status 401. Vacuous: "reading never creates a row" without counting rows; merge test
without a second key; null removal without a prior value; unknown key 400 without proving nothing changed.

**Migration (`test_name_migration.py`).** Load failure on `upgrade_to` import is legitimate. Vacuous: fixtures where
the oldest isn't deleted; unchanged `version` not checked; post-migration IntegrityError not asserted by index.

**SPA.** `clock.test.ts`, `useProfile.test.ts`, `SettingsPage.test.tsx` fail at import (legit). Vacuous/impossible:
a time assertion in a timezone-dependent form; held-read race tests that pass for a write-only build; Save-disabled
tests pass at red because the page is missing (must have a positive half); fake timers; test ids used in Vitest;
`session.test.ts` guard tests with no positive half; `App.settings` tests that can never pass because the harness
(MSW, location.assign, sessionStorage) doesn't behave as assumed. The ripple edits must not weaken existing tests.

**BDD.** Steps must bind (`--generate-missing` prints nothing); the last Then reflects the server (Grace after a
fresh load). Wrong build: Alan sees the name only locally; Grace sees it only from a cache.

**Issue clauses to pin:** "at most 100" inclusive; trim then NFC; "naming nobody"; "including deleted accounts";
"changing only the capitals of your own name is allowed"; null removes a key; "reading never creates a row"; "failed
save puts the previous choice back".

## What ran

| Command | Result |
|---|---|
| `uv run pytest src/services/auth/tests/unit/test_names.py` + `integration/test_name_migration.py` | both fail at collection: `ImportError: cannot import name 'names' from 'auth'` / `'upgrade_to' from 'auth.migrations'` — right, every test in each needs the module |
| `uv run pytest …/test_display_names.py test_preferences.py test_schema.py test_r1_unreachable.py` | 36 failed, 15 passed. Failures: `assert '  José  ' == 'José'`, `200 == 400` ×5, `200 == 409`, `[200, 200] == [200, 409]`, `Grace's rename never waited…`, `{'Sam'} == {'Sam','Sam 2'}`, `404 == 200`, `UndefinedTableError: user_preferences`, `DID NOT RAISE` — all as the report says. The 15 passes are the existing tests and the by-design guards |
| `npm --prefix src/frontend test` | 22 failed / 508 passed; 4 files fail to load (`Failed to resolve import "./clock"`, `./useProfile`, `./SettingsPage`; `clockApplied` via `../settings/clock`) — every test in each needs the module; the 22 are the planned assertion/`is not a function` reds in `App.settings`, `session`, `chat` |
| `npm --prefix src/frontend run typecheck` | 30 errors (report: 30) |
| `uv run pytest tests/bdd --collect-only -q` / `--generate-missing` | 25 collected; stub list empty — every step binds |
| Sketch, Vitest, **correct** (clock, `useProfile`, `usePreferences`, `SettingsPage`, session/storage, chat store, `App`, `ChatLayout`, `WorkspaceSwitcher`, three formatters) | full suite 568/568 (56 files). One first-run failure of `App.test` "signed-out visitor" went away on rerun with no change to test or sketch — a flake of my probe, not of the tests |
| Sketch, **write-only rename** (no cancel, no invalidate) | `useProfile.test.ts` 5 of 7 red |
| Sketch, **invalidate without cancel** | `first directory load…` and `profile read in flight…` red (the plan's analysis holds: invalidate alone cancels only a query with data) |
| Sketch, rename via `mutate(…, {onSuccess})` | `lands after the form … has unmounted` red |
| Sketch, `adopt()` without the rename guard | `outlives a switch whose profile read began before it` red |
| Sketch, no `isFetchedAfterMount` + no mutation `scope` | `waits for this visit's read`, `does not send the second choice before the first…` red (and `goes back to the earlier choice…` with no scope) |
| Sketch, no rollback to the snapshot | `goes back to the earlier choice when a later save fails after an earlier success` red |
| Sketch, `staleTime: Infinity` on preferences | `follows another tab's change on the next focus` red |
| Sketch, **unconditional rollback** (no "cache still holds my value" check) | **all 20 `SettingsPage` tests green — finding 1.** With one `await pause()` added to the sketch's copy of the test, it goes red; correct build with that line: green |
| Python sketch, `names.py` + model hook, correct | `test_names.py` 57/57 |
| Python sketch, dedupe by age with no reservation | `test_dedupe_never_renames_a_newer_name…` red (`'Sam 2 2'`) |
| Python sketch, key = `lower()` | `test_the_key_ignores_case_and_normal_form`, `…setting_a_users_display_name_sets_its_key` red |
| `sketch.sh clean` | done; `git status` shows only this review |

Not run, and labelled **unverified**: the integration tests against a correct build (a sketch needs routes, SQL and the
migration, and containers) — I reasoned through the race tests (below) instead; the BDD journey (needs the Compose
stack). I could not run `ruff` (refused by the sandbox); the lint hook ran on each file the writer wrote.

## Coverage

| Plan test / expectation | Test as written | Outcome |
|---|---|---|
| T1 all 20 unit rows | `test_names.py` (57 cases: every example, every category, both ends of every range plus an outside-neighbour guard, 100/101 with spaces and astral, key incl. ß/NFD, suffix cut, dedupe ×6, model key) | present |
| T2 `test_display_names` 16 rows | all present; the two races split commit/rollback, each with a "really waited" poll (departure, reasoned) | present |
| T2 `test_preferences` 11 rows | present; 404/401 tests assert `detail`/status, row counts assert "never creates" | present |
| T2 migration 4 rows + preferences table | present; deleted-oldest, newer-unique, versions, index by name | present |
| T2 schema, r1 fail-open | present; `a_user` per-id names | present |
| T3 `clock`, `clockApplied`, `useProfile` (7), `SettingsPage` (18 + 2 extra), `App.settings` (13), `session` (7), `chat` (2) | present; extras are kept guards with reasons | present |
| T3 ripple (4 files) | `auth.preferences({})` added to each; existing assertions untouched (diff read) | present |
| T4 feature, steps, page object, `alan` fixture | present; binds | present |
| Expectation: wrong build "unconditional rollback" | `keeps a later choice…` | **departed — passes the wrong build (finding 1)** |
| Every other Expectation (lower() key, age-only dedupe, write-only rename, invalidate-only, cached profile prefill, no serialisation, stale preferences, sign-in-only-local rename) | caught, see *What ran* / *Checked and sound* | present |

## Findings

### 1. `keeps a later choice when an earlier save fails` passes an unconditional rollback — major
**Where:** `src/frontend/src/features/settings/SettingsPage.test.tsx:358-391` · **Checked:** sketch, run
The clause (plan Decision 29, "a failure must not undo a later choice"): when save 1 (24h) fails while save 2
(Automatic) is queued, the screen must stay on Automatic. The test reads `radio('Automatic')` right after
`vi.waitFor(preferenceRequests() === 2)`. In a build whose `onError` always restores its own snapshot (12h), the cache
goes to 12h, but TanStack notifies observers on a `setTimeout(0)` batch, so the DOM still shows Automatic when the
`waitFor` returns; the assertion reads the stale DOM. The reads are gated, so the refetch can't repair it before the
test ends and then `ungate()` lands `{}` — the final assertion passes too. I ran it: all 20 tests green against the
unconditional rollback. The wrong build is the obvious one (the textbook optimistic-update rollback), and the test is
the only one that claims the clause. **Fix:** `await pause()` (the file's existing 25 ms helper) between the `waitFor`
and the `expect(radio('Automatic'))` at line 383. In my sketch that makes the wrong build fail
(`radio('Automatic')` not checked) and the correct build pass. The same pause isn't needed elsewhere: the other
failure tests wait on the state they want (`waitFor`), and I ran the no-rollback and no-serialisation builds against
them.

## Left for later stages
- **Code-writer:** the Python integration tests were not run against any build. Race tests rely on the first-sign-in
  insert happening *inside* the call (the report says so) and on `PATCH` taking the conflict at commit; build
  `update_me` so the unique-index conflict can surface at `commit()` as well as at flush.
- **Code-writer (minor):** `SettingsPage.test.tsx` and `useProfile.test.ts` assert on TanStack's batching; a build
  that sets the rollback in `onSettled` instead of `onError` should also pass — if it doesn't, tell the test pair.
- Report says the Python unit red is `ImportError: cannot import name 'names' from 'auth'`; the plan said
  `ModuleNotFoundError`. The report's version is what I saw; no action.
- **BDD (unverified):** first real run is Task 9. Alan sends in a public channel without joining — `messages.py` says
  visibility suffices, so it should work, but it is the one thing in the journey no earlier scenario has done with a
  second user. The scenario waits for the confirmed row, not for a room join, which is enough for Alan.
- Assumed decisions for the human (carried from the plan reviews): 14–17a, 20, 24–27.

## Checked and sound
- **Red for the right reason:** every load failure is whole-file (all tests need the missing module); `session.test.ts`,
  `chat.test.ts`, `App.settings.test.tsx` fail on assertions/`is not a function`, not on import. Python reds are
  behaviour (200 where 400/409). No typo, wrong path or bad selector found; the 30 `tsc` errors are all the planned kinds.
- **Not green by accident:** 15 passes in the four Auth files are the existing tests and the two by-design guards
  (`never_overwrites`, `leaves_the_workspace_name_alone`).
- **Both halves:** refused/accepted examples, 100/101 with padding, own capitals vs another user, 409 vs a free name,
  Save disabled/enabled, safe/unsafe return paths, held-read before/after the rename, deleted-oldest holder.
- **Clauses:** "at most 100" inclusive on the stored form; "including deleted accounts" (409 + free name beside it);
  "naming nobody" (no email, id or "Workspace" in the body); "reading never creates a row" (row count); null removes; 404
  tests assert `detail`; 401 asserts status.
- **Existing tests:** diff of `App.test`, the three `ChatLayout`/`CreateChannelDialog` files, `session.test.ts`,
  `chat.test.ts`, `test_schema.py`, `test_r1_unreachable.py`: additions only, apart from `a_user`'s name (reason given
  and sound). Full Vitest run: the 508 passes include every pre-existing test.
- **Races (reasoned, integration unverified):** commit/rollback halves wait for a `Lock` wait in `pg_stat_activity`
  before releasing, so a build without the unique index fails both; the polling can't be satisfied by the holder itself.
- **Clock:** `h23` proven at 00:05 in the suite's locale; instants built in local time; context tests use 24h then 12h
  on one instant, so a formatter that ignores the context fails one of the two; "no clock" compares against the old calls.
- **Report matches tree:** every changed file is in the plan's file map; observed reds match what I saw; departures
  (split races, `Refused`, `chr()` for invisibles) are explained and sound. `test/api.ts` stubs follow `auth.membersBy`.
- **No `data-testid` in Vitest**; BDD selectors only in the page object; steps use `parsers.re` with `[^"]*`.

