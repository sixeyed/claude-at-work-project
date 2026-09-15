# Message Search Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Two project rules override those skills:** write **no tests** of any kind, and **never
> commit** — leave the worktree dirty (CLAUDE.md, "Working in this repo"). Where a skill says
> "write the failing test" or "commit", this plan says "verify" and "leave uncommitted".

**Goal:** Messaging enqueues every message write onto `jobs:index`; the Worker indexes it into
Elasticsearch out of band; Messaging serves `GET /api/v1/search/messages` from that index.

**Architecture:** Commit → broadcast → fire-and-forget `XADD` in Messaging. A generic Redis
Streams consumer in the Worker (read / ack+del / reclaim / dead-letter) dispatches by job
`type` to an index handler that writes with ES external versioning; deletes write tombstone
documents. The search route asks ES for ordered candidate ids, filtered by the channels the
caller can see right now, and hydrates them from Postgres.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, `redis.asyncio` (redis-py 8.0.1),
`elasticsearch[async]` 9.x (server 9.4.3), pydantic v2, uv workspace, ruff.

**Spec:** `docs/plans/ch07/01-message-search-pipeline-design.md`

## Global Constraints

- No new tests; no commits. The only test-tree edits allowed are the two placeholder
  `elasticsearch_url` lines in Task 6.
- Worktree: `/Users/elton/scm/manning/caw-search-pipeline`, branch `feature/message-search-pipeline`.
- Stream `jobs:index`; consumer group `worker`; dead-letter stream `jobs:index:dead`.
- Job types `message.upsert` and `message.delete`. Payload fields (camelCase on the wire):
  `messageId, channelId, workspaceId, authorId, body, createdAt, version`. No `op`.
- Index `messages-v1`, alias `messages`, mapping `dynamic: strict`.
- `WORKER_STREAMS` default `jobs:index`. `WORKER_MAX_ATTEMPTS` 5 means a job **runs at most 5
  times**; the 6th delivery is dead-lettered. `WORKER_DEAD_LETTER_MAXLEN` default 10000.
- Search: `q` 1–200 characters after trimming; sort `messageId` desc; `search_after`; results
  hydrated with `deleted_at IS NULL`; ES failure → 503 `"Search is unavailable."`; missing
  index → empty page. ES is not in Messaging's readiness checks.
- Workspace id always from `principal.workspace_id`; never a request parameter named
  `workspace_id` (CH001). Never log a message body (CH008). Log exception *class names*, not
  exception text, for ES and Redis failures.
- After every Python edit the lint hook runs `ruff`; fix anything it blocks on.

## File map

| File | Change | Responsibility |
|---|---|---|
| `src/services/shared/shared/jobs.py` | create | `JobEnvelope`, `JobQueue`, `JOB_DATA_FIELD` |
| `src/services/shared/shared/__init__.py` | modify | export the above; docstring |
| `src/services/contracts/contracts/indexing.py` | create | stream, alias, job type names, `MessageIndexPayload` |
| `src/services/contracts/contracts/__init__.py` | modify | export; docstring |
| `src/services/worker/worker/consumer.py` | create | `StreamConsumer`, `ConsumerConfig`, `Handler`, `PermanentJobError` |
| `src/services/worker/worker/index.py` | create | `messages-v1` mapping, `ensure_messages_index` |
| `src/services/worker/worker/handlers/__init__.py` | create | `build_handlers(es)` registry by stream |
| `src/services/worker/worker/handlers/messages.py` | create | `message.upsert` / `message.delete` handlers |
| `src/services/worker/worker/settings.py` | modify | `WORKER_STREAMS` default, `WORKER_DEAD_LETTER_MAXLEN` |
| `src/services/worker/worker/main.py` | modify | run consumers beside health, graceful drain |
| `src/services/worker/pyproject.toml` | modify | `elasticsearch[async]` |
| `src/services/messaging/messaging/indexing.py` | create | producer + `queue` dependency |
| `src/services/messaging/messaging/messages.py` | modify | `DeleteResult` |
| `src/services/messaging/messaging/routers/messages.py` | modify | enqueue at three sites |
| `src/services/messaging/messaging/realtime.py` | modify | `RealtimeContext.jobs` |
| `src/services/messaging/messaging/realtime_writes.py` | modify | enqueue at three sites |
| `src/services/messaging/messaging/channels.py` | modify | `visible_ids` |
| `src/services/messaging/messaging/search.py` | create | ES query + hydration |
| `src/services/messaging/messaging/routers/search.py` | create | `GET /api/v1/search/messages` |
| `src/services/messaging/messaging/main.py` | modify | build/close `JobQueue` + ES client, include router |
| `src/services/messaging/messaging/settings.py` | modify | `elasticsearch_url` |
| `src/services/messaging/messaging/openapi.py` | modify | placeholder `elasticsearch_url` |
| `src/services/messaging/pyproject.toml` | modify | `elasticsearch[async]` |
| `src/services/messaging/tests/conftest.py`, `tests/test_health.py` | modify | one placeholder line each |
| `docker-compose.yml`, `.env.example`, `charts/collabhub/values.yaml` | modify | config |
| `src/frontend/openapi/messaging.json`, `src/frontend/src/types/messaging.ts` | regenerate | D23 |
| `docs/adr/260914-*.md` | create | ADR via `adr-writer` |
| `docs/design/00-…`, `02-…`, `05-…`, `07-…`, `src/services/messaging/README.md`, worker `main.py` docstring | modify | decisions recorded in this slice |

---

### Task 1: Job envelope and queue in `shared`

**Files:**
- Create: `src/services/shared/shared/jobs.py`
- Modify: `src/services/shared/shared/__init__.py`

**Interfaces:**
- Produces: `JOB_DATA_FIELD: str = "data"`;
  `class JobEnvelope(BaseModel)` with fields `job_id: uuid.UUID` (alias `jobId`),
  `job_type: str` (alias `type`), `version: int`, `occurred_at: datetime`, `attempt: int`,
  `payload: dict[str, Any]`; `JobEnvelope.new(job_type: str, payload: BaseModel) -> JobEnvelope`;
  `JobEnvelope.encode() -> str`; `JobEnvelope.decode(raw: str | bytes) -> JobEnvelope`
  (raises `pydantic.ValidationError`);
  `class JobQueue` with `JobQueue(client: redis.asyncio.Redis)`,
  `JobQueue.from_url(url: str, *, timeout_seconds: float = 1.0) -> JobQueue`,
  `async enqueue(stream: str, job_type: str, payload: BaseModel) -> JobEnvelope`,
  `async aclose() -> None`.

- [ ] **Step 1: Create `shared/jobs.py`**

```python
"""The job envelope and the producer half of Redis Streams (Conventions §7).

Every stream entry has one field, `data`, holding this envelope as JSON. The
envelope is generic — `payload` is a plain dict here — and the typed payload
models live in `collabhub-contracts`, beside the stream names both sides agree
on. `shared` knows how a job travels; `contracts` knows what a job says.

**`attempt` is informational.** Producers write `1` and nothing ever rewrites
it: a stream entry is immutable once added, so the Worker counts retries with
Redis's own delivery count instead. The field stays because Conventions §7.1
names it and a reader of a dead-lettered entry should not find it missing.

**The producer never blocks on the Worker, and must not block on Redis either.**
`from_url` sets short socket timeouts, so an unreachable R3 costs a write about
a second and an exception the caller logs and swallows — not a request that
hangs until the client gives up.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as aioredis
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from shared.ids import uuid7

#: The single field every stream entry carries (Conventions §7.1).
JOB_DATA_FIELD = "data"

#: Envelope schema version — not the source row's version, which is payload.
ENVELOPE_VERSION = 1


class JobEnvelope(BaseModel):
    """Conventions §7.1, camelCase on the wire."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    job_id: uuid.UUID
    # `type` on the wire; `job_type` in Python so no attribute shadows a builtin.
    job_type: str = Field(alias="type")
    version: int = ENVELOPE_VERSION
    occurred_at: datetime
    attempt: int = 1
    payload: dict[str, Any]

    @classmethod
    def new(cls, job_type: str, payload: BaseModel) -> JobEnvelope:
        return cls(
            job_id=uuid7(),
            job_type=job_type,
            occurred_at=datetime.now(UTC),
            payload=payload.model_dump(mode="json", by_alias=True),
        )

    def encode(self) -> str:
        return self.model_dump_json(by_alias=True)

    @classmethod
    def decode(cls, raw: str | bytes) -> JobEnvelope:
        return cls.model_validate_json(raw)


class JobQueue:
    """`XADD` one envelope onto a stream. Fire-and-forget: callers catch."""

    def __init__(self, client: aioredis.Redis) -> None:
        self._client = client

    @classmethod
    def from_url(cls, url: str, *, timeout_seconds: float = 1.0) -> JobQueue:
        return cls(
            aioredis.from_url(
                url,
                decode_responses=True,
                socket_connect_timeout=timeout_seconds,
                socket_timeout=timeout_seconds,
            )
        )

    async def enqueue(self, stream: str, job_type: str, payload: BaseModel) -> JobEnvelope:
        envelope = JobEnvelope.new(job_type, payload)
        await self._client.xadd(stream, {JOB_DATA_FIELD: envelope.encode()})
        return envelope

    async def aclose(self) -> None:
        await self._client.aclose()
```

- [ ] **Step 2: Export from `shared/__init__.py`**

Add `from shared.jobs import JOB_DATA_FIELD, JobEnvelope, JobQueue` after the `shared.ids`
import, add `"JOB_DATA_FIELD"`, `"JobEnvelope"`, `"JobQueue"` to `__all__` (keep it sorted as
ruff's RUF022 expects), and in the module docstring replace
"Still to arrive with the services that need them: the job envelope, the `ObjectStore` protocol, and structlog + OpenTelemetry setup."
with
"The job envelope and queue arrived with message search. Still to arrive with the services that need them: the `ObjectStore` protocol, and structlog + OpenTelemetry setup."

- [ ] **Step 3: Verify**

Run: `cd /Users/elton/scm/manning/caw-search-pipeline && uv run python -c "from pydantic import BaseModel; from shared import JobEnvelope; class P(BaseModel): x: int = 1
e = JobEnvelope.new('t', P()); r = e.encode(); print(r); print(JobEnvelope.decode(r).job_type)"`
Expected: JSON with keys `jobId, type, version, occurredAt, attempt, payload`, then `t`.
(If the one-liner's class syntax is awkward in the shell, put it in the scratchpad as a
throwaway script — not in the repo.)

---

### Task 2: Index contracts

**Files:**
- Create: `src/services/contracts/contracts/indexing.py`
- Modify: `src/services/contracts/contracts/__init__.py`

**Interfaces:**
- Produces: `JOBS_INDEX = "jobs:index"`, `MESSAGES_ALIAS = "messages"`,
  `MESSAGE_UPSERT = "message.upsert"`, `MESSAGE_DELETE = "message.delete"`,
  `class MessageIndexPayload(BaseModel)` with `message_id, channel_id, workspace_id, author_id:
  uuid.UUID`, `body: str`, `created_at: datetime`, `version: int` (camelCase aliases,
  `populate_by_name=True`).

- [ ] **Step 1: Create `contracts/indexing.py`**

```python
"""Message indexing: the job Messaging produces and the index the Worker writes.

Both ends import these names, so a renamed stream or alias is one edit that
breaks loudly rather than two that drift. Worker doc 05 §3–§4, register D25.

**The payload carries the whole document** because the producer already holds
it and the Worker connects to no service database (D25). On `message.delete`
the producer sends `body: ""` — a stream is not a place to keep text somebody
asked to remove — and the Worker writes a tombstone with no body at all.

There is no `op` field. The envelope's `type` already says upsert or delete, and
two fields that could disagree would need a rule for when they do.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

JOBS_INDEX = "jobs:index"

#: What readers query and writers write. The concrete index behind it is the
#: Worker's business (`messages-v1` today), so a reindex can swap it.
MESSAGES_ALIAS = "messages"

MESSAGE_UPSERT = "message.upsert"
MESSAGE_DELETE = "message.delete"


class MessageIndexPayload(BaseModel):
    """The `payload` of both message job types."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    message_id: uuid.UUID
    channel_id: uuid.UUID
    workspace_id: uuid.UUID
    author_id: uuid.UUID
    body: str
    created_at: datetime
    #: `messages.version` — the Elasticsearch external version, so an older
    #: document arriving late is rejected instead of applied.
    version: int = Field(ge=0)
```

- [ ] **Step 2: Update `contracts/__init__.py`**

Replace the whole file with:

```python
"""Pydantic DTOs and job payload models shared across CollabHub service boundaries.

Nothing lives here without a producer and a consumer. `indexing` is the first:
Messaging produces message index jobs, the Worker consumes them, and Messaging
reads the index the Worker writes.

JSON is camelCase on the wire; models declare `alias_generator=to_camel`.
"""

from contracts.indexing import (
    JOBS_INDEX,
    MESSAGE_DELETE,
    MESSAGE_UPSERT,
    MESSAGES_ALIAS,
    MessageIndexPayload,
)

__all__ = [
    "JOBS_INDEX",
    "MESSAGES_ALIAS",
    "MESSAGE_DELETE",
    "MESSAGE_UPSERT",
    "MessageIndexPayload",
]
```

- [ ] **Step 3: Verify** — `uv run python -c "import contracts; print(contracts.MessageIndexPayload.model_json_schema()['required'])"` prints the camelCase field list.

---

### Task 3: Generic stream consumer in the Worker

**Files:**
- Create: `src/services/worker/worker/consumer.py`

**Interfaces:**
- Consumes: `shared.JobEnvelope`, `shared.JOB_DATA_FIELD`.
- Produces: `Handler = Callable[[JobEnvelope], Awaitable[None]]`;
  `class PermanentJobError(Exception)`;
  `@dataclass(frozen=True) class ConsumerConfig(consumer: str, batch_size: int,
  visibility_timeout_seconds: int, max_attempts: int, dead_letter_maxlen: int,
  block_ms: int = 5000, group: str = "worker")`;
  `class StreamConsumer(client: redis.asyncio.Redis, stream: str, handlers: Mapping[str, Handler],
  config: ConsumerConfig)` with `async run(stop: asyncio.Event) -> None`.
  The Redis client **must** be created with `decode_responses=True`.

- [ ] **Step 1: Create `worker/consumer.py`**

```python
"""One Redis Streams consumer loop, reusable by every job stream (doc 05 §5.1).

Read → dispatch by envelope `type` → on success `XACK` and `XDEL`. A handler
that raises leaves its entry pending; a reclaim pass re-delivers entries idle
longer than the visibility timeout, and an entry delivered more than
`max_attempts` times goes to `<stream>:dead` instead of running again.

Four rules worth reading before changing this file:

**The attempt count is Redis's, not the envelope's.** Stream entries cannot be
edited, so `attempt` in the envelope stays at 1 forever. `XAUTOCLAIM` bumps the
entry's delivery count, and `XPENDING` reports it — that is the number compared
with `max_attempts`.

**Acked entries are deleted.** Index jobs carry message bodies (doc 05 §8), and
an acked entry left in the stream is user content kept for no reason. `XDEL`
after `XACK` removes it without a producer-side `MAXLEN`, which would drop
*unread* jobs whenever the Worker was down for long enough.

**Some failures are not worth retrying.** A malformed envelope, an unknown
`type`, or a handler raising `PermanentJobError` go to dead-letter on the first
delivery — five identical failures teach nobody anything.

**Nothing logged here carries job content.** Job ids, types and exception
class names only; the payload may hold a message body.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

import redis.asyncio as aioredis
from pydantic import ValidationError
from redis.exceptions import RedisError, ResponseError

from shared import JOB_DATA_FIELD, JobEnvelope

_log = logging.getLogger("collabhub.worker.consumer")

Handler = Callable[[JobEnvelope], Awaitable[None]]

#: Pause after a Redis error before trying the loop again.
_REDIS_BACKOFF_SECONDS = 2.0


class PermanentJobError(Exception):
    """Retrying this job cannot succeed; dead-letter it now."""


@dataclass(frozen=True)
class ConsumerConfig:
    consumer: str
    batch_size: int
    visibility_timeout_seconds: int
    max_attempts: int
    dead_letter_maxlen: int
    block_ms: int = 5000
    group: str = "worker"


class StreamConsumer:
    def __init__(
        self,
        client: aioredis.Redis,
        stream: str,
        handlers: Mapping[str, Handler],
        config: ConsumerConfig,
    ) -> None:
        self._client = client
        self._stream = stream
        self._handlers = handlers
        self._config = config

    @property
    def dead_stream(self) -> str:
        return f"{self._stream}:dead"

    async def run(self, stop: asyncio.Event) -> None:
        """Consume until `stop` is set, finishing the batch in hand first."""
        loop = asyncio.get_running_loop()
        reclaim_every = max(1.0, self._config.visibility_timeout_seconds / 2)
        next_reclaim = 0.0
        group_ready = False

        while not stop.is_set():
            try:
                if not group_ready:
                    await self._ensure_group()
                    group_ready = True
                if loop.time() >= next_reclaim:
                    await self._reclaim(stop)
                    next_reclaim = loop.time() + reclaim_every
                await self._read_new(stop)
            except RedisError as exc:
                _log.warning(
                    "redis error on %s (%s); retrying in %ss",
                    self._stream,
                    type(exc).__name__,
                    _REDIS_BACKOFF_SECONDS,
                )
                await asyncio.sleep(_REDIS_BACKOFF_SECONDS)

    async def _ensure_group(self) -> None:
        try:
            await self._client.xgroup_create(
                self._stream, self._config.group, id="0", mkstream=True
            )
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def _read_new(self, stop: asyncio.Event) -> None:
        response = await self._client.xreadgroup(
            self._config.group,
            self._config.consumer,
            {self._stream: ">"},
            count=self._config.batch_size,
            block=self._config.block_ms,
        )
        for _stream, entries in response or []:
            for entry_id, fields in entries:
                # First delivery: nothing to compare against max_attempts yet.
                await self._process(entry_id, fields, deliveries=1)
                if stop.is_set():
                    return

    async def _reclaim(self, stop: asyncio.Event) -> None:
        start = "0-0"
        while not stop.is_set():
            result = await self._client.xautoclaim(
                self._stream,
                self._config.group,
                self._config.consumer,
                min_idle_time=self._config.visibility_timeout_seconds * 1000,
                start_id=start,
                count=self._config.batch_size,
            )
            next_start, claimed = result[0], result[1]
            claimed = [(entry_id, fields) for entry_id, fields in claimed if fields]
            if claimed:
                counts = await self._delivery_counts([entry_id for entry_id, _ in claimed])
                for entry_id, fields in claimed:
                    deliveries = counts.get(entry_id, self._config.max_attempts + 1)
                    await self._process(entry_id, fields, deliveries=deliveries)
            if next_start == "0-0":
                return
            start = next_start

    async def _delivery_counts(self, entry_ids: list[str]) -> dict[str, int]:
        pending = await self._client.xpending_range(
            self._stream,
            self._config.group,
            min=entry_ids[0],
            max=entry_ids[-1],
            count=len(entry_ids),
        )
        return {row["message_id"]: row["times_delivered"] for row in pending}

    async def _process(self, entry_id: str, fields: Mapping[str, str], *, deliveries: int) -> None:
        raw = fields.get(JOB_DATA_FIELD)
        try:
            envelope = JobEnvelope.decode(raw) if raw is not None else None
        except ValidationError:
            envelope = None
        if envelope is None:
            await self._dead_letter(entry_id, raw, "malformed-envelope", deliveries)
            return

        if deliveries > self._config.max_attempts:
            await self._dead_letter(entry_id, raw, "max-attempts", deliveries)
            return

        handler = self._handlers.get(envelope.job_type)
        if handler is None:
            await self._dead_letter(entry_id, raw, "unknown-type", deliveries)
            return

        try:
            await handler(envelope)
        except PermanentJobError as exc:
            await self._dead_letter(entry_id, raw, f"permanent:{exc}", deliveries)
            return
        # BLE001: any other failure is retryable by definition — the entry stays
        # pending and the reclaim pass delivers it again.
        except Exception as exc:  # noqa: BLE001
            _log.warning(
                "job %s (%s) failed on delivery %d: %s",
                envelope.job_id,
                envelope.job_type,
                deliveries,
                type(exc).__name__,
            )
            return

        await self._complete(entry_id)

    async def _complete(self, entry_id: str) -> None:
        async with self._client.pipeline(transaction=True) as pipe:
            pipe.xack(self._stream, self._config.group, entry_id)
            pipe.xdel(self._stream, entry_id)
            await pipe.execute()

    async def _dead_letter(
        self, entry_id: str, raw: str | None, reason: str, deliveries: int
    ) -> None:
        _log.warning(
            "dead-lettering %s entry %s: %s after %d deliveries",
            self._stream,
            entry_id,
            reason,
            deliveries,
        )
        async with self._client.pipeline(transaction=True) as pipe:
            pipe.xadd(
                self.dead_stream,
                {
                    JOB_DATA_FIELD: raw or "",
                    "error": reason,
                    "deliveries": str(deliveries),
                    "sourceId": entry_id,
                },
                maxlen=self._config.dead_letter_maxlen,
                approximate=True,
            )
            pipe.xack(self._stream, self._config.group, entry_id)
            pipe.xdel(self._stream, entry_id)
            await pipe.execute()
```

`PermanentJobError` messages are written by our own handlers (Task 4) and must be short fixed
reasons such as `"invalid payload"` — never exception text from ES.

- [ ] **Step 2: Verify redis-py response shapes** (throwaway, scratchpad only)

Start `docker run --rm -d --name caw-scratch-redis -p 6390:6379 redis:8`, then in a scratchpad
script: `xgroup_create(..., mkstream=True)`, `xadd`, `xreadgroup` without ack,
`xautoclaim(min_idle_time=0)`, `xpending_range`. Confirm `xautoclaim` returns
`[next_start, [(id, fields)], deleted]` with `decode_responses=True`, and `xpending_range`
rows have `message_id` and `times_delivered`. Adjust the indexing in `_reclaim` /
`_delivery_counts` if not. `docker stop caw-scratch-redis` afterwards.

---

### Task 4: Elasticsearch index lifecycle and message handlers

**Files:**
- Create: `src/services/worker/worker/index.py`
- Create: `src/services/worker/worker/handlers/__init__.py`
- Create: `src/services/worker/worker/handlers/messages.py`
- Modify: `src/services/worker/pyproject.toml`

**Interfaces:**
- Consumes: `worker.consumer.Handler`, `worker.consumer.PermanentJobError`, `contracts.*`.
- Produces: `MESSAGES_INDEX = "messages-v1"`, `MESSAGES_MAPPINGS: dict`,
  `async ensure_messages_index(es: AsyncElasticsearch) -> None`;
  `build_message_handlers(es: AsyncElasticsearch) -> dict[str, Handler]`;
  `build_handlers(es: AsyncElasticsearch) -> dict[str, dict[str, Handler]]` (keyed by stream).

- [ ] **Step 1: Add the dependency**

In `src/services/worker/pyproject.toml` dependencies add `"elasticsearch[async]>=9.1,<10",`.
Run: `cd /Users/elton/scm/manning/caw-search-pipeline && uv lock && uv sync`
Expected: `elasticsearch` 9.x resolved into `uv.lock`.

- [ ] **Step 2: Create `worker/index.py`**

```python
"""The `messages` index: its mapping and its creation (doc 05 §4).

The Worker owns index lifecycle. Readers — Messaging's search route — use the
alias `messages` and never name `messages-v1`, so a reindex can build
`messages-v2` beside it and move the alias in one step.

**`dynamic: strict`.** A field nobody mapped is a bug in a producer, and a
strict index rejects it loudly instead of guessing a type that a later reindex
would have to live with.

**`deleted` is a field, not an absence.** A deleted message is a tombstone
document with no `body` (register D8d, and the ADR for this slice): hard-deleting
it would let a late, stale upsert recreate it once Elasticsearch forgets the
deleted version (`index.gc_deletes`, 60 s by default).
"""

from __future__ import annotations

from elasticsearch import AsyncElasticsearch, BadRequestError

from contracts import MESSAGES_ALIAS

MESSAGES_INDEX = "messages-v1"

MESSAGES_MAPPINGS: dict = {
    "dynamic": "strict",
    "properties": {
        "messageId": {"type": "keyword"},
        "channelId": {"type": "keyword"},
        "workspaceId": {"type": "keyword"},
        "authorId": {"type": "keyword"},
        "body": {"type": "text"},
        "createdAt": {"type": "date"},
        "deleted": {"type": "boolean"},
    },
}


async def ensure_messages_index(es: AsyncElasticsearch) -> None:
    """Create `messages-v1` with its alias, or accept that a replica already did."""
    try:
        await es.indices.create(
            index=MESSAGES_INDEX,
            mappings=MESSAGES_MAPPINGS,
            aliases={MESSAGES_ALIAS: {}},
        )
    except BadRequestError as exc:
        if exc.error != "resource_already_exists_exception":
            raise
```

- [ ] **Step 3: Create `worker/handlers/messages.py`**

```python
"""`message.upsert` and `message.delete` → the `messages` index (doc 05 §3).

Both are one external-versioned `index` call, which is what makes them
idempotent and order-safe with no bookkeeping of our own: Elasticsearch refuses
a version that is not newer than the one it holds, with a 409. That 409 is
**success** here — it means the index already reflects this change or a later
one, whether the job was delivered twice or arrived after a newer edit.

A delete writes a tombstone at the bumped version: identifiers, `deleted: true`,
and no `body`, so the text leaves the index the moment the job runs.
"""

from __future__ import annotations

from elasticsearch import AsyncElasticsearch, BadRequestError, ConflictError
from pydantic import ValidationError

from contracts import MESSAGE_DELETE, MESSAGE_UPSERT, MESSAGES_ALIAS, MessageIndexPayload
from shared import JobEnvelope
from worker.consumer import Handler, PermanentJobError


def build_message_handlers(es: AsyncElasticsearch) -> dict[str, Handler]:
    async def upsert(envelope: JobEnvelope) -> None:
        await _write(es, envelope, deleted=False)

    async def delete(envelope: JobEnvelope) -> None:
        await _write(es, envelope, deleted=True)

    return {MESSAGE_UPSERT: upsert, MESSAGE_DELETE: delete}


async def _write(es: AsyncElasticsearch, envelope: JobEnvelope, *, deleted: bool) -> None:
    try:
        payload = MessageIndexPayload.model_validate(envelope.payload)
    except ValidationError as exc:
        raise PermanentJobError("invalid payload") from exc

    document = payload.model_dump(mode="json", by_alias=True, exclude={"body", "version"})
    document["deleted"] = deleted
    if not deleted:
        document["body"] = payload.body

    try:
        await es.index(
            index=MESSAGES_ALIAS,
            id=str(payload.message_id),
            document=document,
            version=payload.version,
            version_type="external",
        )
    except ConflictError:
        # Already at this version or newer — see the module docstring.
        return
    except BadRequestError as exc:
        # A mapping rejection will be rejected identically on every retry.
        raise PermanentJobError("rejected by index") from exc
```

- [ ] **Step 4: Create `worker/handlers/__init__.py`**

```python
"""Handlers by stream, then by job type.

A stream in `WORKER_STREAMS` with no entry here is a configuration error the
Worker refuses to start with — consuming a stream it cannot handle would
dead-letter every job on it.
"""

from __future__ import annotations

from elasticsearch import AsyncElasticsearch

from contracts import JOBS_INDEX
from worker.consumer import Handler
from worker.handlers.messages import build_message_handlers


def build_handlers(es: AsyncElasticsearch) -> dict[str, dict[str, Handler]]:
    return {JOBS_INDEX: build_message_handlers(es)}
```

- [ ] **Step 5: Verify** — `uv run python -c "import worker.handlers, worker.index"` exits 0;
  `uv run python -c "import elasticsearch as e; print(e.ApiError.error)"` confirms `.error`
  exists on the installed client.

---

### Task 5: Worker settings and entry point

**Files:**
- Modify: `src/services/worker/worker/settings.py`
- Modify: `src/services/worker/worker/main.py`

**Interfaces:**
- Consumes: `StreamConsumer`, `ConsumerConfig` (Task 3); `ensure_messages_index`,
  `build_handlers` (Task 4).
- Produces: `create_health_app(settings)` unchanged (the existing health test uses it);
  `run(settings)`, `main()`.

- [ ] **Step 1: Settings**

In `settings.py` replace the `worker_streams` block with:

```python
    # Which streams this deployment consumes, so CPU-heavy and IO-heavy pools can
    # be split later without a code change (register D17, still open). Only
    # streams with handlers belong here: the Worker refuses to start on one it
    # cannot handle, rather than dead-lettering every job on it. `jobs:index` is
    # the only one built.
    worker_streams: str = "jobs:index"
    worker_max_attempts: int = 5
    worker_visibility_timeout_seconds: int = 60
    worker_batch_size: int = 16
    # Dead-letter entries hold job payloads, which for index jobs means message
    # bodies (doc 05 §8) — so the dead stream is capped deliberately, not left
    # to grow.
    worker_dead_letter_maxlen: int = 10_000
```

- [ ] **Step 2: Replace `worker/main.py`**

```python
"""Worker entry point.

The Worker is headless (design doc 05 §2): a long-running asyncio process with
no business HTTP. It serves the health endpoints Kubernetes probes and, beside
them, one consumer task per stream in `WORKER_STREAMS`.

**Startup order.** Health first, so a probe can see *why* the Worker is not
ready; then the `messages` index is ensured, retrying until Elasticsearch
answers; then the consumers start. A job read before the index exists would
fail and be retried anyway, but waiting keeps the logs about the real cause.

**Shutdown drains.** SIGTERM stops Uvicorn, which sets `stop`; each consumer
finishes the entry in hand and returns. Anything unfinished is still pending in
Redis and is reclaimed by the next consumer (Conventions §10).

**A consumer that dies takes the process with it.** If the consume task raises,
the health server is told to exit — a Worker answering `/health/live` while
consuming nothing is the failure nobody notices.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import socket

import redis.asyncio as aioredis
import uvicorn
from elasticsearch import AsyncElasticsearch
from elasticsearch import ConnectionError as EsConnectionError
from fastapi import FastAPI

from shared import build_health_router, http_check, redis_check
from worker.consumer import ConsumerConfig, StreamConsumer
from worker.handlers import build_handlers
from worker.index import ensure_messages_index
from worker.settings import Settings

HEALTH_PORT = 8000
_INDEX_RETRY_SECONDS = 5.0

_log = logging.getLogger("collabhub.worker")


def create_health_app(settings: Settings) -> FastAPI:
    """The Worker's only HTTP surface."""
    app = FastAPI(title="CollabHub Worker (health)", version="0.1.0")
    app.include_router(
        build_health_router(
            {
                "redis-streams": redis_check(settings.redis_streams_url),
                "elasticsearch": http_check(settings.elasticsearch_url),
            }
        )
    )
    return app


async def _wait_for_index(es: AsyncElasticsearch, stop: asyncio.Event) -> bool:
    while not stop.is_set():
        try:
            await ensure_messages_index(es)
        except EsConnectionError as exc:
            _log.warning(
                "elasticsearch not ready (%s); retrying in %ss",
                type(exc).__name__,
                _INDEX_RETRY_SECONDS,
            )
            await asyncio.sleep(_INDEX_RETRY_SECONDS)
        else:
            return True
    return False


async def run(settings: Settings) -> None:
    es = AsyncElasticsearch(settings.elasticsearch_url)
    # Found on the first live run: without an explicit socket timeout above the
    # 5 s `XREADGROUP BLOCK`, every idle read ended in a TimeoutError. Built code
    # passes `socket_timeout=_REDIS_SOCKET_TIMEOUT_SECONDS` (15.0).
    redis_client = aioredis.from_url(
        settings.redis_streams_url, decode_responses=True, socket_timeout=15.0
    )
    registry = build_handlers(es)

    missing = [stream for stream in settings.streams if stream not in registry]
    if missing:
        await es.close()
        await redis_client.aclose()
        raise SystemExit(
            f"No handlers for WORKER_STREAMS entries: {', '.join(missing)}. "
            f"Built streams: {', '.join(sorted(registry))}."
        )

    config = ConsumerConfig(
        consumer=socket.gethostname(),
        batch_size=settings.worker_batch_size,
        visibility_timeout_seconds=settings.worker_visibility_timeout_seconds,
        max_attempts=settings.worker_max_attempts,
        dead_letter_maxlen=settings.worker_dead_letter_maxlen,
    )
    consumers = [
        StreamConsumer(redis_client, stream, registry[stream], config)
        for stream in settings.streams
    ]

    server = uvicorn.Server(
        uvicorn.Config(
            create_health_app(settings),
            # Binds all interfaces because the container is the boundary; what is
            # reachable is the pod's and the ingress's concern, not the process's.
            host="0.0.0.0",  # noqa: S104
            port=HEALTH_PORT,
            log_level=settings.log_level,
        )
    )
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()

    # Uvicorn captures SIGTERM while serving and re-raises it after `serve()`
    # returns. With the default handler that re-raise would kill the process
    # before the drain below; with this one it only sets `stop`, again.
    def _on_signal(*_: object) -> None:
        loop.call_soon_threadsafe(stop.set)

    signal.signal(signal.SIGTERM, _on_signal)

    async def consume() -> None:
        if await _wait_for_index(es, stop):
            await asyncio.gather(*(consumer.run(stop) for consumer in consumers))

    consume_task = asyncio.create_task(consume())

    def _on_consume_done(task: asyncio.Task[None]) -> None:
        if not task.cancelled() and task.exception() is not None:
            _log.error("consumer task failed: %s", type(task.exception()).__name__)
            server.should_exit = True

    consume_task.add_done_callback(_on_consume_done)

    try:
        await server.serve()
    finally:
        stop.set()
        try:
            await consume_task
        finally:
            await es.close()
            await redis_client.aclose()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run(Settings()))
```

- [ ] **Step 3: Verify** — `uv run pytest src/services/worker -q` passes (existing health tests);
  `WORKER_STREAMS=jobs:thumbnail REDIS_STREAMS_URL=redis://localhost:1 ELASTICSEARCH_URL=http://localhost:1 OBJECT_STORE_ENDPOINT=http://x uv run collabhub-worker`
  exits with the "No handlers for WORKER_STREAMS entries: jobs:thumbnail" message.

---

### Task 6: Messaging producer

**Files:**
- Create: `src/services/messaging/messaging/indexing.py`
- Modify: `src/services/messaging/messaging/messages.py` (the `delete` function and `__all__`)
- Modify: `src/services/messaging/messaging/routers/messages.py` (send, edit, delete routes)
- Modify: `src/services/messaging/messaging/realtime.py` (`RealtimeContext`)
- Modify: `src/services/messaging/messaging/realtime_writes.py` (three handlers)
- Modify: `src/services/messaging/messaging/main.py`, `settings.py`, `openapi.py`, `pyproject.toml`
- Modify: `src/services/messaging/tests/conftest.py`, `src/services/messaging/tests/test_health.py` (one placeholder line each)

**Interfaces:**
- Consumes: `shared.JobQueue`; `contracts.JOBS_INDEX`, `MESSAGE_UPSERT`, `MESSAGE_DELETE`,
  `MessageIndexPayload`.
- Produces: `indexing.queue(request: Request) -> JobQueue`;
  `async indexing.enqueue_upsert(queue: JobQueue, message: MessageResponse, *, workspace_id: uuid.UUID) -> None`;
  `async indexing.enqueue_delete(...)` same signature;
  `messages.DeleteResult(message: Message, deleted_now: bool)`;
  `messages.delete(...) -> DeleteResult | None`;
  `RealtimeContext.jobs: JobQueue`; `app.state.jobs: JobQueue`; `app.state.search: AsyncElasticsearch`;
  `Settings.elasticsearch_url: str`.

- [ ] **Step 1: Dependency** — add `"elasticsearch[async]>=9.1,<10",` to Messaging's
  `pyproject.toml` dependencies; `uv lock && uv sync`.

- [ ] **Step 2: Settings** — in `settings.py`, after `redis_streams_url`:

```python
    # Read-only: the Worker writes the `messages` index, this service queries it
    # for `GET /search/messages`. Not a readiness dependency — an Elasticsearch
    # outage degrades search and must not take chat out of rotation.
    elasticsearch_url: str
```

- [ ] **Step 3: Placeholders** — `openapi.py` `_PLACEHOLDERS` gains
  `"elasticsearch_url": "http://openapi.invalid:9200",`; `tests/conftest.py` `build_settings`
  dict gains `"elasticsearch_url": "http://elasticsearch.invalid:9200",`;
  `tests/test_health.py` `_settings()` gains
  `elasticsearch_url="http://elasticsearch:9200",`. Nothing else in the test tree changes.

- [ ] **Step 4: Create `messaging/indexing.py`**

```python
"""The `jobs:index` producer (doc 02 §5 step 4, register D25).

Called after every committed message write — send, edit and delete, over REST
and over the socket — right after the room broadcast. Order everywhere:
commit → broadcast → enqueue.

**Fire-and-forget, as Conventions §7 says.** The write has already succeeded
and the client is owed its response; an unreachable R3 must not turn that into
an error. So a failed enqueue is logged and swallowed, and search misses that
change until a reindex path exists (register, 🔴). `JobQueue.from_url` keeps the
socket timeouts short so the attempt cannot hang a request either.

**It enqueues the response DTO, not the ORM row.** The DTO is what was
committed and already has a deleted message's body redacted to `""`, so a
delete job cannot carry text the user asked to remove.

**The workspace is the caller's `wsp` claim.** `messages` has no workspace
column; the visibility check that let the write happen is what proved the
channel belongs to that workspace.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import Request

from contracts import JOBS_INDEX, MESSAGE_DELETE, MESSAGE_UPSERT, MessageIndexPayload
from messaging.schemas import MessageResponse
from shared import JobQueue

_log = logging.getLogger("collabhub.messaging.indexing")


def queue(request: Request) -> JobQueue:
    """FastAPI dependency: `jobs = Depends(indexing.queue)`.

    The `Request` annotation is load-bearing, as it is on `realtime.server`.
    """
    return request.app.state.jobs


async def enqueue_upsert(
    jobs: JobQueue, message: MessageResponse, *, workspace_id: uuid.UUID
) -> None:
    await _enqueue(jobs, MESSAGE_UPSERT, message, workspace_id)


async def enqueue_delete(
    jobs: JobQueue, message: MessageResponse, *, workspace_id: uuid.UUID
) -> None:
    await _enqueue(jobs, MESSAGE_DELETE, message, workspace_id)


async def _enqueue(
    jobs: JobQueue, job_type: str, message: MessageResponse, workspace_id: uuid.UUID
) -> None:
    payload = MessageIndexPayload(
        message_id=message.id,
        channel_id=message.channel_id,
        workspace_id=workspace_id,
        author_id=message.author_id,
        body=message.body,
        created_at=message.created_at,
        version=message.version,
    )
    try:
        await jobs.enqueue(JOBS_INDEX, job_type, payload)
    # BLE001: fire-and-forget — whatever went wrong, the committed write stands.
    except Exception as exc:  # noqa: BLE001
        _log.warning(
            "%s not enqueued for message %s (%s); search will miss this change",
            job_type,
            message.id,
            type(exc).__name__,
        )
```

- [ ] **Step 5: `messages.delete` reports whether it deleted**

In `messages.py`: add `from dataclasses import dataclass`; add `"DeleteResult"` to `__all__`
(sorted); add above `delete`:

```python
@dataclass(frozen=True)
class DeleteResult:
    """The tombstone, and whether *this* call made it.

    A repeat delete returns the existing tombstone without bumping `version`,
    and the index producer needs to know that: a job for an unchanged version
    would be refused by Elasticsearch anyway, so it is not worth sending.
    """

    message: Message
    deleted_now: bool
```

Change the signature's return type to `DeleteResult | None`; replace
`if message.deleted_at is not None: return message` with
`return DeleteResult(message, deleted_now=False)` inside that `if`; replace the final
`return message` with `return DeleteResult(message, deleted_now=True)`. Update the docstring
line "A second delete returns the existing tombstone untouched" to add "— with
`deleted_now=False`".

- [ ] **Step 6: REST routes** — in `routers/messages.py`:

Add imports `from messaging import channels, indexing, messages, realtime` and
`from shared import JobQueue, PageParams, ProblemException, UserPrincipal, require_user`.
Add parameter `jobs: JobQueue = Depends(indexing.queue),` after `sio` in `send_message`,
`edit_message` and `delete_message`. Then:

- `send_message`: after `await realtime.publish_message_received(sio, response)` add
  `await indexing.enqueue_upsert(jobs, response, workspace_id=principal.workspace_id)`.
- `edit_message`: after `publish_message_edited` add the same `enqueue_upsert` line.
- `delete_message`: rename the local `deleted` to `result`; `if result is None:` 404;
  `response = _as_message(result.message)`; after `publish_message_deleted` add

```python
    if result.deleted_now:
        await indexing.enqueue_delete(jobs, response, workspace_id=principal.workspace_id)
```

Add one sentence to the module docstring's last paragraph: "Then, for the search index, it
enqueues a `jobs:index` job — fire-and-forget, see `indexing.py`."

- [ ] **Step 7: Socket handlers** — in `realtime.py` add `from shared import JobQueue` (merge
  into the existing `shared` import) and a field `jobs: JobQueue` at the end of
  `RealtimeContext`. In `main.build_asgi_app`, pass `jobs=app.state.jobs` to `RealtimeContext`.
  In `realtime_writes.py` import `indexing` alongside `channels, messages, realtime`, and:

- `send_message`: after `publish_message_received` add
  `await indexing.enqueue_upsert(context.jobs, response, workspace_id=principal.workspace_id)`.
- `edit_message`: same after `publish_message_edited`.
- `delete_message`: rename `deleted` → `result`; `response = _as_message(result.message)`;
  after `publish_message_deleted`:

```python
        if result.deleted_now:
            await indexing.enqueue_delete(
                context.jobs, response, workspace_id=principal.workspace_id
            )
```

(`result` is defined inside the `async with` block; the enqueue sits after it at function
level, beside the publish, using `result` — valid Python, same as `response` today.)

- [ ] **Step 8: Build and close the clients in `create_app`**

In `main.py` add `from elasticsearch import AsyncElasticsearch` and `JobQueue` to the `shared`
import. After `redis_client = ...`:

```python
    # R3, for the index producer. Short timeouts: see `shared/jobs.py`.
    jobs = JobQueue.from_url(settings.redis_streams_url)
    # Query-only. Fails fast so a search against a sick cluster returns 503
    # promptly rather than holding a worker for the default 10 s per try.
    search_client = AsyncElasticsearch(
        settings.elasticsearch_url, request_timeout=5, max_retries=1, retry_on_timeout=False
    )
```

In `lifespan` after `await redis_client.aclose()` add `await jobs.aclose()` and
`await search_client.close()`. After `app.state.realtime = None` add
`app.state.jobs = jobs` and `app.state.search = search_client`.

- [ ] **Step 9: Verify** — `uv run python -m messaging.openapi > /dev/null` exits 0;
  `uv run pytest -m "not integration and not bdd" -q` passes.

---

### Task 7: Search endpoint

**Files:**
- Modify: `src/services/messaging/messaging/channels.py` (add `visible_ids`, export)
- Create: `src/services/messaging/messaging/search.py`
- Create: `src/services/messaging/messaging/routers/search.py`
- Modify: `src/services/messaging/messaging/main.py` (include router)

**Interfaces:**
- Consumes: `app.state.search` (Task 6), `contracts.MESSAGES_ALIAS`, `shared.encode_cursor`,
  `shared.Page`, `shared.PageRequest`, `routers.messages._as_message`.
- Produces: `channels.visible_ids(session, *, workspace_id, user_id) -> list[uuid.UUID]`;
  `search.MAX_QUERY_CHARS = 200`; `class search.SearchUnavailableError(Exception)`;
  `async search.search_messages(es, session, *, workspace_id, user_id, query: str, page: PageRequest) -> Page[Message]`.

- [ ] **Step 1: `channels.visible_ids`** — after `get_visible` in `channels.py`:

```python
async def visible_ids(
    session: AsyncSession, *, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> list[uuid.UUID]:
    """Every channel id this caller may see — the search route's filter.

    The same `_visible_query` as every other read, reduced to ids, so search
    cannot drift from what the sidebar and the history routes allow. Computed
    per request, which is why removing someone from a private channel or
    archiving one takes effect in search immediately with nothing to reindex.
    """
    query = _visible_query(workspace_id, user_id).with_only_columns(Channel.id).order_by(None)
    return list((await session.execute(query)).scalars().all())
```

Verify the SQL keeps the outer join:
`uv run python -c "import uuid; from messaging import channels; from sqlalchemy.dialects import postgresql; print(channels._visible_query(uuid.uuid4(), uuid.uuid4()).with_only_columns(channels.Channel.id).order_by(None).compile(dialect=postgresql.dialect()))"`
Expected: `SELECT channels.id FROM channels LEFT OUTER JOIN channel_members ON …` with the
three `WHERE` predicates. If the join is lost, use
`select(Channel.id).select_from(_visible_query(...).subquery())` instead.

- [ ] **Step 2: Create `messaging/search.py`**

```python
"""Message search: Elasticsearch finds candidates, Postgres decides what is shown.

`GET /search/messages` (doc 02 §3.1.6, register D8c) in three steps.

1. **Authorize before asking.** The caller's visible channel ids come from the
   same query every other read uses, and the Elasticsearch query is filtered to
   them and to the `wsp` workspace. Nothing about who may see what is stored in
   the index, so nothing in the index can be stale about it.
2. **Ask for ids only**, newest first — `messageId` descending, because UUID v7
   in fixed-length lowercase hex sorts in time order — with `search_after` as
   the cursor. The same keyset shape as history (Conventions §4.1).
3. **Hydrate from Postgres**, dropping anything deleted or no longer visible, and
   keep Elasticsearch's order. The index lags the database by however long the
   Worker takes; hydration is what stops that lag from showing a deleted
   message's text.

**A page can be shorter than `limit`** when hydration drops rows. `nextCursor`
comes from the Elasticsearch hits, not the survivors, so no match is ever
skipped — only `nextCursor: null` means there is nothing more.
"""

from __future__ import annotations

import uuid
from typing import Any

from elasticsearch import ApiError, AsyncElasticsearch, NotFoundError, TransportError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contracts import MESSAGES_ALIAS
from messaging import channels
from messaging.models import Message
from shared import Page, PageRequest, encode_cursor

__all__ = ["MAX_QUERY_CHARS", "SearchUnavailableError", "search_messages"]

MAX_QUERY_CHARS = 200


class SearchUnavailableError(Exception):
    """Elasticsearch could not answer. The router turns this into a 503."""


async def search_messages(
    es: AsyncElasticsearch,
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    query: str,
    page: PageRequest,
) -> Page[Message]:
    channel_ids = await channels.visible_ids(
        session, workspace_id=workspace_id, user_id=user_id
    )
    if not channel_ids:
        return Page(items=[], next_cursor=None)

    hit_ids = await _candidate_ids(es, workspace_id, channel_ids, query, page)
    has_more = len(hit_ids) > page.limit
    hit_ids = hit_ids[: page.limit]
    next_cursor = encode_cursor(str(hit_ids[-1])) if has_more else None

    return Page(items=await _hydrate(session, hit_ids, channel_ids), next_cursor=next_cursor)


async def _candidate_ids(
    es: AsyncElasticsearch,
    workspace_id: uuid.UUID,
    channel_ids: list[uuid.UUID],
    query: str,
    page: PageRequest,
) -> list[uuid.UUID]:
    request: dict[str, Any] = {
        "index": MESSAGES_ALIAS,
        "query": {
            "bool": {
                # `operator: and` — every word must match. `match`, not
                # `query_string`: no query syntax is exposed to users.
                "must": [{"match": {"body": {"query": query, "operator": "and"}}}],
                "filter": [
                    {"term": {"workspaceId": str(workspace_id)}},
                    {"terms": {"channelId": [str(c) for c in channel_ids]}},
                    {"term": {"deleted": False}},
                ],
            }
        },
        "sort": [{"messageId": "desc"}],
        "size": page.fetch_limit,
        "source": False,
        "track_total_hits": False,
    }
    if page.cursor:
        request["search_after"] = list(page.cursor)

    try:
        result = await es.search(**request)
    except NotFoundError as exc:
        # The Worker has never run, so the alias does not exist yet: nothing
        # has been indexed, which is an empty result and not an outage.
        if exc.error == "index_not_found_exception":
            return []
        raise SearchUnavailableError from exc
    except (ApiError, TransportError) as exc:
        raise SearchUnavailableError from exc

    return [uuid.UUID(hit["_id"]) for hit in result["hits"]["hits"]]


async def _hydrate(
    session: AsyncSession, ids: list[uuid.UUID], channel_ids: list[uuid.UUID]
) -> list[Message]:
    """The rows behind the hits, in hit order.

    `deleted_at IS NULL` is right here and is not the history exception from
    Conventions §3: search does not return tombstones.
    """
    if not ids:
        return []
    query = select(Message).where(
        Message.id.in_(ids),
        Message.channel_id.in_(channel_ids),
        Message.deleted_at.is_(None),
    )
    rows = {m.id: m for m in (await session.execute(query)).scalars()}
    return [rows[i] for i in ids if i in rows]
```

- [ ] **Step 3: Create `messaging/routers/search.py`**

```python
"""`GET /api/v1/search/messages` (doc 02 §3.1, §3.1.6).

A thin proxy in Messaging rather than a search gateway (register D8c 🟡). All
the rules live in `messaging/search.py`; this module validates the query string
and translates failures.

**Plain `require_user`.** Searching is a read and is outside the fail-closed
denylist set (Conventions §5.2).

**No workspace parameter**, and there must never be one: the workspace is the
`wsp` claim, and the channel filter is computed from it on every request.
"""

from __future__ import annotations

from typing import Annotated

from elasticsearch import AsyncElasticsearch
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from messaging import search
from messaging.db import session as db_session
from messaging.routers.messages import _as_message
from messaging.schemas import MessageListResponse
from shared import PageParams, ProblemException, UserPrincipal, require_user

router = APIRouter(prefix="/api/v1/search", tags=["search"])


def _search_client(request: Request) -> AsyncElasticsearch:
    return request.app.state.search


@router.get("/messages", response_model=MessageListResponse)
async def search_messages(
    q: Annotated[str, Query(max_length=search.MAX_QUERY_CHARS)],
    page: PageParams,
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
    es: AsyncElasticsearch = Depends(_search_client),
) -> MessageListResponse:
    """Messages matching every word of `q`, newest first, in channels the caller can see.

    **A short page is not the last page** — hydration can drop a hit whose row
    was deleted after it was indexed. Only `nextCursor: null` means the end.
    """
    query = q.strip()
    if not query:
        message = "Enter something to search for."
        raise ProblemException.validation_error(message, errors={"q": [message]})
    if page.cursor is not None and len(page.cursor) != 1:
        raise ProblemException.validation_error("The cursor is not valid.")

    try:
        found = await search.search_messages(
            es,
            session,
            workspace_id=principal.workspace_id,
            user_id=principal.user_id,
            query=query,
            page=page,
        )
    except search.SearchUnavailableError as exc:
        raise ProblemException.service_unavailable("Search is unavailable.") from exc

    return MessageListResponse(
        items=[_as_message(m) for m in found.items], next_cursor=found.next_cursor
    )
```

- [ ] **Step 4: Include the router** — in `main.py` import
  `from messaging.routers import search as search_routes` and add
  `app.include_router(search_routes.router)` after the message routers.

- [ ] **Step 5: Verify**
  - `uv run python -m messaging.openapi | python3 -c "import json,sys; print('/api/v1/search/messages' in json.load(sys.stdin)['paths'])"` → `True`.
  - `python3 .claude/hooks/checks/conventions.py src/services/messaging/messaging/search.py src/services/messaging/messaging/routers/search.py src/services/messaging/messaging/channels.py` → no findings.
  - `uv run pytest -m "not integration and not bdd" -q` passes.

---

### Task 8: Configuration, chart, and generated types

**Files:**
- Modify: `docker-compose.yml`, `.env.example`, `charts/collabhub/values.yaml`
- Regenerate: `src/frontend/openapi/messaging.json`, `src/frontend/src/types/messaging.ts`

- [ ] **Step 1: Compose** — in the `messaging` service `environment`, after
  `REDIS_STREAMS_URL`, add:

```yaml
      # Read-only, for GET /search/messages. Deliberately not in depends_on: an
      # Elasticsearch outage degrades search, it does not stop chat starting.
      ELASTICSEARCH_URL: ${ELASTICSEARCH_URL}
```

  In the `worker` service `environment` add `WORKER_STREAMS: ${WORKER_STREAMS}` and
  `WORKER_DEAD_LETTER_MAXLEN: ${WORKER_DEAD_LETTER_MAXLEN}`. No new `depends_on`: the Worker
  never calls Messaging.

- [ ] **Step 2: `.env.example`** — the Elasticsearch header comment becomes
  `# Elasticsearch — written by the Worker, read by Messaging's search route`. In the Worker
  block replace the `WORKER_STREAMS` line with:

```bash
# Only streams the Worker has handlers for — it refuses to start otherwise.
# jobs:index is the only one built; add the others as their handlers land.
WORKER_STREAMS=jobs:index
```

  and after `WORKER_BATCH_SIZE=16` add:

```bash
# Dead-letter entries hold job payloads (message bodies, for jobs:index), so the
# dead stream is capped rather than left to grow.
WORKER_DEAD_LETTER_MAXLEN=10000
```

- [ ] **Step 3: Chart values** — Messaging's secret comment becomes
  `# Supplies POSTGRES_DSN, all three REDIS_*_URL values and ELASTICSEARCH_URL.`; Worker
  `env` `WORKER_STREAMS: jobs:index` and add `WORKER_DEAD_LETTER_MAXLEN: "10000"`.
  Run `helm template charts/collabhub > /dev/null` if `helm` is installed.

- [ ] **Step 4: Generated types (D23)**

```bash
cd /Users/elton/scm/manning/caw-search-pipeline
uv run python -m messaging.openapi > src/frontend/openapi/messaging.json
cd src/frontend && npm ci && npm run generate:api
```

  Expected: `src/types/messaging.ts` gains `"/api/v1/search/messages"`. `git diff --stat src/frontend`
  shows only those two files.

---

### Task 9: Decisions and documentation

**Files:**
- Create: `docs/adr/260914-message-search-index-is-a-candidate-list.md` (via `adr-writer`)
- Modify: `docs/design/07-open-decisions-register.md`, `docs/design/00-platform-conventions.md`,
  `docs/design/02-messaging-service.md`, `docs/design/05-worker-service.md`,
  `src/services/messaging/README.md`

- [ ] **Step 1: ADR** — invoke the `adr-writer` skill with: *The message search index is a
  candidate list, not a source of truth. Deletes write tombstone documents at the bumped
  external version instead of hard-deleting, because Elasticsearch forgets a deleted
  document's version after `index.gc_deletes` and a late stale upsert would resurrect the
  text. Authorization is a per-request filter on the caller's visible channel ids, never data
  in the index. Results are hydrated from Postgres with `deleted_at IS NULL`, so index lag
  cannot show deleted text, and a page may be shorter than `limit`. Alternatives: hard delete
  (doc 05 as written); ACLs in index documents (would need a reindex on every membership
  change); returning ES documents directly (second DTO, lag leaks).* Status Accepted,
  2026-09-14.

- [ ] **Step 2: Register (doc 07)**
  - "Settled" paragraph: add **Settled 2026-09-14:** message search built — see the ADR.
  - D8c: replace the "Built against it 2026-08-16" text with "**Built against it 2026-09-14:**
    `GET /api/v1/search/messages` is a thin proxy in Messaging; the Worker writes the
    `messages` index from `jobs:index`. Results are hydrated from Postgres — see the [ADR]."
  - D25: replace "`messages` has no `version` column yet" with "`messages.version` exists and
    is the external version; the `jobs:index` producer and consumer are built (2026-09-14)".
  - New row in *Worker*: `| D29 | Reindex / backfill path for search | 🔴 Open | Needed
    before search can be trusted after an R3 outage: enqueue is fire-and-forget (Conventions
    §7), so a lost job leaves the index wrong until something rebuilds it. Likely a Messaging
    internal endpoint paging messages plus a `reindex` job type (doc 05 §4) | Worker +
    Messaging |`

- [ ] **Step 3: Conventions §7.1** — after the "Ack / retry" bullet, replace it with:

```markdown
- **Ack / retry:** Worker `XACK`s on success and then `XDEL`s the entry, so job payloads —
  which can hold user content — do not outlive their processing. Unacked entries are
  reclaimed via `XAUTOCLAIM` after a visibility timeout. **Attempts are counted with Redis's
  delivery count**, because a stream entry cannot be edited: `attempt` in the envelope is
  written as `1` and is informational. A job runs at most `maxAttempts` times (default 5);
  the next delivery moves it to `jobs:<name>:dead` (capped with an approximate `MAXLEN`) and
  acks it. A malformed envelope or an unknown `type` is dead-lettered on first delivery.
  *(Clarified 2026-09-14 while building message search.)*
```

- [ ] **Step 4: Doc 02**
  - §1: "**not built; see §5**" → "built 2026-09-14".
  - §3.1 table, search row purpose: "Thin proxy to Elasticsearch (D8c). See §3.1.6."
  - §3.1.5: delete the `GET /search/messages` row.
  - New §3.1.6 *Search — added 2026-09-14*, summarising spec §3: contract, query-time
    visibility, newest-first `search_after`, Postgres hydration and short pages, 503 / empty on
    missing index, not a readiness dependency, `terms` limit (`index.max_terms_count`,
    65 536) noted; link the ADR.
  - §4.1 R3 bullet: drop "**The producer is not built; see §5.**"
  - §5 step 4: payload loses `op`; replace the "Step 4 is not built — noted 2026-08-16" block
    with a short "Built 2026-09-14" paragraph: fire-and-forget after the broadcast at all six
    write sites, delete jobs carry `body: ""`, repeat deletes enqueue nothing, failure logged.
  - §6: add `ELASTICSEARCH_URL` (read-only, search).

- [ ] **Step 5: Doc 05**
  - §3 table `jobs:index` message row: payload without `op`; action "External-versioned
    `index` into `messages`; `message.delete` writes a tombstone (no `body`, `deleted: true`).
    A version conflict is success." Add note under the D25 paragraph referencing the ADR.
  - §4: `messages` row doc shape adds `deleted`; add the mapping table and `dynamic: strict`;
    note the edge-ngram line applies to names/file names, not `body`.
  - §5.1: rewrite steps 3–4 per Conventions §7 as updated; add "consumer name is the hostname";
    "refuses to start on a stream with no handlers"; "the index is ensured before consumers
    start".
  - §6: `WORKER_STREAMS` default `jobs:index`; add `WORKER_DEAD_LETTER_MAXLEN`.
  - §8: replace the MAXLEN bullet's "Set `MAXLEN` trimming deliberately" with the decision:
    acked entries are `XDEL`ed; dead stream capped by `WORKER_DEAD_LETTER_MAXLEN`.

- [ ] **Step 6: Messaging README** — in "What is built" add a **Search.** paragraph
  (`GET /api/v1/search/messages`, fed by `jobs:index` via the Worker); change "Not built:
  threads, reactions, read receipts and search" to drop "and search"; add a rule under
  "Rules worth knowing": **Search results come from Postgres, not Elasticsearch** — one
  paragraph pointing at `search.py` and the ADR.

---

### Task 10: Verification

- [ ] **Step 1: Static** — `uv run ruff check src/services && uv run ruff format --check src/services`;
  `python3 .claude/hooks/checks/conventions.py` (changed files since HEAD). Expected: clean.
- [ ] **Step 2: Existing suites** — `uv run pytest -m "not integration and not bdd" -q` and
  `uv run pytest src/services/messaging -q` (needs Docker). Expected: all pass, same counts
  as on `main`.
- [ ] **Step 3: Stack.** Check `docker compose ls`. If a `collabhub` project is running from
  the primary checkout, **ask before replacing it**. Otherwise copy
  `/Users/elton/scm/manning/caw-project/.env` into the worktree, set `WORKER_STREAMS=jobs:index`
  and add `WORKER_DEAD_LETTER_MAXLEN=10000` in that copy, and
  `docker compose up -d --build`. Tell the user their own `.env` needs the same two changes.
- [ ] **Step 4: End to end** (manual, per spec §6):
  - `docker compose logs worker` shows the index ensured and no errors;
    `curl -s localhost:9200/_alias/messages` shows `messages-v1`.
  - Send, edit, delete a message (SPA or `curl` with a token). `curl -s localhost:9200/messages/_doc/<id>`
    shows `_version` 0 → 1 → 2 and the last `_source` has `deleted: true` and no `body`.
  - `GET /api/v1/search/messages?q=<word>` finds a live message; returns nothing for the
    deleted one.
  - `docker compose stop worker`; send two messages; `docker compose exec redis-streams redis-cli XLEN jobs:index` → 2;
    `docker compose start worker`; XLEN → 0; both searchable.
  - `docker compose stop elasticsearch`; search → 503 problem document; sending still 201;
    `XPENDING jobs:index worker` shows pending entries after a send; `start elasticsearch`;
    pending drains.
  - `redis-cli XADD jobs:index '*' data '{"jobId":"00000000-0000-7000-8000-000000000000","type":"nope","occurredAt":"2026-09-14T00:00:00Z","payload":{}}'`
    → `XLEN jobs:index:dead` is 1 with `error unknown-type`.
  - `docker compose stop worker` completes within a few seconds (graceful drain, no SIGKILL).
- [ ] **Step 5: Leave uncommitted.** `git status` in the worktree; report the changed files
  to the user. Do not stage or commit.
