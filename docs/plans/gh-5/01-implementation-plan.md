# Display names, unique names and a preferences page — implementation plan

> **For agentic workers:** this plan is executed by `scripts/deliver.sh`: the test-writer does every
> RED task, the code-writer every GREEN one. Three project rules override the superpowers skills.
> **Never commit** — every task ends with the worktree dirty. **Red first** — no production code
> until the test-reviewer has approved the failing tests. **Plans live in `docs/plans/`.**

**Goal:** A signed-in user renames themselves on a new `/settings` page; display names are unique
across CollabHub, ignoring case and Unicode form; the same page holds the first per-user preference,
a 12/24-hour clock, stored by Auth (D28).

**Architecture:** Auth gains one pure module, `auth/names.py` — trim + NFC, the refused characters,
the comparison key, the `X 2` suffix rule and the duplicate renamer — used by `PATCH /users/me`, by
`provision_user` and by migration `0002`. Uniqueness is a **`users.display_name_key` column the
application computes** (canonical caseless form) under a unique index, so the rule is computed in one
place and the index settles every race. A `user_preferences` row per user holds `prefs jsonb`, merged
in one SQL statement. The SPA adds `features/settings/` (the page, the profile and preferences
queries), writes a rename into the session profile and every cached workspace directory from the
mutation's own `onSuccess` — cancelling reads already in flight so none lands the old name over it —
and passes the clock to the three time formatters through a context `ChatLayout` provides from the
preferences query.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 async, Alembic, pytest + testcontainers (Postgres,
Redis, Dex) · React 19, TanStack Query 5.101, React Router, Vitest + MSW · pytest-bdd + Playwright.

**Issue:** `docs/plans/gh-5/00-issue.md` — read it first; this plan argues from it, not repeating it.

**Worktree:** `/home/runner/work/claude-at-work-project/caw-gh-5`, branch `feature/gh-5`, from
`main` at `957371e`.

## Decisions

Decided by the issue:

| # | Question | Answer |
|---|---|---|
| 1 | Scope | Req 1–8; *Not in this issue* stays out |
| 2 | Who renames whom | Only yourself; no admin rename |
| 3 | Name scope | One name per user, global |
| 4 | Uniqueness | Across all of CollabHub, deleted accounts included — new **D46**; the 409 names nobody and no workspace. A deliberate exception to Conventions §5.4 / the 404 rule, recorded there in Task 8 |
| 5 | Lookalikes, ZWJ/ZWNJ | Confusables not handled; U+2800 allowed; every default-ignorable refused, ZWJ/ZWNJ included |
| 6 | Live push of a rename | None; doc 06's "Renames are not covered" stays true except for the renamer's own tab |
| 7 | Preferences (**D28**, 🔴 in the register today, decided by this issue) | Auth, `user_preferences(user_id, prefs jsonb, version, updated_at)`, per user, server-validated keys; SPA holds them in TanStack Query only (D24); the name stays on `users` |
| 8 | Preferences offered | `clock` only |
| 9 | R1 down | Both PATCH routes `require_user`, fail open (not in Conventions §5.2's set) |
| 10 | Auth client types | Hand-typed in `lib/auth/api.ts`: `updateMe`, `preferences`, `updatePreferences` |
| 11 | Logs | No display name in any log call (CH008) |

Taken in this plan:

| # | Question | Answer | Why, and the alternative |
|---|---|---|---|
| 12 | How "ignoring case" is compared | `display_name_key = NFC(NFD(stored).casefold())`, computed by `names.name_key` and set by a SQLAlchemy `@validates("display_name")` on `User`, so no ORM writer can forget it; unique index `uq_users_display_name_key` | The issue asks app and DB to compare the same way. A unique index on `lower(display_name)` would compare in the DB with rules that depend on the database's `LC_CTYPE` (ASCII-only under `C`) and are not case folding (`ß`/`SS`, final sigma), while the app would need its own copy. One function, one stored key, one index. Cost to change later: a migration recomputing the column |
| 13 | Making the race safe | The unique index is the authority. `update_me` maps the `IntegrityError` at commit to the 409. `provision_user` inserts the user inside a SAVEPOINT; on `IntegrityError` it re-checks whether that key is now taken — taken: next candidate; not taken: re-raise (an email race, as today) | Advisory locks would serialise every sign-in; a check-then-insert alone loses the race the issue names |
| 14 | "1–100 characters" — **assumed** | Code points of the stored (trimmed, NFC) form, Python `len`; the SPA counts `[...s]` | The issue doesn't say. Graphemes would need a library on both sides. Changing it: `names.check` and one SPA line |
| 15 | An IdP name that fails Req 1 (empty, refused characters, over 100) — **assumed** | `names.provisional`: normalise, drop refused characters, truncate to 100, else the email's local part treated the same, else `"user"`; then the suffix rule | Req 3 says sign-in never refuses over a name; it doesn't say how an unusable name is repaired. Changing it: one function |
| 16 | A suffix that would pass 100 characters — **assumed** | The base is cut so `"{base} {n}"` is at most 100 | Otherwise Req 3 could create a name Req 1 refuses |
| 17 | Stored names that fail Req 1 at migration time — **assumed** | Migration 0002 passes each normalised name through `names.provisional(name, email local part)` only when `names.check` refuses it, then dedupes | Req 4 says trim + NFC; it can't have meant to store `""` (a `"   "` name `PATCH` accepts today). Changing it: one branch; the data change is one-way either way |
| 17a | Which names a suffix may not take | Before any suffix is chosen, `dedupe` **reserves** the key of every name that is no duplicate and of the oldest holder of every duplicate group; only then are the newer duplicates suffixed, oldest first, each skipping reserved and already-given keys | Req 4 renames "every duplicate except the oldest" — a name that was never a duplicate (`"Sam 2"`, newer than a duplicated `"sam"`) is never renamed. The alternative, assigning purely by age, renames it |
| 18 | Re-saving your own name | 200, **no write**: `version` and `updated_at` unchanged | "changes nothing" (Req 1) read literally |
| 19 | Messages | `"A display name is required."`, `"A display name can be at most 100 characters."`, `"A display name can't contain invisible or control characters."`; 409: `detail` and `errors.displayName` both `"That name is already taken."` | The issue fixes only the 409 text |
| 20 | Preferences wire shape | A bare object of the stored, known keys (`{}` or `{"clock":"24h"}`); `PATCH` returns the merged result; `PATCH {}` writes nothing | "returns the stored keys" (Req 6). Unknown keys a row may hold are left out of the response — **assumed**; none can be written through the API |
| 21 | The merge | `INSERT … ON CONFLICT (user_id) DO UPDATE SET prefs = (user_preferences.prefs \|\| :set) - :removed, version = user_preferences.version + 1, updated_at = now() RETURNING prefs` (both columns qualified: an unqualified one is ambiguous with `excluded`) | One statement under the row lock: two tabs' different keys both survive, and the first-write insert race can't 500 |
| 22 | How the clock reaches the formatters | `ChatLayout` fetches preferences (`usePreferences`) and provides `ClockContext`; `MessageItem`, `ThreadSummary`, `SearchResult` read `useClock()` | Every page that shows a time is inside the shell; leaf components stay free of tokens and queries, and their existing tests (no context → Automatic) are untouched |
| 23 | 12/24 hours | `hourCycle: 'h12'` / `'h23'`, not `hour12` | `hour12: false` can produce `h24` ("24:05") in some engines; `h23` cannot |
| 24 | When Save is disabled — **assumed** | Value unchanged (`trim().normalize('NFC')` equals the stored name), empty after trimming, over 100 code points, or a save in flight. Everything else goes to the server, whose 400 renders on the field | The full rule lives once, in Python. JS `trim()` and Python `strip()` differ on a few code points; that only moves a button, never what is stored |
| 25 | Return to the route after sign-in — **assumed** | `Protected` passes `location` to `/sign-in`; `signIn(provider, returnTo)` stores a safe same-origin path in `sessionStorage` (`collabhub.returnTo`); `/auth/callback` navigates to `takeReturnPath()` | The Paths table needs it and the SPA doesn't do it (see *Corrections*). Applies to every protected route. A second sessionStorage entry, a path only — doc 06 §4 updated. Changing it: three functions |
| 26 | "Back to chat" target — **assumed** | `/c/{lastChannelId}` from the chat store (client state; `ChannelView` clears `activeChannelId` on unmount), else `/`; cleared on a workspace change | A channel id from the old workspace would open its 404 |
| 27 | Where `/settings` renders — **assumed** | Inside the chat shell, so the sidebar's `current-user` stays visible | It is how "the sidebar shows the new name at once" is seen |
| 28 | Cache keys, and a fresh read | `['me', userId]` and `['user-preferences', userId]`, not workspace-scoped; Settings' observers use `refetchOnMount: 'always'`, and the Profile form renders only once `isFetchedAfterMount` (`queryObserver.js:328`) and the read succeeded — a profile cached by an earlier visit never prefills the field. A failed read shows `role="alert"` "Couldn't load your profile." and no form | Per user (Decided 3, 7); "reads from the server on every visit" (Req 8); a field is initialised once, so it must wait for this visit's read |
| 29 | Clock save races | Writes are serialised (`scope: { id: 'user-preferences' }`, `mutationCache.js:30-75`). On error a mutation rolls back to its snapshot only if the cache still holds its own optimistic value, then invalidates the query | A failure must not undo a later choice; two failures end on the server's truth |
| 30 | Unmount mid-save | Cache and session writes live in `useMutation`'s own `onSuccess` (`mutation.js:123`, runs whatever observes it), never in `mutate(…, { onSuccess })` (`mutationObserver.js:77`, skipped once unsubscribed) | Paths row "Leaving mid-save" |
| 30a | A directory or profile read in flight when a rename lands | `applyRename`, in order and synchronously: `cancelQueries` on `['workspace-members']` and `['me', id]` (reverts at once — `retryer.js:29-34`, `query.js:267-273`; the cancelled response is discarded); `setQueriesData` with the new name; `invalidateQueries({ queryKey: ['workspace-members'], refetchType: 'all' })`, so every cached directory is re-read after the commit | Writing alone loses to a fetch answered before the commit (`setQueriesData` cancels nothing); `invalidateQueries` alone cancels only a query that already has data (`query.js:188`) and leaves the sidebar on the old name until it lands. Cost: one members request per cached workspace per rename |
| 30b | A renewal or switch whose `GET /users/me` was answered before the rename | `updateProfile` bumps a module counter; `adopt()` notes it before its reads and, if it moved meanwhile and the profile read is the same user's, keeps the session's profile over the read | Else `adopt()` puts the old name back in the sidebar for up to a renewal (≤15 min), and the sidebar and own messages disagree (*Where the rules meet* row 3). A read started after the rename is adopted as it is — the guard can't freeze a name |
| 31 | Migration code | `0002` imports `auth.names` | The issue requires "the same code as Req 1". Cost: a later edit to `names.py` changes what a fresh run of 0002 does — recorded in its docstring |
| 32 | Register | D28 → 🟢 (issue); new **D46** 🟢 in Platform/Auth | — |
| 33 | The journey's author step | `Then Grace sees "…" written by Alan Turing` — the vocabulary's bare form (`00-scenario-vocabulary.md:344`), its tail read as a display name by a `parsers.re` step in the new steps module only | The existing `written by Ada` binds in `test_message_steps.py` alone (per-module `scenarios`), so the two never meet |

Nearest 🔴 entries, not touched: **D38** (whether a renewal that fails on the network signs out) —
Decision 25 changes where sign-in *lands*, not renewal; **D13** (avatar bucket) — `avatarAsset` is
unchanged; **D18** (notifications) — not a preference here (Decided 8).

## Corrections to the issue

- **"A unique index on the lower-cased stored name is enough"** — not used: see Decision 12. Postgres
  `lower()` depends on the database's ctype and is not case folding, so app and DB would not compare
  the same way; the stored key makes the comparison one function.
- **"The SPA's sign-in returns to the route it started from"** — it does not. `Protected` redirects
  with no state (`App.tsx:83`) and `Callback` always navigates to `/` (`App.tsx:63`). Built here
  (Decision 25), written into doc 06 §4 in Task 8.
- **"An explicit `displayName: null` is a 400 today"** — confirmed: `routers/users.py:61-65`, pinned by
  `test_users.py:101`. Kept.
- **"`provision_user` is the only place a name is created"** — confirmed: the only `User(` in
  `src/services/auth/auth` is `identities.py:101`, called only from `link_identity`
  (`identities.py:168`); `test_schema.py:22` inserts directly in tests.
- **`hour12`/`hourCycle`** — `hourCycle` only (Decision 23), proven in the suite's locale (Task 3).

## Test approach — recommendation to the test pair

**BDD outside-in, one journey.** A new page a user sees, and the only proof that a rename made in one
browser is what another person's browser shows. Everything under it goes down the pyramid.

| Behaviour | Layer | File |
|---|---|---|
| Alan renames himself in Settings; his sidebar shows it; Grace, after loading, sees it on his message | **BDD** | `tests/bdd/features/display_names.feature` |
| Trim, NFC, every refused/accepted example, every category and ignorable range, the key, suffixes, `provisional`, `dedupe` | unit | `auth/tests/unit/test_names.py` |
| `PATCH /users/me` 400/409/no-op, deleted names, races, first-sign-in suffixing | integration | `auth/tests/integration/test_display_names.py` |
| Preferences GET/PATCH | integration | `auth/tests/integration/test_preferences.py` |
| Migration 0002 | integration | `auth/tests/integration/test_name_migration.py` |
| The index refuses a duplicate | integration | `test_schema.py` (modify) |
| Both PATCHes fail open | integration | `test_r1_unreachable.py` (modify) |
| Clock options and output | Vitest | `features/settings/clock.test.ts` |
| The three formatters follow the context | Vitest | `features/settings/clockApplied.test.tsx` |
| The page: form states, errors, Saved, clock save and revert | Vitest | `features/settings/SettingsPage.test.tsx` |
| Rename writes session + every directory, also after unmount | Vitest | `features/settings/useProfile.test.ts` |
| Routes and Paths rows through the real `App` | Vitest | `src/App.settings.test.tsx` |
| `updateProfile`, return path | Vitest | `lib/auth/session.test.ts` (modify) |
| `lastChannelId` | Vitest | `stores/chat.test.ts` (modify) |

**What no test here covers:** Grace's tab picking up the name on focus/reconnect/staleness (existing
behaviour, `useWorkspaceMembers.test.tsx`, unchanged); the `name` claim staying stale ≤15 minutes
(row 4, left as the issue leaves it); locales other than the suite's.

**Baseline**, `docs/test-report.md` at `2f1cc69acc5f`: Unit 1871 passed (auth 59, frontend 503).
Integration (only `tools/delivery`, 48) and End-to-end have no baseline; Task 9 records them.

## Global constraints

- `PATCH /users/me` edits the row named by the token's `sub`, never an id from the body (CH001).
- The name-taken lookup on `users` deliberately reads deleted rows (D46): CH009 fires on that
  `select()` — waive it on its line with `# conventions: ok — a deleted account's name stays taken (D46).`
- No display name in a log call (CH008); the 409 body carries no user id, email or workspace.
- Every SQL value is a bound parameter (CH006), the migration included.
- Ingress: `/api/v1/users` is already allowed (`charts/collabhub/templates/ingress.yaml:50`,
  checked); the preferences routes sit under it. No new environment variable. No chart change.
- SPA: server state in TanStack Query only (D24); Vitest queries by role/label/text, never
  `data-testid`; BDD selectors only in page objects. Everything else is as CLAUDE.md says.

## File map

Paths shortened: `auth/` = `src/services/auth/`, SPA paths relative to `src/frontend/src/`.

| File | Change | Responsibility | Task |
|---|---|---|---|
| `auth/tests/unit/test_names.py` | create | the name rules | 1 |
| `auth/tests/integration/` `test_display_names.py` · `test_preferences.py` · `test_name_migration.py` | create | rename, 409, races, first sign-in · preferences routes · migration 0002 | 2 |
| `auth/tests/integration/` `test_schema.py` · `test_r1_unreachable.py` | modify | distinct names in `a_user`, the unique index · fail-open for both PATCHes | 2 |
| `test/api.ts` | modify | `auth.updateMe`, `auth.preferences`, `auth.updatePreferences`, `auth.meBy` stubs | 3 |
| `features/settings/clock.test.ts` · `clockApplied.test.tsx` · `SettingsPage.test.tsx` · `useProfile.test.ts` | create | the SPA's red | 3 |
| `App.settings.test.tsx` | create | routes and Paths rows | 3 |
| `lib/auth/session.test.ts` · `stores/chat.test.ts` | modify | new tests | 3 |
| `App.test.tsx` · `features/channels/ChatLayout.test.tsx` · `ChatLayout.attachments.test.tsx` · `CreateChannelDialog.test.tsx` | modify | add `auth.preferences({})` to signed-in arrangements — `ChatLayout` now fetches preferences | 3 |
| `tests/bdd/features/display_names.feature` · `steps/test_display_name_steps.py` | create | the journey | 4 |
| `tests/bdd/pages/chat_page.py` · `tests/bdd/conftest.py` | modify | settings methods; `alan_context`/`alan` | 4 |
| `auth/auth/names.py` · `alembic/versions/0002_unique_display_names.py` | create | the rules · key, dedupe, index, `user_preferences` | 5 |
| `auth/auth/models.py` · `migrations.py` | modify | `display_name_key`, `@validates`, `UserPreferences` · `upgrade_to(dsn, revision)` | 5 |
| `auth/auth/identities.py` · `routers/users.py` · `schemas.py` | modify | `provision_user` suffixing · rename rules, 409 · request/response models | 6 |
| `auth/auth/routers/preferences.py` · `preferences.py` · `main.py` | create · create · modify | preferences routes and SQL | 6 |
| `lib/auth/api.ts` · `session.ts` · `storage.ts` | modify | client calls; `updateProfile`; return path | 7 |
| `App.tsx` · `features/channels/WorkspaceSwitcher.tsx` · `ChatLayout.tsx` · `stores/chat.ts` | modify | route, link, `ClockContext`, `lastChannelId` | 7 |
| `features/settings/clock.ts` · `usePreferences.ts` · `useProfile.ts` · `SettingsPage.tsx` | create | the feature | 7 |
| `features/channels/MessageItem.tsx` · `threads/ThreadSummary.tsx` · `search/SearchResult.tsx` | modify | `useClock()`; their D28 comments | 7 |
| `docs/design/00-…` · `01-…` · `06-…` · `07-…` · two ADRs · `auth/api.http` | modify / create | the record | 8 |

Deliberately unchanged: the Auth conftest's `TABLES` — `TRUNCATE … CASCADE` (`testkit/db.py:27`)
reaches `user_preferences` through its foreign key, and a table missing at red would error every Auth
integration test; `tests/bdd/conftest.py`'s truncation (Task 4 survives it); the `name` claim.

## How this plan runs

| Phase | Tasks | Who | Ends with |
|---|---|---|---|
| **RED** | 1–4 | test-writer | failing unit, integration, Vitest and BDD tests, each failing for the reason given — **test-reviewer gate** |
| GREEN — Auth | 5–6 | code-writer | Tasks 1–2 pass |
| GREEN — SPA | 7 | code-writer | Task 3 passes, `typecheck` clean |
| Finish | 8–9 | code-writer | the record, then verification (the journey's first run) |

One RED phase: Auth's types are hand-typed, so `tsc` is red from Task 3 to Task 7 like the tests.

---

## Task 1: The name rules (RED)

**Files:** `auth/tests/unit/test_names.py` (create)

**Interfaces** — `auth.names`, implemented in Task 5:

```python
MAX_LENGTH = 100
class InvalidNameError(ValueError):      # str(exc) is the user-facing message (Decision 19)
def normalise(raw: str) -> str           # unicodedata.normalize("NFC", raw.strip())
def check(name: str) -> None             # on a normalised name; raises InvalidNameError
def clean(raw: str) -> str               # normalise, then check; the stored form
def name_key(name: str) -> str           # NFC(NFD(name).casefold())
def candidates(base: str) -> Iterator[str]          # base, "base 2", "base 3", … each ≤ 100
def first_free(base: str, taken: Collection[str]) -> str   # taken holds keys
def provisional(raw: str, fallback: str) -> str     # Decision 15; always passes check()
@dataclass(frozen=True) class NameRow: id: UUID; created_at: datetime; display_name: str; email: str
def dedupe(rows: Sequence[NameRow]) -> dict[UUID, str]   # every row's final name (Req 4, Decisions 17, 17a)
```

Refused: general category in `{"Cc","Cf","Cs","Co","Cn","Zl","Zp"}`, or `Default_Ignorable_Code_Point`.
Python's `unicodedata` has no such property, so `names.py` carries the Unicode 15.0 table
(Python 3.12's `unidata_version`) as ranges — the value is the point:

```python
_DEFAULT_IGNORABLE = (
    (0x00AD, 0x00AD), (0x034F, 0x034F), (0x061C, 0x061C), (0x115F, 0x1160), (0x17B4, 0x17B5),
    (0x180B, 0x180F), (0x200B, 0x200F), (0x202A, 0x202E), (0x2060, 0x206F), (0x3164, 0x3164),
    (0xFE00, 0xFE0F), (0xFEFF, 0xFEFF), (0xFFA0, 0xFFA0), (0xFFF0, 0xFFF8),
    (0x1BCA0, 0x1BCA3), (0x1D173, 0x1D17A), (0xE0000, 0xE0FFF),
)
```

Every test fails at collection with `ModuleNotFoundError: No module named 'auth.names'` — right, since
every test in the file needs it. Each gets a one-line docstring saying what breaks if the rule goes.

| Test | Proves |
|---|---|
| `test_a_name_is_trimmed_and_composed` | `"  José  "` with `e`+U+0301 → `"José"` precomposed; `"Ada  Lovelace"` keeps its inner spaces; U+00A0 and U+3000 at the ends are trimmed |
| `test_each_refused_example_is_refused` (param: `"Grace​"`, `"Graceㅤ"`, `"Gr͏ace"`, `"Grace\x07"`, `" "`) | `clean` raises, with the Decision 19 message for each |
| `test_each_accepted_example_is_accepted` (param: both `José` forms, `"Zoë"`, `"李小龍"`, `"O'Brien"`, `"Ada  Lovelace"`, `"⠀Ada"`) | `clean` returns the expected stored form — U+2800 stays allowed (Decided 5) |
| `test_one_character_of_each_refused_category_is_refused` (param: `\x1f` Cc, `⁦` Cf, `\ud800` Cs, `` Co, `͸` Cn, ` ` Zl, ` ` Zp, mid-name) | each category on its own |
| `test_every_default_ignorable_range_is_refused_at_both_ends` | first and last code point of each range refused, and the code point just outside each end allowed (e.g. U+3163, U+3165, U+2070) — a neighbour some other rule refuses (Cn, Cf) is skipped; catches an off-by-one |
| `test_the_zero_width_joiner_is_refused` | Decided 5, named on its own |
| `test_length_counts_after_trimming` | 100 code points (+ spaces either side) accepted; 101 refused; `""` refused; `"😀" * 100` accepted (code points, not UTF-16) |
| `test_the_key_ignores_case_and_normal_form` | `name_key` equal for `"José"`, `"JOSÉ"`, `"josé"`; `"Straße"`/`"STRASSE"` equal; `"Ada"` vs `"Adá"` differ |
| `test_candidates_count_from_two` | `"X"`, `"X 2"`, `"X 3"` |
| `test_candidates_cut_the_base_to_fit` | base of 100 `a` → second candidate is 98 `a` + `" 2"`, length 100; tenth is 97 `a` + `" 10"` |
| `test_first_free_skips_taken_names_ignoring_case` | taken keys `{"sam", "sam 2"}`, base `"Sam"` → `"Sam 3"`; nothing taken → `"Sam"` |
| `test_provisional_drops_refused_characters_and_truncates` | `"Gr​ace"` → `"Grace"`; 120 chars → 100 |
| `test_provisional_falls_back_to_the_email_then_user` | `"​"` with fallback `"zed"` → `"zed"`; both unusable → `"user"` |
| `test_dedupe_keeps_the_oldest_and_suffixes_the_rest_by_age` | `"Sam"` (t0), `" sam"` (t1), `"SAM"` (t2) → `"Sam"`, `"sam 2"`, `"SAM 3"` — each keeps its own spelling as base |
| `test_dedupe_breaks_a_created_at_tie_on_id` | two rows at one instant: the lower id keeps the name |
| `test_dedupe_sees_duplicates_only_after_normalising` | `"José"` (old) and `"José"` (new) → `"José"`, `"José 2"` |
| `test_dedupe_skips_a_suffix_someone_already_holds` | `"Sam"`, `"Sam 2"`, then a newer `"sam"` → `"sam 3"`; `"Sam 2"` unchanged |
| `test_dedupe_never_renames_a_newer_name_that_was_no_duplicate` | `"Sam"` (t0), `"sam"` (t1), `"Sam 2"` (t2) → `"Sam"`, `"sam 3"`, `"Sam 2"` — fails a build that suffixes by age before reserving (`"sam 2"`, then `"Sam 2 2"`) (Decision 17a) |
| `test_dedupe_repairs_a_name_check_refuses` | `"   "` with email `zed@x` → `"zed"` (Decision 17) |
| `test_setting_a_users_display_name_sets_its_key` | `User(id=…, email=…, display_name="José").display_name_key == "josé"`; assigning `"ADA"` makes it `"ada"` — no session |

## Task 2: The routes, the SQL, the races and the migration (RED)

**Files:** as in the file map. Tests use the conftest's `client`, `sessions`, `engine`,
`postgres_server`, `app_settings` and `testkit.dexflow` sign-in; deleted accounts are made with SQL as
`test_deleted_accounts.py:29` does.

**Interfaces** — the wire contract Tasks 3, 6 and 7 depend on:

```
PATCH /api/v1/users/me              {displayName?, avatarAsset?} → 200 UserResponse
   400  errors.displayName  (Decision 19 messages; null stays "A display name is required")
   409  {detail: "That name is already taken.", errors: {displayName: ["That name is already taken."]}}
GET   /api/v1/users/me/preferences  → 200 {} | {"clock": "12h"|"24h"}        404 deleted account
PATCH /api/v1/users/me/preferences  {"clock": "12h"|"24h"|null}  → 200 merged object
   400  errors.<key> for an unknown key (extra="forbid") or a bad value     404 deleted account
detail on both 404s: "This account no longer exists."
```

`auth.migrations.upgrade_to(dsn: str, revision: str) -> None` (async); `upgrade_to_head` calls it with
`"head"`.

`test_display_names.py` — red is the route answering today's way:

| Test | Proves | Expected red |
|---|---|---|
| `test_a_name_is_stored_trimmed_and_composed` | `"  José  "` → 200 `"José"` (NFC), and GET agrees | assertion: stored untrimmed, decomposed |
| `test_a_refused_name_is_400_on_display_name_and_changes_nothing` (param: Req 1's five) | 400, `"displayName" in errors`, `GET /users/me` unchanged | assertion: 200 for all five (`" "` passes `min_length`) |
| `test_every_accepted_example_is_stored` (param) | 200 and the exact stored form | the decomposed `José` fails; the rest already pass — they pin the positive side |
| `test_a_100_character_name_with_spaces_is_kept_and_101_refused` | `" " + "a"*100 + " "` → 200; `"a"*101` → 400 | assertion: raw 102 > `max_length` → 400 |
| `test_a_taken_name_is_409_naming_nobody` | Ada → `"GRACE"`: 409 with the exact body; body has no `grace@`, no Grace's id, no workspace name; Ada's name unchanged | assertion: 200 |
| `test_names_that_differ_only_in_normal_form_collide` | Ada `"José"`, Grace `"josé"` → 409 | assertion: 200 |
| `test_changing_only_your_own_capitals_is_allowed` | Ada `"ada"` → `"ADA"` 200; Grace → `"ADA"` 409 (same request, another user) | assertion: Grace's is 200 |
| `test_saving_the_name_you_have_changes_nothing` | 200; `users.version` and `updated_at` unchanged (read with `sessions`) | assertion: version bumped |
| `test_a_deleted_accounts_name_stays_taken` | Grace deleted; Ada → `"grace"` 409; Ada → `"Grace Hopper"` 200 | assertion: 200 |
| `test_two_renames_to_one_name_at_once_one_wins` | Grace and Alan `PATCH "Sam"` via `asyncio.gather` → statuses `[200, 409]`; one row with key `sam` | assertion: `[200, 200]` |
| `test_a_rename_racing_an_uncommitted_first_sign_in` | a session holds an uncommitted `provision_user(display_name="Sam")`; Grace's `PATCH "Sam"` is started as a task, then the holder **commits** → 409; second variant, the holder **rolls back** → 200 | assertion: 200 in the commit variant (no index, nothing blocks) |
| `test_a_first_sign_in_racing_an_uncommitted_rename` | a session holds Grace's row renamed to `"Sam"`, uncommitted; `provision_user(display_name="Sam")` in its own session as a task; holder commits → `"Sam 2"`; rolls back → `"Sam"` | assertion: `"Sam"` in the commit variant |
| `test_two_first_sign_ins_with_one_name_both_succeed` | two `provision_user("Sam")`, each in its own `sessions.begin()`, gathered → names `{"Sam", "Sam 2"}`, both rows exist | assertion: `{"Sam"}` |
| `test_a_first_sign_in_with_a_taken_name_takes_the_next_suffix` | Grace renames to `"ada"`, Alan to `"ada 2"`; Ada's first Dex sign-in → `"ada 3"` and her own workspace `"ada 3's Workspace"` | assertion: `"ada"` |
| `test_an_unusable_idp_name_still_signs_in` | `provision_user(display_name="​", email="zed@collabhub.dev")` → `"zed"` | assertion: `"​"` stored |
| `test_a_sign_in_never_overwrites_an_existing_name` | Ada renames to `"Ada L"`, signs in again → `"Ada L"` | passes at red — pins Req 3's last clause |
| `test_a_rename_leaves_the_workspace_name_alone` | after Ada's rename, her own workspace is still `"ada's Workspace"` | passes at red — pins *Where the rules meet* row 5 |

In both "racing" tests the holder commits or rolls back only once the other side is really waiting
on it — poll `pg_stat_activity` for a `wait_event_type = 'Lock'` backend — or the race is never run.
At red nothing waits (no index), so the poll gives up after a short bound and the test goes on to
fail on its assertion.

`test_preferences.py` — red is a 404 from a route that doesn't exist:

| Test | Proves | Expected red |
|---|---|---|
| `test_no_preferences_read_as_an_empty_object_and_make_no_row` | GET 200 `{}`; `SELECT count(*) FROM user_preferences` is 0 | 404 |
| `test_a_patch_is_read_back` | `{"clock":"24h"}` → 200 same; GET same | 404 |
| `test_null_removes_a_key` | then `{"clock":null}` → `{}` | 404 |
| `test_a_patch_merges_rather_than_replaces` | row seeded by SQL with `{"clock":"12h","legacy":1}`; PATCH 24h → DB holds `{"clock":"24h","legacy":1}`; GET returns `{"clock":"24h"}` only | the seed's `INSERT` errors (`relation "user_preferences" does not exist`) — this test only |
| `test_an_unknown_key_is_400_on_that_key_and_nothing_changes` | after 12h, `{"theme":"dark","clock":"24h"}` → 400, `"theme" in errors`; GET still 12h | 404 |
| `test_a_bad_value_is_400_on_the_key` (param: `"25h"`, `12`) | `set(errors) == {"clock"}` | 404 |
| `test_an_empty_patch_writes_nothing` | `{}` → 200 `{}`, no row | 404 |
| `test_two_first_patches_at_once_both_land` | user with no row; 12h and 24h gathered → both 200, one row, value one of the two | 404 |
| `test_preferences_belong_to_the_user_not_the_workspace` | Ada sets 24h; after `/auth/switch-workspace` GET is 24h; Grace's GET is `{}` | 404 |
| `test_a_deleted_account_gets_404_with_its_detail` | 200 before; after deletion GET and PATCH 404 with `detail == "This account no longer exists."` | 404 without that detail — the assertion on `detail` tells the two apart |
| `test_preferences_need_a_token` | 401 both | 404 — routing runs before auth |

`test_name_migration.py` — every test needs `upgrade_to`, so the file fails to load with
`ImportError: cannot import name 'upgrade_to' from 'auth.migrations'`. Each test gets a database of
its own at `0001` from a **synchronous, function-scoped fixture in the file**, `db_at_0001(postgres_server)
-> str` — `service_database(postgres_server, f"auth_m_{uuid.uuid4().hex[:8]}", lambda dsn:
upgrade_to(dsn, "0001"))` — because `service_database` calls `asyncio.run` (`testkit/databases.py:46-48`)
and so can't run inside an `async def` test (`asyncio_mode = "auto"`); `postgres_dsn` is made the same
way. The `async` test then seeds `users` with SQL and `await upgrade_to(dsn, "head")`:

| Test | Proves |
|---|---|
| `test_the_migration_normalises_names_and_renames_duplicates` | `"Sam"` (oldest, **deleted**), `" sam"`, `"SAM"`, `"José"`, `"José"` → `"Sam"`, `"sam 2"`, `"SAM 3"`, `"José"`, `"José 2"`; keys set — a deleted account counts as the oldest holder |
| `test_the_migration_leaves_a_newer_unique_name_alone` | `"Sam"` (t0), `"sam"` (t1), `"Sam 2"` (t2) → `"Sam"`, `"sam 3"`, `"Sam 2"` with its `version` unchanged (Decision 17a) |
| `test_only_renamed_rows_get_a_new_version` | unchanged rows keep `version`; renamed and re-normalised ones are +1 |
| `test_after_the_migration_a_duplicate_is_refused` | inserting `"SAM"` raises `IntegrityError` (`uq_users_display_name_key`) |

`test_schema.py` (modify): `a_user(email)` gets a display name from its own id
(`f"user {user_id.hex}"`), never from the email — `ada@example.com` and `ADA@EXAMPLE.COM` would share
a key — so `test_email_uniqueness_ignores_case` fails only on the email; today both users are
`"Ada Lovelace"`, and after Task 5 it would pass on the name index. Add
`test_display_names_are_unique_ignoring_case_and_form`: `"José"` then `"JOSÉ"` (other emails) →
`IntegrityError`; `"José"` and `"Josie"` coexist. Red: `DID NOT RAISE`.

`test_r1_unreachable.py` (modify): `test_profile_and_preference_edits_fail_open_when_r1_is_unreachable`
— with the `r1_down` client, both PATCHes answer 200 (the 503 tests beside it are the other side).
Red: the preferences PATCH is a 404.

## Task 3: The SPA's red (RED)

**Interfaces** — Task 7 implements; tests import only what they need:

```ts
// lib/auth/api.ts
export type Clock = '12h' | '24h'
export interface Preferences { clock?: Clock }
export function updateMe(accessToken: string, body: { displayName: string }): Promise<Profile>
export function preferences(accessToken: string): Promise<Preferences>
export function updatePreferences(accessToken: string, patch: { clock: Clock | null }): Promise<Preferences>
// lib/auth/session.ts
export function updateProfile(profile: api.Profile): void   // signed in as profile.id → replace, notify, and outlive an adopt() whose reads began earlier (Decision 30b); else no-op
export async function signIn(provider = 'dex', returnTo?: string): Promise<void>
export function takeReturnPath(): string                     // the stored path once, then '/'
// lib/auth/storage.ts
export function isSafeReturnPath(path: string): boolean      // starts '/', not '//' or '/\', not /sign-in or /auth/
// stores/chat.ts
lastChannelId: string | null      // set by setActiveChannel(id) when id !== null; never by null
clearLastChannel(): void
// features/settings/clock.ts
export const ClockContext: React.Context<Clock | undefined>
export function useClock(): Clock | undefined
export function timeOptions(clock?: Clock): Intl.DateTimeFormatOptions
export function dateTimeOptions(clock?: Clock): Intl.DateTimeFormatOptions
export function formatTime(iso: string, clock?: Clock): string        // toLocaleTimeString([], timeOptions(clock))
export function formatDateTime(iso: string, clock?: Clock): string    // toLocaleString([], dateTimeOptions(clock))
// features/settings/usePreferences.ts
export const preferencesKeys = { mine: (userId: string) => ['user-preferences', userId] as const }
export function usePreferences(accessToken: string, userId: string, options?: { refetchOnMount?: 'always' })
export function useSetClock(accessToken: string, userId: string)      // mutate(clock: Clock | null)
// features/settings/useProfile.ts
export const profileKeys = { me: (userId: string) => ['me', userId] as const }
export function useMyProfile(accessToken: string, userId: string)    // staleTime 0, refetchOnMount 'always'
export function useRenameMe(accessToken: string, userId: string)     // mutate(displayName: string)
export function applyRename(queryClient: QueryClient, profile: Profile): void
// features/settings/SettingsPage.tsx
export function SettingsPage(props: { accessToken: string; userId: string }): JSX.Element
```

`timeOptions`: Automatic `{ hour: '2-digit', minute: '2-digit' }` (no `hourCycle` key), `'12h'` adds
`hourCycle: 'h12'`, `'24h'` adds `hourCycle: 'h23'`. `dateTimeOptions`: Automatic
`{ dateStyle: 'medium', timeStyle: 'short' }`, plus the same `hourCycle`. `applyRename`: calls
`session.updateProfile`; then, synchronously, Decision 30a — `cancelQueries` on `['workspace-members']`
and `profileKeys.me(id)`, `setQueryData` on `profileKeys.me` and `setQueriesData` replacing
`user.displayName` for `profile.id` in every cached workspace, then `invalidateQueries({ queryKey:
['workspace-members'], refetchType: 'all' })`.

**Markup** the tests query (Task 7 matches it): heading "Settings"; a "Profile" section with a textbox
labelled "Display name", a "Save" button, a `role="status"` "Saved", and the field error in
`role="alert"`; a "Preferences" section with a `fieldset` legend "Clock" and radios "Automatic",
"12-hour", "24-hour", its error in `role="alert"`; a link "Back to chat"; the sidebar's
`current-user` is a link whose name is the display name. BDD-only test ids (Task 4):
`settings-page`, `settings-display-name-input`, `settings-display-name-save`, `settings-saved`,
`back-to-chat`, and `current-user` stays on the link.

**Helpers** (`test/api.ts`): `auth.updateMe(reply: Profile | ((body) => Profile | Promise<Profile>))`,
`auth.preferences(prefs: Preferences)`, `auth.updatePreferences(reply: Preferences | ((body) =>
Preferences | Promise<Preferences>))`; a promise reply holds the request in flight, recorded on
arrival, as `auth.membersBy` does; `auth.meBy(reply: (call: number) => Profile | Promise<Profile>)`, the
same for `GET /users/me`. `Preferences` is a type import, so the helpers load at red and only `tsc` fails.

In `useProfile.test.ts` a cached directory is made the real way — `useWorkspaceMembers` mounted for the
workspace (and unmounted for an inactive one) — never by `setQueryData` alone: a query with no
`queryFn` can't be refetched, so Decision 30a's refetch would never go out. Fake only what is needed: `setPageAttention` (`test/page.ts`) for focus; time-dependent output uses an
instant built in **local** time — `new Date(2026, 8, 15, 13, 5).toISOString()` — so "13:05" holds in
any time zone.

| File · test | Proves | Expected red |
|---|---|---|
| `clock.test.ts` — `gives today's options when Automatic` · `12-hour adds h12` · `24-hour adds h23` (both functions, exact objects) · `formats 13:05 on the 24-hour clock` · `formats 01:05 or 1:05, never 13, on the 12-hour clock` | Decision 23, Req 7 | `Failed to resolve import "./clock"` — every test needs it |
| `clockApplied.test.tsx` — `MessageItem's time follows the clock` · `ThreadSummary's` · `SearchResult's` (each rendered inside `ClockContext.Provider` 24h then 12h) · `with no clock each formats exactly as before` (`toLocaleTimeString([], {hour,minute})` / `toLocaleString([], {dateStyle:'medium', timeStyle:'short'})`) | the three formatters (Req 7) | load failure on `../settings/clock` — a file of its own so no existing test is hidden |
| `useProfile.test.ts` — `applyRename updates the session and every cached directory` (two workspaces cached, other members untouched) · `applyRename leaves another user's session alone` · `the rename lands after the form that started it has unmounted` (hold `updateMe`, `mutate`, `unmount()`, release → session profile and directory updated) · `a directory read answered before the rename can't put the old name back` (directory cached with "Old"; `membersBy` holds call 2 with "Old", started by an invalidation; `applyRename("New")`; release call 2 → the cache still says "New", and call 3, the refetch the rename starts, has gone out and lands "New") · `a directory read started after the rename lands as the server says` (other order: call 2 starts after `applyRename` and answers "Newer" → "Newer") · `a first directory load in flight is restarted` (no data yet; call 1 held with "Old"; `applyRename`; release → the directory ends on call 2's "New") · `a profile read in flight can't undo the rename` (`['me', id]` refetch held with "Old", `applyRename`, release → "New") | Req 5, *Where the rules meet* row 3, Paths "mid-save" (Decisions 30, 30a) — the held-read tests fail a build that only writes the caches | load failure on `./useProfile` |
| `SettingsPage.test.tsx` — `prefills from the server, not the session` (session says "Old", `GET /users/me` "New") · `waits for this visit's read, not a cached profile` (`['me', id]` pre-seeded "Old", read held → no textbox; release "New" → the textbox's first value is "New") · `a failed profile read shows an error and no form` · `Save is disabled while unchanged, including after spaces` · `a capitals-only change enables Save` · `Save is disabled when empty after trimming` · `100 emoji enable Save, 101 disable it` · `sends the name as typed and shows the stored form back` · `a 400 shows its message on the field and no cache is written` · `a 409 shows "That name is already taken." on the field` · `Saved appears after success and goes on the next edit` · `the stored clock is checked, Automatic when absent` · `choosing 24-hour sends {clock:"24h"} at once` · `choosing Automatic sends {clock:null}` · `a failed save puts the previous choice back and shows the error` · `a failure while a later choice is pending keeps the later choice` · `a later failure after an earlier success returns to the earlier choice` · `when both fail the clock is re-read from the server` · `the second choice is not sent before the first has answered` | Req 1, 7, 8; Decisions 24, 29 | load failure on `./SettingsPage` |
| `App.settings.test.tsx` (fresh `App` per test, as `App.test.tsx:55-59`) — `clicking your name opens Settings inside the shell` · `a direct load of /settings shows the server's current name` (second `GET /users/me` answers a newer name than `adopt()`'s) · `every visit reads the profile and preferences again` (visit 1 reads "A" and 12h; leave; the server now says "B" and 24h; visit 2 → the field's value is "B" and "24-hour" is checked) · `Back to chat returns to the last channel` · `Back to chat goes to / when no channel was open` · `after a workspace switch Back to chat goes to /` · `a signed-out visit to /settings is remembered for sign-in` (stub `location.assign` as `session.test.ts:314-315`; `sessionStorage['collabhub.returnTo'] === '/settings'`) · `the callback returns to the remembered route` (verifier and return path in sessionStorage, `/auth/callback?code=…` → `/settings`) · `leaving mid-save still renames the sidebar and the directory` (hold `updateMe`, click Back to chat, release → `current-user` link shows the new name; the directory cache holds it) · `leaving with an unsaved edit drops it` · `a workspace switch on Settings keeps the field and the clock` (`session.changeWorkspace` from the same fresh module) · `a clock choice re-renders cached messages without refetching them` (on `/c/:id`, set `['user-preferences','user-ada']` — the literal key — to 24h: the time turns 24-hour, no second messages GET) · `the clock follows another tab's change on the next focus` (blur, server now 24h, focus → refetch → 24-hour) | Req 5, 7, 8; every Paths row but Grace's; Decisions 25–27 | assertions: `/settings` renders "No such page."; nothing written to sessionStorage; callback lands on `/` |
| `session.test.ts` (add) — `updateProfile replaces the signed-in profile and notifies` · `updateProfile does nothing when signed out or for another user` · `signIn remembers a safe return path` · `signIn ignores an unsafe one` (param `//evil.example`, `https://evil.example`, `/\evil`, `/sign-in`) · `takeReturnPath gives the path once, then /` · `a switch whose profile read began before updateProfile keeps the renamed profile` (`auth.meBy` holds the switch's read with "Old"; `changeWorkspace`; `updateProfile("New")`; release → `snapshot()` profile "New", workspace switched) · `a switch whose read begins after updateProfile adopts the server's profile` (`updateProfile("New")`, then a switch answering "Newer" → "Newer") | Decisions 25, 30b | `session.updateProfile is not a function`, `takeReturnPath is not a function`; sessionStorage assertions — existing tests keep running |
| `chat.test.ts` (add) — `remembers the last channel after the active one is cleared` · `clearLastChannel forgets it` | Decision 26 | assertion: `lastChannelId` undefined |

Ripple: `App.test.tsx` (`aReturningUser`), `ChatLayout.test.tsx` (`beforeEach`),
`ChatLayout.attachments.test.tsx`, and `CreateChannelDialog.test.tsx`'s "from the chat shell" block
(`:98-115`, which mounts `ChatLayout`) gain `auth.preferences({})`, so no test leans on an unstubbed
request (`test/setup.ts:32`, `onUnhandledRequest: 'error'`) once `ChatLayout` fetches preferences. They
still pass at red. These four are every test file that mounts `ChatLayout` or `App` (grep at `957371e`);
the test-writer re-greps.

## Task 4: The journey (RED)

**Files:** `tests/bdd/features/display_names.feature`, `steps/test_display_name_steps.py`,
`pages/chat_page.py`, `tests/bdd/conftest.py`

```gherkin
@bdd
Feature: Display names

  Everyone in CollabHub goes by a name of their own choosing, and no two people
  share one, so a name on a message always means one person. Changing yours is
  something you do once, on Settings; your own screen shows it straight away,
  and everyone else sees it the next time their view of the workspace is fetched.

  Background:
    Given Ada is signed in

  Scenario: Grace sees the name Alan chose on his message
    Given Ada has created a public channel named "general"
    And Alan has sent "the kettle is on" in "general"
    When Alan changes his display name to "Alan Turing" in Settings
    Then Alan sees "Alan Turing" as his name
    When Grace opens CollabHub
    And Grace opens the "general" channel
    Then Grace sees "the kettle is on" written by Alan Turing
```

- `conftest.py`: `ALAN = "alan@collabhub.dev"`; `alan_context` (session scope,
  `_signed_in_context(…, ALAN)`) and `alan` (function scope, `_restore`) beside `ada`/`grace`.
- Steps, `parsers.re` with `[^"]*` groups so no phrase swallows a quote: `Alan has sent "…" in "…"`
  (`alan.open()`, `open_channel`, `send_message_and_wait`), `Alan changes his display name to "…" in
  Settings`, `Alan sees "…" as his name`, and `Grace sees "(?P<body>[^"]*)" written by (?P<name>.+)` —
  the vocabulary's bare form, the tail a display name (Decision 33) — through the existing `has_author`.
  Reused verbatim: `Ada is signed in`, `Ada has created a public channel named "…"`, `Grace opens
  CollabHub`, `Grace opens the "…" channel`.
- `ChatPage`: `open_settings()` (click `current-user`, expect `settings-page`),
  `change_display_name(name)` (fill `settings-display-name-input`; if `settings-display-name-save` is
  enabled, click it and expect `settings-saved`; if disabled the name is already `name`),
  `has_current_user(name)` (retrying `expect(...).to_have_text`).
- **Reruns:** Auth's tables survive scenarios; no other scenario uses Alan (no `alan` in `tests/bdd`),
  so on a rerun Save is disabled (name unchanged) and the step's branch for that keeps it passing.
- Red: `--generate-missing` lists the four new steps; at e2e it fails at the rename step. First run: Task 9.

## Task 5: The rules, the key and the migration (GREEN)

**Files:** `names.py`, `models.py`, `alembic/versions/0002_unique_display_names.py`, `migrations.py`

- [ ] `names.py` to Task 1's interface; Task 1 passes. `User.display_name_key` (`String`, not null),
  `Index("uq_users_display_name_key", "display_name_key", unique=True)`, and:

```python
@validates("display_name")
def _keep_key(self, _key: str, value: str) -> str:
    # Every ORM write of a name goes through here, so the key can't drift (Decision 12).
    self.display_name_key = names.name_key(value)
    return value
```

- [ ] `UserPreferences`: `user_id` PK + FK `users.id`, `prefs JSONB NOT NULL DEFAULT '{}'`, `version`, `updated_at`.
- [ ] Migration `0002` (`down_revision = "0001"`), in order, all SQL bound:
  1. `ADD COLUMN display_name_key text NULL`;
  2. `SELECT id, created_at, display_name, email FROM users` — **every** row, deleted included (D46);
  3. normalise each name (`names.normalise`, then `provisional` if `check` refuses — Decision 17),
     `names.dedupe` (reserving first — Decision 17a), and `UPDATE users SET display_name = :n, display_name_key = :k, version =
     version + 1, updated_at = now() WHERE id = :id` for rows whose name changed; set the key on the rest;
  4. `ALTER COLUMN display_name_key SET NOT NULL`; `CREATE UNIQUE INDEX uq_users_display_name_key`;
  5. `CREATE TABLE user_preferences`.
  Downgrade drops the table, the index and the column; the renamed names stay (one-way, Req 4). The
  docstring says it imports `auth.names` and what that costs (Decision 31).
- [ ] `migrations.upgrade_to(dsn, revision)`; `upgrade_to_head` delegates. Run
  `test_name_migration.py` and `test_schema.py`: pass.
- [ ] Leave uncommitted.

## Task 6: The routes (GREEN)

- [ ] `schemas.UpdateUserRequest.display_name: str | None = None` — the pydantic length bounds go,
  because they ran on the untrimmed value (`" " + "a"*100 + " "` was refused). `update_me`: null → the
  existing 400; else `names.clean` (`InvalidNameError` → 400 `errors.displayName`); equal to the stored
  name → return without writing (Decision 18); else assign, bump, commit — `IntegrityError` → rollback,
  409 with Task 2's body.
- [ ] `identities.provision_user`: `base = names.provisional(display_name, email.split("@")[0])`;
  for each `names.candidates(base)`: skip if the key is taken (the CH009-waived select), else insert
  inside `session.begin_nested()`; on `IntegrityError` take the next only if that key is now taken,
  otherwise re-raise (Decision 13). The workspace is named from the name stored. `link_identity` is
  unchanged.
- [ ] `preferences.py`: `read(session, user_id) -> dict` (no row → `{}`, never inserts) and
  `merge(session, user_id, set_: dict, removed: list[str]) -> dict` — the statement in Decision 21.
- [ ] `schemas.PreferencesResponse` (`clock: Literal["12h","24h"] | None = None`, served with
  `response_model_exclude_none=True`) and `UpdatePreferencesRequest(CamelRequest)` with
  `extra="forbid"`, the same field, read through `model_fields_set` (`None` → removed). A `X | None`
  field keeps the error location `("body","clock")`, so `errors` is keyed `clock` — Task 2 checks it.
- [ ] `routers/preferences.py` (`prefix="/api/v1/users"`, `GET/PATCH /me/preferences`,
  `require_user`, `find_user` → 404 `"This account no longer exists."`), registered in `main.py`.
- [ ] Run Task 2: all pass. Auth integration: every file green.
- [ ] Leave uncommitted.

## Task 7: The SPA (GREEN)

- [ ] `lib/auth/api.ts`: the three calls (`PATCH` with `Authorization`, through `request`).
- [ ] `storage.ts`: `returnPath` (read/write/clear, key `collabhub.returnTo`) and `isSafeReturnPath`.
  `session.ts`: `updateProfile` with `adopt()`'s guard (Decision 30b), `signIn(provider, returnTo)` writes only a safe path,
  `takeReturnPath()`; the module docstring notes the second sessionStorage entry.
- [ ] `App.tsx`: `Protected` → `<Navigate to="/sign-in" replace state={{ from: pathname + search }} />`;
  `SignIn` passes `state.from` to `session.signIn`; `Callback` navigates to `session.takeReturnPath()`
  on success; route `/settings` → `<Protected><SettingsRoute/></Protected>`.
- [ ] `stores/chat.ts`: `lastChannelId`, `clearLastChannel`. `ChatLayout`: `clearLastChannel()` in the
  workspace effect's cleanup; `usePreferences(current.accessToken, current.profile.id)` and
  `<ClockContext.Provider value={data?.clock}>` around the shell.
- [ ] `WorkspaceSwitcher`: `current-user` becomes `<Link to="/settings">`.
- [ ] `features/settings/`: `clock.ts`, `usePreferences.ts` (`useSetClock` per Decision 29, cache
  writes in the hook's own callbacks), `useProfile.ts` (`useRenameMe` calls `applyRename` from its own
  `onSuccess` — Decision 30; `applyRename` per Decision 30a), `SettingsPage.tsx` to Task 3's markup; the
  Profile form renders once this mount's read has succeeded (`isFetchedAfterMount`, Decision 28), and
  "Back to chat" goes to `/c/{lastChannelId}` or `/`.
- [ ] `MessageItem.tsx:68-70`, `ThreadSummary.tsx:16-18`, `SearchResult.tsx:22-24`: `formatTime` /
  `formatDateTime` with `useClock()`; their comments that cite D28 as open now say the clock preference.
- [ ] Task 3 passes; `npm --prefix src/frontend run typecheck` clean.
- [ ] Leave uncommitted.

## Task 8: The record

- [ ] Register: D28 → 🟢 with Decided 7 and "built 2026-10-21"; new **D46** row in *Platform / Auth*
  — global unique names, compared by `display_name_key`, deleted accounts included, the existence leak
  it accepts and that the 409 names nobody.
- [ ] ADRs with the `adr-writer` skill: `docs/adr/261021-user-preferences-in-auth.md` (D28) and
  `docs/adr/261021-display-names-unique-across-collabhub.md` (D46, with the key-over-`lower()` choice).
- [ ] Doc 01 §3: the preferences routes; `PATCH /users/me`'s trimming, refusals, 409. §4:
  `display_name_key` and its index, `user_preferences`, the first-sign-in suffix rule (Decisions 15–16).
- [ ] Doc 06 §3 `/features/settings`; §4 the return path (Decision 25) beside the PKCE verifier; §5.2
  *Names*: the renamer's own tab updates at once (Decisions 30a–b); §9: D28 decided, the clock built.
- [ ] Conventions §5.4: the D46 exception — a display-name 409 may reveal a name exists in another
  workspace, and names nobody and no workspace. `auth/api.http`: the preferences requests.
- [ ] Sweep: `grep -rn "D28" src docs/design`, `grep -rn "Renames are not covered" docs` — every hit says
  the new state; `grep -rn "display_name" src/services/auth/auth` — every write via the model or 0002.

## Task 9: Verification

- [ ] `scripts/test.sh lint unit integration`, then `scripts/test.sh e2e` — each once; the whole e2e
  layer is the journey's first run (`-- -k display_names` only to iterate on a failure). Unit at or
  above 1871; record the integration and e2e counts, which have no baseline.
- [ ] `python3 .claude/hooks/checks/conventions.py $(git diff --name-only HEAD)` and
  `.claude/hooks/security.sh`; the CH009 waiver names every checker that fires on its line.
- [ ] **First real run** (`docker compose up -d --build`): rename Ada, watch sidebar and messages; Grace's
  name in capitals from Alan's browser, read the 409 body; 24-hour on a message, thread summary and
  search result; reload `/settings`; open it signed out. Fix anything found with a test; record it below.
- [ ] Fill in *Found while building*. Leave the worktree dirty and report.

## Found while building

Code-writer, round 1. Every plan task built; every red test went green on the first run of its
layer, and the journey passed on its first e2e run. Deviations:

- **`useSetClock` skips the cache write and the re-read while another save is queued**
  (`isMutating` counts the mutation being settled, so "alone" is `<= 1`). Decision 29 says an
  error rolls back "only if the cache still holds its own optimistic value, then invalidates";
  invalidating while a later save is pending can land a read that predates it and flicker the
  screen. Pinned by `SettingsPage.test.tsx` › `keeps a later choice when an earlier save fails`
  and `does not send the second choice…`. A success likewise writes the server's answer only when
  alone.
- **`UpdatePreferencesRequest` sets its own `model_config`** (`alias_generator=to_camel,
  extra="forbid"`) instead of inheriting `CamelRequest`'s, because pydantic merges configs only by
  key and the base has none to extend; same effect as the plan. Pinned by
  `test_an_unknown_key_is_400…`.
- **`update_me` also checks the key before writing** (a pre-check for the quick 409) and keeps the
  commit-time `IntegrityError` mapping as the authority, only for `uq_users_display_name_key` — any
  other integrity error is re-raised. Pinned by `test_two_renames_to_one_name_at_once_one_wins` and
  `test_a_rename_racing_an_uncommitted_first_sign_in`.
- **A body that carries nothing** (`PATCH /users/me {}`) now writes nothing either — before it bumped
  `version`. No test; follows from Decision 18's "no write when nothing changes".
- **`takeReturnPath` re-checks `isSafeReturnPath` on read**, since the stored value is untrusted
  `sessionStorage`. `signIn` clears any earlier stored path when given none or an unsafe one.
  Pinned by the `signIn ignores an unsafe one` cases.
- **`PreferencesSection` radios are never disabled while the read loads**, because the tests click
  one straight after the profile field appears; until the read lands "Automatic" shows checked.
- **The hooks' formatter strips an import added before its first use**, so imports were added after
  the code using them. No effect on the result.
- No bug was found by the e2e run or the unit/integration runs; nothing beyond the above needed a
  new test. **Not run by this stage:** the plan's by-hand "first real run" in two browsers (see the
  green report, *Left for the human*).

## Not in this plan

- Everything under *Not in this issue*; refreshing the `name` claim on rename (*Where the rules meet*
  row 4); cross-tab coordination of the refresh cookie (doc 06 §4).

## Self-review

- **Req 1** → Tasks 1, 2 (stored, refused, accepted, 100, re-save), 3, 5, 6. **Req 2** → 1, 2 (409, NFC,
  capitals, deleted, races), schema, 5, 6. **Req 3** → 1, 2 (suffix, two at once, races, unusable, never
  overwrites), 6. **Req 4** → 1 and 2 (`dedupe`, migration, newer unique holder), 5. **Req 5** → 3
  (`applyRename`, held reads, `adopt()` guard, mid-save), 4, 7. **Req 6** → 2, 5, 6. **Req 7** → 3, 7.
  **Req 8** → 3 (page, App, this visit's read), 4, 7.
- **Where the rules meet**: concurrency → `test_two_renames…`; rename vs sign-in → both `…racing…`
  tests; own view → `applyRename` and held-read tests, the switch tests in `session.test.ts`; token →
  *Not in this plan*; workspace name → `…leaves_the_workspace_name_alone`; clock and cache → `a clock
  choice re-renders…`; two tabs → `test_a_patch_merges…`, `test_two_first_patches…`.
- **Paths**: every row but Grace's → named `App.settings.test.tsx` tests; Grace → directory tests + the
  journey; deleted account → `…name_stays_taken`, `…gets_404…`.
- **Names** (`user_preferences`, `display_name_key`, `uq_users_display_name_key`, `collabhub.returnTo`,
  the two query keys) are used identically; **ripple**: `a_user` and four SPA test files — RED work.

## Review responses

Round 1 (`reviews/plan-reviewer-1.md`):

1. Fixed — Decisions 30a (cancel, write, re-read; TanStack lines cited) and 30b (`adopt()` guard);
   held-read tests in both orders in `useProfile.test.ts` and `session.test.ts`; `auth.meBy` helper.
2. Fixed — Decision 17a's reservation rule; the newer-holder fixture at unit and in the migration test.
3. Fixed — `CreateChannelDialog.test.tsx` in the ripple and file map; no other mount found.
4. Fixed — a synchronous function-scoped fixture `db_at_0001`, as `postgres_dsn` is made.
5. Fixed — `a_user` names each user from its own id. 6. Fixed — qualified in Decision 21.
7. Fixed — `isFetchedAfterMount` (Decision 28); two tests assert the field's value; failed read tested.
8. Fixed — the vocabulary's bare form via `parsers.re` (Decision 33).
