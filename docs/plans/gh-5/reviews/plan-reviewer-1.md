# Plan review — gh-5, round 1: changes_requested

A strong plan: every requirement and *Decided already* item is covered, the readings the issue leaves
open are decision rows, and the issue's two false assumptions are caught. Four majors remain, each a
small fix: the rename's two cache writes have no answer for a fetch already in flight, the migration's
dedupe has no rule or test for a newer non-duplicate that already holds a suffix, one test file that
renders `ChatLayout` is missing from the ripple, and the migration tests' database fixture would hit
`asyncio.run` inside a running loop, which the red import failure hides.

## Expectations

Written from the issue, doc 01 §3–§4, doc 06 §5.2 *Names*/§9, Conventions §5.4, register D28,
and the code (`routers/users.py`, `identities.py`, `oidc.py`, `routers/federation.py`,
`schemas.py`, `shared/problems.py`, `App.tsx`, `lib/auth/session.ts`, `lib/auth/api.ts`,
`useWorkspaceMembers.ts`, `WorkspaceSwitcher.tsx`, `stores/chat.ts`, the auth integration
conftest and `test_schema.py`) before the plan was opened.

### Decisions
- D1. Req 1's "1–100 characters" is *after* trim+NFC — but `UpdateUserRequest` has
  `min_length=1, max_length=100` on the raw input. Is a 99-char name with leading spaces, or
  a decomposed name that is >100 code points raw and ≤100 after NFC, accepted? Is
  "characters" code points?
- D2. Where does `Default_Ignorable_Code_Point` come from? Python's `unicodedata` has no
  such property — a hand-written table, the `regex` package, or something else; and which
  Unicode version (Python's `unidata_version` decides Cn)?
- D3. "The application and the database compare the same way" — `lower()` vs Python
  `.lower()`/`.casefold()`; Postgres 18 also has `casefold()`. Which, and does the DB's
  collation/ctype (C vs en_US.utf8 vs builtin) change what `lower()` folds? The issue asks
  the plan to say whether `lower()` ≠ full case folding matters.
- D4. The 409: pre-check, or catch the unique-index `IntegrityError` (by constraint name),
  or both? A pre-check alone loses the race.
- D5. "Saving the name you already have … changes nothing" — do `version` and
  `updated_at` stay untouched (today they always bump)?
- D6. Req 3's suffix for an IdP name that itself fails Req 1 (control chars, empty after
  trim, >100 chars, or `X` at 99–100 chars so `X 2` exceeds 100) — "sign-in never refuses
  over a name", so what is stored?
- D7. Req 4's migration: what happens to a stored name that fails Req 1 after
  normalising (empty, >100, ignorable chars)? Does "oldest" include deleted accounts? What
  if `X 2` is already taken by another stored name? Downgrade?
- D8. Sign-in returning to `/settings`: `Protected` sends to `/sign-in` and `Callback`
  always navigates to `/` — the issue's assumption is false today. Built, or declared?
- D9. "Back to chat … to the last channel" — from what state, and what when there is none
  (direct load of `/settings`)?
- D10. Is `/settings` inside `ChatLayout` (sidebar with `current-user`) or standalone?
- D11. Client-side "invalid" for Save's disabled state — does the SPA replicate Req 1's
  rules (JS `\p{Default_Ignorable_Code_Point}`), and is "unchanged" compared raw or
  normalised?
- D12. How the clock reaches the three formatters: `hour12` or `hourCycle` (`h23` vs
  `hour12:false`, which some engines render midnight as `24:xx`), and how
  `toLocaleString` with `dateStyle`/`timeStyle` (SearchResult) takes it.
- D13. Where chat pages get the `clock` preference — a preferences query used outside
  `/settings` too; what renders before it loads?
- D14. "Reads … from the server on every visit" — fresh fetch on each mount of `/settings`
  (`staleTime: 0`/`refetchOnMount: 'always'`), not the session `profile`.
- D15. Preferences PATCH semantics: body not an object, `{}`, `null` for an absent key on
  a user with no row — does PATCH create the row? What does `version` do?

### Conflicts
- C1. Decided already 4 (409 reveals a name in another workspace) vs Conventions §5.4 /
  CLAUDE.md "404 not 403" tenancy — needs the conventions exception in the record.
- C2. D28 is 🔴 in the register today; Decided already 7 decides it 🟢 — the record task
  must flip it in this slice or the plan builds on a 🔴.
- C3. Paths: "`/settings` while signed out → back on `/settings`" vs the code (D8).
- C4. Req 5 "renamer's own tab shows the new name at once" vs Decided already 6 / doc 06
  "Renames are not covered" — doc 06 must be updated, not contradicted.

### Tests
- T1. Every Req 1 example both sides at unit (pure validator), plus the trim-then-length
  boundary (100 vs 101 after trim/NFC).
- T2. 409 case-insensitive and NFC-only collisions; own-capitals rename; deleted account
  keeps its name; "naming nobody" — the 409 body asserted to hold no name/workspace.
- T3. Concurrent rename — two real concurrent transactions, exactly one 200.
- T4. First sign-in suffix incl. `X 2` already taken → `X 3`, two at once, workspace named
  from the suffixed result, and a rename racing a sign-in.
- T5. Migration: duplicates only after normalisation, oldest kept, deleted included,
  existing `X 2` collision — on a DB at the previous revision with seeded rows.
- T6. Preferences: merge, `null`, unknown key, bad value, `{}` with no row (and no row
  created), 404 deleted, two concurrent PATCHes of different keys (only one key exists —
  how is "don't lose each other's change" proven?).
- T7. Vitest: Save disabled unchanged/invalid, 400/409 on the field, "Saved"; session
  profile *and* directory updated; unmount mid-save still updates both; clock in all three
  formatters with a fixture that differs 12h vs 24h (afternoon time); revert on failure.
- T8. BDD: Alan renames; Grace's last step after a reload.

### Risks
- R1. Existing tests seed duplicate names: `test_schema.py:a_user()` gives every user
  "Ada Lovelace" — the unique index breaks it (a RED-stage change). Auth conftest `TABLES`
  must gain `user_preferences`.
- R2. Federation commits only at the end (`federation.py:212`, after `issue_code`): an
  `IntegrityError` on name there would fail the sign-in. The suffix retry needs a flush in a
  savepoint inside `provision_user`; a concurrent uncommitted insert blocks the flush.
- R3. Renewal race: `adopt()` re-reads `/users/me`; a renewal/switch in flight across a
  rename lands after the rename's session write and puts the old name back.
- R4. Directory race: a members fetch in flight when the rename succeeds lands with the old
  name over `setQueryData`; other workspaces' cached directories keep the old name.
- R5. TanStack `useMutation` callbacks: options-level `onSuccess` runs after unmount;
  `mutate(…, { onSuccess })` does not. Which does the plan rely on?
- R6. Clock revert: two quick choices where the first fails after the second succeeds.
- R7. CH008 — no display name in a log, including migration logging.
- R8. Ripple: doc 01/06/conventions/register/2 ADRs, `api.ts` hand types, BDD `alan`
  fixtures, ingress already allows `/api/v1/users` (checked), nginx SPA fallback (checked).

## Coverage

| Issue item or expectation | Plan | Outcome |
|---|---|---|
| Req 1 trim, NFC, 1–100, refused categories, examples both sides, 400 `errors.displayName`, nothing changes, re-save no-op | Decisions 14, 18, 19; Task 1 table; Task 2 `…stored_trimmed…`, `…refused…`, `…accepted…`, `…100…`, `…saving the name you have…` | covered |
| Req 2 unique, case/NFC-insensitive, app = DB, deleted included, 409 text naming nobody, own capitals, `josé`/`José` | Decisions 12, 13; Task 2 409 tests; `test_schema` index test | covered (key column replaces `lower()`, as a Correction) |
| Req 3 suffix on first sign-in, workspace from result, never refuses, never overwrites | Decisions 13, 15, 16; Task 2 sign-in tests | covered |
| Req 4 migration: trim+NFC with Req 1's code, dedupe keeping oldest, Req 3 suffix, one-way | Decisions 17, 31; Task 1 `dedupe` tests; Task 2 migration tests | **misread in one case** — finding 2 |
| Req 5 own tab at once (sidebar + own messages); others on next refetch; no broadcast | `applyRename`, Decision 30; App tests | covered, **race unanswered** — finding 1 |
| Req 6 preferences GET/PATCH, `{}` no row, merge, `null`, 400 per key, 404 deleted | Decisions 20, 21; `test_preferences.py` | covered |
| Req 7 clock, three formatters, at once, revert on failure | Decisions 22, 23, 29; `clock.test.ts`, `clockApplied.test.tsx`, page tests | covered |
| Req 8 page, Save states, Saved, link from `current-user`, Back to chat, server read every visit, direct load | Decisions 24–28; `SettingsPage.test.tsx`, `App.settings.test.tsx` | covered (finding 7 minor) |
| Decided 1–11 | Decisions table rows 1–11 | covered |
| Where the rules meet ×7 | Self-review maps each | covered |
| Paths ×8 | App tests, journey, integration | covered |
| Tests (pytest, Vitest, one BDD journey, `alan` fixture) | Tasks 1–4 | covered |
| Record (register D28/D46, 2 ADRs, docs 01/06, conventions §5.4) | Task 8 | covered |
| Not in this issue | *Not in this plan* | covered |
| D1 length after trim, code points | Decision 14 (assumed), Task 6 drops pydantic bounds | settled |
| D2 DI table / Unicode version | Task 1 table, Unicode 15.0 (Python 3.12 — `pyproject.toml` pins `<3.13`) | settled; ranges checked against DerivedCoreProperties 15.0 |
| D3 app vs DB comparison | Decision 12 | settled |
| D4 pre-check vs index | Decision 13 | settled |
| D5 re-save bumps nothing | Decision 18 | settled |
| D6 unusable / long IdP name | Decisions 15, 16 | settled |
| D7 bad stored names, deleted oldest, existing suffix holder | Decision 17; migration test (deleted oldest) | settled except the newer-holder case — finding 2 |
| D8 / C3 return to `/settings` after sign-in | Correction + Decision 25 | settled |
| D9 Back to chat target | Decision 26 | settled |
| D10 inside the shell | Decision 27 | settled |
| D11 client validity | Decision 24 | settled |
| D12 `hourCycle` | Decision 23 | settled |
| D13 clock outside `/settings` | Decision 22 (`data?.clock` → Automatic until loaded) | settled |
| D14 fresh read each visit | Decision 28 | settled (finding 7) |
| D15 PATCH edge bodies | Decision 20, `test_an_empty_patch_writes_nothing` | settled |
| C1 D46 vs §5.4 | Decision 4, Task 8 | settled |
| C2 D28 🔴 → 🟢 | Decision 7, Task 8 | settled |
| C4 doc 06 "Renames are not covered" | Task 8 doc 06 §5.2 + sweep | settled |
| T1–T8 | Tasks 1–4 | covered (T5 gap: finding 2) |
| R1 `test_schema` duplicates; `TABLES` | Task 2; *Deliberately unchanged* (CASCADE — checked `testkit/db.py:27`) | settled (finding 5 minor) |
| R2 federation commits late | Decision 13 savepoint in `provision_user` | settled |
| R3 renewal `adopt()` overwrites profile | — | **missing** — finding 1 |
| R4 in-flight directory fetch | — | **missing** — finding 1 |
| R5 unmount callbacks | Decision 30 | settled; checked |
| R6 clock save ordering | Decision 29 | settled; checked |
| R7 CH008 | Global constraints | settled |

## Findings

### 1. A rename's cache writes have no answer for a read already in flight — major
**Where:** Decision 30, Task 3 `applyRename` · **Checked:** `lib/auth/session.ts:76-94` (`adopt()`
fetches `api.me` then `set()`s the profile), `:122-138`, `:199-212`;
`useWorkspaceMembers.ts:53-64`; TanStack `setQueriesData` does not cancel a running fetch.
`applyRename` writes the session profile and every cached directory. Two readers can land after it
with the old name: a renewal or workspace switch whose `GET /users/me` was answered before the rename
committed (then `adopt()` restores the old name in the sidebar until the next renewal, ≤15 min), and a
directory fetch already in flight (focus, reconnect, unknown id) that lands after `setQueriesData`. The
issue's *Where the rules meet* row 3 says the sidebar and own messages "never disagree". Settle each
pair — e.g. cancel or invalidate the directories rather than only writing them, and have
`updateProfile` survive a later `adopt()` of an older read — or say why it is harmless, in a decision
row; and name a test with a held fetch (`holdHistoryFetch`-style) for whichever is built.

### 2. Dedupe can rename a name that was never a duplicate — major
**Where:** Task 1 `dedupe` tests, Task 2 migration tests, Decision 17 · **Checked:** issue Req 4.
Req 4 renames "every duplicate except the oldest". `test_dedupe_skips_a_suffix_someone_already_holds`
has the holder of `"Sam 2"` **older** than the duplicate, where processing by age and reserving every
pre-existing unique name give the same answer. With `"Sam"` (t0), `"sam"` (t1), `"Sam 2"` (t2), a
build that assigns by age gives `"sam"` → `"sam 2"`, then renames the non-duplicate `"Sam 2"` to
`"Sam 2 2"`. State the rule (every name that is not a duplicate, and every oldest holder, is reserved
before any suffix is chosen) and add the newer-holder fixture at unit, and in the migration test.

### 3. `CreateChannelDialog.test.tsx` renders `ChatLayout` and is not in the ripple — major
**Where:** File map row "App.test.tsx · ChatLayout.test.tsx · ChatLayout.attachments.test.tsx", Task 3
*Ripple* · **Checked:** `grep ChatLayout src/**/*.test.tsx` — `CreateChannelDialog.test.tsx:112`
mounts `<ChatLayout current={aSession()}>`; `test/setup.ts:32` is `onUnhandledRequest: 'error'`.
Once Task 7 makes `ChatLayout` fetch preferences, that file's tests meet an unstubbed request at green,
where the code-writer may not touch a test. Add it to the RED ripple (and re-grep for any other mount).

### 4. The migration tests' database can't be made where the plan makes it — major
**Where:** Task 2, `test_name_migration.py` paragraph · **Checked:** `testkit/databases.py:36-49`
(`service_database` is synchronous and calls `asyncio.run` twice); root `pyproject.toml:61`
`asyncio_mode = "auto"`.
"Each test makes a database of its own … `service_database(…)`, seeds `users` with SQL, then
`await`s `upgrade_to(…, "head")`" reads as an `async def` test calling it — which raises
`RuntimeError: asyncio.run() cannot be called from a running event loop`. At red the file fails on the
`upgrade_to` import first, so the test-reviewer never sees it, and the code-writer can't fix it. Say how
the per-test database is made (a sync function-scoped fixture, as `postgres_dsn` is, or
`asyncio.to_thread`).

### 5. `a_user`'s derived names must differ in key, not only in case — minor
**Where:** Task 2 `test_schema.py` · **Checked:** `test_schema.py:21-48`.
`test_email_uniqueness_ignores_case` uses `ada@example.com` and `ADA@EXAMPLE.COM`; a name "derived
from the email" (its local part, or the email itself) has the same `display_name_key` for both, so the
test would still pass on the name index — the thing the change is meant to stop. Derive it from
something case-distinct (the uuid).

### 6. `version = version + 1` in Decision 21's upsert — minor, unverified
**Where:** Decision 21 · **Checked:** *unverified* (no run). Postgres reports an unqualified column in
`ON CONFLICT DO UPDATE SET` as ambiguous with `excluded`; qualify it as `prefs` already is.

### 7. A second visit can prefill from the cached profile — minor
**Where:** Decision 28, Task 7 "the Profile form renders once the profile has loaded" · **Checked:**
issue Req 8. With `['me', userId]` cached from an earlier visit, the form has data before the
`refetchOnMount: 'always'` read lands, and a field initialised once keeps the stale name. Say whether
the form waits for the fetch made on this mount, and let `every visit reads the profile and preferences
again` assert the field's value, not only that a request went out.

### 8. Step phrase `written by "Alan Turing"` departs from the vocabulary — minor
**Where:** Task 4 · **Checked:** `docs/plans/ch06/gherkin/00-scenario-vocabulary.md:344`,
`test_message_steps.py:39` — the existing form is `Grace sees "{body}" written by Ada` (bare name).
Either keep the vocabulary's form (`written by Alan Turing` via `parsers.re`) or record the variant.

## Left for later stages

- Minor findings 5–8, if not taken up.
- **Assumed** decisions the human should see at the end: 14 (code points), 15–16 (repairing and
  cutting an IdP name), 17 (repairing a stored name the migration finds invalid), 20 (unknown stored
  keys omitted), 24 (Save's client-side checks), 25 (return-to-route after sign-in, for every protected
  route), 26 (Back to chat target), 27 (`/settings` inside the shell).
- Code pair: Decision 12 compares with full case folding (`ß` = `SS`) — wider than `lower()`; the D46
  ADR should say so.

## Checked and sound

- Header base `957371e` is `main` and the parent of `82c8bcb` (`git log`); 598 lines, sections in the
  exemplar's order, *Found while building* empty, no committing task, RED 1–4 before GREEN 5–7.
- Corrections: `App.tsx:63,83` confirm no return path; `routers/users.py:61-65` and
  `test_users.py:101` confirm null → 400; only `identities.py:101` constructs `User`, no raw
  `INSERT INTO users` anywhere in `src`/`tests`/`tools`.
- TanStack 5 (primary checkout): `mutation.js:123` options `onSuccess` runs regardless of observers;
  `mutationObserver.js:77` skips `mutate()` callbacks without listeners; `mutationCache.js:60-79` scope
  serialises; `onMutate` runs before the scoped wait, so the optimistic re-render is immediate.
- Expected failures: preferences 404 (no route; `/{user_id}` can't match two segments); `ImportError`
  for `upgrade_to`; `ModuleNotFoundError` for `auth.names`; `… is not a function` for session exports;
  pydantic raw `max_length` refusing the padded 100.
- `TRUNCATE … CASCADE` (`testkit/db.py:27`) reaches `user_preferences`; BDD truncation leaves Auth.
- Dex test config has `alan` (`docker/dex/config.test.yaml:55`); `_signed_in_context` puts him in the
  shared workspace; the journey's last step is Grace's fresh load — the server's state.
- Ingress `/api/v1/users` (`ingress.yaml:50`); no env var; Auth has no OpenAPI module; nginx fallback.
- D28 flipped and D46 added in Task 8; no 🔴 built on (D38, D13, D18 named and untouched).
- Verification names `lint unit integration` and `e2e`, conventions and security hooks.
