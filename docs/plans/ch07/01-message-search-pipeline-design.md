# Message search pipeline — design

**Status:** Approved in brainstorming, 2026-09-14 · **Branch:** `feature/message-search-pipeline`
**Touches:** Messaging (producer + search route), Worker (consumer + index), `shared`, `contracts`

## Context

Messaging writes messages and broadcasts them; nothing indexes them. Doc 02 §5 left the
`jobs:index` producer out on purpose because no Worker read the stream, and doc 02 §3.1.5
lists `GET /search/messages` as unbuilt for the same reason. The Worker is a skeleton that
serves health checks and consumes nothing. `contracts` is empty; the job envelope does not
exist yet.

This slice builds message search **out of band from the message flow**: Messaging enqueues
after commit and never waits, the Worker populates Elasticsearch, and Messaging serves a
search endpoint that reads the index. No SPA UI.

### Decisions taken while designing

| Question | Answer |
|---|---|
| Scope | Write side **plus** `GET /api/v1/search/messages`. No UI |
| Enqueue fails after commit (R3 down) | Fire-and-forget, as Conventions §7 says: the write succeeds, the failure is logged and swallowed. Index drift is accepted until a reindex path exists (new 🔴 register row) |
| Deleted message in ES | **Tombstone document** at the bumped version, `body` removed, `deleted: true` — not a hard delete, because ES forgets a deleted doc's version after `index.gc_deletes` (~60 s) and a late stale upsert would resurrect the text |
| Result ordering | **Newest first**: sort `messageId` desc, `search_after` cursor — the same keyset shape as history |
| Existing Messaging integration fixture | One-line edit adding a placeholder `elasticsearch_url`. No new tests (CLAUDE.md) |

### Out of scope

A search UI; searching files or canvas (`files`/`canvas` aliases, D12 🔴); reindex/backfill;
highlighting; per-channel search filter; structlog/OpenTelemetry setup (still unbuilt in
`shared`, stdlib `logging` as the rest of Messaging uses today); other Worker streams.

---

## 1. Components

| Unit | Location | Purpose | Depends on |
|---|---|---|---|
| Job envelope + queue | `shared/jobs.py` | `JobEnvelope` (Conventions §7.1) and `JobQueue.enqueue(stream, type, payload)` — one `XADD` of a single `data` field | `redis.asyncio`, `shared.uuid7` |
| Index contracts | `contracts/indexing.py` | `JOBS_INDEX = "jobs:index"`, `MESSAGES_ALIAS = "messages"`, job types `message.upsert` / `message.delete`, `MessageIndexPayload` (camelCase) | `pydantic` |
| Producer | `messaging/indexing.py` | Build a payload from a committed `Message` + workspace id and enqueue it; swallow and log failure | `shared.jobs`, `contracts.indexing` |
| Visible channel ids | `messaging/channels.py` — `visible_ids()` | `_visible_query` selecting ids only | existing |
| Search domain | `messaging/search.py` | Build + run the ES query, hydrate hits from Postgres | ES async client, `channels`, `messages` |
| Search route | `messaging/routers/search.py` | `GET /api/v1/search/messages` | `search`, `require_user`, `PageParams` |
| Stream consumer | `worker/consumer.py` | Generic read / ack / reclaim / dead-letter loop per stream, handlers by `type` | `redis.asyncio`, `shared.jobs` |
| Index lifecycle | `worker/index.py` | Ensure `messages-v1` + alias `messages` at startup; mapping | ES async client |
| Index handler | `worker/handlers/messages.py` | `message.upsert` / `message.delete` → ES external-versioned write | `worker/index.py`, `contracts.indexing` |

A new dependency: `elasticsearch[async]` (9.x, matching the 9.4.3 server) in Messaging and
Worker, pinned per service.

---

## 2. Write path

### 2.1 Producer (Messaging)

`messaging/indexing.py` exposes `enqueue_upsert(queue, message, workspace_id)` and
`enqueue_delete(queue, message, workspace_id)`. They are called at all **six** write sites —
`routers/messages.py` send/edit/delete and `realtime_writes.py` send/edit/delete — immediately
after the existing `realtime.publish_*` call. Order everywhere: **commit → broadcast →
enqueue.**

- **`workspaceId` comes from the principal's `wsp` claim.** `messages` has no workspace
  column; the visibility check already proved the channel is in that workspace.
- **Payload:** `{messageId, channelId, workspaceId, authorId, body, createdAt, version}` from
  the committed row. `message.delete` sends **`body: ""`** so R3 never carries text a user
  asked to remove. Doc 05 §3's `op` field is dropped: the envelope `type` already says
  upsert or delete, and two fields that can disagree is one too many. Doc 05 is updated.
- **Repeat deletes enqueue nothing.** `messages.delete` returns an existing tombstone without
  bumping `version` (doc 02 §3.1.4); the producer only enqueues when this call performed the
  delete. `messages.delete` returns `DeleteResult(message, deleted_now: bool)` instead of a
  bare `Message | None` — a return-shape change at its two callers, not a new query.
- **Failure:** any exception from `enqueue` is caught, logged at `warning` with `messageId`
  and the exception class (never the body), and swallowed. The client's write has already
  succeeded. The queue's Redis client uses ~1 s connect and socket timeouts, so an R3 outage
  costs a write about a second rather than hanging it.
- **Wiring:** a `JobQueue` over `REDIS_STREAMS_URL` is built in `create_app`, hung on
  `app.state.jobs`, closed in `lifespan`; the socket handlers get it through
  `RealtimeContext`. Unlike `app.state.realtime` it is real under the integration suite, whose
  fixture already points `redis_streams_url` at the test Redis container — so those tests
  enqueue into a throwaway stream and assert nothing about it.

### 2.2 Job envelope

```json
{ "jobId": "<uuid7>", "type": "message.upsert", "version": 1,
  "occurredAt": "2026-09-14T10:15:00Z", "attempt": 1, "payload": { ... } }
```

`attempt` is written as `1` by producers and is **informational only**: stream entries are
immutable, so the Worker's authoritative attempt count is Redis's delivery count (§2.3).
`traceId` is omitted until OpenTelemetry lands in `shared`.

### 2.3 Consumer (Worker)

One asyncio task per stream in `WORKER_STREAMS`, run under `asyncio.gather` beside the health
server in `worker.main.run`.

1. **Startup:** `XGROUP CREATE <stream> worker 0 MKSTREAM`, treating `BUSYGROUP` as success.
   The Worker **refuses to start** if a configured stream has no registered handlers.
2. **Read:** `XREADGROUP GROUP worker <consumer> COUNT WORKER_BATCH_SIZE BLOCK <ms> STREAMS
   <stream> >`. Consumer name is the hostname (pod name) so a restarted pod's pending entries
   are reclaimed rather than orphaned under a name nobody uses.
3. **Dispatch:** parse the envelope; look up the handler by `type`. A malformed envelope or an
   unknown type is **dead-lettered immediately** — retrying cannot fix it.
4. **Success:** `XACK` then `XDEL`. Deleting acked entries keeps user-authored bodies out of
   R3 without a producer-side `MAXLEN`, which could drop unread jobs during a Worker outage.
5. **Failure:** log `jobId`, `type`, exception class; leave the entry pending.
6. **Reclaim:** a periodic `XAUTOCLAIM` with `min-idle-time = WORKER_VISIBILITY_TIMEOUT_SECONDS`
   re-delivers stale entries. Before running a reclaimed entry, its delivery count (from
   `XPENDING` extended form) is compared to `WORKER_MAX_ATTEMPTS`; a job runs at most that many
   times, and a delivery beyond it is dead-lettered instead of run.
7. **Dead-letter:** `XADD <stream>:dead` with the original `data` plus `error` (a short fixed
   reason, no message text) and `deliveries`, capped with an approximate `MAXLEN` of
   `WORKER_DEAD_LETTER_MAXLEN` (default 10 000) because it holds user content, then `XACK` +
   `XDEL` the original.
8. **Shutdown:** on SIGTERM stop reading new entries, let in-flight handlers finish, exit.
   Anything unfinished stays pending and is reclaimed by the next consumer.

### 2.4 Index lifecycle and handler (Worker)

**At startup**, before consumers start: create `messages-v1` if absent and add alias
`messages` → `messages-v1`. `resource_already_exists_exception` is success, so concurrent
replicas cannot fail each other.

**Mapping** (`dynamic: strict`):

| Field | Type |
|---|---|
| `messageId`, `channelId`, `workspaceId`, `authorId` | `keyword` |
| `body` | `text` (standard analyzer) |
| `createdAt` | `date` |
| `deleted` | `boolean` |

**Handler:** `index(index="messages", id=messageId, version=payload.version,
version_type="external", document=...)`.

- `message.upsert` → the document with `deleted: false`.
- `message.delete` → the same identifiers with **no `body`** and `deleted: true`.
- **A `version_conflict_engine_exception` (409) is success.** It means the index already holds
  this version or a newer one, which covers both duplicate delivery and out-of-order arrival
  with one mechanism and no `jobId` bookkeeping.
- Any other ES error or a connection failure raises → the job stays pending → retried.
  Delayed, not lost.

The index handler needs **no service token**, so this slice adds no Auth dependency to the
Worker.

---

## 3. Search endpoint (Messaging)

### 3.1 Contract

`GET /api/v1/search/messages?q=&limit=&cursor=` · `Depends(require_user)` · not in the
fail-closed denylist set.

- `q`: required, 1–200 characters after trimming; missing or blank → 400 `validation-error`
  with `errors.q`.
- `limit`, `cursor`: `PageParams` (default 50, max 200).
- Response: `MessageListResponse` — `{items: MessageResponse[], nextCursor}`.

### 3.2 Authorization happens at query time

`channels.visible_ids(session, workspace_id=principal.workspace_id, user_id=principal.user_id)`
returns every channel id the caller can see — public channels in the workspace plus private
channels they are a member of, archived excluded — using the same `_visible_query` every other
route uses. If it is empty, return an empty page without calling ES.

Because the filter is computed per request, removing someone from a private channel or
archiving a channel takes effect in search immediately; nothing in the index needs rewriting.
(`terms` accepts up to `index.max_terms_count`, 65 536 by default — far above a workspace's
channel count; noted in doc 02 rather than guarded.)

### 3.3 Query

```json
{
  "size": "<limit + 1>",
  "query": { "bool": {
    "must":   [{ "match": { "body": { "query": "<q>", "operator": "and" } } }],
    "filter": [
      { "term":  { "workspaceId": "<wsp claim>" } },
      { "terms": { "channelId": ["<visible ids>"] } },
      { "term":  { "deleted": false } }
    ]
  }},
  "sort": [{ "messageId": "desc" }],
  "search_after": ["<decoded cursor id>"],
  "_source": false
}
```

- `match` with `operator: and` — every word must match; no query syntax is exposed to users.
- UUID v7 is fixed-length lowercase hex, so `messageId` descending on a `keyword` is newest
  first. `search_after` is omitted on the first page.
- `nextCursor` is `encode_cursor(<id of hit number limit>)` when ES returned `limit + 1` hits,
  else `null`.

### 3.4 Hydration from Postgres

ES supplies an **ordered list of candidate ids** and nothing else. Messaging loads those rows:

```python
select(Message).where(
    Message.id.in_(ids),
    Message.channel_id.in_(visible_ids),
    Message.deleted_at.is_(None),
)
```

…and returns them in ES order as `MessageResponse`.

- **Index lag cannot leak text.** A message deleted a moment ago whose tombstone has not been
  indexed is dropped here.
- **One DTO.** Items are the `MessageResponse` the SPA already renders, with current body,
  `editedAt` and `version` — not a second, drifting shape.
- **ES is never the authority** for who may see what; it narrows candidates.

**Consequence: a page may hold fewer than `limit` items** when hydration drops rows.
`nextCursor` is still taken from the ES hits, so no result is skipped. Only
`nextCursor: null` means the end. This is stated in the route docstring and in doc 02.

`deleted_at IS NULL` is correct here and is *not* the history exception: search does not
return tombstones. It also satisfies CH009.

### 3.5 Failure modes

| Condition | Response |
|---|---|
| ES unreachable, timeout, or 5xx | 503 `ProblemException.service_unavailable("Search is unavailable.")` — nothing from ES in `detail` |
| `index_not_found_exception` (Worker has never started) | Empty page, 200 |
| Malformed cursor | 400, via `decode_cursor` |

ES is **not** added to Messaging's `/health/ready`: an ES outage degrades search and must not
take chat out of rotation.

---

## 4. Configuration

| Var | Service | Where | Notes |
|---|---|---|---|
| `ELASTICSEARCH_URL` | Messaging (new) | `Settings`, `docker-compose.yml`, chart secret comment | Required. `.env.example` comment becomes "written by the Worker, read by Messaging" |
| `WORKER_STREAMS` | Worker | `Settings` default, compose, chart `values.yaml` | Becomes `jobs:index` — only streams with handlers |
| `WORKER_DEAD_LETTER_MAXLEN` | Worker (new) | `Settings`, compose, `.env.example`, chart | Default 10 000; approximate cap on `<stream>:dead` |

Messaging's async ES client is built in `create_app`, hung on `app.state.search`, and closed
in `lifespan`. The Worker's is built in `run` and closed on shutdown.

The Messaging integration fixture gains `"elasticsearch_url": "http://localhost:9200"` in
`build_settings`. The client connects lazily, so no container starts and nothing new is
asserted.

After the route exists: `python -m messaging.openapi > src/frontend/openapi/messaging.json`,
then `npm run generate:api` (D23). Types only; no UI.

---

## 5. Decisions and documentation, in this slice

**ADR** (`adr-writer`): *the message search index is a candidate list, not a source of truth*
— tombstone documents, query-time channel filtering, and Postgres hydration, recorded
together because each relies on the others.

**Register (`07-open-decisions-register.md`)**

- D8c stays 🟡 (thin proxy in Messaging) with a "Built against it 2026-09-14" note; remove the
  "neither exists" text.
- D25: correct the stale "`messages` has no `version` column yet"; note the producer exists.
- New row, 🔴: **reindex / backfill path for search** — fire-and-forget means an index that
  drifts during an R3 outage stays wrong until one exists. Scope Worker + Messaging.

**Conventions §7** — `attempt` in the envelope is informational; retries count Redis delivery
count; acked entries are `XDEL`ed; unknown types and malformed envelopes dead-letter
immediately.

**Doc 02** — §1 and §5 step 4 lose "not built"; §3.1.5 loses the search row; new §3.1.6
search semantics (visibility at query time, hydration, short pages, 503, terms limit); §4.1 R3
note; §6 adds `ELASTICSEARCH_URL`.

**Doc 05** — §3 `message.delete` writes a tombstone; §4 the concrete mapping and
`dynamic: strict`; §5.1 delivery count, `XDEL`, refuse streams without handlers, consumer name;
§6 `WORKER_STREAMS` default; §8 the trimming answer.

**Code docstrings** — `shared/__init__.py` (the envelope has arrived), `contracts/__init__.py`,
`worker/main.py` (no longer "no consumer groups are read"); Messaging README gains search.

---

## 6. Verification

No new tests (CLAUDE.md).

1. `ruff check` / `ruff format`, the lint hook, and `python3 .claude/hooks/checks/conventions.py`
   over changed files — CH001 (workspace from claim), CH006, CH007, CH008, CH009 in particular.
2. Existing suites still pass: `uv run pytest -m "not integration and not bdd"` and
   `uv run pytest src/services/messaging`.
3. Manual, against `docker compose up -d --build`:
   - Send, edit, delete in the SPA. `curl localhost:9200/messages/_doc/<id>` shows the
     upsert, the bumped `_version`, then a tombstone with no `body`.
   - `GET /api/v1/search/messages?q=` (via `api.http`) finds a message; a non-member cannot
     find a private channel's message; a deleted message stops appearing.
   - `docker compose stop worker`, send several messages, `start worker`: search catches up
     and `XLEN jobs:index` returns to 0.
   - `docker compose stop elasticsearch`: search returns 503, sending still works, jobs stay
     pending; start ES and they drain.
   - Publish a job with an unknown `type` via `redis-cli XADD`: it lands in `jobs:index:dead`.
