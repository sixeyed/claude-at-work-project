# Test pyramid handoff — unit layer

Handoff, 2026-09-15. This is for an agent taking over the **unit layer** of CollabHub's test
pyramid, with no context from the session that designed it. Two sister handoffs cover the other
layers: [integration](03-test-pyramid-handoff-integration.md) and
[end-to-end](03-test-pyramid-handoff-e2e.md).

You own three workstreams, in this order:

1. **Python unit framework** — the small remainder that plan A didn't build.
2. **Frontend unit framework** — Vitest for the SPA. The design calls this "plan C", and no
   implementation plan exists for it yet.
3. **Unit backfill** — the missing unit tests, Python and SPA, including replacements for the BDD
   scenarios that are moving down a layer.

---

## Before you start

### Read these

| Document | Why |
|---|---|
| `CLAUDE.md` | The working rules. It wins over this handoff if they ever disagree. |
| `docs/design/00-platform-conventions.md` | The cross-service contract. §11 describes the test layers once plan A lands. |
| `docs/plans/ch07/01-test-pyramid-design.md` | **The approved design, and your authority.** Read "The three layers", "Where a test goes", "Framework 1", "Framework 3" and the BDD triage table under "Framework 4". |
| `docs/plans/ch07/02-test-pyramid-a-layout-and-testkit-implementation-plan.md` | The foundation you build on: what exists and why. |
| `docs/design/07-open-decisions-register.md` D32, `docs/adr/260915-a-test-pyramid-with-journeys-at-the-top.md` | The decision as recorded. Both are written in plan A's Task 10. |
| `docs/design/06-frontend-spa.md` | The SPA's structure and state rules, for workstream 2. |

Ignore `docs/project/`. It's book-production material.

### Check the foundation is there

Plan A builds the layout, the `testkit` plugin and the unit guard. Your branch has to start from
code that contains it:

```bash
uv run pytest --collect-only -q -m unit | tail -1            # 122 or more collected, no errors
uv run pytest --collect-only -q -m integration | tail -1     # 287 or more collected
grep -rn 'pytest.mark.integration' src/services --include='*.py' --exclude-dir=testkit   # prints nothing
grep -n -- '-m unit' scripts/test.sh                          # prints the unit layer's pytest line
```

Plan A is merged to `main`, so branch from `main`. If any of these fail, the foundation isn't
what this handoff expects. **Stop and ask Elton.**

### Working rules that bite

These come from CLAUDE.md and are repeated here because they are easy to get wrong:

- **Branch and worktree:** create a new git worktree on a new feature branch before your first
  edit, and tell Elton the branch name and path.
- **Never commit or stage.** No `git add`, `git commit` or `git stash`. Use plain `mv`, never
  `git mv`.
- **Write your plan into the repo.** Use superpowers:writing-plans to write it at
  `docs/plans/ch07/04-test-pyramid-unit-<topic>-implementation-plan.md` (prefix `04` is
  reserved for this handoff; integration has `05`, end-to-end `06`), and get
  Elton's approval before executing it.
- **Test first, and stop at red.** Write the failing test, run it, and stop so Elton can review
  the tests before any production code is written.
- **Backfill tests pass the moment they're written,** because the behaviour already exists. So
  prove each one can fail:
  1. Break the behaviour it pins, temporarily, with a one-line change.
  2. Run the test and watch it go red.
  3. Restore the code.
  4. Record the command and the output as the evidence.

  Then stop for review, the same as red.
- **Never fake a database, Redis or Elasticsearch** to reach behaviour. If a unit test can't reach
  something, say so; that behaviour belongs to integration.
- **Hooks:**
  - An edit hook runs ruff and eslint and **blocks** on findings. Fix them.
  - A turn-end hook runs security checks. It is advisory.
- **Decisions:** a 🔴 decision in the register means stop and ask. New register IDs are reserved
  per handoff, so the three parallel branches don't collide: **D33** unit, **D34** integration,
  **D35** end-to-end. Record any decision you make in
  the same slice: register row, source design doc, and an ADR through `adr-writer` when it's
  significant.

---

## What the unit layer is (settled)

| | |
|---|---|
| **Proves** | a rule, a mapping, a wire shape, an app's wiring |
| **Python** | pytest, in `src/services/<service>/tests/unit/`. The directory decides the layer: `testkit`'s plugin marks the test `unit`, and a test file anywhere else under `tests/` stops the run. |
| **Frontend** | Vitest + Testing Library + MSW. Tests sit beside their source as `Foo.test.tsx`. |
| **Guard** | A unit test can't open a non-Unix socket (pytest-socket), and `DOCKER_HOST` is `tcp://docker.invalid:1`. The plugin enforces both. |
| **Substitutes allowed** | A recorder for something **we** own at the edge (`RecordingServer` for the Socket.IO server, a recording `JobQueue`); typed MSW handlers; a fake Socket.IO client. |
| **Never** | A fake database session, a fake Redis, a fake repository. |
| **Imports** | Shared helpers come from `testkit`. `from tests… import` is a ruff error (TID251), because `tests` is one namespace package spanning every service. |
| **Run** | `scripts/test.sh unit` runs pytest with coverage (reported, no gate). Your workstream 2 adds Vitest. |

**Rules become unit-testable by extraction, never by fakes** (decision 2). Pull the decision out as
a pure function over values that are already loaded, and leave the async function as the shell
that fetches and writes. SQLAlchemy models construct without a session
(`src/services/messaging/tests/unit/test_read_markers.py` already builds a `Channel`). Do it when
you touch a module, not as a big-bang refactor.

### Known gaps in the foundation

- **pytest-socket's own opt-outs re-open the network for a unit test.** A
  `@pytest.mark.enable_socket` marker or the `socket_enabled` fixture works, because
  pytest-socket's `pytest_runtest_setup` runs after the plugin's `tryfirst` guard. Nothing uses
  them today, so don't start. Closing the gap is a `plugin.py` change: write a failing pytester
  test first, and ask Elton before doing it.
- **`layer_of` is tested only through whole pytest runs.** Nested `tests/unit/sub/` paths and
  paths outside `tests/` have no direct test. Elton declined those tests on 2026-09-15, so
  leave it.
- **A test file under a service but outside its `tests/` belongs to no layer.** For example,
  `src/services/messaging/messaging/test_x.py`: `layer_of` returns `None`, so neither `-m unit`
  nor `-m integration` selects it, and `scripts/test.sh` never runs it. None exist today
  (123 + 287 + 43 = 453). Closing it is a `plugin.py` change: write a failing pytester test
  first, and ask Elton.
- **The socket guard is lifted before a unit test's fixture teardown.** pytest-socket's own
  `pytest_runtest_teardown` has no ordering, so it re-enables sockets before pytest tears
  fixtures down. `DOCKER_HOST` stays guarded, because testkit's teardown is `trylast`. This is
  low impact.

---

## Workstream 1 — Python unit framework

Small. Both items are owned by this handoff; the integration handoff doesn't touch these modules.

1. **Move `RecordingServer` into `testkit/fakes.py`.**
   - Today it's a class inside `src/services/messaging/tests/unit/test_read_markers.py`. It stands
     in for `socketio.AsyncServer`, recording `emit(event, data, **kwargs)`.
   - Move it verbatim, docstring included, and import it from `testkit.fakes` in that test file.
   - Keep `test_read_markers.py`'s 10 tests passing unchanged.
2. **Row factories (`testkit/factories.py`) — only when a second test needs one.** The design
   deliberately defers `a_channel()` and `a_message()` until duplication is real. The first
   candidate is the policy tests in workstream 3, item 1.

**Coverage floor:** don't set one yet (decision 11). At the end of workstream 3, record the
measured `TOTAL` from `scripts/test.sh unit` per service in your final report, and propose a floor
for Elton to decide.

---

## Workstream 2 — Frontend unit framework (Vitest)

Nothing exists yet: no test runner, no test files, no test scripts in `src/frontend/package.json`.

### Versions, checked on 2026-09-15 — re-check before pinning

| Package | Version | Why |
|---|---|---|
| `vitest`, `@vitest/coverage-v8` | 5.0.1 | Peer `vite ^6.4`. The installed Vite is 6.4.3. It shares `vite.config.ts`, so Tailwind v4 and the React plugin just work. |
| `jsdom` | **29.1.1** | jsdom 30.x requires Node `^24.15`, and Elton's Mac runs Node 24.10. 29 accepts `>=24.0.0`. The build image is `node:24-slim`. |
| `@testing-library/react` / `dom` / `user-event` / `jest-dom` | 16.3.3 / 10.4.2 / 14.6.7 / 7.0.1 | Behaviour through the DOM, not component internals. `jest-dom` 7 peers `@testing-library/dom >=10 <11`. |
| `msw` | 2.15.0 | REST stubbed at the network edge, so `openapi-fetch` and TanStack Query run for real. |

### Build this

- **Config:** add a `test` block to the existing `src/frontend/vite.config.ts`, not a second
  config file:
  - `environment: 'jsdom'`
  - `setupFiles: ['src/test/setup.ts']`
  - `restoreMocks: true`
- **npm scripts:** `"test": "vitest run"`, `"test:watch": "vitest"`.
- **`src/test/setup.ts`:**
  - `@testing-library/jest-dom/vitest` matchers
  - an MSW `setupServer` with `onUnhandledRequest: 'error'`, so an unstubbed call fails the test
  - after each test: reset the handlers, clean up the DOM, and reset the Zustand store in
    `src/stores/chat.ts`
- **`src/test/render.tsx`:** `renderWithProviders(ui, { route, session })`.
  - A **fresh `QueryClient` per test**, with `retry: false`. A shared client leaks cache between
    tests.
  - A `MemoryRouter`.
  - The fake socket.
- **`src/test/api.ts`:** MSW handlers typed from the **generated** `src/types/messaging.ts`
  (register D23). A stub whose body doesn't match the OpenAPI schema must fail `tsc`. If
  `src/types/messaging.ts` is stale, regenerate it:
  `python -m messaging.openapi > src/frontend/openapi/messaging.json`, then `npm run generate:api`.
- **`src/test/socket.ts`:** an in-memory fake of the `socket.io-client` surface the app uses:
  `on`, `off`, and `emit` with an ack callback. `serverEmit(event, payload)` pushes server events.
  Swap it in with `vi.mock` of `connect()` from `src/lib/realtime/socket.ts`.
- **`src/test/factories.ts`:** `aChannel()`, `aMessage()`, typed from the generated schema.
- **ESLint:** add an override in `src/frontend/eslint.config.js` for `src/test/**` and
  `**/*.test.{ts,tsx}`. `react-refresh/only-export-components` warns on helper modules. Keep the
  config non-type-aware; its header comment explains why.
- **`scripts/test.sh`:** in `layer_unit`, after pytest, run
  `ensure_node_modules; (cd src/frontend && npm run --silent test)`. Use the same helper
  `layer_lint` uses. Update the script's header comment.
- **CLAUDE.md:** replace "Frontend unit tests wait for Vitest (… plan C)" in "Working in this repo"
  with how to run them.

### Red for the framework

Write one pilot test per helper, each proving the helper works:

- `upsertMessage` from `src/features/channels/useMessages.ts` against a real `QueryClient`, which
  proves `render.tsx`'s client wiring
- `problemFrom` from `src/lib/api/client.ts` against an MSW problem response, which proves `api.ts`
  and `onUnhandledRequest`
- a `MessageItem` render, which proves providers and factories
- a `useChannelSocket` handler reacting to `serverEmit('message_received', …)`, which proves the
  fake socket

### Constraints that bite in the SPA

- **TanStack Query owns all server state, and Zustand owns client state only (D24).** Never
  assert on a channel or message list in the store.
- **Selectors:** Testing Library queries by role, label or text.
  - `data-testid` is the BDD suite's contract; there are 66 in the SPA. Don't rename or remove any.
  - Don't add new ones for Vitest's sake.
- **Tailwind v4 is light-only.** Don't assert on classes.

---

## Workstream 3 — Unit backfill

Start this only after workstreams 1 and 2. Run it in priority order, and give each item its own
plan slice and its own red review.

### Python

1. **The first worked example of decision 2: message edit and delete policies.** It was deferred
   from plan A. In `src/services/messaging/messaging/messages.py`:
   - **`check_editable(message: Message, *, user_id: uuid.UUID) -> None`** raises
     `AlreadyDeletedError` if `message.deleted_at` is set, *then* `NotAuthorError` if
     `message.author_id != user_id`. State is checked before authorship, which is the order `edit`
     checks in today.
   - **`check_deletable(message: Message, *, user_id: uuid.UUID, is_channel_admin: bool) -> None`**
     raises `NotDeletableError` if the caller is neither the author nor a channel admin.
     - It is silent about an already-deleted message: a repeat delete returns the existing
       tombstone (D8d).
     - `delete` must still query `channels.is_admin` only for someone who isn't the author.
   - `edit` and `delete` call them. Visibility stays in `_visible`, which is SQL.
   - Tests go in `src/services/messaging/tests/unit/test_message_policy.py`:
     - the author may edit
     - someone else may not
     - a deleted message can't be edited even by its author
     - a deleted message of Grace's says *deleted* before *not yours*
     - the author may delete
     - a channel admin may delete someone else's
     - someone who is neither may not
     - deleting an already-deleted message is not a permission error
   - This one is *new code*, so it is true red. Import errors first, then stop.
   - Prove the routes still apply the rules:
     `scripts/test.sh integration -- src/services/messaging/tests/integration/test_messages.py`.
2. **Channel name and kind rules:** `validate_name` and `validate_kind` in
   `src/services/messaging/messaging/channels.py`.
   - Today they're reached only over HTTP against Postgres:
     `test_invalid_names_are_rejected_with_a_reason_per_rule`, `test_valid_names_are_accepted`,
     `test_a_name_is_trimmed_before_it_is_stored`,
     `test_dm_channels_cannot_be_created_through_this_api`.
   - Unit-test every rule: required, too short (3), too long (80), must start with a letter,
     letters/numbers/hyphens only, trimming, unknown kind.
   - Keep the integration tests that prove the *route* maps each rule to its problem, and trim
     those to one per route if they duplicate.
3. **Message body rules:** `validate_body(raw, *, max_chars)` in `messages.py`. Cover empty,
   whitespace-only, over the limit, exactly at the limit, and "the configured limit is the one
   applied".
4. **Contract tests, producer side** (decision 7). `messaging.indexing._enqueue` builds a
   `contracts.indexing.MessageIndexPayload` from a `MessageResponse` and calls
   `JobQueue.enqueue(JOBS_INDEX, job_type, payload)`.
   - With a recording `JobQueue`, a class of ours at the edge, assert:
     - the stream name
     - the job type for upsert and for delete
     - every payload field, including `version` and `workspace_id` from the argument, not the
       response
   - Also assert that an enqueue failure is swallowed and logged *without the body*: fire-and-forget,
     and CH008 forbids PII in logs.
5. **Contract tests, consumer side.** `shared.jobs.JobEnvelope.new/encode/decode` round-trips a
   `MessageIndexPayload`, and camelCase survives the wire.
   - Read `src/services/worker/worker/handlers/messages.py`. If building the Elasticsearch document
     from an envelope can be pulled out as a pure function, extract it the same way as item 1 and
     unit-test it.
   - The ES write itself is integration.
6. **Search query rules.** `src/services/messaging/messaging/search.py` has
   `MAX_QUERY_CHARS = 200` and builds an ES query in `_candidate_ids`.
   - Unit-test query validation, and the query body *if* its construction can be separated from
     the ES call.
   - `_hydrate` is SQL, so it's integration.
7. **Worker consumer decisions.** `src/services/worker/worker/consumer.py` decides retry vs
   dead-letter from `deliveries` against `ConsumerConfig.max_attempts`, and from
   `PermanentJobError`. It is written against Redis.
   - Only if that decision can be pulled into a pure function without restructuring the consumer,
     unit-test it.
   - Otherwise leave it to the integration handoff, which owns the consumer's behaviour against a
     real stream.

### SPA (Vitest)

The BDD triage (design, Framework 4) moves these behaviours down to Vitest:

| Target | Behaviour to cover | Replaces BDD scenario |
|---|---|---|
| `CreateChannelDialog.tsx` | name validation feedback for every rule; a duplicate-name problem shown to the user; creating a channel navigates into it | channels: "cannot be reused, whatever its case", "cannot be blank", "has to be one people can type", "not longer than 80 characters", and the outline rows of "creates a public channel" beyond the one kept |
| `ChannelHeader.tsx` | an admin renames; a non-admin is not offered rename or archive | channels: "A channel admin renames a channel"; permissions: "A member without admin rights is not offered the channel controls" |
| `ChannelList.tsx` | an archived channel leaves the list | channels: "An admin archives a channel and it leaves the list" |
| `MessageItem.tsx` | author and timestamp shown; edited marker; no edit control on someone else's message; tombstone rendering | messages: "shows its author and timestamp", "Ada cannot edit Grace's message", "A non-admin cannot delete someone else's message" (UI half) |
| `MessageComposer.tsx` | blank not sent; over 8000 characters rejected with feedback | messages: "A blank message is not sent", "over 8000 characters is rejected" |
| `MessageList.tsx` | loads older messages when the top sentinel is reached (drive the observer callback; no real scroll) | messages: "Scrolling up loads older messages" |
| `TypingIndicator.tsx` / `useTyping.ts` | indicator appears on a typing event and clears after it stops | realtime: "A typing indicator appears … and clears" (UI half) |
| `useSendMessage` in `useMessages.ts` | an optimistic message appears at once and is confirmed; a rejected send rolls back and shows the error | realtime: "A sent message appears immediately and is confirmed", "A rejected send is rolled back and the error is shown" |

Library code with no BDD counterpart:
- `src/lib/api/client.ts`: `problemFrom`, `problemFromBody`, `describeError`, `bearer`
- `src/lib/auth/pkce.ts`: `createVerifier`, `challengeFor`
- `src/lib/auth/session.ts`:
  - the state machine: `subscribe`, `snapshot`, `restore`, `signIn`, `completeSignIn`,
    `changeWorkspace`, `signOut`
  - renewal scheduling, with fake timers
- `useMessages.ts`: `upsertMessage`, `removeMessage`, `isPending`
- `src/stores/chat.ts`

**Report replacements for the BDD suite.** For every row above, give the replacement test's file
and name in a `## BDD replacements` section of your `04-test-pyramid-unit-…` plan, and keep it
updated as each replacement lands. The end-to-end agent reads that section from `main`; a final
report is invisible to it. The end-to-end handoff deletes a BDD scenario
*only* once its replacement has landed, and it works from your table. If you decide a behaviour
can't be covered in Vitest, say so, so that scenario is kept.

---

## Done when

- `RecordingServer` is imported from `testkit.fakes`.
- `npm test` runs Vitest with the four helpers and pilots.
  - `scripts/test.sh unit` runs pytest and then Vitest, and fails when either fails.
  - `scripts/test.sh lint` is still clean: eslint and tsc over the new test files.
- The Python backfill items 1–7 are done, or explicitly handed to integration with a reason.
- The SPA table is covered, and the BDD replacement table is delivered.
- Measured coverage per service is reported, with a proposed floor.
- CLAUDE.md and Conventions §11 match what exists.

## Not yours

- **The integration handoff owns these:**
  - containers, database-per-service, Redis-per-role and Elasticsearch fixtures
  - `testkit/{containers,databases,images,tokens,apps,db}.py`
  - Worker and search behaviour against real stores
- **The end-to-end handoff owns these:** `scripts/test.sh e2e`, deleting BDD scenarios, and new
  journeys.
- **Out of scope everywhere:** a coverage gate, pytest-xdist, mutation or visual testing.

## Coordinating with the other two handoffs

- **`pyproject.toml` and `uv.lock`:** you may not touch them at all, since Vitest is npm. If you
  do, expect a `uv.lock` merge conflict with the integration branch; resolve it by re-running
  `uv lock`.
- **`scripts/test.sh`:** you edit `layer_unit`, and the e2e handoff adds `layer_e2e`. Both handoffs
  edit the script's header comment, and e2e also changes the argument `case` and the `all`
  expansion, so expect a small conflict there and resolve it by keeping both sets of changes.
- **`testkit`:** you own `fakes.py` and `factories.py`. `plugin.py` is shared; change it only with
  a failing pytester test and Elton's review.
- **CLAUDE.md "Testing" and `docs/design/00-platform-conventions.md` §11:** all three handoffs may
  edit these. Re-read both sections from `main` before editing, and expect to merge text.
