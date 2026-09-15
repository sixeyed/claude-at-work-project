# Read Markers and Unread Counts — TDD Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Three project rules override those skills.** Tests are **unit tests only** — pytest with no
> Docker; no new testcontainers tests, no `tests/bdd` scenarios, no frontend tests. **Stop at red**:
> after Task 2 nothing else runs until Elton has reviewed the failing tests. **Never commit** —
> leave the worktree dirty (CLAUDE.md, "Working in this repo"). Where a skill says "commit", this
> plan says "leave uncommitted".

**Goal:** A person can mark a channel read up to a message, over REST or the socket, and every
`Channel` the API returns says how far they have read and how many messages they have not.

**Architecture:** A new `channel_reads` table holds one forward-only pointer per (channel,
person), gated on channel *visibility* like reading and posting, not on membership. The channel
reads that build a `Channel` DTO add the pointer and a correlated unread count; the guards every
write path uses stay lean. A write moves the pointer with a guarded upsert, then tells the
reader's *own* other sessions through a per-user, per-workspace room.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 async + asyncpg, Alembic, python-socketio,
pydantic v2, pytest (`asyncio_mode = "auto"`), uv, ruff.

**Spec:** `docs/design/02-messaging-service.md` — §3.1 (`POST /channels/{id}/read`), §3.2
(`mark_read`, `read_receipt_updated`), §4 (`last_read_id`; "unread counts are derived"). The spec
says almost nothing past those three lines, so the decisions below fill it in and Task 9 writes
them back.

**Worktree:** `/Users/elton/scm/manning/caw-read-markers`, branch `feature/read-markers`, from
`main` at `f3f7c21`. Baseline: `102 passed` on the unit layer.

---

## How this plan runs

| Phase | Tasks | Ends with |
|---|---|---|
| 0 — rules | 0 | CLAUDE.md says what we now do |
| **RED** | 1–2 | ten failing unit tests, each failing for its stated reason — **STOP for review** |
| GREEN | 3–7 | the ten pass, nothing else breaks |
| REFACTOR | 8 | same tests green, code tidied |
| Finish | 9–10 | docs, register, ADR, regenerated types, full verification |

Green goes one test group at a time: run only that group's tests, watch them pass, then run
the whole unit layer before the next task.

## Decisions for review

Settled with Elton on 2026-09-15:

1. **Tests are back, unit only for now.** CLAUDE.md's no-tests rule is replaced in Task 0.
2. **Read state lives in a new table, gated on visibility.** `channel_reads (channel_id, user_id,
   last_read_id, updated_at)`. Grace has no membership row in `#general` and can't make one, and
   she still gets unread counts there. `channel_members.last_read_id`, which shipped unused in
   `0001`, is dropped.

This plan's own calls, which need your yes or no:

3. **What counts as unread:** every message in the channel after the marker that **someone else**
   wrote and that **is not deleted**. With no marker, that's every such message in the channel.
   The count is **exact and uncapped**. *Risk:* for a public channel you've never opened, the
   sidebar counts its whole history on every load. The alternative is a cap, e.g. `LIMIT 100`
   inside the count, shown as "99+".
4. **The marker only moves forward.** Marking an older message than the current marker changes
   nothing and still returns success. That's what two tabs racing each other need. It replaces the
   optimistic-concurrency `version` Conventions §3 asks of updatable rows: here the guard is
   `last_read_id < excluded.last_read_id`, so an update can't be lost, and there is nothing to
   conflict on. This deviation gets recorded.
5. **`POST /channels/{id}/read` returns 204 with no body.** The message must be in *that* channel.
   Anything else is the same 404 the message routes use ("No such channel."), so ids can't be
   probed. A tombstone can be marked read, since it's in the history.
6. **`lastReadId` and `unreadCount` are required on every `Channel` DTO**, with no defaults, so
   the generated TypeScript fields aren't optional. Creating a channel returns `null` / `0`.
7. **Only the reads that build a DTO count.** `get_visible` gains `with_read_state=False`. The
   guards behind `send_message`, `join_channel` and the member routes don't pay for a count.
8. **`mark_read` is a write event on the socket.** Expiry and denylist are re-checked, the
   denylist fails open, and the ack is `{ "ok": true }`.
9. **`read_receipt_updated` goes only to the reader's own sessions,** in the room
   `user:{workspaceId}:{userId}`, which every connection joins on connect. The room includes the
   workspace because one person can have tabs open in two workspaces (Conventions §5.4). When the
   read came over the socket, the sending connection is skipped. The event is never sent to the
   channel, so nobody sees anyone else's read position.
10. **Sending a message doesn't move the sender's own marker.** Their own messages are already
    excluded from the count (decision 3).
11. **The SPA is out of scope.** There's no frontend test layer, and it isn't being added now. The
    OpenAPI document and generated types are regenerated so the contract is ready for the SPA.
12. **Recorded as register D31 🟢** with an ADR, in Task 9.

## What no unit test covers — read before approving red

Unit tests can't reach Postgres, so run the mutation check against the list below. **None of
these would fail a test in this plan:**

- the four unread rules in `_with_read_state` (own messages, tombstones, no marker, the `>`
  boundary)
- which callers pass `with_read_state=True` (get, the re-read after a rename, archive)
- the forward-only guard in the upsert, and "broadcast only when the marker actually moved"
- the 404s: a channel you can't see, a message from another channel, an unknown message id
- commit before publish
- `connect` joining the reader room
- the happy path of socket `mark_read`, and its expiry and revocation checks
- migration `0003`: the new table, and the dropped column

The **existing** integration suite (Task 10) proves only that the changed channel queries still
run and return valid DTOs, and that the migrations apply. Checking semantics is by hand, in Task
10 step 6. If that gap is too wide, the cheapest fix is to let integration tests cover the first
three bullets. The testcontainers fixtures to do that already exist.

## Global Constraints

- The workspace comes from `principal.workspace_id` only, never a path, body or event payload
  (CH001).
- A channel the caller can't see is a 404, never a 403 (CH004). The wording is `"No such channel."`
- `require_user`, never `require_user_sensitive`: read state isn't in the Conventions §5.2
  fail-closed set.
- Commit, then publish. Publishers do nothing when `sio is None`.
- Socket handlers that ack are wrapped in `@_acked` and never raise.
- JSON is camelCase, SQL is snake_case. UUID v7 ids compare in time order in both Python and
  Postgres.
- No foreign key on `user_id` (it belongs to Auth) or on `last_read_id` (a retention job may
  hard-delete messages, D16).
- The lint hook runs `ruff` and eslint after every edit and blocks on findings: fix them.
  Conventions checks: `python3 .claude/hooks/checks/conventions.py`.

## File map

| File | Change | Responsibility |
|---|---|---|
| `CLAUDE.md` | modify | replace the no-tests rule |
| `src/services/messaging/tests/test_read_markers.py` | create | the unit tests |
| `src/services/messaging/messaging/alembic/versions/0003_channel_reads.py` | create | table + drop column |
| `src/services/messaging/messaging/models.py` | modify | `ChannelRead`; drop `ChannelMember.last_read_id` |
| `src/services/messaging/tests/conftest.py` | modify | add `channel_reads` to `TABLES` |
| `src/services/messaging/messaging/channels.py` | modify | `VisibleChannel` read fields, `_with_read_state`, `with_read_state=` |
| `src/services/messaging/messaging/schemas.py` | modify | `ChannelResponse` read fields, `MarkReadRequest` |
| `src/services/messaging/messaging/routers/channels.py` | modify | `_as_channel` mapping; DTO reads ask for read state |
| `src/services/messaging/messaging/read_state.py` | create | `mark_read` domain function |
| `src/services/messaging/messaging/routers/read_state.py` | create | `POST /api/v1/channels/{channel_id}/read` |
| `src/services/messaging/messaging/main.py` | modify | include the router |
| `src/services/messaging/messaging/realtime.py` | modify | `reader_room`, `publish_read_receipt`, join on connect |
| `src/services/messaging/messaging/realtime_writes.py` | modify | `MarkReadPayload`, `mark_read` handler |
| `src/frontend/openapi/messaging.json`, `src/frontend/src/types/messaging.ts` | regenerate | D23 |
| `docs/design/00-…`, `02-…`, `07-…`, `docs/adr/260915-…`, `src/services/messaging/README.md` | modify/create | decisions recorded in this slice |

`tests/bdd/conftest.py` truncates `channels … CASCADE`, which reaches `channel_reads` through its
foreign key. It is deliberately left alone: no `tests/bdd` edits at this stage.

---

## Phase 0 — rules

### Task 0: Replace the no-tests rule in CLAUDE.md

**Files:** Modify `CLAUDE.md:62` and `CLAUDE.md:149-150`

- [ ] **Step 1: Replace the rule in "Working in this repo"**

old:
```markdown
- **DO NOT WRITE ANY TESTS — until further notice.** No unit, integration or BDD tests, and no new steps, feature files or page objects in `tests/bdd`. The test approach is being rethought; the Testing section below describes the existing suites, not a mandate to extend them. This overrides any skill or workflow (TDD included) that says to write tests.
```
new:
```markdown
- **New behaviour is test-driven, with unit tests only — for now.** Write the failing unit test first (pytest, no Docker — `scripts/test.sh unit`), run it, and **stop at red** so the tests can be reviewed before any production code is written. No new integration tests, no new steps, feature files or page objects in `tests/bdd`, and no frontend tests until that is widened. Say plainly what a unit test cannot reach rather than faking a database to reach it.
```

- [ ] **Step 2: Replace the opening of "Testing"**

old:
```markdown
**Write no new tests until further notice** — see Working in this repo. The
commands below run the suites that already exist.
```
new:
```markdown
**New tests are unit tests, written first** — see Working in this repo. The
commands below run every suite; only the unit layer is growing at the moment.
```

- [ ] **Step 3: Leave uncommitted.**

---

## Phase 1 — RED

### Task 1: Write the unit tests

**Files:** Create `src/services/messaging/tests/test_read_markers.py`

**Interfaces the tests demand** (produced by Tasks 4–7):
- `messaging.channels.VisibleChannel(channel, my_role, last_read_id: uuid.UUID | None = None, unread_count: int = 0)`
- `messaging.schemas.ChannelResponse` fields `last_read_id: uuid.UUID | None`, `unread_count: int` (required)
- `messaging.schemas.MarkReadRequest` with `message_id: uuid.UUID`
- `POST /api/v1/channels/{channel_id}/read` → 204, body `MarkReadRequest`
- `messaging.realtime.reader_room(workspace_id, user_id) -> str`
- `messaging.realtime.publish_read_receipt(sio, *, workspace_id, user_id, channel_id, message_id, skip_sid=None) -> None`
- a `mark_read` handler on `/messaging`, registered by `register_write_handlers`

Imports are **modules or names that already exist**, so the file always collects. A missing
function then fails its own test instead of breaking collection for the whole file.

- [ ] **Step 1: Create the test file**

```python
"""Read markers and unread counts — the unit layer (spec §3.1, §3.2).

No Docker. These run against the real app object, the real schemas and a real
Socket.IO server with nothing listening and nothing connected.

What a unit test cannot reach is deliberately *not* faked here: the unread
count query, the forward-only upsert and the 404s behind visibility all need
Postgres to tell the truth, and a fake session would only test the fake. The
plan in docs/plans/ch07/02-read-markers-implementation-plan.md lists them.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
import socketio

from messaging import realtime
from messaging.channels import VisibleChannel
from messaging.main import create_app
from messaging.models import Channel
from messaging.realtime import NAMESPACE, RealtimeContext
from messaging.realtime_writes import register_write_handlers
from messaging.routers.channels import _as_channel
from messaging.settings import Settings

ADA = uuid.uuid4()
GRACE = uuid.uuid4()
WORKSPACE = uuid.uuid4()
OTHER_WORKSPACE = uuid.uuid4()
CHANNEL = uuid.uuid4()
MESSAGE = uuid.uuid4()
AT = datetime(2026, 9, 15, 9, 0, tzinfo=UTC)

READ_ROUTE = "/api/v1/channels/{channel_id}/read"


def _settings() -> Settings:
    """Syntactically valid and unreachable — nothing in this file dials them.

    Local rather than imported from `test_health.py`: every service has a
    `tests` package, so a cross-test import binds to whichever one pytest
    found first.
    """
    return Settings(
        postgres_dsn="postgresql+asyncpg://collabhub:collabhub@postgres:5432/collabhub_messaging",
        redis_cache_url="redis://redis-cache:6379/0",
        redis_realtime_url="redis://redis-rt:6379/0",
        redis_streams_url="redis://redis-streams:6379/0",
        elasticsearch_url="http://elasticsearch:9200",
        auth_issuer="http://localhost:8001",
        auth_jwks_url="http://auth:8000/.well-known/jwks.json",
    )


@pytest.fixture
def app():
    return create_app(_settings())


class RecordingServer:
    """Stands in for `socketio.AsyncServer` where only `emit` is called.

    Records the whole call — event, payload and every keyword — so an emit to
    the wrong room, namespace or sid fails the assertion rather than passing it.
    """

    def __init__(self) -> None:
        self.emits: list[tuple[str, Any, dict[str, Any]]] = []

    async def emit(self, event: str, data: Any = None, **kwargs: Any) -> None:
        self.emits.append((event, data, kwargs))


# --- the REST contract -----------------------------------------------------


def test_the_api_declares_a_route_to_mark_a_channel_read(app):
    """The route the SPA's generated client is built from (register D23).

    Breaks if the route is missing, is not a POST, answers anything but 204, or
    takes a body other than `{messageId}`.
    """
    doc = app.openapi()

    assert READ_ROUTE in doc["paths"]
    operation = doc["paths"][READ_ROUTE]["post"]
    assert "204" in operation["responses"]
    assert operation["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/MarkReadRequest"
    }

    request = doc["components"]["schemas"]["MarkReadRequest"]
    assert request["required"] == ["messageId"]
    assert request["properties"]["messageId"]["format"] == "uuid"


def test_a_channel_always_reports_the_callers_read_state(app):
    """Required, not optional — so the generated TypeScript is not `unreadCount?`.

    A default on either field would drop it from `required` here, and every
    sidebar render would need a null check for a value the server always has.
    """
    schema = app.openapi()["components"]["schemas"]["ChannelResponse"]

    assert {"lastReadId", "unreadCount"} <= set(schema["required"])
    assert schema["properties"]["unreadCount"]["type"] == "integer"


async def test_marking_a_channel_read_needs_an_access_token(app):
    """Breaks if the route is registered without `require_user`.

    A valid body, so the only thing wrong with the request is the missing token.
    """
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/channels/{uuid.uuid4()}/read", json={"messageId": str(uuid.uuid4())}
        )

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")


@pytest.mark.parametrize(
    ("last_read_id", "unread_count", "expected_last_read_id"),
    [
        pytest.param(MESSAGE, 3, str(MESSAGE), id="read-up-to-a-message"),
        pytest.param(None, 7, None, id="never-read"),
    ],
)
def test_the_channel_dto_carries_the_read_state_it_was_read_with(
    last_read_id, unread_count, expected_last_read_id
):
    """The mapping from the domain read to the wire shape.

    Breaks if `_as_channel` drops either field, reads one from the wrong
    attribute, or falls back to a default instead of what the query returned.
    """
    channel = Channel(
        id=CHANNEL,
        workspace_id=WORKSPACE,
        name="general",
        topic=None,
        kind="public",
        created_by=ADA,
        created_at=AT,
        updated_at=AT,
        archived_at=None,
        version=0,
    )
    visible = VisibleChannel(
        channel=channel, my_role=None, last_read_id=last_read_id, unread_count=unread_count
    )

    body = _as_channel(visible).model_dump(mode="json", by_alias=True)

    assert body["lastReadId"] == expected_last_read_id
    assert body["unreadCount"] == unread_count
    assert body["myRole"] is None


# --- the socket ------------------------------------------------------------


def test_a_readers_room_is_one_person_in_one_workspace():
    """Breaks if the room drops the workspace — the cross-workspace leak.

    One person can have a tab open in each of two workspaces, and a connection
    must never carry another workspace's traffic (Conventions §5.4).
    """
    ada_here = realtime.reader_room(WORKSPACE, ADA)

    assert realtime.reader_room(OTHER_WORKSPACE, ADA) != ada_here
    assert realtime.reader_room(WORKSPACE, GRACE) != ada_here
    # Nor can it collide with a channel's room for the same id.
    assert realtime.room(ADA) != ada_here


@pytest.mark.parametrize(
    "skip_sid",
    [
        pytest.param(None, id="from-rest"),
        pytest.param("sid-ada-tab-1", id="from-the-socket"),
    ],
)
async def test_a_read_receipt_goes_only_to_the_readers_own_sessions(skip_sid):
    """Breaks if the receipt goes to the channel's room — telling everyone in
    `#general` how far Ada has read — or to the wrong event, payload or sid.
    """
    sio = RecordingServer()

    await realtime.publish_read_receipt(
        sio,
        workspace_id=WORKSPACE,
        user_id=ADA,
        channel_id=CHANNEL,
        message_id=MESSAGE,
        skip_sid=skip_sid,
    )

    assert sio.emits == [
        (
            "read_receipt_updated",
            {"channelId": str(CHANNEL), "userId": str(ADA), "messageId": str(MESSAGE)},
            {
                "room": f"user:{WORKSPACE}:{ADA}",
                "namespace": "/messaging",
                "skip_sid": skip_sid,
            },
        )
    ]


async def test_a_read_receipt_without_a_socket_server_is_a_no_op():
    """`create_app` has no socket server; the REST route must still work.

    Breaks if the publisher loses its `None` guard, which would turn every
    `POST /read` under `ASGITransport` into a 500.
    """
    assert (
        await realtime.publish_read_receipt(
            None, workspace_id=WORKSPACE, user_id=ADA, channel_id=CHANNEL, message_id=MESSAGE
        )
        is None
    )


async def test_a_malformed_mark_read_acks_a_400_rather_than_hanging(app):
    """The failure mode that hangs a browser: a handler that raises sends no ack.

    Breaks if `mark_read` is not registered, is not wrapped in `@_acked`, or
    does not require `messageId`. The payload is rejected before the handler
    reads a session, so no connection is needed to reach it.
    """
    context = RealtimeContext(
        settings=app.state.settings,
        sessions=app.state.sessions,
        security=app.state.security,
        jobs=app.state.jobs,
    )
    sio = socketio.AsyncServer(async_mode="asgi")
    register_write_handlers(sio, context)

    handler = sio.handlers[NAMESPACE].get("mark_read")
    assert handler is not None, "no mark_read handler on /messaging"

    ack = await handler("sid-ada-tab-1", {"channelId": str(CHANNEL)})

    assert ack["ok"] is False
    assert ack["problem"]["status"] == 400
```

- [ ] **Step 2: Let the lint hook run; fix anything it blocks on.** The likely candidates are
      import order or line length. Don't change any assertions.

### Task 2: Run them red, then STOP

- [ ] **Step 1: Run the new file**

Run: `uv run pytest src/services/messaging/tests/test_read_markers.py -v`

Expected: **10 failed, 0 passed, 0 errors at collection.** Each test should fail for this reason:

| Test | Expected failure |
|---|---|
| `…declares_a_route_to_mark_a_channel_read` | `AssertionError` — the route is not in `doc["paths"]` |
| `…always_reports_the_callers_read_state` | `AssertionError` — `lastReadId`/`unreadCount` not in `required` |
| `…needs_an_access_token` | `assert 404 == 401` — no such route yet |
| `…carries_the_read_state…[read-up-to-a-message]` | `TypeError` — `VisibleChannel` has no `last_read_id` |
| `…carries_the_read_state…[never-read]` | same `TypeError` |
| `…readers_room_is_one_person_in_one_workspace` | `AttributeError` — no `realtime.reader_room` |
| `…goes_only_to_the_readers_own_sessions[from-rest]` | `AttributeError` — no `realtime.publish_read_receipt` |
| `…goes_only_to_the_readers_own_sessions[from-the-socket]` | same `AttributeError` |
| `…without_a_socket_server_is_a_no_op` | same `AttributeError` |
| `…malformed_mark_read_acks_a_400…` | `AssertionError: no mark_read handler on /messaging` |

If a test **passes**, it's testing behaviour that already exists: fix the test. If a test fails
for a **different** reason (an import error, a settings error, a fixture error), fix that and
run again until the table matches.

- [ ] **Step 2: Confirm nothing else moved**

Run: `uv run pytest -m "not integration and not bdd" -q`
Expected: `10 failed, 102 passed`.

- [ ] **Step 3: STOP.** Report the red output (the table above, filled in with the real messages)
      and wait for review. **Do not start Phase 2 until Elton says to.**

---

## Phase 2 — GREEN

### Task 3: The table (no unit test drives this — see "What no unit test covers")

**Files:**
- Create: `src/services/messaging/messaging/alembic/versions/0003_channel_reads.py`
- Modify: `src/services/messaging/messaging/models.py:100-123`
- Modify: `src/services/messaging/tests/conftest.py:45`

**Interfaces:** Produces `messaging.models.ChannelRead` with `channel_id`, `user_id`,
`last_read_id`, `updated_at`.

- [ ] **Step 1: Create the migration**

```python
"""Read state.

A table of its own rather than the `last_read_id` column `0001` shipped on
`channel_members`, and that column is dropped here. Membership is not what
gates reading a channel — visibility is (spec §3.1.1) — and nobody in this
scope can add themselves to a channel, so a pointer on the membership row would
give Grace no unread count in a public `#general` she reads every day.

Two columns the conventions would expect are absent on purpose:

* **No `version`.** The pointer only moves forward — the upsert is guarded by
  `last_read_id < excluded.last_read_id` — so there is no lost update for
  optimistic concurrency to catch, and nothing for a client to conflict on.
* **No foreign key on `last_read_id`.** A retention job may hard-delete messages
  (register D16), and a marker must not stop it. `user_id` carries none either:
  users are Auth's rows (Conventions §2).

No index beyond the primary key: every read of this table is one
`(channel_id, user_id)` pair, joined from the channel row.

Revision ID: 0003
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMPTZ = TIMESTAMP(timezone=True)


def upgrade() -> None:
    op.create_table(
        "channel_reads",
        sa.Column(
            "channel_id",
            UUID(as_uuid=True),
            sa.ForeignKey("channels.id"),
            primary_key=True,
        ),
        sa.Column("user_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("last_read_id", UUID(as_uuid=True), nullable=False),
        sa.Column("updated_at", TIMESTAMPTZ, nullable=False, server_default=sa.func.now()),
    )
    op.drop_column("channel_members", "last_read_id")


def downgrade() -> None:
    op.add_column(
        "channel_members", sa.Column("last_read_id", UUID(as_uuid=True), nullable=True)
    )
    op.drop_table("channel_reads")
```

- [ ] **Step 2: Update the models.** Delete this line from `ChannelMember`:

```python
    last_read_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
```

Then add this class after `ChannelMember`:

```python
class ChannelRead(Base):
    """How far one person has read in one channel.

    Keyed on the channel and the person, not on membership: anyone who can see
    a channel can read it, so anyone who can see it has a place they read up
    to. See `0003_channel_reads` for why there is no `version` and no foreign key
    on `last_read_id`.
    """

    __tablename__ = "channel_reads"

    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("channels.id"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    last_read_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        Timestamp, nullable=False, server_default=func.now()
    )
```

- [ ] **Step 3: Truncate the new table in the integration fixtures**

```python
TABLES = "messages, channel_reads, channel_members, channels"
```

- [ ] **Step 4: Run the unit layer.** Run `uv run pytest -m "not integration and not bdd" -q`.
      Expected: still `10 failed, 102 passed`, since nothing the tests look at has changed.

### Task 4: Read state on the Channel DTO → tests 2, 4

**Files:**
- Modify: `src/services/messaging/messaging/channels.py`
- Modify: `src/services/messaging/messaging/schemas.py`
- Modify: `src/services/messaging/messaging/routers/channels.py`

**Interfaces:**
- Consumes: `ChannelRead` (Task 3)
- Produces: `VisibleChannel(channel, my_role, last_read_id=None, unread_count=0)`;
  `channels.get_visible(..., with_read_state: bool = False)`; `channels.list_page` always with read
  state; `ChannelResponse.last_read_id`, `ChannelResponse.unread_count` (required).

- [ ] **Step 1: `channels.py`, the dataclass and imports**

```python
from messaging.models import (
    ADMIN,
    CREATABLE_KINDS,
    MEMBER,
    PUBLIC,
    Channel,
    ChannelMember,
    ChannelRead,
    Message,
)
```

```python
@dataclass(frozen=True)
class VisibleChannel:
    """A channel plus the caller's relationship to it.

    The role is part of the read rather than a second query, because the sidebar
    needs it for every row and the UI decides what to offer from it.

    The read state is filled only by the reads that build a `Channel` DTO —
    `list_page`, and `get_visible(with_read_state=True)`. The guards every write
    path runs leave it at its defaults and do not pay for a count.
    """

    channel: Channel
    my_role: str | None
    last_read_id: uuid.UUID | None = None
    unread_count: int = 0
```

- [ ] **Step 2: `channels.py`, add `_with_read_state` below `_visible_query`**

```python
def _with_read_state(query: Select, user_id: uuid.UUID) -> Select:
    """Add the caller's marker and unread count to a `_visible_query`.

    Unread is every message after the marker that **someone else** wrote and
    that **is not deleted** — with no marker, every such message in the
    channel. Your own messages are never unread to you, and a tombstone is not
    something to catch up on.

    A correlated count per channel row. `ix_messages_channel_time` is
    `(channel_id, id DESC)`, so `id > last_read_id` is a range on it; the
    author and `deleted_at` tests are filters on the rows in that range.

    Not folded into `_visible_query`: `send_message`, `join_channel` and every
    member route authorize through that query, and none of them should pay for
    a count they never read.
    """
    unread = (
        select(func.count(Message.id))
        .where(
            Message.channel_id == Channel.id,
            Message.author_id != user_id,
            Message.deleted_at.is_(None),
            or_(ChannelRead.last_read_id.is_(None), Message.id > ChannelRead.last_read_id),
        )
        .correlate(Channel, ChannelRead)
        .scalar_subquery()
    )
    return query.outerjoin(
        ChannelRead,
        (ChannelRead.channel_id == Channel.id) & (ChannelRead.user_id == user_id),
    ).add_columns(ChannelRead.last_read_id, unread)
```

- [ ] **Step 3: `channels.py`, `list_page` and `get_visible`**

In `list_page`, change the first line and the row mapping:

```python
    query = _with_read_state(_visible_query(workspace_id, user_id), user_id)
```
```python
    result = await session.execute(query.limit(page.fetch_limit))
    rows = [VisibleChannel(*row) for row in result.all()]
```

Replace `get_visible`:

```python
async def get_visible(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    channel_id: uuid.UUID,
    with_read_state: bool = False,
) -> VisibleChannel | None:
    """One channel, if this caller is allowed to know it exists.

    `None` covers every negative case — wrong workspace, archived, private and
    not a member, or simply absent — because the router turns them all into the
    same 404 on purpose.

    `with_read_state` is for the routes that return a `Channel` DTO. A guard
    leaves it off; the row then carries the dataclass defaults, which nothing on
    that path serializes.
    """
    query = _visible_query(workspace_id, user_id)
    if with_read_state:
        query = _with_read_state(query, user_id)
    row = (await session.execute(query.where(Channel.id == channel_id))).first()
    return VisibleChannel(*row) if row else None
```

- [ ] **Step 4: `schemas.py`.** `ChannelResponse` gets two required fields before `my_role`, and
      one paragraph added to its docstring:

```python
    version: int
    last_read_id: uuid.UUID | None
    unread_count: int
    my_role: str | None = None
```

Docstring paragraph to append:

```
    `lastReadId` and `unreadCount` are required and have no default, on purpose:
    a default drops a field from the OpenAPI `required` list, and the generated
    TypeScript would make every sidebar render null-check a count the server
    always sends. A channel just created reports `null` and `0`.
```

- [ ] **Step 5: `routers/channels.py`, `_as_channel` and `_visible_or_404`**

```python
def _as_channel(visible: channels.VisibleChannel) -> ChannelResponse:
    """The DTO, built field by field.

    Not `model_validate(visible.channel, from_attributes=True)` any more: the
    read state is on the `VisibleChannel`, not the row, and the DTO requires it.
    """
    channel = visible.channel
    return ChannelResponse(
        id=channel.id,
        name=channel.name,
        topic=channel.topic,
        kind=channel.kind,
        created_by=channel.created_by,
        created_at=channel.created_at,
        updated_at=channel.updated_at,
        archived_at=channel.archived_at,
        version=channel.version,
        last_read_id=visible.last_read_id,
        unread_count=visible.unread_count,
        my_role=visible.my_role,
    )


async def _visible_or_404(
    session: AsyncSession,
    principal: UserPrincipal,
    channel_id: uuid.UUID,
    *,
    with_read_state: bool = False,
) -> channels.VisibleChannel:
    """The channel, or the 404 that covers every reason it is not available."""
    found = await channels.get_visible(
        session,
        workspace_id=principal.workspace_id,
        user_id=principal.user_id,
        channel_id=channel_id,
        with_read_state=with_read_state,
    )
    if found is None:
        raise ProblemException.not_found("No such channel.")
    return found
```

These three routes return a `Channel` DTO and must ask for read state:

- `get_channel`: replace its body with `return _as_channel(await _visible_or_404(session, principal, channel_id, with_read_state=True))`
- `update_channel`: the re-read becomes `updated = await _visible_or_404(session, principal, channel_id, with_read_state=True)`
- `archive_channel`: the guard becomes `visible = await _visible_or_404(session, principal, channel_id, with_read_state=True)`

`create_channel` needs no change: `channels.create` returns `VisibleChannel(channel, ADMIN)`,
whose defaults `None` and `0` are correct for a channel created a moment ago.

- [ ] **Step 6: Run the group**

Run: `uv run pytest src/services/messaging/tests/test_read_markers.py -v -k "reports_the_callers_read_state or carries_the_read_state"`
Expected: 3 passed.

- [ ] **Step 7: Run the unit layer.** Run `uv run pytest -m "not integration and not bdd" -q`.
      Expected: `7 failed, 105 passed`.

### Task 5: Marking read over REST → tests 1, 3

**Files:**
- Create: `src/services/messaging/messaging/read_state.py`
- Create: `src/services/messaging/messaging/routers/read_state.py`
- Modify: `src/services/messaging/messaging/schemas.py` (add `MarkReadRequest`)
- Modify: `src/services/messaging/messaging/main.py`

**Interfaces:**
- Consumes: `channels.get_visible`, `messages.get`, `ChannelRead`, and
  `realtime.publish_read_receipt` (Task 6)
- Produces: `read_state.mark_read(session, *, workspace_id, user_id, channel_id, message_id) -> bool | None`.
  It returns `None` when the channel isn't visible or the message isn't in it, `True` when the
  marker moved, and `False` when it was already there or further on.

Task 6 adds `realtime.publish_read_receipt`. This route calls it, so do Task 6 **Step 1** first
if running these tasks in a different order. Otherwise the route fails with an import-time
`AttributeError` only when it's called, and test 3 still passes, because `require_user` refuses
the request first.

- [ ] **Step 1: `schemas.py`, append**

```python
class MarkReadRequest(CamelRequest):
    """Mark a channel read up to and including one message.

    The message must be in the channel named by the path. Marking an older
    message than the one already marked is accepted and changes nothing — two
    tabs racing each other is the normal case, not a conflict.
    """

    message_id: uuid.UUID
```

- [ ] **Step 2: Create `read_state.py`**

```python
"""Read state — how far each person has read in each channel.

Same shape as `channels.py` and `messages.py`: plain async functions taking an
`AsyncSession`, no FastAPI imports, so the REST route and the `mark_read` socket
event share one set of rules.

**Visibility gates it, not membership.** Anyone who can see a channel can read
it, so anyone who can see it may say how far they have read. The row lives in
`channel_reads`, not on `channel_members`, for exactly that reason.

**The marker only moves forward.** The upsert is guarded, so an older message
arriving after a newer one — two tabs, or a slow request — is a no-op rather
than a step backwards. UUID v7 ids sort by time in Postgres as they do here.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from messaging import channels, messages
from messaging.models import ChannelRead


async def mark_read(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    channel_id: uuid.UUID,
    message_id: uuid.UUID,
) -> bool | None:
    """Move the caller's marker in a channel up to `message_id`.

    `None` when the caller cannot see the channel, or the message is not in it
    — one answer for both, so the router gives one 404 and an id cannot be
    probed. `True` when the marker moved; `False` when it was already there or
    further on, which callers use to skip a broadcast that would say nothing.

    A tombstone may be marked read: it is part of the history the caller is
    looking at.
    """
    visible = await channels.get_visible(
        session, workspace_id=workspace_id, user_id=user_id, channel_id=channel_id
    )
    if visible is None:
        return None

    message = await messages.get(session, message_id=message_id)
    if message is None or message.channel_id != channel_id:
        return None

    proposed = insert(ChannelRead).values(
        channel_id=channel_id, user_id=user_id, last_read_id=message_id
    )
    statement = proposed.on_conflict_do_update(
        index_elements=[ChannelRead.channel_id, ChannelRead.user_id],
        set_={"last_read_id": proposed.excluded.last_read_id, "updated_at": func.now()},
        where=ChannelRead.last_read_id < proposed.excluded.last_read_id,
    )
    result = await session.execute(statement)
    return result.rowcount == 1
```

- [ ] **Step 3: Create `routers/read_state.py`**

```python
"""Marking a channel read (spec §3.1).

Its own module because it is its own resource: a per-person pointer, not a
channel attribute and not a message. The rules are the service's usual ones —
workspace from the token, a channel you cannot see is a 404, plain
`require_user`, commit then publish.
"""

from __future__ import annotations

import uuid

import socketio
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from messaging import read_state, realtime
from messaging.db import session as db_session
from messaging.schemas import MarkReadRequest
from shared import ProblemException, UserPrincipal, require_user

router = APIRouter(prefix="/api/v1/channels", tags=["read-state"])


@router.post("/{channel_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(
    channel_id: uuid.UUID,
    body: MarkReadRequest,
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
    sio: socketio.AsyncServer | None = Depends(realtime.server),
) -> None:
    """Mark a channel read up to and including one message.

    **204 either way** — whether the marker moved or was already further on.
    The client sent the newest message it has shown, and "you had already read
    that" is not an error it could act on.

    The receipt goes to the caller's *other* sessions only, and only when the
    marker moved. Nobody else is told how far anyone has read.
    """
    advanced = await read_state.mark_read(
        session,
        workspace_id=principal.workspace_id,
        user_id=principal.user_id,
        channel_id=channel_id,
        message_id=body.message_id,
    )
    if advanced is None:
        raise ProblemException.not_found("No such channel.")

    await session.commit()
    if advanced:
        await realtime.publish_read_receipt(
            sio,
            workspace_id=principal.workspace_id,
            user_id=principal.user_id,
            channel_id=channel_id,
            message_id=body.message_id,
        )
```

- [ ] **Step 4: `main.py`.** Import the router, then include it after the message routers:

```python
from messaging.routers import read_state as read_state_routes
```
```python
    app.include_router(read_state_routes.router)
```

- [ ] **Step 5: Run the group**

Run: `uv run pytest src/services/messaging/tests/test_read_markers.py -v -k "declares_a_route or needs_an_access_token"`
Expected: 2 passed.

- [ ] **Step 6: Run the unit layer.** Expected: `5 failed, 107 passed`.

### Task 6: The reader's room and the receipt → tests 5, 6, 7

**Files:** Modify `src/services/messaging/messaging/realtime.py`

**Interfaces:** Produces `reader_room(workspace_id, user_id) -> str` and
`publish_read_receipt(sio, *, workspace_id, user_id, channel_id, message_id, skip_sid=None) -> None`.

- [ ] **Step 1: Add below `room`**

```python
def reader_room(workspace_id: uuid.UUID | str, user_id: uuid.UUID | str) -> str:
    """One person's own connections, in one workspace — where read receipts go.

    The workspace is in the name because one person can have a tab open in each
    of two workspaces, and a connection must never carry another workspace's
    traffic (Conventions §5.4). Every connection joins this room on connect.
    """
    return f"user:{workspace_id}:{user_id}"
```

- [ ] **Step 2: Add at the end of the outbound half**

```python
async def publish_read_receipt(
    sio: socketio.AsyncServer | None,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    channel_id: uuid.UUID,
    message_id: uuid.UUID,
    skip_sid: str | None = None,
) -> None:
    """Tell the reader's other sessions how far they have read.

    **To the reader's own room, never the channel's.** Everyone in `#general`
    learning how far Ada has read is a feature nobody asked for and a privacy
    decision nobody made.

    `skip_sid` is the connection the read arrived on, when it arrived over the
    socket — that tab already knows. A REST read skips nobody.
    """
    if sio is None:
        return

    await sio.emit(
        "read_receipt_updated",
        {"channelId": str(channel_id), "userId": str(user_id), "messageId": str(message_id)},
        room=reader_room(workspace_id, user_id),
        namespace=NAMESPACE,
        skip_sid=skip_sid,
    )
```

- [ ] **Step 3: Join the reader room in `connect`**, directly after `save_session`:

```python
        # Read receipts from this person's other sessions arrive here.
        await server.enter_room(
            sid, reader_room(principal.workspace_id, principal.user_id), namespace=NAMESPACE
        )
```

- [ ] **Step 4: Run the group**

Run: `uv run pytest src/services/messaging/tests/test_read_markers.py -v -k "readers_room or read_receipt"`
Expected: 4 passed.

- [ ] **Step 5: Run the unit layer.** Expected: `1 failed, 111 passed`.

### Task 7: `mark_read` over the socket → test 8

**Files:** Modify `src/services/messaging/messaging/realtime_writes.py`

**Interfaces:** Consumes `read_state.mark_read` (Task 5) and `realtime.publish_read_receipt`
(Task 6).

- [ ] **Step 1: Imports and payload**

```python
from messaging import channels, indexing, messages, read_state, realtime
```

```python
class MarkReadPayload(CamelRequest):
    """`mark_read`: `{channelId, messageId}` (spec §3.2)."""

    channel_id: uuid.UUID
    message_id: uuid.UUID
```

- [ ] **Step 2: Handler.** Add it inside `register_write_handlers`, after `delete_message`:

```python
    @sio.event(namespace=NAMESPACE)
    @_acked
    async def mark_read(sid: str, payload: Any) -> dict[str, Any]:
        """Move the caller's read marker; tell their other sessions if it moved.

        A write, so it gets the write checks — expiry and the denylist, failing
        open — even though what it writes is only ever the caller's own.
        """
        event = _parse(MarkReadPayload, payload)
        principal = await principal_of(sid)
        await check_revoked(principal)

        async with context.sessions() as session:
            advanced = await read_state.mark_read(
                session,
                workspace_id=principal.workspace_id,
                user_id=principal.user_id,
                channel_id=event.channel_id,
                message_id=event.message_id,
            )
            if advanced is None:
                raise ProblemException.not_found("No such channel.")
            await session.commit()

        if advanced:
            await realtime.publish_read_receipt(
                sio,
                workspace_id=principal.workspace_id,
                user_id=principal.user_id,
                channel_id=event.channel_id,
                message_id=event.message_id,
                # This tab already knows; the broadcast is for the others.
                skip_sid=sid,
            )
        return _ok()
```

- [ ] **Step 3: Module docstring.** Change "Four rules run through every write handler here —
      `send_message`, `edit_message` and `delete_message`." to "Four rules run through every
      write handler here — `send_message`, `edit_message`, `delete_message` and `mark_read`."

- [ ] **Step 4: Run the file**

Run: `uv run pytest src/services/messaging/tests/test_read_markers.py -v`
Expected: 10 passed.

- [ ] **Step 5: Run the unit layer.** Expected: `112 passed`.

---

## Phase 3 — REFACTOR

### Task 8: Tidy, staying green

- [ ] **Step 1: Look for these, and fix only what's actually there**
  - The REST route and the socket handler both translate `mark_read`'s `None` into the same 404
    and call the same publisher. If the two blocks read identically, leave them alike rather than
    extracting a helper. `send_message`, `edit_message` and `delete_message` already mirror their
    routers this way, and one transport-specific difference (`skip_sid`) is the reason to keep
    them separate.
  - `routers/channels.py` `get_channel` should now be one line through `_visible_or_404`. Remove
    any leftover inline `get_visible` call.
  - Docstrings that still say read receipts are unbuilt: `messaging/models.py` module docstring,
    `0001_channels.py` stays as history, and `realtime.py`'s module docstring if it lists the
    rooms a connection joins.
- [ ] **Step 2: Run `uv run ruff check src/services/messaging && uv run ruff format --check src/services/messaging`.**
- [ ] **Step 3: Run `python3 .claude/hooks/checks/conventions.py`.** Expected: no findings. CH009
      is satisfied by `Message.deleted_at` in `_with_read_state`.
- [ ] **Step 4: Run the unit layer.** Expected: `112 passed`.

---

## Finish

### Task 9: Record the decisions in this slice

**Files:** `docs/design/02-messaging-service.md`, `docs/design/00-platform-conventions.md`,
`docs/design/07-open-decisions-register.md`, `docs/adr/260915-read-state-follows-visibility.md`,
`src/services/messaging/README.md`, `CLAUDE.md`

- [ ] **Step 1: Doc 02**
  - §3.1 table, `POST /channels/{id}/read`: change Auth from "channel member" to "see §3.1.7".
    Change Purpose to "Mark read up to `{ "messageId": "..." }`. 204; the marker only moves
    forward."
  - §3.1.3 `Channel` DTO: add `"lastReadId": "uuid|null", "unreadCount": 0`, plus one paragraph
    (decision 6).
  - New **§3.1.7 Read state — added 2026-09-15**, with decisions 2–5, 7 and 10 as short rules,
    in the same voice as §3.1.1.
  - §3.1.5: delete the `POST /channels/{id}/read` row. In the closing paragraph, remove
    "and `last_read_id` on `channel_members`".
  - §3.2 client table, `mark_read`: "Update read marker; ack `{ok: true}`; broadcast
    `read_receipt_updated` to the reader's own room `user:{workspaceId}:{userId}`, skipping this
    connection." Server table: note the room.
  - §3.2.4 check table: "the three write events only" becomes "the four write events —
    `send_message`, `edit_message`, `delete_message`, `mark_read`".
  - §4 DDL: remove `last_read_id` from `channel_members`, and add the `channel_reads` DDL with
    the migration's reasoning as comments. Replace "Read state is a per-member pointer
    (`last_read_id`); unread counts are derived (messages with `id > last_read_id`)." with the
    decision 3 rule.
- [ ] **Step 2: Conventions §6, rooms bullet.** Append: "A connection also joins its reader room,
      `user:{workspaceId}:{userId}` — one person in one workspace — for events addressed to that
      person's own sessions."
- [ ] **Step 3: Register.** Add a row **D31**, "Read state keying and unread semantics", 🟢
      Decided 2026-09-15. Notes: a `channel_reads` table gated on visibility, a forward-only
      marker, unread = others' non-deleted messages after the marker, receipts to the reader's
      own room. Owner: Messaging. Link the ADR. Follow the existing column layout of the rows
      above it.
- [ ] **Step 4: ADR.** Use the `adr-writer` skill: "Read state follows channel visibility, not
      membership". Context is §3.1.1 and the no-self-join rule. The alternatives considered are
      the members-only column and a capped count.
- [ ] **Step 5: README.** Under "What is built", add `POST /api/v1/channels/{id}/read`, socket
      `mark_read` and `read_receipt_updated`, and `lastReadId`/`unreadCount` on channels. Remove
      "read receipts" from "Not built".
- [ ] **Step 6: CLAUDE.md.** Add `D31 read state follows visibility` to the "Settled so far"
      list.

### Task 10: Regenerate and verify

- [ ] **Step 1: Run `uv run python -m messaging.openapi > src/frontend/openapi/messaging.json`.**
- [ ] **Step 2: Run `cd src/frontend && npm run generate:api && npm run typecheck`.** Expected:
      clean. No SPA code builds a `Channel` by hand, which was checked while writing this plan.
- [ ] **Step 3: Run `scripts/test.sh unit`.** Expected: `112 passed`.
- [ ] **Step 4: Run `scripts/test.sh integration -- src/services/messaging`** (needs Docker).
      Expected: every existing test passes. This is the regression check that migration `0003`
      applies and that the changed list and detail queries still run.
- [ ] **Step 5: Run `scripts/test.sh lint`.** Expected: passes.
- [ ] **Step 6: Check by hand what no test covers**, against `docker compose up -d --build` on the
      development stack. `$TOKEN` is an access token from the signed-in SPA (devtools → any
      `/api/v1` request's `Authorization` header). `$ADA` and `$GRACE` are two signed-in users.
  1. Ada creates `#read-check`, then Grace posts three messages. `GET /api/v1/channels` as Ada
     shows `unreadCount: 3, lastReadId: null`.
  2. Ada marks the second message read: `curl -s -o /dev/null -w '%{http_code}' -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"messageId":"<second>"}' http://localhost:8002/api/v1/channels/<id>/read`.
     Expect `204`, then `unreadCount: 1`.
  3. Ada marks the *first* message read. Expect `204` and still `unreadCount: 1` (forward-only).
  4. Ada posts a message. Expect still `unreadCount: 1` (own messages excluded).
  5. Grace deletes her third message. Expect `unreadCount: 0` (tombstones excluded).
  6. Ada marks read a message id from a different channel, and a random UUID. Expect `404` both
     times.
  7. With two SPA tabs open as Ada, a REST mark-read in one produces `read_receipt_updated` in
     the other (devtools → WS frames), and in no tab of Grace's.
- [ ] **Step 7: Leave uncommitted.** Report what changed and the results of steps 3–6.

---

## Not in this plan

- **SPA badges, marking read on view (throttled, doc 06 §5.2) and `read_receipt_updated`
  handling.** These need a decision on how the frontend is tested first.
- **Integration coverage** of the list in "What no unit test covers", when the test layers widen.
- **A cap on the unread count**, if decision 3's risk turns out to be real.
