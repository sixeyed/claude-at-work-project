# Prompt: plan Slices 2–7 in parallel

Paste the fenced block below into a **fresh Claude Code session at the repo root**. It plans; it
does not build. Every slice still hits its own 🛑 Gherkin approval gate when someone comes to
implement it — see `02-messaging-core-delivery-plan.md` §"How every slice runs".

It runs nine subagents in two waves: six planners, then three reviewers. Expect it to take a
while and to leave seven new files in `docs/plans/ch06/`, uncommitted.

---

``````markdown
You are coordinating the writing of six implementation plans — one for each of Slices 2 to 7 of
the CollabHub messaging build. Slice 1 is already built, accepted and documented.

**You are the coordinator and you stay the coordinator.** You do not write a slice plan yourself.
Your context is for the seams between slices and for reconciling what comes back. Six subagents
write the plans; three more review them.

## Read this first

Nothing below happens until you have read:

- `CLAUDE.md` — the repo rules the plans keep citing.
- `docs/plans/ch06/01-messaging-core-strategy-plan.md` — reference points and idiom to copy.
- `docs/plans/ch06/02-messaging-core-delivery-plan.md` — the seven slices, the shared protocol,
  the amendment block dated 2026-08-15, and the two decisions at the top.
- `docs/plans/ch06/03-slice-01-implementation-plan.md` — **the shape every plan you commission
  must match.**
- `docs/design/00-platform-conventions.md`, `02-messaging-service.md`, `06-frontend-spa.md`,
  `07-open-decisions-register.md`.
- The code Slice 1 actually shipped, because these plans describe extending *what exists*, not
  what the delivery plan predicted: `src/services/messaging/messaging/`,
  `src/frontend/src/features/channels/`, `src/frontend/src/lib/api/`, and
  `tests/bdd/` (`conftest.py`, `pages/`, `steps/`, `features/channels.feature`).

**Ignore `docs/project/` entirely.** It is book-production material, not project input.

Where the delivery plan and the shipped code disagree, the code wins and the plan you commission
says so — that is exactly the kind of correction Slice 1's plan carries in its "Gaps closed"
section.

---

## What gets written

| File | Written by |
|---|---|
| `docs/plans/ch06/04-slice-contracts.md` | You, in Phase 1 |
| `docs/plans/ch06/05-slice-02-implementation-plan.md` | Planner 2 |
| `docs/plans/ch06/06-slice-03-implementation-plan.md` | Planner 3 |
| `docs/plans/ch06/07-slice-04-implementation-plan.md` | Planner 4 |
| `docs/plans/ch06/08-slice-05-implementation-plan.md` | Planner 5 |
| `docs/plans/ch06/09-slice-06-implementation-plan.md` | Planner 6 |
| `docs/plans/ch06/10-slice-07-implementation-plan.md` | Planner 7 |

Sequence-prefixed, continuing `01`/`02`/`03`. Nothing else in the repo changes.

---

## Phase 1 — freeze the seams

Do this yourself, before dispatching anything. Write `docs/plans/ch06/04-slice-contracts.md`.

Six planners working blind will close the same gap two different ways wherever slices touch. This
document is the answer, and it is the reason the fan-out is safe. It is not a summary of the
delivery plan — it is a set of **rulings**, each naming the one slice that owns the thing.

Rule on every item below. Where the delivery plan already recommends an answer, confirm it or
overturn it, once, and say which. Where nothing does, decide it and record why.

1. **Tombstones and the messages index.** Delivery plan decision 1 proposes that history returns
   soft-deleted rows with `body` redacted and `deletedAt` set, and that `ix_messages_channel_time`
   is therefore created **without** the `WHERE deleted_at IS NULL` predicate. This binds S3 (the
   migration), S4 (the semantics) and S7 (the D8d ADR). One ruling, cited by all three.
2. **Migration ownership.** `0002_messages` lands in S3 and no other slice adds a migration.
   Columns whose features arrive later (`last_read_id`, `thread_root_id`, `attachments`, `version`)
   ship with their table so no table churns. `reactions` is not created.
3. **Optimistic concurrency.** S2 defines the pattern — `WHERE id = :id AND version = :expected`,
   zero rows affected → 409 `conflict`. S4 applies it to messages by citation, not by restating it.
   Name the shape once here.
4. **`shared/security.py` and the ASGI entry point.** S5 owns both: extracting
   `async def verify_user_token(context, token) -> UserPrincipal` from `RequireUser.__call__`, and
   adding `build_asgi_app` alongside `create_app` so tests keep using `ASGITransport` while the
   container runs `uvicorn ... --factory`. S6 consumes them and must not respecify them.
5. **The `realtime.py` split.** S5 = handshake auth, `join_channel`/`leave_channel`, and the
   outbound publishers called by the REST routers after commit. S6 = the inbound `send_message` /
   `edit_message` / `delete_message` handlers with acks, and `typing` → `user_typing`. State which
   file each half lands in and how `test_realtime.py` is divided.
6. **BDD harness growth.** `tests/bdd/conftest.py` currently truncates
   `MESSAGING_TABLES = "channel_members, channels"` — S3 adds `messages`, child table first. Then,
   per slice: new `.feature` file or an extension of an existing one · new page object or new
   methods on `pages/chat_page.py` · which fixtures are added and by whom. Step modules **must** be
   named `test_*.py` or pytest silently never collects them. Selectors stay `data-testid` only,
   owned by page objects.
7. **Frontend seams.** The TanStack query keys for messages are defined in S3 and written into by
   S5's socket handlers with `queryClient.setQueryData` — there is never a second copy of the
   message list in Zustand (D24). `stores/chat.ts` gains connection status in S5. The feature
   folder is `features/channels/`, never `features/chat/`.
8. **OpenAPI regeneration.** Any slice that adds or changes a route regenerates
   `src/frontend/openapi/messaging.json` via `python -m messaging.openapi` and reruns
   `npm run generate:api` (D23). Say it once here; each plan's Verification section repeats the
   commands.
9. **Design-doc writeback ownership.** Exactly one slice owns each doc section, so two plans cannot
   both claim to rewrite `docs/design/02-messaging-service.md` §3.1. Assign every section any slice
   is likely to touch — 02 §3.1/§3.2/§4/§9, 06 §2/§3/§5.2, and the register. D8d flips to 🟢 in the
   slice that decides it (S4), not in S7; S7 keeps the sweep.
10. **Open decisions in play.** D8d 🔴 (S4 settles it) · D16 🔴 retention (stays open; nothing in
    scope depends on it) · D8b 🟡 DMs (`kind='dm'` still rejected) · D28 🔴 no user preferences.
    State the standing rule: a planner records a 🔴 it hits as a **Contract question**, it does not
    pick an answer.
11. **Branch names.** `feature/messaging-s2-admin` · `-s3-messages` · `-s4-edit-delete` ·
    `-s5-realtime` · `-s6-socket-write` · `-s7-decisions`.

Write it in the house style of the other ch06 documents: sentence-case title, `## Context` first,
`---` between sections, ~100-column wrap, `·` as an inline separator, the 🔴🟡🟢 statuses used the
way the register uses them.

---

## Phase 2 — dispatch six planners, in parallel

**Issue all six Agent calls in a single message.** One per message runs them sequentially and
wastes the entire point.

Each planner writes exactly one file, and no two planners write the same file. That disjointness
is what makes this safe without git worktrees — do not use worktrees, and do not let a planner
touch anything outside its own output path.

Use this prompt for each, substituting the placeholders:

````
You are writing ONE implementation plan: Slice {{N}} of the CollabHub messaging build,
"{{TITLE}}".

Write it to `docs/plans/ch06/{{OUTPUT_PATH}}` and to no other file. Everything else in the
repository is read-only to you.

## What this plan is for

Slice 1 is built, accepted and documented. Slices 2–7 are specified only as a paragraph each in
the delivery plan. Your plan does two things, in this order:

1. **Validates the delivery plan for your slice against the design docs and the shipped code, and
   closes the gaps it finds.** This is the valuable half. Slice 1's plan found nine gaps — a DTO
   that existed in no design doc, a visibility rule that made its own demo unsatisfiable, two
   missing indexes, a harness design that would have revoked the test users' sessions. Expect to
   find comparable things. Name the offending document and section every time.
2. **Specifies the slice in enough detail to build from** — file by file, pointing at the existing
   file to copy rather than describing a pattern in the abstract.

## Read

- `docs/plans/ch06/04-slice-contracts.md` — **the frozen cross-slice rulings. Binding.** Where it
  rules on something your slice touches, follow it and cite it; do not re-decide it.
- `docs/plans/ch06/02-messaging-core-delivery-plan.md` — read the whole thing (the amendment
  blockquote, the two decisions, "How every slice runs"), then your own section, `## Slice {{N}} —
  {{TITLE}}`.
- `docs/plans/ch06/03-slice-01-implementation-plan.md` — **the shape to match.** Read it for
  structure and register as much as for content.
- `docs/plans/ch06/01-messaging-core-strategy-plan.md` — reference points and idiom to copy.
- `CLAUDE.md`, and `docs/design/00-platform-conventions.md`, `02-messaging-service.md`,
  `06-frontend-spa.md`, `07-open-decisions-register.md`.
- The shipped Slice 1 code, which is what you are extending: `src/services/messaging/messaging/`
  (`models.py`, `schemas.py`, `channels.py`, `routers/channels.py`, `main.py`, `db.py`,
  `settings.py`, `alembic/versions/`), `src/services/messaging/tests/`,
  `src/frontend/src/features/channels/`, `src/frontend/src/lib/api/`, and `tests/bdd/`.

**Ignore `docs/project/`.** Read only what your slice needs; do not sweep the repo.

## Structure — match Slice 1's plan

```
# Slice {{N}} — {{TITLE}}

## Context
## Gaps closed
### 1. <subject> — <what is wrong with the design>
### 2. ...
### Also corrected in the delivery plan     (only if there is something)
## How the slice runs
## Work
### A. <work package> — <path>
### B. ...
## Verification
```

- `## Context` — three or four short paragraphs. Open with a relative markdown link back to
  `02-messaging-core-delivery-plan.md`. State that the plan validates and then specifies. Restate
  the slice's demo in one sentence. Close by counting the gaps found.
- `## Gaps closed` — numbered `###` sections. Each titles the subject and what is wrong with the
  design, names the offending doc and section ("Doc 02 §3.1", "Conventions §4.2", "CLAUDE.md"),
  then makes the call **in bold**. Use whatever medium fits: a markdown table for a rules matrix, a
  fenced `jsonc` block for a DTO, fenced `sql` for DDL and indexes, a bullet list for validation
  rules. Where the fix belongs in a design doc rather than only in code, end with a bolded
  instruction — "**Write this back into `docs/design/02-messaging-service.md` §3.1.**" — and check
  `04-slice-contracts.md` first that your slice is the one that owns that section.
- `## How the slice runs` — deliberately thin. "Unchanged from the delivery plan" plus six
  one-line reminders (Gherkin first · 🛑 stop for explicit approval · build outside-in and watch it
  fail for the right reason · never edit a scenario to fit the implementation · `data-testid` only,
  owned by page objects · branch `{{BRANCH}}`, never commit, leave the tree dirty). Then a bolded
  **Scenarios** paragraph listing your slice's scenario titles inline, separated by `·`, and a line
  saying what deliberately stays at integration level instead of in Gherkin.
  **Write no Gherkin.** Scenario titles only — the `.feature` file is written and approved at the
  gate, not here.
- `## Work` — lettered packages (`A.`, `B.`, …) grouping by area: BDD, backend, frontend,
  decisions. Within each, a **file-by-file bullet list**, every bullet leading with a backticked
  path, then the specification and the *why*. Point at the file to copy:
  "`list_page` mirrors `members_page` (`auth/identities.py:253`)". Include short inline code
  fragments where they save a paragraph; no long listings. No checkboxes, no time estimates, no
  "Phase N" numbering, no per-task acceptance criteria.
- `## Verification` — a fenced `bash` block of the commands, with trailing `#` comments; then a
  one-line note on anything operational; then a bolded **Manual demo:** paragraph; then a bolded
  **Done:** sentence ending with the tree left dirty.

House style: sentence-case headings, `---` between top-level sections, ~100-column wrap, bold for
the call made and for warnings, `·` as an inline separator, 🛑 for the approval gate and 🔴🟡🟢 for
register statuses, design docs cited as "doc 02 §3.1".

## Reuse, do not invent

The repo has one finished service and it is the template. Point at it by name:

- Composition root and `lifespan` — `src/services/auth/auth/main.py`; messaging's own `main.py` is
  now a working example of the same thing.
- Domain layer — `auth/identities.py`: plain async functions, `AsyncSession` first, no FastAPI
  imports, domain exceptions the router translates. Messaging's `channels.py` follows it.
- Router idiom — `auth/routers/workspaces.py` and messaging's `routers/channels.py`: private
  `_guard()` helpers at module top, signature order `page: PageParams`, then
  `principal: UserPrincipal = Depends(require_user)`, then `session: ... = Depends(db_session)`.
- Keyset pagination — `shared.PageParams` / `PageRequest.fetch_limit` / `build_page` in
  `src/services/shared/shared/pagination.py`, used by `members_page` at `auth/identities.py:253`.
- Schemas — `auth/schemas.py` `CamelModel` / `CamelRequest`, and the deliberate asymmetry between
  them; `body.model_fields_set` for PATCH merge semantics (`auth/routers/users.py`).
- Shared helpers — `shared.uuid7()`, `install_problem_handlers`, `install_cors`,
  `install_security`, `require_user`, `JwksClient`, `Denylist`, `build_health_router`.
- Integration test fixtures — `src/services/messaging/tests/conftest.py` (testcontainers Postgres
  and Redis, per-test truncate, RS256 minting via `StaticKeySource`).

If you find yourself specifying a new pattern, check first whether one of these already is it.

## Rules that hold in every slice

Test them, don't just assert them: `workspace_id` comes from `principal.workspace_id` (the `wsp`
claim) and never from a path, query or body · cursor pagination only, `{items, nextCursor}` via
`build_page`, never `OFFSET` · RFC 7807 on every non-2xx, no internal detail in `detail` ·
camelCase JSON, snake_case SQL · UUID v7 from `shared.uuid7()`, generated in the application ·
a resource the caller may not see is 404, never 403 · timestamps UTC `timestamptz` · every read
filters that table's soft-delete column, which for `channels` is `archived_at`, not `deleted_at`.

## What you must not do

- Do not write, edit or create any file other than `docs/plans/ch06/{{OUTPUT_PATH}}`.
- No production code, no `.feature` files, no design-doc edits, no changes to another plan. Your
  plan *says* what should be written back to a design doc; it does not write it back.
- Never run `git add`, `git commit`, or open a PR.
- Do not spawn subagents.
- Do not decide anything that crosses into another slice. If your slice's answer to a question
  would constrain another slice, and `04-slice-contracts.md` has not already ruled on it, record it
  in your plan as a bolded **Contract question:** with your recommendation, and repeat it in your
  return message. Same for anything 🔴 in the register.

## Return

Twenty lines maximum, as data for the coordinator, not prose for a human:

- the gaps you closed, one line each;
- every **Contract question** you raised, with your recommendation;
- the files and design-doc sections your plan claims to own;
- anything you could not resolve from the docs or the code.
````

Substitutions:

| `{{N}}` | `{{TITLE}}` | `{{OUTPUT_PATH}}` | `{{BRANCH}}` |
|---|---|---|---|
| 2 | Channel administration and membership | `05-slice-02-implementation-plan.md` | `feature/messaging-s2-admin` |
| 3 | Messages: send and read history | `06-slice-03-implementation-plan.md` | `feature/messaging-s3-messages` |
| 4 | Messages: edit and delete | `07-slice-04-implementation-plan.md` | `feature/messaging-s4-edit-delete` |
| 5 | Real-time delivery (broadcast only) | `08-slice-05-implementation-plan.md` | `feature/messaging-s5-realtime` |
| 6 | Socket write path, optimistic send, typing | `09-slice-06-implementation-plan.md` | `feature/messaging-s6-socket-write` |
| 7 | Record the decisions | `10-slice-07-implementation-plan.md` | `feature/messaging-s7-decisions` |

Two slices need an extra line in their dispatch:

- **Slice 5** — add: "You own the `shared/security.py` extraction and the `build_asgi_app` change
  per contract 4. Specify them fully; Slice 6 will cite you."
- **Slice 7** — add: "This slice is documentation only. Your `## Work` has no backend or frontend
  package — it has the ADR, the register updates, the design-doc reflections and the README sweep.
  Its Verification is a docs check, not a test run. Before you specify anything, read the plans in
  `docs/plans/ch06/` numbered 05–09 if they exist yet and note that decisions recorded in an
  earlier slice are **not** yours to record again."

---

## Phase 3 — reconcile

Read the six returns. Then:

1. Rule on every **Contract question** raised. You decide these — do not stall the run waiting for
   the user. Where a ruling would change a contract Slice 1 has already shipped, that one goes to
   the user instead.
2. Amend `docs/plans/ch06/04-slice-contracts.md` in place with the new rulings, as a dated
   amendment blockquote in ch06 style — `> **Amended <date>, after the planners returned.**` —
   rather than rewriting history.
3. Patch the affected plans yourself. Do not re-dispatch a planner for a one-line correction.
4. Keep a list of every call you made and why. It goes in your final report.

---

## Phase 4 — three reviewers, in parallel

**All three Agent calls in one message.** They are read-only: they report findings, they never
edit. You apply the fixes.

Give each the same preamble — "Six implementation plans for Slices 2–7 of the CollabHub messaging
build have just been written in parallel by separate agents against
`docs/plans/ch06/04-slice-contracts.md`. Review them on one lens only. Report findings as
`file:line — what is wrong — what it should say`. Edit nothing." — and then one of:

- **Seams.** "Read all six plans (`docs/plans/ch06/05-…` through `10-…`) plus
  `04-slice-contracts.md`. Find: two plans that contradict each other · two plans that both claim
  to create or own the same file, migration, test module or design-doc section · a file or
  behaviour that every plan assumes someone else builds · a slice that depends on something an
  earlier slice never delivers · a contract ruling a plan quietly violates. Be specific about which
  two plans clash."
- **Fidelity.** "Every factual claim these plans make about the design docs, `CLAUDE.md` and the
  existing source must be checked against the actual file. Open them. Look for: `§` references
  that point at the wrong section or no section · helpers, functions, fixtures, columns and
  settings that do not exist · line references that have moved · claims about what Slice 1 shipped
  that the code contradicts · statements about a decision's register status that
  `docs/design/07-open-decisions-register.md` does not support. This lens catches confident
  invention, so verify rather than skim — assume nothing is true because it reads plausibly."
- **Executability and reuse.** "Judge whether each plan could be built from by an engineer with no
  context. Flag: a pattern invented where `src/services/auth/` or `src/services/shared/` already
  has one — name the existing one · placeholders and hand-waving (`TBD`, 'handle errors
  appropriately', 'similar to the channels router', 'add tests for the above') · a type, schema or
  endpoint referenced but never defined · a `## Work` bullet that names no file · a Verification
  section whose commands would not actually prove the slice works. Also flag the reverse: a plan so
  long it has stopped being a plan."

Apply every finding you agree with. Where you disagree with a reviewer, say so in the final report
rather than silently ignoring it.

---

## Phase 5 — report, then stop

Confirm all seven files exist and each matches the structure above. Then report to the user:

- the files written;
- every call you made in Phase 1 and Phase 3, and why;
- what the reviewers found and what you changed;
- the open questions left for them, including anything 🔴 that a slice will hit at build time.

Then stop. Do not start building a slice. Do not write any `.feature` file.

---

## Hard rules

- **Never commit.** Stage nothing, run no `git commit`, open no PR. Leave the tree dirty and tell
  the user what changed.
- **Ignore `docs/project/`.**
- **This run changes nothing under `src/`, `tests/` or `docs/design/`.** It writes seven markdown
  files in `docs/plans/ch06/` and nothing else. The plans *describe* the design-doc writebacks;
  each slice performs its own when it is built.
- A 🔴 decision that would change something Slice 1 already shipped goes to the user, not to you.
``````
