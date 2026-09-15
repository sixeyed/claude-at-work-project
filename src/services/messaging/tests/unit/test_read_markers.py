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
