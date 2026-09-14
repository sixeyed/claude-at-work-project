# CollabHub — Worker Service

> Headless background processor: indexing, thumbnails, notifications, exports, retention.
> Read [Platform Conventions](./00-platform-conventions.md) first.

**Status:** Draft · **Runtime:** Python 3.12 worker (headless asyncio, no HTTP except health)
**Owns:** all async job processing + the Elasticsearch index lifecycle
**Depends on:** Redis Streams (R3), Elasticsearch, Garage, Auth (service tokens) — **no PostgreSQL**

---

## 1. Purpose & Responsibilities

A headless Python worker that consumes jobs from **Redis Streams (R3)** and does the heavy,
non-interactive work. Scales horizontally via **KEDA** based on stream depth.

**Owns:**
- Consuming all `jobs:*` streams (Conventions §7).
- The **Elasticsearch index lifecycle**: mappings, aliases, reindexing, and writes. ES is
  write-only from the Worker; services read from ES directly (or via a search gateway).
- Image thumbnailing/optimisation (Pillow).
- Notification dispatch.
- Export generation (canvas → PNG/SVG/PDF).
- Data retention / cleanup sweeps.

**Does NOT:** serve user requests, or touch any service's database in either direction. Data
arrives in the job payload or through the owning service's internal endpoint (§5.2).

---

## 2. Runtime & Dependencies
- A long-running **asyncio** process; one supervised consumer coroutine per job type
  (no web framework for business logic).
- `redis-py` (`redis.asyncio`) for R3 consumer groups (`XREADGROUP` / `XAUTOCLAIM`).
- `elasticsearch` (the async `elasticsearch-py` client) for ES.
- `Pillow` for image work.
- The shared S3-compatible `ObjectStore` (boto3) for Garage, reused from `collabhub-shared`
  — not built yet; `shared` currently carries Problem Details, UUID v7, token verification,
  the denylist, cursor pagination and CORS.
- `httpx` for internal calls to owning services. **No SQLAlchemy and no database driver** —
  🟢 **Decided 2026-07-27 (register D25):** the Worker connects to no service database. See §5.2.
- Exposes only `/health/live` and `/health/ready` (Conventions §10) via a minimal
  Starlette/FastAPI health app; no business HTTP.

---

## 3. Interface — Jobs Consumed

All jobs use the Conventions §7 envelope. One consumer group `worker` per stream; handlers keyed
by `type`.

| Stream | `type` | Payload | Handler action |
|--------|--------|---------|----------------|
| `jobs:index` | `message.upsert` / `message.delete` | `{ messageId, channelId, workspaceId, authorId, body, createdAt, version, op }` | Build the ES document from the payload alone and upsert/delete in `messages`. |
| `jobs:index` | `document.index` | `{ documentId, workspaceId, name, textProjection, version }` | Index canvas text projection (if canvas search enabled). |
| `jobs:index` | `asset.index` | `{ assetId, workspaceId, fileName, contentType, ownerId, createdAt, version }` | Index file metadata for file search. |
| `jobs:thumbnail` | `thumbnail.generate` | `{ assetId, objectKey, variants[] }` | Fetch from Garage, generate variants (Pillow), store back, report variants to Asset svc. |
| `jobs:notify` | `notify.dispatch` | `{ userId, kind, data }` | Resolve the recipient via Auth's internal endpoint, then deliver. (Auth has no such endpoint yet — see §9.) |
| `jobs:export` | `canvas.export` | `{ documentId, format, requestedBy }` | Fetch state from `GET /internal/documents/{id}/state`, render, store in Garage, notify requester. |
| `jobs:retention` | `retention.sweep` | `{ scope }` | Call the owning service's internal sweep endpoint — `POST /internal/messages/sweep`, `/internal/documents/sweep`, `/internal/assets/sweep`. The Worker deletes nothing itself. |

🟢 **Decided 2026-07-27 (register D25).** Index payloads carry the whole document rather than
an identifier, because the producer already holds it and the read-back would land on the
busiest path in the system. `version` is a monotonic value from the source row, used as the
Elasticsearch external version so a late-arriving older document is rejected instead of
applied — without it, two rapid edits can be indexed out of order. `messages.version` exists
for exactly this (Messaging doc §4) and is bumped on every edit and delete. See the
[ADR](../adr/260727-worker-never-reads-service-databases.md).

The Worker emits no events of its own except results delivered back through owning services
(e.g. Asset `POST /assets/{id}/variants`) or notifications.

---

## 4. Elasticsearch Index Design

Worker owns mappings + aliases. Read-side queries (from Messaging/SPA) hit the aliases.

| Alias | Doc shape (key fields) | Source |
|-------|------------------------|--------|
| `messages` | `messageId, channelId, workspaceId, authorId, body, createdAt` | `jobs:index` |
| `files` | `assetId, workspaceId, fileName, contentType, ownerId, createdAt` | `jobs:index` |
| `canvas` | `documentId, workspaceId, name, textProjection, updatedAt` | `jobs:index` (if enabled) |

- Use index-per-alias with date or version suffix to allow zero-downtime reindex
  (`messages-v1` ← alias `messages`).
- Analyzer: standard + edge-ngram field for autocomplete on names/file names.
- Reindex is a maintenance job (manual trigger or a `jobs:index` `reindex` type).

---

## 5. Internal Design

### 5.1 Consumer loop (per stream)
1. `XREADGROUP GROUP worker {consumer} COUNT n BLOCK m STREAMS jobs:x >`.
2. For each entry: parse envelope, dispatch by `type`, run handler **idempotently** (keyed on
   `jobId`/natural key).
3. On success `XACK`. On handler exception, do **not** ack; increment `attempt` on reclaim.
4. Periodically `XAUTOCLAIM` stale pending entries (crashed consumers) past the visibility
   timeout. After `maxAttempts` (5), `XADD` to `jobs:x:dead` and `XACK` the original.

Each consumer runs as its own asyncio task; CPU-heavy handlers (thumbnail/export) offload the
blocking work to a thread/process pool so they don't stall the event loop.

### 5.2 Data access rule
The Worker touches no service database, in either direction. Everything a handler needs
arrives one of two ways:

- **In the job payload**, where the producing service already held it — index jobs carry the
  full document (§3).
- **From the owning service's internal endpoint**, where it could not travel in the payload —
  too large (canvas state), too live (a user's notification address), or a deletion that only
  the owner should perform. These calls are authenticated with a **service token**
  (Conventions §5.5), which is the same mechanism as the variant write-back.

Results that must update a service's database follow the same rule: call the internal
endpoint, e.g. `POST /api/v1/internal/assets/{id}/variants` with scope
`assets:write-variants`. Retention inverts — the Worker calls each service's internal sweep
endpoint and that service deletes its own rows.

ES and Garage are shared infrastructure the Worker is authorized to write directly.

🟢 **Decided 2026-07-27 (register D14)** — internal endpoint, not an event and not a direct
write. See the [ADR](../adr/260727-service-tokens-for-internal-calls.md). Note this makes
Auth a runtime dependency of the Worker: fetch a token at startup and refresh before expiry,
retrying with backoff. A job whose write-back fails is left unacked and reclaimed, so an
Auth outage delays processing rather than losing work.

🟢 **Decided 2026-07-27 (register D25)** — the read side follows the same shape, and the
Worker gets no database connection at all. That widens the Auth coupling above: notification
and export handlers now need a service token too, so an Auth outage delays more of the
Worker's surface. The failure mode is unchanged — delay, not loss. See the
[ADR](../adr/260727-worker-never-reads-service-databases.md).

### 5.3 Scaling (KEDA)
🟢 **Decided 2026-09-14 (register D17)** — two pools, split on latency. See the
[ADR](../adr/260914-worker-pools-split-on-latency.md).

| Pool | Streams | Replicas |
|------|---------|----------|
| `notify` | `jobs:notify` | 1 → N. The floor holds the < 5 s p95 target (§8) |
| `batch` | `jobs:index`, `jobs:thumbnail`, `jobs:export`, `jobs:retention` | 0 → N |

Each pool is its own Deployment with `WORKER_STREAMS` set to its streams, and its own
`ScaledObject` with one Redis Streams trigger per stream on **`lagCount`** for consumer group
`worker`. **Corrected 2026-09-14 — this section said `pendingEntriesCount`**, which counts
entries a consumer has read and not acked. With zero pods nothing is read, so the count never
leaves 0 and a pool at zero never wakes. Lag is what the group has not yet read; it is the only
Redis Streams metric KEDA can scale from zero on, and needs Redis 7+.

The split is on latency, not the CPU/IO axis this doc first suggested, because one Deployment
cannot both scale to zero and hold a notify floor. Splitting `batch` by CPU/IO later needs no
code change — only another pool.

**Consumer groups must exist before a producer writes to their stream.** The Worker does not
create them yet, and no service produces jobs yet either, so today this is silent: KEDA (v2.20.1)
reads a missing stream as lag `0` with no error, so `batch` correctly sits at zero. **Corrected
2026-09-14** — the earlier version of this paragraph said the triggers error and the fallback
holds each pool at one replica until the groups exist; that is not what the scaler does. A
missing *group* on a stream that already exists is also not an error — KEDA reads `XLEN` as the
lag instead, so if a producer ships before the Worker creates its groups, the affected pool scales
to its max and nothing drains it, because no consumer is reading. The fallback's real job is
covering Redis being unreachable or the trigger's auth failing, not a missing group. Consumer
groups must therefore be created before, or in the same slice as, the first producer for their
stream — from ID `0`, `XGROUP CREATE <stream> worker 0 MKSTREAM` — so the lag KEDA measures
matches what's already in the stream.

---

## 6. Configuration
Common vars (Conventions §8). Plus:

| Var | Notes |
|-----|-------|
| `ELASTICSEARCH_URL` | ES endpoint. |
| `WORKER_STREAMS` | Which streams this deployment consumes. Set per pool by the chart — `notify` and `batch` (§5.3, register D17); defaults to every stream for a single local/Compose process. |
| `WORKER_MAX_ATTEMPTS` | Default 5. |
| `WORKER_VISIBILITY_TIMEOUT_SECONDS` | Reclaim threshold. |
| `WORKER_BATCH_SIZE` | `COUNT` per read. |
| `RETENTION_MESSAGE_DAYS` / `RETENTION_ASSET_PENDING_HOURS` / etc. | Retention policy knobs. |
| `NOTIFY_*` | Provider config for push/email. |

## 7. Cross-Cutting
No inbound auth (no business HTTP); uses a **service token** for outbound internal calls.
Trace continuity: read `traceId` from the job envelope and continue the span (Conventions §9).
Metrics: `jobs_processed_total{type,result}`, `jobs_dead_total{stream}`, handler duration
histograms, ES bulk latency.

## 8. Non-Functional & Limits
- Every handler idempotent and safe to retry.
- No user-facing latency contract except `jobs:notify` (target < 5 s p95).
- Back-pressure handled by stream depth + KEDA, never by dropping jobs.
- Poison messages land in `*:dead` for inspection, never block the stream.
- Index payloads now carry message bodies, so `jobs:index` and `jobs:index:dead` hold user
  content. Set `MAXLEN` trimming deliberately rather than by default, and treat dead-letter
  retention and access as handling user data (register D25).

## 9. Open Decisions
- ~~**Whether the Worker reads service databases**~~ — 🟢 **Decided 2026-07-27 (register
  D25).** It does not. Fat job payloads plus internal endpoints. See §5.2 and the
  [ADR](../adr/260727-worker-never-reads-service-databases.md).
- ~~**Specialised worker pools**~~ — 🟢 **Decided 2026-09-14 (register D17).** Two pools,
  `notify` and `batch`, split on latency. See §5.3 and the
  [ADR](../adr/260914-worker-pools-split-on-latency.md).
- Notification channels in scope for v1 (in-app only vs. push + email).
- Whether canvas search (`canvas` index) ships in v1 — depends on Canvas producing a text
  projection.
- ~~Result write-back mechanism~~ — 🟢 **Decided 2026-07-27:** internal endpoint + service
  token. See §5.2.
- Export rendering engine for canvas (headless renderer / server-side Yjs via `pycrdt` + skia) —
  non-trivial; may defer.
- **The internal endpoints this Worker depends on do not exist yet.** `jobs:notify` needs a way
  to resolve a recipient's notification address from Auth, and every `retention.sweep` scope
  needs its owning service's sweep endpoint. They are specified in each service's §3 but
  unbuilt, so those handlers cannot ship before them.
- **Consumer-group creation must land before, or alongside, the first producer of any given
  stream** (§5.3) — create each stream's group from ID `0` (`XGROUP CREATE <stream> worker 0
  MKSTREAM`) as part of the same slice that starts writing to it, not after. A producer that
  ships first leaves KEDA reading `XLEN` as lag with no consumer group to drain it, pinning that
  pool at its max replica count.
