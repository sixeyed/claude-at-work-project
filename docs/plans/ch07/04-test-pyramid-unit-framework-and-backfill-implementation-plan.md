# Test pyramid, unit layer — framework and backfill implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the Python unit framework, add Vitest to the SPA, and backfill the missing unit
tests, Python and SPA, including the replacements for the BDD scenarios that move down a layer.

**Architecture:** Python rules become unit-testable by extracting pure functions over loaded
values (decision 2), never by faking a store. The SPA gets Vitest in the existing Vite config, with
MSW at the network edge, a fresh `QueryClient` per test and an in-memory fake of the
`socket.io-client` surface, mocked once for every test in `src/test/setup.ts`.

**Tech Stack:** pytest 9, pytest-socket (through `testkit`), Vitest 5.0.1, jsdom 29.1.1, Testing
Library, MSW 2.15.0.

**Spec:** [03-test-pyramid-handoff-unit.md](03-test-pyramid-handoff-unit.md), which argues from
[01-test-pyramid-design.md](01-test-pyramid-design.md).

Branch `feature/test-pyramid-unit`, worktree `../caw-test-pyramid-unit`. Started 2026-09-15.

## Global Constraints

- Nothing is committed or staged (CLAUDE.md). No `git add`, `git commit`, `git stash` or `git mv`.
- A unit test never fakes a database, Redis or Elasticsearch. What it can't reach belongs to integration.
- `from tests… import` is banned (TID251). Shared helpers come from `testkit`, and a service's own go through fixtures.
- `pyproject.toml` and `uv.lock` are not touched.
- `testkit/plugin.py` is not touched. The known gaps in the handoff stay open.
- Vitest selectors are role, label or text. No `data-testid` is added, renamed or removed (66 exist). No assertion reads a class.
- Server state is never asserted through the Zustand store (D24).
- Pinned versions: `vitest` and `@vitest/coverage-v8` 5.0.1, `jsdom` 29.1.1 (30.x needs Node ^24.15), `@testing-library/react` 16.3.3, `@testing-library/dom` 10.4.2, `@testing-library/user-event` 14.6.7, `@testing-library/jest-dom` 7.0.1, `msw` 2.15.0. All were re-checked with `npm view` on 2026-09-15.

## How review ran on this branch

**Status, 2026-09-15:** every task below is built, and `scripts/test.sh lint unit` passes. No
register ID was needed: nothing here decided anything D32 had not already settled, so **D33
is unused**. This branch was not committed.

Elton asked for the whole handoff to be built in one go, with assumptions made rather than
questions asked (2026-09-15). The red and prove-it-can-fail checkpoints were still run, one per
slice. Their evidence is recorded under **Evidence** at the end, so it can be reviewed
afterwards rather than in between.

## Deviations from the handoff, and why

1. **The message row factory is a fixture in `messaging/tests/unit/conftest.py`, not
   `testkit/factories.py`.**
   - CLAUDE.md, which wins over the handoff, says a service's own helpers go through fixtures.
   - A `Message` is Messaging's own model. `testkit` would have to depend on
     `collabhub-messaging`, which is a `pyproject.toml` and `uv.lock` change.
   - Two test files use it, so the "second test" condition is met.
   - `testkit/factories.py` is not created.
2. **`renderWithProviders(ui, { route, path })` takes no `session`.**
   - No component under test reads the session except through props, or through `useSession()`
     over a module store that has no injection seam.
   - `session.ts` is tested directly, with MSW standing in for Auth.
   - `aSession()` in `src/test/factories.ts` builds the `Session` prop that `ChatLayout` takes.
3. **`MessageList` has no IntersectionObserver.**
   - It loads older pages from its `onScroll` handler.
   - The test fires `scroll` on the list. jsdom's `scrollTop` is 0, which is under the threshold.
   - No real scrolling is involved, which is what the handoff wanted.

---

## File map

**Python**

| File | Change |
|---|---|
| `src/services/testkit/testkit/fakes.py` | new: `RecordingServer` (moved verbatim), `RecordingJobQueue` |
| `src/services/messaging/tests/unit/test_read_markers.py` | import `RecordingServer` from `testkit.fakes` |
| `src/services/messaging/tests/unit/conftest.py` | new: `a_message` factory fixture |
| `src/services/messaging/messaging/messages.py` | extract `check_editable`, `check_deletable` |
| `src/services/messaging/messaging/search.py` | extract `validate_query`, `candidate_query` |
| `src/services/messaging/messaging/routers/search.py` | call `search.validate_query` |
| `src/services/worker/worker/handlers/messages.py` | extract `index_request` |
| `src/services/worker/worker/consumer.py` | extract `triage` |
| `src/services/messaging/tests/unit/test_message_policy.py` | new |
| `src/services/messaging/tests/unit/test_channel_rules.py` | new |
| `src/services/messaging/tests/unit/test_message_body.py` | new |
| `src/services/messaging/tests/unit/test_indexing.py` | new: producer contract |
| `src/services/messaging/tests/unit/test_search_query.py` | new |
| `src/services/worker/tests/unit/test_message_handlers.py` | new: consumer contract |
| `src/services/worker/tests/unit/test_consumer_triage.py` | new |
| `src/services/messaging/tests/integration/test_channels.py`, `test_messages.py` | trim duplicate parametrize rows |

**SPA** (`src/frontend/`)

| File | Change |
|---|---|
| `package.json`, `package-lock.json` | dev dependencies, `test`, `test:watch` |
| `vite.config.ts` | `test` block |
| `eslint.config.js` | override for `src/test/**`, `**/*.test.{ts,tsx}` |
| `src/test/setup.ts` | jest-dom, MSW server, socket mock, per-test reset |
| `src/test/render.tsx` | `renderWithProviders`, `createTestQueryClient` |
| `src/test/api.ts` | `server`, typed `messaging` and `auth` stubs, `problem` |
| `src/test/socket.ts` | `FakeSocket`, `latestSocket()`, `connectedSockets()` |
| `src/test/factories.ts` | `aChannel`, `aMessage`, `aMessagePage`, `aSession`, `aWorkspaceMember` |
| `src/**/X.test.ts(x)` | beside their source |
| `scripts/test.sh` | `layer_unit` runs Vitest after pytest |
| `CLAUDE.md`, `docs/design/00-platform-conventions.md` §11 | how the frontend unit tests run |

---

## Workstream 1 — Python unit framework

### Task 1: `RecordingServer` into `testkit.fakes`

**Files:** Create `src/services/testkit/testkit/fakes.py`. Modify
`src/services/messaging/tests/unit/test_read_markers.py`.

**Produces:**
- `testkit.fakes.RecordingServer`, with `.emits: list[tuple[str, Any, dict[str, Any]]]` and
  `async emit(event, data=None, **kwargs)`.
- `testkit.fakes.RecordingJobQueue` (Task 6). Its `.enqueued` is a
  `list[tuple[str, str, BaseModel]]`, its `async enqueue(stream, job_type, payload)` returns
  `None`, and `fail_with: Exception | None` makes it raise instead.

- [ ] Move the class verbatim, docstring included. Delete it from the test file and import it
  from `testkit.fakes`.
- [ ] Run `uv run pytest src/services/messaging/tests/unit/test_read_markers.py -q` and expect
  10 passed.

## Workstream 3 — Python backfill

A unit test builds a `Message` without a session:

```python
# src/services/messaging/tests/unit/conftest.py
@pytest.fixture
def a_message():
    def build(**overrides) -> Message:
        values = dict(id=uuid7(), channel_id=uuid.uuid4(), author_id=uuid.uuid4(), body="hello",
                      thread_root_id=None, attachments=[], created_at=AT, edited_at=None,
                      deleted_at=None, version=0)
        return Message(**(values | overrides))
    return build
```

### Task 2: message edit and delete policies (true red)

**Files:** `messaging/messages.py`, `tests/unit/test_message_policy.py`.

**Produces:**

```python
def check_editable(message: Message, *, user_id: uuid.UUID) -> None:
    """State, then authorship — that order is the security property."""
    if message.deleted_at is not None:
        raise AlreadyDeletedError(message.id)
    if message.author_id != user_id:
        raise NotAuthorError(message.id)

def check_deletable(message: Message, *, user_id: uuid.UUID, is_channel_admin: bool) -> None:
    """Author or channel admin. Silent about an already-deleted message (D8d)."""
    if message.author_id != user_id and not is_channel_admin:
        raise NotDeletableError(message.id)
```

`edit` calls `check_editable` after `_visible`. `delete` still queries `channels.is_admin` only for
a non-author:

```python
is_channel_admin = message.author_id != user_id and await channels.is_admin(...)
check_deletable(message, user_id=user_id, is_channel_admin=is_channel_admin)
```

**Tests:**
- `test_the_author_may_edit`
- `test_someone_else_may_not_edit`
- `test_a_deleted_message_cannot_be_edited_even_by_its_author`
- `test_a_deleted_message_of_graces_says_deleted_before_not_yours`
- `test_the_author_may_delete`
- `test_a_channel_admin_may_delete_someone_elses`
- `test_someone_who_is_neither_may_not_delete`
- `test_deleting_an_already_deleted_message_is_not_a_permission_error`

**Steps:**
- [ ] Write the tests.
- [ ] Run them and expect an `ImportError` on `check_editable`. That is red.
- [ ] Implement.
- [ ] Run them and expect them to pass.
- [ ] Run
  `scripts/test.sh integration -- src/services/messaging/tests/integration/test_messages.py` and
  expect it to pass.

### Task 3: channel name and kind rules (backfill)

**Files:** `tests/unit/test_channel_rules.py`, and trim `tests/integration/test_channels.py`.

**Tests:**
- required: `""` and `"   "`
- too short: `"ab"` fails, `"abc"` passes
- too long: 81 fails, 80 passes
- must start with a letter: `"1password"`, `"-general"`
- characters: `"dev team"`, `"dev_team"`, `"général"`
- valid names: `general`, `team-42`, `Design-Review`, `a1b`
- trimming happens before the length check: `"  ab  "` is too short, and `"  general  "` returns
  `"general"`
- kinds: `public` and `private` are accepted; `dm` and `bogus` raise `UnknownKindError`

**Integration trim:** keep one example per rule per route.
- `test_invalid_names_are_rejected_with_a_reason_per_rule` drops `"   "`, `"-general"`,
  `"dev_team"` and `"général"`.
- `test_valid_names_are_accepted` keeps `general` only.

**Prove it can fail:**
- [ ] Change `MIN_NAME_LENGTH = 3` to `2`, run, and expect red.
- [ ] Restore it.

### Task 4: message body rules (backfill)

**Files:** `tests/unit/test_message_body.py`, and trim `tests/integration/test_messages.py`.

**Tests:** empty, whitespace-only, over the limit, exactly at the limit, whitespace kept
verbatim, and the configured limit being the one applied (`max_chars=10`: 10 passes, 11 raises).

**Integration trim:** `test_an_empty_message_is_rejected` keeps `"   "` only.

**Prove it can fail:**
- [ ] Change `>` to `>=` in `validate_body`, run, and expect red.
- [ ] Restore it.

### Task 5: search query rules (extraction)

**Files:** `messaging/search.py`, `messaging/routers/search.py`, `tests/unit/test_search_query.py`.

**Produces:**
- `search.QueryRequiredError(Exception)`.
- `search.validate_query(raw: str) -> str` strips the query, and raises `QueryRequiredError` when
  nothing is left.
- `search.candidate_query(workspace_id, channel_ids, query, page) -> dict[str, Any]` builds the
  exact dict `_candidate_ids` passes to `es.search(**request)`.

**Tests:**
- blank is refused
- the query is trimmed
- the route declares `maxLength: 200` on `q`, read from `create_app(...).openapi()`
- the request filters on the `wsp` workspace, the visible channels and `deleted: False`
- `match` with `operator: and`
- sorted by `messageId` descending
- `size` is `page.fetch_limit`
- `search_after` only when there is a cursor
- `source` is False

**Steps:**
- [ ] Red is an `ImportError`.
- [ ] Integration for search is the integration handoff's, so none is run here.

### Task 6: producer contract (backfill)

**Files:** `tests/unit/test_indexing.py`, and `RecordingJobQueue` in `testkit/fakes.py`.

**Tests:**
- An upsert goes to `jobs:index` as `message.upsert`, and a delete as `message.delete`.
- Every payload field is asserted.
- `workspace_id` comes from the argument.
- `version` comes from the response.
- The payload validates as `MessageIndexPayload`.
- A delete of a tombstone carries `body == ""`. The response is built through
  `routers.messages._as_message(a_message(deleted_at=AT))`.
- A failed enqueue is swallowed. It logs one warning that names the job type and the exception
  class, and the body appears nowhere in `caplog.text`.

**Prove it can fail:**
- [ ] Swap `workspace_id=workspace_id` for `workspace_id=message.channel_id`, and expect red.
- [ ] Restore it.

### Task 7: consumer contract and the ES document (extraction)

**Files:** `worker/handlers/messages.py`, `tests/unit/test_message_handlers.py`.

**Produces:** `index_request(envelope: JobEnvelope, *, deleted: bool) -> dict[str, Any]`, which
returns the keyword arguments for `es.index`:

- `index`
- `id`
- `document`
- `version`
- `version_type="external"`

It raises `PermanentJobError("invalid payload")` on a payload that fails validation. `_write` calls
it.

**Tests:**
- `JobEnvelope.new → encode → decode` round-trips a `MessageIndexPayload`, and the wire JSON is
  camelCase (`messageId`, `workspaceId`, `createdAt`, `type`, `jobId`).
- An upsert document carries the body and `deleted: False`.
- A delete document has no `body` key and `deleted: True`.
- `version` is external, and is taken from the payload.
- `version` is not in the document.
- An invalid payload is permanent.

**Steps:**
- [ ] Red is an `ImportError`.

### Task 8: consumer triage (extraction)

**Files:** `worker/consumer.py`, `tests/unit/test_consumer_triage.py`.

**Produces:**

```python
@dataclass(frozen=True)
class Run:
    envelope: JobEnvelope
    handler: Handler

@dataclass(frozen=True)
class DeadLetter:
    reason: str  # "malformed-envelope" | "max-attempts" | "unknown-type"

def triage(fields: Mapping[str, str], *, deliveries: int, max_attempts: int,
           handlers: Mapping[str, Handler]) -> Run | DeadLetter
```

`_process` becomes: triage, and on `DeadLetter` dead-letter the entry. Otherwise it runs the
handler with the existing `PermanentJobError` and retry branches. The order stays malformed, then
attempts, then unknown type.

**Tests:**
- the `data` field is missing
- the JSON is not an envelope
- `deliveries == max_attempts` runs
- `deliveries > max_attempts` dead-letters, even a valid job
- malformed wins over max-attempts
- an unknown type
- a known type gets its own handler

**Steps:**
- [ ] Red is an `ImportError`.
- [ ] Retry and dead-letter over a real stream stay with the integration handoff.

---

## Workstream 2 — Frontend unit framework

### Task 9: Vitest, the helpers, and one pilot per helper

**Produces:**

- **`src/test/api.ts`:**
  - `server` (msw/node `setupServer()`)
  - `MESSAGING_URL`, `AUTH_URL`
  - `messaging.get|post|patch|delete(path, body | resolver)`. The path is an OpenAPI path key
    whose success body is typed from `paths`, so a mismatched body fails `tsc`.
  - `messaging.problem(method, path, status, problemBody)`
  - `auth.members(members)` for the workspace directory
  - `requests()`, which records `{ method, url, body }` for assertions
- **`src/test/socket.ts`:** `class FakeSocket`.
  - `connected`
  - `on`, `off`
  - `emit(event, ...args, ack?)`
  - `timeout(ms).emit(...)`, whose ack is called as `(err, response)`
  - `serverEmit(event, payload)`
  - `serverConnect()`, `serverDisconnect()`
  - `onEmit(event, (payload) => ackResponse)`, for a server-side responder
  - `emitted`, which records `{ event, args }`
  - `close()`, `disconnect()`

  It also exports `latestSocket()`, `resetSockets()`, and `fakeConnect(accessToken)`, which is
  what `connect` is mocked to.
- **`src/test/render.tsx`:**
  - `createTestQueryClient()`, with `retry: false` for queries and mutations and `gcTime: Infinity`
  - `renderWithProviders(ui, { route = '/', path?, queryClient?, socket? })`, returning the RTL
    result plus `{ queryClient, socket, user, location() }`
- **`src/test/factories.ts`:** `aChannel(overrides)`, `aMessage(overrides)`,
  `aMessagePage(items, nextCursor)`, `aSession(overrides)`, `aWorkspaceMember(overrides)`.

**Pilots:**
- `useMessages.test.ts`: `upsertMessage`
- `client.test.ts`: `problemFrom` against MSW, plus a `@ts-expect-error` on a mistyped stub, which
  keeps the typing honest in `tsc`
- `MessageItem.test.tsx`: author and time
- `useChannelSocket.test.tsx`: `serverEmit('message_received')` lands in the cache

**Steps:**
- [ ] Red: write the pilots before the helpers exist.
- [ ] `npm test` fails on the missing modules.
- [ ] Build the helpers.
- [ ] Green.
- [ ] `scripts/test.sh lint unit` green.

## Workstream 3 — SPA backfill

### Task 10: library code

- **`client.test.ts`:**
  - `problemFrom` keeps `errors`, falls back to `statusText` on a non-JSON body, and
    `fieldError` returns the first message
  - `problemFromBody` with no body
  - `describeError`
  - `bearer`
- **`pkce.test.ts`:**
  - the verifier is 43 base64url characters and unique per call
  - `challengeFor` matches the RFC 7636 appendix B vector
- **`session.test.ts`:** Auth is stubbed with MSW, and each test uses a fresh module through
  `vi.resetModules()`.
  - `restore` signs in from a refresh
  - `restore` on a 401 is signedOut with no error
  - `subscribe` is notified
  - `completeSignIn` with `error=access_denied`
  - `completeSignIn` without a verifier
  - `completeSignIn` with a code and verifier clears the verifier before the exchange, then signs in
  - `changeWorkspace` adopts the new token's `wsp`
  - `changeWorkspace` failure signs out
  - `signOut` calls logout and signs out even when logout fails
  - renewal is scheduled `expiresIn − 60` seconds ahead, with fake timers
  - a failed renewal signs out
  - `signIn` writes the verifier and navigates to `loginUrl`
- **`useMessages.test.ts`:**
  - `upsertMessage` replaces in place, prepends new, and no-ops on an empty cache
  - `removeMessage`
  - `isPending`
- **`chat.test.ts`:** active channel, drafts set and clear, connection status.

### Task 11: components and hooks (the BDD replacements)

Every row of the handoff's SPA table has a test file. The names are in **BDD replacements** below.

**Prove each one can fail:** break the component for one line, run the file, and expect red.
Then restore it. The evidence goes at the end.

## Finish

- [ ] `scripts/test.sh lint unit` green.
- [ ] Record coverage per service and propose a floor.
- [ ] Update CLAUDE.md "Working in this repo" and "Testing", and Conventions §11.

---

## BDD replacements

The end-to-end handoff reads this table from `main`, and deletes a scenario only once its
replacement has landed.

Every replacement below has **landed on `feature/test-pyramid-unit`**, and each was proven
able to fail (see Evidence). The paths are relative to `src/frontend/src/features/channels/`
unless a path says otherwise. `messaging/…` and `worker/…` are under `src/services/`.

| Feature | BDD scenario | Replacement test(s) | Verdict |
|---|---|---|---|
| channels | Ada creates a public channel and lands in it: the outline rows `team-42` and `Design-Review` | `CreateChannelDialog.test.tsx` › creating a channel from the chat shell › creates "%s" and lands the user in it (all three rows) | demote those rows; keep one example (`general`) as the journey |
| channels | A public channel name cannot be reused, whatever its case | `CreateChannelDialog.test.tsx` › shows a name already in use, whatever its case, in the banner · integration `test_public_names_collide_regardless_of_case` | demote |
| channels | A channel name cannot be blank | `CreateChannelDialog.test.tsx` › shows the server’s reason for a blank name against the name field · unit `messaging/tests/unit/test_channel_rules.py::test_a_name_is_required` | demote |
| channels | A channel name has to be one people can type (6 rows) | `CreateChannelDialog.test.tsx` › shows the server’s reason for … (one per row: too short, digit, hyphen, space, underscore, accent) · unit `test_channel_rules.py::test_a_name_shorter_than_three_characters_is_refused`, `::test_a_name_must_start_with_a_letter`, `::test_a_name_uses_only_letters_numbers_and_hyphens` | demote |
| channels | A channel name cannot be longer than 80 characters | `CreateChannelDialog.test.tsx` › shows the server’s reason for a name over 80 characters against the name field · unit `test_channel_rules.py::test_a_name_longer_than_eighty_characters_is_refused` | demote |
| channels | A channel admin renames a channel | `ChannelHeader.test.tsx` › lets a channel admin rename the channel (PATCH with the held version, then the list and detail are invalidated) · integration `test_an_admin_renames_a_channel`, `test_a_rename_is_what_the_next_read_returns` | demote |
| channels | An admin archives a channel and it leaves the list | `ChannelList.test.tsx` › drops a channel an admin archives, and leaves its page · `ChannelHeader.test.tsx` › asks before archiving, and a cancel sends nothing | demote |
| permissions | A member without admin rights is not offered the channel controls | `ChannelHeader.test.tsx` › offers a member no channel controls · › offers someone who never joined no channel controls. The "But Ada is offered" half is › lets a channel admin rename the channel | demote |
| messages | A message shows its author and timestamp | `MessageItem.test.tsx` › shows its author and the time it was sent | demote |
| messages | A blank message is not sent | `MessageComposer.test.tsx` › sends nothing when the box is empty · › does not keep a message of nothing but spaces, and says why · unit `messaging/tests/unit/test_message_body.py::test_an_empty_or_whitespace_only_body_is_refused` | demote |
| messages | A message over 8000 characters is rejected | `MessageComposer.test.tsx` › rejects a message over 8000 characters with the reason, and keeps the text · unit `test_message_body.py::test_a_body_over_the_limit_is_refused`, `::test_a_body_of_exactly_the_limit_is_accepted` | demote |
| messages | Scrolling up loads older messages | `MessageList.test.tsx` › loads older messages above the rest when the top of the history is reached · › asks for nothing more once the oldest page is in · › shows the newest page oldest-first, as a conversation reads | demote |
| messages | Ada cannot edit Grace's message | `MessageItem.test.tsx` › offers Ada no way to edit or delete Grace’s message · unit `messaging/tests/unit/test_message_policy.py::test_someone_else_may_not_edit` · integration `test_a_non_author_cannot_edit` | demote |
| messages | A channel admin deletes another user's message | unit `test_message_policy.py::test_a_channel_admin_may_delete_someone_elses` · `MessageItem.test.tsx` › offers a channel admin delete, but never edit, on someone else’s message · integration `test_a_channel_admin_deletes_another_users_message` | demote |
| messages | A non-admin cannot delete someone else's message (UI half) | `MessageItem.test.tsx` › offers Ada no way to edit or delete Grace’s message · unit `test_message_policy.py::test_someone_who_is_neither_may_not_delete` · integration `test_a_non_admin_cannot_delete_someone_elses_message` | demote |
| realtime | A typing indicator appears for Grace and clears when Ada stops (UI half) | `useTyping.test.ts` › shows someone as typing when they start, and clears them once they stop · `MessageComposer.test.tsx` › shows who is typing, by name · `TypingIndicator.test.tsx` › is absent when nobody is typing | demote (the socket fan-out half is integration) |
| realtime | A sent message appears immediately and is confirmed | `useMessages.test.ts` › useSendMessage › shows the message at once, then swaps in the confirmed one · › shows a message once when its broadcast beats its acknowledgement · `MessageComposer.test.tsx` › empties the box the moment a message is sent | demote |
| realtime | A rejected send is rolled back and the error is shown | `useMessages.test.ts` › useSendMessage › rolls a refused send back and keeps the server’s reason · › rolls back within five seconds when no acknowledgement comes · `MessageComposer.test.tsx` › rejects a message over 8000 characters with the reason, and keeps the text | demote |

**Nothing in the handoff's SPA table was found impossible to cover in Vitest**, so no scenario
has to be kept for want of a replacement.

Two rows of the design's triage are not this layer's, and this branch adds nothing for them:
- "A rename is visible to everyone" is demoted to integration, where
  `test_a_rename_is_what_the_next_read_returns` already exists.
- "Grace does not receive messages for a channel she is not looking at" is integration's rooms
  test.

## What went to integration, and why

- **The Worker's `triage` and `index_request` run nowhere against a real stream or index.**
  Their decisions are unit-tested. The Worker has no integration tests, and the integration
  handoff owns `run_consumer`.
- **What the consumer does with a handler's own failure** — `PermanentJobError`, retry,
  `XACK`/`XDEL` — sits around an `await` on Redis. It was left in `_process`, not extracted.
- **Search's `_hydrate` and `channels.visible_ids`** are SQL.
- **Routes mapping each rule to its problem** stay in integration, trimmed to one example per
  rule per route: 9 parametrize rows removed, 154 → 145 messaging integration tests.

## Coverage, and a proposed floor

Measured 2026-09-15 at the end of the backfill.

**Python:** `scripts/test.sh unit` reports **TOTAL 58%** (2907 statements, branch coverage on).

| Service | Unit coverage |
|---|---|
| shared | 83% |
| contracts | 100% |
| auth | 55% |
| messaging | 51% |
| canvas | 96% |
| asset | 96% |
| worker | 47% |

Canvas and Asset are high only because they are scaffolds with a health route.

**SPA:** `npx vitest run --coverage` gives:
- lines 76.7%
- statements 74.5%
- branches 65.2%
- functions 74.2%

These exclude `src/test/`, generated types and the tests themselves.

**Proposed floor, for Elton to decide.** No gate has been configured; decision 11 still holds.
- **Python:** a whole-tree `fail_under = 55` in `[tool.coverage.report]`, three points under
  what was measured.
- **SPA:** a Vitest `coverage.thresholds.lines` of 70.
- **No per-service floors yet.** The scaffolds would pass any number, and Messaging and the
  Worker would pin a number that the integration handoff's work does not move, because
  integration coverage is not measured.
- Ratchet both up as later slices add unit tests, rather than setting them high now.

## Evidence

### Python

Recorded by the executor of Tasks 1–8. Every command runs from the worktree root.

| Task | Kind | Command | Result |
|---|---|---|---|
| 1 | move | `uv run pytest src/services/messaging/tests/unit/test_read_markers.py -q` | 10 passed |
| 2 | true red | `uv run pytest src/services/messaging/tests/unit/test_message_policy.py -q` | `ImportError: cannot import name 'check_deletable' from 'messaging.messages'`, then 8 passed |
| 3 | prove it can fail | `MIN_NAME_LENGTH = 3` → `2`, then `uv run pytest …/test_channel_rules.py -q` | `2 failed, 22 passed` (`test_a_name_shorter_than_three_characters_is_refused`, `test_the_length_rules_apply_to_the_trimmed_name`), restored |
| 4 | prove it can fail | `len(raw) > max_chars` → `>=`, then `uv run pytest …/test_message_body.py -q` | `2 failed, 7 passed` (`test_a_body_of_exactly_the_limit_is_accepted`, `test_the_configured_limit_is_the_one_applied`), restored |
| 5 | true red | `uv run pytest …/test_search_query.py -q` | `AttributeError: module 'messaging.search' has no attribute 'QueryRequiredError'`, then 12 passed |
| 6 | prove it can fail | `workspace_id=workspace_id` → `workspace_id=message.channel_id`, then `uv run pytest …/test_indexing.py -q` | `1 failed, 5 passed` (`test_the_payload_carries_every_field_from_the_committed_message`), restored |
| 7 | true red | `uv run pytest src/services/worker/tests/unit/test_message_handlers.py -q` | `ImportError: cannot import name 'index_request'` |
| 8 | true red | `uv run pytest src/services/worker/tests/unit/test_consumer_triage.py -q` | `ImportError: cannot import name 'DeadLetter'`; with Task 7, the Worker unit tests give 17 passed |
| all | integration | `scripts/test.sh integration -- src/services/messaging/tests/integration -q` | `145 passed` |

`conventions.py` over the changed files exits 0, and ruff check and format are clean.

### SPA framework (Task 9)

**Red.** The four pilots, before any helper existed:

```
$ npx vitest run
 FAIL  src/lib/api/client.test.ts            Error: Cannot find module '../../test/api'
 FAIL  src/lib/realtime/useChannelSocket.test.tsx  Error: Cannot find module '../../test/factories'
 FAIL  src/features/channels/MessageItem.test.tsx  Error: Cannot find module '../../test/factories'
 FAIL  src/features/channels/useMessages.test.ts   Error: Cannot find module '../../test/factories'
 Test Files  4 failed (4)
```

**Green:** `4 passed (4)`, `Tests 6 passed`. `eslint --max-warnings 0 .` and `tsc --noEmit` are
clean.

**Typed stubs:** the `@ts-expect-error` in `client.test.ts` would itself fail `tsc` as unused if a
mistyped stub ever compiled.

### SPA backfill (Tasks 10–11)

Everything passed on first run: 14 files, 97 tests, with no stderr warnings. Each behaviour was
then broken with a one-line change, the one test file run, and the source restored with
`git checkout`.

| Source | Break | Red |
|---|---|---|
| `MessageItem.tsx` | `canEdit` drops `&& isAuthor` | 2 failed: Grace’s message; admin never edit |
| `MessageItem.tsx` | `(isAuthor \|\| myRole === 'admin')` → `(isAuthor)` | 1 failed: admin delete |
| `MessageItem.tsx` | edited marker ignores `deleted` | 1 failed: tombstone |
| `ChannelHeader.tsx` | `isAdmin = true` | 2 failed: no controls for a member or a non-member |
| `useChannels.ts` | rename skips the detail invalidation | 1 failed: admin renames |
| `CreateChannelDialog.tsx` | field error never rendered | 8 failed: every rule |
| `CreateChannelDialog.tsx` | banner never rendered | 1 failed: name already in use |
| `ChatLayout.tsx` | `navigate('/')` after create | 3 failed: lands the user in it |
| `useChannels.ts` | no list invalidation | 1 failed: archive leaves the list |
| `MessageComposer.tsx` | `if (!draft) return` removed | 1 failed: empty box sends nothing |
| `MessageComposer.tsx` | draft not restored on error | 2 failed: spaces; over 8000 |
| `MessageComposer.tsx` | never disabled | 1 failed: disabled while down |
| `MessageList.tsx` | scroll never loads | 2 failed: loads older; nothing more |
| `useMessages.ts` | `select` stops reversing items | 2 failed: order |
| `TypingIndicator.tsx` | "and" wording | 1 failed |
| `TypingIndicator.tsx` | renders when empty | 1 failed |
| `useTyping.ts` | TTL 4000 → 40000 | 1 failed: clears once they stop |
| `useTyping.ts` | own-user filter removed | 1 failed |
| `useTyping.ts` | throttle removed | 1 failed |
| `useTyping.ts` | `off` removed | 1 failed: stops listening |
| `useMessages.ts` | no optimistic upsert | 3 failed: send tests |
| `useMessages.ts` | send timeout 5000 → 50000 | 1 failed: rolls back within five seconds |
| `useMessages.ts` | `if (existing)` → `if (false)` | 3 failed: replace; broadcast twice; race |
| `useMessages.ts` | new message appended, not prepended | 1 failed: head of newest page |
| `useMessages.ts` | `onError` rollback skipped | 3 failed: refused; timeout; no socket |
| `useMessages.ts` | `temp:` prefix → `tmp:` | 2 failed: isPending; shows at once |
| `useChannelSocket.ts` | `message_received` not subscribed | 1 failed |
| `client.ts` | `errors` dropped | 1 failed |
| `client.ts` | `describeError` returns `String(caught)` | 2 failed |
| `pkce.ts` | padding kept | 2 failed, including the RFC 7636 vector |
| `session.ts` | renew margin 60 → 30 | 2 failed: renewal |
| `session.ts` | `wsp` claim read as `sub` | 3 failed |
| `session.ts` | logout failure not caught | 1 failed |
| `chat.ts` | `clearDraft` clears every draft | 1 failed |

**One break stayed green, and it is not a gap.** Removing `&& hasNextPage` from `MessageList`'s
scroll guard leaves 4 passed. TanStack Query's `fetchNextPage` does nothing when there is no next
page, so that guard only saves a function call.

The raw output is in the session scratchpad as `spa-mutations.txt`.

### The whole layer

```
$ scripts/test.sh lint unit
==> lint: ruff                All checks passed!
==> lint: CollabHub conventions
==> lint: frontend            (eslint, tsc)
==> lint: helm
==> unit tests: pytest        196 passed, 321 deselected — TOTAL 58%
==> unit tests: vitest        Test Files 14 passed (14), Tests 97 passed (97)
==> passed: lint unit
```

The unit layer fails when only Vitest fails. With `clearDraft` broken in `chat.ts`,
`scripts/test.sh unit` exits **1**: pytest reports `196 passed`, then Vitest reports
`1 failed | 96 passed`. The file was restored afterwards.
