"""The Socket.IO handshake, the rooms, and the broadcasts (spec §3.2).

Against a real uvicorn on an ephemeral port, with the real Postgres and Redis
containers — not `ASGITransport`, which cannot carry a WebSocket and, more to
the point, wraps a `create_app` whose `app.state.realtime` is `None`. A REST
write through that publishes nothing, so a test that used it would prove the
opposite of what it claims.

What is here and deliberately not in the Gherkin: every way a handshake can be
refused. A browser cannot be made to present a malformed or service-audience
token without lying about what the app does.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import httpx
import pytest
import socketio

pytestmark = pytest.mark.integration

#: Long enough that a slow container does not fail a test, short enough that a
#: genuinely absent broadcast does not cost a minute.
WAIT = 5


async def connected(url: str, token: str) -> socketio.AsyncSimpleClient:
    client = socketio.AsyncSimpleClient()
    await client.connect(
        url, namespace="/messaging", auth={"token": token}, transports=["websocket"]
    )
    return client


async def rest(url: str, headers: dict[str, str]) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=url, headers=headers)


async def make_channel(client: httpx.AsyncClient, name="general", **body) -> dict:
    response = await client.post("/api/v1/channels", json={"name": name, **body})
    assert response.status_code == 201, response.text
    return response.json()


# --- the handshake ---------------------------------------------------------


async def test_a_valid_token_connects(realtime_url, tokens):
    client = await connected(realtime_url, tokens.mint())

    assert client.connected

    await client.disconnect()


async def test_the_token_may_come_from_the_query_string(realtime_url, tokens):
    """Conventions §6's fallback, for clients that cannot set the auth payload.

    The fallback and not the primary, because a query string ends up in access
    logs.
    """
    client = socketio.AsyncSimpleClient()
    await client.connect(
        f"{realtime_url}?access_token={tokens.mint()}",
        namespace="/messaging",
        transports=["websocket"],
    )

    assert client.connected

    await client.disconnect()


@pytest.mark.parametrize(
    "token",
    [
        pytest.param(None, id="absent"),
        pytest.param("not-a-jwt", id="malformed"),
    ],
)
async def test_a_bad_token_is_refused(realtime_url, token):
    client = socketio.AsyncSimpleClient()

    with pytest.raises(socketio.exceptions.ConnectionError):
        await client.connect(
            realtime_url,
            namespace="/messaging",
            auth={"token": token} if token else {},
            transports=["websocket"],
        )


async def test_an_expired_token_is_refused(realtime_url, tokens):
    client = socketio.AsyncSimpleClient()

    with pytest.raises(socketio.exceptions.ConnectionError):
        await client.connect(
            realtime_url,
            namespace="/messaging",
            auth={"token": tokens.mint(lifetime=timedelta(minutes=-5))},
            transports=["websocket"],
        )


async def test_a_service_token_is_refused(realtime_url, tokens):
    """The audience split holds on the socket exactly as it does on HTTP."""
    client = socketio.AsyncSimpleClient()

    with pytest.raises(socketio.exceptions.ConnectionError):
        await client.connect(
            realtime_url,
            namespace="/messaging",
            auth={"token": tokens.mint(aud="collabhub-internal", sub="service:worker")},
            transports=["websocket"],
        )


# --- joining rooms ---------------------------------------------------------


async def test_joining_a_public_channel_needs_no_membership(realtime_url, tokens):
    """The room mirrors the read rule, not the membership rule.

    Grace has never joined `#general`. Authorizing the room on membership would
    make a public channel broadcast only to whoever had been added to it — and
    nothing in this scope lets anyone add themselves.
    """
    async with await rest(realtime_url, tokens.header()) as ada_http:
        channel = await make_channel(ada_http, "general")

    grace = await connected(realtime_url, tokens.mint(user_id=tokens.GRACE))
    ack = await grace.call("join_channel", channel["id"], timeout=WAIT)

    assert ack == {"ok": True}

    await grace.disconnect()


async def test_joining_a_private_channel_you_are_not_in_acks_a_404(realtime_url, tokens):
    async with await rest(realtime_url, tokens.header()) as ada_http:
        channel = await make_channel(ada_http, "launch-plans", kind="private")

    grace = await connected(realtime_url, tokens.mint(user_id=tokens.GRACE))
    ack = await grace.call("join_channel", channel["id"], timeout=WAIT)

    assert ack["ok"] is False
    # 404 and never 403 — a 403 would confirm the channel exists.
    assert ack["problem"]["status"] == 404
    assert ack["problem"]["type"] == "https://collabhub.dev/problems/not-found"

    await grace.disconnect()


async def test_joining_another_workspaces_channel_acks_a_404(realtime_url, tokens):
    async with await rest(realtime_url, tokens.header()) as ada_http:
        channel = await make_channel(ada_http, "general")

    elsewhere = await connected(realtime_url, tokens.mint(workspace_id=tokens.OTHER_WORKSPACE))
    ack = await elsewhere.call("join_channel", channel["id"], timeout=WAIT)

    assert ack["ok"] is False
    assert ack["problem"]["status"] == 404

    await elsewhere.disconnect()


async def test_joining_a_channel_that_does_not_exist_acks_a_404(realtime_url, tokens):
    client = await connected(realtime_url, tokens.mint())

    ack = await client.call("join_channel", str(uuid.uuid4()), timeout=WAIT)

    assert ack["ok"] is False
    assert ack["problem"]["status"] == 404

    await client.disconnect()


# --- the broadcasts --------------------------------------------------------


async def test_a_rest_send_reaches_a_joined_client(realtime_url, tokens):
    """The whole point of the slice, at its smallest.

    Ada writes over REST; Grace, who joined the room and never joined the
    channel, receives it.
    """
    async with await rest(realtime_url, tokens.header()) as ada_http:
        channel = await make_channel(ada_http, "general")

        grace = await connected(realtime_url, tokens.mint(user_id=tokens.GRACE))
        assert (await grace.call("join_channel", channel["id"], timeout=WAIT))["ok"]

        await ada_http.post(
            f"/api/v1/channels/{channel['id']}/messages", json={"body": "the coffee has arrived"}
        )
        event, payload = await grace.receive(timeout=WAIT)

    assert event == "message_received"
    # camelCase, exactly as the REST route returns it — the SPA writes both into
    # one cache entry and reads them through one generated type.
    assert payload["body"] == "the coffee has arrived"
    assert payload["channelId"] == channel["id"]
    assert payload["authorId"] == str(tokens.ADA)
    assert isinstance(payload["createdAt"], str)

    await grace.disconnect()


async def test_an_edit_and_a_delete_both_broadcast(realtime_url, tokens):
    async with await rest(realtime_url, tokens.header()) as ada_http:
        channel = await make_channel(ada_http, "general")

        grace = await connected(realtime_url, tokens.mint(user_id=tokens.GRACE))
        assert (await grace.call("join_channel", channel["id"], timeout=WAIT))["ok"]

        sent = (
            await ada_http.post(
                f"/api/v1/channels/{channel['id']}/messages", json={"body": "standup at four"}
            )
        ).json()
        assert (await grace.receive(timeout=WAIT))[0] == "message_received"

        await ada_http.patch(
            f"/api/v1/messages/{sent['id']}",
            json={"body": "standup at five", "version": sent["version"]},
        )
        edited_event, edited = await grace.receive(timeout=WAIT)

        await ada_http.delete(f"/api/v1/messages/{sent['id']}")
        deleted_event, deleted = await grace.receive(timeout=WAIT)

    assert edited_event == "message_edited"
    assert edited["body"] == "standup at five"
    assert edited["editedAt"] is not None

    assert deleted_event == "message_deleted"
    # The full redacted message, not `{messageId, channelId}`: the row stays in
    # the history and the client has to render the tombstone.
    assert deleted["id"] == sent["id"]
    assert deleted["body"] == ""
    assert deleted["deletedAt"] is not None

    await grace.disconnect()


async def test_a_client_in_another_room_receives_nothing(realtime_url, tokens):
    async with await rest(realtime_url, tokens.header()) as ada_http:
        general = await make_channel(ada_http, "general")
        random = await make_channel(ada_http, "random")

        grace = await connected(realtime_url, tokens.mint(user_id=tokens.GRACE))
        assert (await grace.call("join_channel", random["id"], timeout=WAIT))["ok"]

        await ada_http.post(
            f"/api/v1/channels/{general['id']}/messages", json={"body": "only for general"}
        )

        # socketio raises its own `TimeoutError`, not asyncio's.
        with pytest.raises(socketio.exceptions.TimeoutError):
            await grace.receive(timeout=2)

    await grace.disconnect()


async def test_leaving_a_room_stops_the_broadcasts(realtime_url, tokens):
    async with await rest(realtime_url, tokens.header()) as ada_http:
        channel = await make_channel(ada_http, "general")

        grace = await connected(realtime_url, tokens.mint(user_id=tokens.GRACE))
        assert (await grace.call("join_channel", channel["id"], timeout=WAIT))["ok"]
        assert (await grace.call("leave_channel", channel["id"], timeout=WAIT))["ok"]

        await ada_http.post(
            f"/api/v1/channels/{channel['id']}/messages", json={"body": "anyone there"}
        )

        # socketio raises its own `TimeoutError`, not asyncio's.
        with pytest.raises(socketio.exceptions.TimeoutError):
            await grace.receive(timeout=2)

    await grace.disconnect()


# --- the wrapper ------------------------------------------------------------


async def test_the_health_endpoint_still_answers_through_the_socket_wrapper(realtime_url):
    """The Compose healthcheck calls this, and it now goes through `ASGIApp`.

    Verified rather than assumed: everything that is not the engine.io path
    falls through to the FastAPI app, and if it ever stopped doing so the
    symptom would be every container reporting unhealthy.
    """
    async with httpx.AsyncClient(base_url=realtime_url) as client:
        response = await client.get("/health/live")

    assert response.status_code == 200
