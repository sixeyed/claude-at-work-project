# Test Pyramid — Integration backfill — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Project rules override those skills.** Never commit or stage. Backfill tests pass the moment
> they are written, because the behaviour exists — so **each one is proven able to fail**: a
> one-line break in the code it pins, the test run red, the code restored, the command and output
> recorded under *Proof each test can fail*.
>
> **Run note (2026-09-15).** Elton asked for everything built and tested without stopping to
> ask, so each slice's review happens on the final report rather than between slices.

**Goal:** Integration tests at the public boundary for the Worker's consumer, its message handlers
and index, Messaging's `jobs:index` producer and message search, and Redis role separation — plus
confirmation of the integration tests that replace the demoted BDD scenarios.

**Architecture:** Built on [the framework plan](05-test-pyramid-integration-framework-implementation-plan.md):
shared containers from `testkit`, a Redis index per role, Elasticsearch on demand, the Worker's
`run_consumer` / `jobs` harness. No production code changes.

**Tech Stack:** pytest, testcontainers (Redis 8, Elasticsearch 9.4.3, Postgres 18), redis-py
asyncio, elasticsearch-py async, python-socketio's `AsyncSimpleClient`, httpx.

**Spec:** [03-test-pyramid-handoff-integration.md](03-test-pyramid-handoff-integration.md),
workstream 2; [ADR 260914 — the index is a candidate list](../../adr/260914-message-search-index-is-a-candidate-list.md);
doc 05 §3–§5.1; doc 02 §3.1.6; register D25, D34.

## Global Constraints

- The directory decides the layer: every file here is under a service's `tests/integration/`.
- No mocks of a service's own Postgres, Redis or Elasticsearch.
- Messaging's code and tests import nothing from `worker`; the harness (`testkit.search`) may.
- `from tests… import` is banned (TID251): shared helpers from `testkit`, a service's own through
  fixtures.

## This plan's own calls

1. **Seeding Elasticsearch for search goes through the Worker's code, from `testkit`.**
   `testkit.search.MessagesIndex` builds the index with `ensure_messages_index` and writes
   documents with the Worker's `message.upsert` / `message.delete` handlers. A copy of the mapping
   in Messaging's tests would keep passing after the real mapping changed. Documents go straight
   through the handlers rather than a consumer, so a test can make the index lag the database —
   the case hydration exists for. Recorded as part of D34.
2. **Idempotency is proven at the handler, not the consumer.** The consumer has no `jobId`
   bookkeeping by design (doc 05 §3): the external version is what makes a duplicate harmless. So
   "same `jobId` twice, one effect" runs through the real message handlers against Elasticsearch.
3. **The ack test uses a 60 s visibility timeout.** `XAUTOCLAIM` removes deleted entries from the
   pending list, so with a short timeout a reclaim pass would tidy up after a missing `XACK` and
   the test would pass on broken code. Found by the mutation run.
4. **R2 separation is checked by connection.** Pub/Sub is server-wide, so the test asserts the
   backplane's subscribing connection selected `db=1` in `CLIENT LIST`.
5. **Unknown job type:** the code dead-letters it on first delivery with reason `unknown-type`
   (consumer module docstring, doc 05 §5.1 step 5). That is what the test pins.
6. **A mapping rejection** (`BadRequestError` → `PermanentJobError("rejected by index")`) is not
   tested: every document the handler builds comes from a validated `MessageIndexPayload`, so the
   public boundary cannot produce one. Reaching it would mean changing the mapping under test.
7. **The Worker has no Redis role test of its own.** It uses one role, and its harness connects
   to R3 by construction, so a role test would restate the fixture. Auth's and Messaging's are
   real: each exercises the app's own client wiring.

## File map

| Path | Tests |
|---|---|
| `src/services/worker/tests/integration/test_consumer.py` | ack, retry, permanent, max attempts, reclaim, unknown type, malformed envelope |
| `src/services/worker/tests/integration/test_message_index.py` | index + alias, idempotent ensure, upsert, tombstone, late older version, stale upsert after delete, duplicate delivery, invalid payload |
| `src/services/testkit/testkit/search.py` | `MessagesIndex` — seeding helper |
| `src/services/messaging/tests/integration/test_indexing.py` | send / edit / delete / socket send enqueue; rejected write enqueues nothing; unreachable R3 |
| `src/services/messaging/tests/integration/test_search.py` | hydrated match, Postgres body, paging, private channel, other workspace, deleted, tombstone, no index, ES down, 200/201 chars, blank |
| `src/services/messaging/tests/integration/test_redis_roles.py` | R3 jobs, R1 denylist, R2 backplane connection |
| `src/services/auth/tests/integration/test_redis_roles.py` | login-flow keys on R1 only |

## Task 1: Worker consumer

- [ ] Tests in `test_consumer.py` (names above).
- [ ] Run: `uv run pytest -m integration src/services/worker/tests/integration/test_consumer.py`
- [ ] Prove each can fail (below).

## Task 2: Worker handlers and index

- [ ] Tests in `test_message_index.py`.
- [ ] Run with the file path; prove each can fail.

## Task 3: Messaging producer

`test_messages.py` had no stream assertions (`grep -n "jobs\|xrange" test_messages.py` prints
nothing), so this is new coverage, not a duplicate.

- [ ] Tests in `test_indexing.py`; run; prove.

## Task 4: Message search

- [ ] `testkit/search.py`, then `test_search.py`; run; prove.

## Task 5: Redis role separation

- [ ] `test_redis_roles.py` in Messaging and Auth; run; prove Messaging's three.

## Task 6: BDD replacements (below)

---

## After merging `main` (2026-09-15)

The unit handoff landed first and refactored code these tests cover into pure functions
(plan 04; notes in the handoff's *Notes from the unit layer*). Merged in without a commit; see
the framework plan. On the merged code, before any change here: **317 integration tests passed**.

### Tests removed because the unit layer now proves them

| Removed | Now proven by |
|---|---|
| `test_consumer.py::test_an_unknown_job_type_is_dead_lettered_on_first_delivery` | `worker/tests/unit/test_consumer_triage.py::test_an_unknown_type_is_dead_lettered` |
| `test_consumer.py::test_a_malformed_envelope_is_dead_lettered_on_first_delivery` | `test_consumer_triage.py::test_an_entry_that_is_not_an_envelope_is_malformed` |
| `test_message_index.py::test_an_invalid_payload_is_dead_lettered_without_the_validation_text` | `worker/tests/unit/test_message_handlers.py::test_an_invalid_payload_is_permanent`; the fixed-reason rule stays proven by the consumer's permanent-error test |
| `test_search.py::test_a_query_may_be_200_characters_but_not_201` | `messaging/tests/unit/test_search_query.py::test_the_route_caps_the_query_at_200_characters` |
| Payload-shape assertions in `test_indexing.py` (workspace, author, body, `createdAt`, `body: ""`) | `messaging/tests/unit/test_indexing.py`. The integration tests keep what only the routes and a real stream show: which writes enqueue, the job type, the message id and the committed version |

Call 5 above (unknown job type) is superseded by the first row.

### Tests added for what plan 04 listed as untested anywhere

- **`test_consumer.py::test_the_consumer_recovers_when_its_stream_and_group_are_lost`** — `run`'s
  Redis-error path. **It found a bug.** The consumer created its group once, at startup; after
  the stream was lost (R3 flushed, the key deleted), a producer's `XADD` recreated it without
  the group and every read failed with `NOGROUP`, forever.
  - Red, on `main`'s code: `AssertionError: timed out after 15s waiting for jobs:index to
    drain`, with `redis error on jobs:index (ResponseError); retrying in 2.0s` logged eight
    times.
  - Fix, `worker/consumer.py`: `group_ready = False` in the `except RedisError` branch, so the
    retry ensures the group again (`BUSYGROUP` makes that free when nothing was lost). Recorded in
    doc 05 §5.1, step 6.
  - Green: `29 passed` across the Worker and the Messaging producer and search files; unit `209
    passed`.
  - redis-py 8 retries a dropped *connection* itself, so `run`'s backoff is reached by server
    errors such as `NOGROUP`, not by a killed socket — which is why this, and not a connection
    kill, is the test.
- **`test_message_index.py::test_a_write_the_index_refuses_is_dead_lettered_at_once`** — a
  `BadRequestError` from the real `es.index` becoming `permanent:rejected by index`, reached by
  putting two indices behind `messages` with no write index (a half-done reindex, D29). This
  replaces call 6's "not reachable": it is, without touching the mapping.
- **`test_consumer.py::test_a_permanent_error_…`** now also asserts `sourceId`, since
  `_dead_letter`'s entry fields are otherwise untested.

**Collected after these changes: integration 315** (278 existing + testkit 4, Worker 13,
Messaging 19, Auth 1).

### Proof against the refactored code — 24 mutants, 24 red

Re-run with the runner above on the merged code, for every test kept. `git status --short` on the
source directories afterwards showed only the consumer fix.

| Break | Test(s) | Result |
|---|---|---|
| `_complete` without `XACK` | ack test | **1 failed** 16.07s |
| reclaim claims nothing | transient retry, crashed-consumer reclaim | **2 failed** 31.49s |
| `permanent:{exc}` → `permanent:{exc.__cause__}` | permanent error | **1 failed** 0.81s |
| `_delivery_counts` returns 1 for every entry | max attempts | **1 failed** 30.88s |
| the fix reverted (`group_ready = False` removed) | stream-and-group recovery | **1 failed** 16.70s |
| `index_request` without `version` / `version_type` | upsert version, late older version, stale upsert after delete, delivered twice | **4 failed** 18.58s |
| `except ConflictError` raises `PermanentJobError` | late older version, delivered twice | **2 failed** 15.78s |
| `except BadRequestError` → `except KeyError` | index refuses the write | **1 failed** 22.32s |
| index created without its alias | ensure creates index + alias | **1 failed** 11.02s |
| `resource_already_exists_exception` re-raised | ensuring twice | **1 failed** 13.36s |
| delete enqueued as `MESSAGE_UPSERT` | delete enqueues a delete | **1 failed** 2.27s |
| `except Exception` → `except ValueError` in the producer | unreachable stream | **1 failed** 2.51s |
| R3 producer on the cache URL | index jobs on the streams index | **1 failed** 2.50s |
| denylist client on the streams URL | denylist on the cache index | **1 failed** 2.22s |
| backplane on the cache URL | backplane on the realtime index | **1 failed** 2.51s |
| `match` → `match_all` | a match comes back as the message | **1 failed** 17.32s |
| sort `asc` | newest first, paged | **1 failed** 13.42s |
| page keeps the look-ahead hit | newest first, paged | **1 failed** 17.48s |
| both visible-channel filters removed | private channel excluded | **1 failed** 13.87s |
| both channel filters and the workspace term removed | other workspace excluded | **1 failed** 17.56s |
| hydration without `deleted_at IS NULL` | deleted after indexing | **1 failed** 14.93s |
| `index_not_found_exception` not an empty result | before anything is indexed | **1 failed** 15.47s |
| `service_unavailable` → `ProblemException(500)` | ES down is a 503 | **1 failed** 2.45s |
| blank-query 400 → `ProblemException(500)` | blank query is a 400 | **1 failed** 13.50s |

The tables above this section record the run before the merge, against the code as it was then.

## BDD replacements

Confirmed 2026-09-15 by reading each test against its scenario in `tests/bdd/features/`. The
end-to-end handoff deletes a scenario only when both its unit and its integration replacements are
confirmed; this table is the integration half. "SPA half" names what no service test can see and
the Vitest component the design assigns it to.

| BDD scenario | Integration test (confirmed) | What it covers | SPA half, not covered here |
|---|---|---|---|
| channels: "A public channel name cannot be reused, whatever its case" | `src/services/messaging/tests/integration/test_channels.py::test_public_names_collide_regardless_of_case` (params `general`, `General`, `GENERAL`) and `::test_a_rejected_duplicate_leaves_one_channel` | 409 `conflict` Problem Details for every case; the list holds the channel exactly once | showing "already taken" — Vitest `CreateChannelDialog` |
| channels: "A channel admin renames a channel" | `test_channels.py::test_an_admin_renames_a_channel` and `::test_a_rename_is_what_the_next_read_returns` | 200 with the new name and bumped version; the list shows the new name and not the old | "Ada is looking at general-chat" — Vitest `ChannelHeader` |
| channels: "A rename is visible to everyone in the workspace" | `test_channels.py::test_a_rename_is_what_the_next_read_returns` | Grace's next `GET /channels` returns only `general-chat`. The scenario has Grace *open* CollabHub, and Messaging emits no rename event, so the next read is the whole behaviour | — |
| channels: "An admin archives a channel and it leaves the list" | `test_channels.py::test_an_admin_archives_a_channel_and_it_leaves_the_list` | 200 with `archivedAt`; the list is empty; the channel is then a 404 | Vitest `ChannelList` |
| messages: "Scrolling up loads older messages" | `test_pagination.py::test_the_walk_sees_every_message_exactly_once_newest_first` and `::test_a_message_sent_mid_walk_does_not_shift_the_pages` | 120 messages across three cursor pages: every one exactly once, newest first; a send mid-walk shifts nothing | triggering the next page on scroll — Vitest `MessageList` |
| messages: "A channel admin deletes another user's message" | `test_messages.py::test_a_channel_admin_deletes_another_users_message` | Ada, the channel admin, deletes Grace's message: 200 with `deletedAt` | tombstone rendering — Vitest `MessageItem` |
| messages: "A non-admin cannot delete someone else's message" | `test_messages.py::test_a_non_admin_cannot_delete_someone_elses_message`; over the socket, `test_realtime_writes.py::test_deleting_someone_elses_message_as_a_non_admin_acks_a_403` | 403 and the message unchanged in history | "Grace has no way to delete" (the control is hidden) — Vitest `MessageItem`, with unit `check_deletable` |
| realtime: "Grace does not receive messages for a channel she is not looking at" | `test_realtime.py::test_a_client_in_another_room_receives_nothing`, `::test_leaving_a_room_stops_the_broadcasts`; the scenario's last step (opening `general` shows it) is `test_messages.py::test_a_sent_message_comes_back_in_the_history` | a socket joined to `random` gets nothing for a send to `general`; leaving a room stops broadcasts | which room the SPA joins when a channel opens — Vitest |
| realtime: "A typing indicator appears for Grace and clears when Ada stops" | `test_realtime_writes.py::test_typing_reaches_the_room_but_not_the_sender` | `user_typing` with Ada's id reaches Grace and not Ada, and nothing is persisted | **"clears when Ada stops" has no server behaviour**: there is no `typing_stopped` event (`realtime_writes.py`, the `typing` handler's docstring), so clearing is the SPA's timeout — on `main` as Vitest `TypingIndicator.test.tsx` and `useTyping.test.ts` (plan 04). No integration test can be written for it |

---

## Proof each test can fail

Recorded below from `uv run python mutate.py mutants_*.py` — a scratch runner (session
scratchpad, not the repo) that applies a text replacement, runs
`uv run pytest -m integration -q <node ids>`, and restores the file. `git status --short` on the
source directories printed nothing afterwards. Each row: the break, then pytest's result.

### Worker — 12 mutants, 12 red

| Break (file: old → new) | Tests run | Result |
|---|---|---|
| `consumer.py`: `_complete` without `pipe.xack(...)` | `test_a_handled_job_is_acknowledged_and_leaves_the_pending_list` | **1 failed** in 15.93s (drain timed out, entry still pending) |
| `consumer.py`: `claimed = [... if fields]` → `claimed = []` | `test_a_transient_failure_is_retried_and_then_succeeds`, `test_an_entry_a_crashed_consumer_left_pending_is_reclaimed` | **2 failed** in 31.54s |
| `consumer.py`: `f"permanent:{exc}"` → `f"permanent:{exc.__cause__}"` | `test_a_permanent_error_is_dead_lettered_at_once_with_its_fixed_reason` | **1 failed** in 0.71s |
| `consumer.py`: `deliveries > max_attempts` → `> max_attempts + 1` | `test_a_job_that_keeps_failing_is_dead_lettered_after_max_attempts` | **1 failed** in 3.98s |
| `consumer.py`: unknown type's `_dead_letter(... "unknown-type" ...)` removed | `test_an_unknown_job_type_is_dead_lettered_on_first_delivery` | **1 failed** in 6.00s |
| `consumer.py`: `except ValidationError:` → `except KeyError:` | `test_a_malformed_envelope_is_dead_lettered_on_first_delivery` | **1 failed** in 15.72s |
| `handlers/messages.py`: `version=` and `version_type="external"` removed | upsert, older-version, stale-upsert-after-delete, delivered-twice | **4 failed** in 15.04s |
| `handlers/messages.py`: `if not deleted:` guard on `body` removed | tombstone, stale-upsert-after-delete | **2 failed** in 13.30s |
| `handlers/messages.py`: `PermanentJobError("invalid payload")` → `PermanentJobError(str(exc))` | `test_an_invalid_payload_is_dead_lettered_without_the_validation_text` | **1 failed** in 17.93s |
| `handlers/messages.py`: `exclude={"body", "version"}` → `exclude={"body"}` | `test_an_upsert_writes_the_document_at_the_messages_version` | **1 failed** in 12.37s |
| `index.py`: `aliases={MESSAGES_ALIAS: {}}` removed | `test_ensure_creates_the_versioned_index_behind_the_alias` | **1 failed** in 16.00s |
| `index.py`: `if exc.error != "resource_already_exists_exception":` removed | `test_ensuring_the_index_again_is_harmless` | **1 failed** in 11.64s |

The first row is what found call 3: with a one-second visibility timeout, a reclaim pass cleaned
the pending list after the missing `XACK` and the test passed on the broken code.

### Messaging — 16 mutants, 16 red (one after fixing its test)

| Break (file: old → new) | Test run | Result |
|---|---|---|
| `indexing.py`: delete enqueued as `MESSAGE_UPSERT` | `test_a_delete_enqueues_a_delete_with_the_body_redacted` | **1 failed** in 2.46s |
| `indexing.py`: `workspace_id=workspace_id` → `workspace_id=message.channel_id` | `test_a_sent_message_enqueues_an_upsert_carrying_the_whole_document` | **1 failed** in 2.32s |
| `indexing.py`: `except Exception` → `except ValueError` | `test_an_unreachable_stream_does_not_fail_the_write` | **1 failed** in 2.62s (unhandled exception, 500) |
| `main.py`: `JobQueue.from_url(settings.redis_streams_url)` → `redis_cache_url` | `test_redis_roles.py::test_index_jobs_go_to_the_streams_index` | **1 failed** in 2.55s |
| `main.py`: denylist client on `redis_streams_url` | `test_redis_roles.py::test_the_denylist_messaging_reads_is_the_cache_index` | **1 failed** in 2.35s |
| `realtime.py`: `AsyncRedisManager(redis_realtime_url` → `redis_cache_url` | `test_redis_roles.py::test_the_backplane_connects_on_the_realtime_index` | **1 failed** in 2.49s |
| `search.py`: `match` on `body` → `match_all` | `test_a_match_comes_back_as_the_message_itself` | **1 failed** in 15.73s |
| `search.py`: sort `desc` → `asc` | `test_results_are_newest_first_and_page_by_cursor` | **1 failed** in 14.65s |
| `search.py`: `hit_ids[: page.limit]` → `[: page.limit + 1]` | `test_results_are_newest_first_and_page_by_cursor` | **1 failed** in 18.73s |
| `search.py`: both visible-channel filters removed (ES `terms` and hydration `channel_id.in_`) | `test_a_private_channel_you_are_not_in_is_excluded` | first run **1 passed** — see below; after the fix **1 failed** in 37.36s |
| `search.py`: both channel filters and the `workspaceId` term removed | `test_another_workspaces_messages_are_excluded` | **1 failed** in 17.02s |
| `search.py`: hydration's `deleted_at IS NULL` removed | `test_a_message_deleted_after_it_was_indexed_is_not_returned` | **1 failed** in 12.65s |
| `search.py`: `index_not_found_exception` no longer an empty result | `test_before_anything_is_indexed_search_is_empty_not_an_error` | **1 failed** in 16.93s |
| `routers/search.py`: `service_unavailable(...)` → `ProblemException(500)` | `test_elasticsearch_being_down_is_a_503` | **1 failed** in 2.24s |
| `routers/search.py`: `max_length=MAX_QUERY_CHARS` → `+ 1` | `test_a_query_may_be_200_characters_but_not_201` | **1 failed** in 13.08s |
| `routers/search.py`: `if not query:` → `if query is None:` | `test_a_blank_query_is_a_400` | **1 failed** in 17.07s |

`git status --short src/services/messaging/messaging` printed nothing after each run.

**Multi-site breaks are deliberate.** Search applies the visible-channel filter twice — to the
Elasticsearch candidates and again at hydration — and the workspace term is a third line behind
both. Removing any one alone leaves the test green, correctly: that is defence in depth working.
The tenancy mutants remove every line that stands between a caller and another workspace's rows.

### What the mutation run changed in the tests

- **The private-channel test was passing for the wrong reason.** Grace could see no channel at
  all, so `search_messages` returned at `if not channel_ids` before any filter ran. The test now
  creates a public channel Grace can see first; the mutant then fails it.
- **`test_a_tombstone_in_the_index_is_not_returned` was deleted.** A tombstone has no `body`, so
  no query can match it whatever Messaging's filters do; no break in Messaging's code could make
  it fail. What it meant to pin is the Worker's tombstone, which
  `test_message_index.py::test_a_delete_leaves_a_tombstone_with_no_body` proves.
- **Not provable by a one-line break:** `test_the_body_shown_is_postgres_not_the_index` (search
  would have to return the index's text, which it never fetches — `"source": False`) and Auth's
  `test_a_login_in_progress_is_kept_on_the_cache_index` (Auth has only one Redis URL to get
  wrong). Both stay as guards against a redesign.
