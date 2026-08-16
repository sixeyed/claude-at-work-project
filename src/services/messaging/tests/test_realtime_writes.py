"""Inbound Socket.IO events — sending, editing, deleting and typing (spec §3.2).

Against the same uvicorn-on-an-ephemeral-port fixture the outbound tests use.
What is here and deliberately not in the Gherkin: the acks nothing in the
browser emits yet (edit and delete stay on REST in the SPA), the 409 on a stale
version, and the two token states a browser cannot be made to present.

The rule most of these defend is the one the delivery plan got wrong: **the
socket authorizes a write on channel visibility, not on room membership.** A
room is per-`sid` in-memory state that a reconnect destroys, and gating on it
would make the socket stricter than the REST route it replaces.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import httpx
import pytest
import socketio
from sqlalchemy import text

pytestmark = pytest.mark.integration

WAIT = 5


async def connected(url: str, token: str) -> socketio.AsyncSimpleClient:
    client = socketio.AsyncSimpleClient()
    await client.connect(
        url, namespace="/messaging", auth={"token": token}, transports=["websocket"]
    )
    return client


async def make_channel(url: str, headers: dict[str, str], name="general", **body) -> dict:
    async with httpx.AsyncClient(base_url=url, headers=headers) as client:
        response = await client.post("/api/v1/channels", json={"name": name, **body})
    assert response.status_code == 201, response.text
    return response.json()


# --- sending ---------------------------------------------------------------


async def test_send_message_writes_the_row_and_acks_it(realtime_url, tokens, engine):
    channel = await make_channel(realtime_url, tokens.header())
    ada = await connected(realtime_url, tokens.mint())

    ack = await ada.call(
        "send_message",
        {"channelId": channel["id"], "body": "lunch is at one"},
        timeout=WAIT,
    )

    assert ack["ok"] is True
    assert ack["data"]["body"] == "lunch is at one"
    assert ack["data"]["authorId"] == str(tokens.ADA)

    async with engine.connect() as connection:
        stored = await connection.scalar(
            text("SELECT body FROM messages WHERE id = :id"), {"id": ack["data"]["id"]}
        )
    assert stored == "lunch is at one"

    await ada.disconnect()


async def test_a_socket_send_reaches_the_room(realtime_url, tokens):
    channel = await make_channel(realtime_url, tokens.header())
    ada = await connected(realtime_url, tokens.mint())
    grace = await connected(realtime_url, tokens.mint(user_id=tokens.GRACE))
    assert (await grace.call("join_channel", channel["id"], timeout=WAIT))["ok"]

    await ada.call(
        "send_message", {"channelId": channel["id"], "body": "the coffee has arrived"}, timeout=WAIT
    )
    event, payload = await grace.receive(timeout=WAIT)

    assert event == "message_received"
    assert payload["body"] == "the coffee has arrived"

    await ada.disconnect()
    await grace.disconnect()


async def test_sending_needs_visibility_and_not_room_membership(realtime_url, tokens):
    """Grace has joined no room and no channel, and may still post.

    The case that tells the two possible rules apart: a membership gate passes
    every other test in this file and fails exactly here.
    """
    channel = await make_channel(realtime_url, tokens.header())
    grace = await connected(realtime_url, tokens.mint(user_id=tokens.GRACE))

    ack = await grace.call(
        "send_message",
        {"channelId": channel["id"], "body": "shipping this afternoon"},
        timeout=WAIT,
    )

    assert ack["ok"] is True

    await grace.disconnect()


async def test_sending_to_an_invisible_channel_acks_a_404(realtime_url, tokens):
    channel = await make_channel(realtime_url, tokens.header(), "launch-plans", kind="private")
    grace = await connected(realtime_url, tokens.mint(user_id=tokens.GRACE))

    ack = await grace.call(
        "send_message", {"channelId": channel["id"], "body": "who let me in"}, timeout=WAIT
    )

    assert ack["ok"] is False
    # 404 and never 403 — a 403 would confirm the channel exists.
    assert ack["problem"]["status"] == 404

    await grace.disconnect()


async def test_an_over_long_body_acks_a_400_with_the_field_error(realtime_url, tokens):
    channel = await make_channel(realtime_url, tokens.header())
    ada = await connected(realtime_url, tokens.mint())

    ack = await ada.call(
        "send_message", {"channelId": channel["id"], "body": "a" * 8001}, timeout=WAIT
    )

    assert ack["ok"] is False
    assert ack["problem"]["status"] == 400
    # The same `errors` map the REST route produces, so one client parser serves
    # both transports.
    assert ack["problem"]["errors"]["body"] == ["A message must be 8000 characters or fewer."]

    await ada.disconnect()


async def test_an_empty_body_acks_a_400(realtime_url, tokens):
    channel = await make_channel(realtime_url, tokens.header())
    ada = await connected(realtime_url, tokens.mint())

    ack = await ada.call("send_message", {"channelId": channel["id"], "body": "   "}, timeout=WAIT)

    assert ack["ok"] is False
    assert ack["problem"]["errors"]["body"] == ["A message cannot be empty."]

    await ada.disconnect()


async def test_a_malformed_payload_acks_rather_than_dropping_the_callback(realtime_url, tokens):
    """The regression test for the failure mode that hangs a browser.

    A handler that raised would never send its ack, and the client's callback
    would simply never fire — an optimistic bubble with no error and no way out.
    """
    ada = await connected(realtime_url, tokens.mint())

    ack = await ada.call("send_message", {"body": "no channel here"}, timeout=WAIT)

    assert ack["ok"] is False
    assert ack["problem"]["status"] == 400

    await ada.disconnect()


# --- editing and deleting --------------------------------------------------


async def test_edit_message_acks_the_edited_message_and_broadcasts(realtime_url, tokens):
    channel = await make_channel(realtime_url, tokens.header())
    ada = await connected(realtime_url, tokens.mint())
    grace = await connected(realtime_url, tokens.mint(user_id=tokens.GRACE))
    assert (await grace.call("join_channel", channel["id"], timeout=WAIT))["ok"]

    sent = (
        await ada.call(
            "send_message", {"channelId": channel["id"], "body": "standup at four"}, timeout=WAIT
        )
    )["data"]
    assert (await grace.receive(timeout=WAIT))[0] == "message_received"

    ack = await ada.call(
        "edit_message",
        {"messageId": sent["id"], "body": "standup at five", "version": sent["version"]},
        timeout=WAIT,
    )
    event, payload = await grace.receive(timeout=WAIT)

    assert ack["ok"] is True
    assert ack["data"]["body"] == "standup at five"
    assert ack["data"]["editedAt"] is not None
    assert event == "message_edited"
    assert payload["body"] == "standup at five"

    await ada.disconnect()
    await grace.disconnect()


async def test_editing_with_a_stale_version_acks_a_409(realtime_url, tokens):
    """The socket is not a way around optimistic concurrency.

    Spec §3.2 gives `edit_message` no `version` at all; built as documented, this
    would be the way to lose someone else's edit silently.
    """
    channel = await make_channel(realtime_url, tokens.header())
    ada = await connected(realtime_url, tokens.mint())

    sent = (
        await ada.call("send_message", {"channelId": channel["id"], "body": "first"}, timeout=WAIT)
    )["data"]
    await ada.call(
        "edit_message",
        {"messageId": sent["id"], "body": "second", "version": sent["version"]},
        timeout=WAIT,
    )

    ack = await ada.call(
        "edit_message",
        {"messageId": sent["id"], "body": "third", "version": sent["version"]},
        timeout=WAIT,
    )

    assert ack["ok"] is False
    assert ack["problem"]["status"] == 409

    await ada.disconnect()


async def test_editing_someone_elses_message_acks_a_403(realtime_url, tokens):
    channel = await make_channel(realtime_url, tokens.header())
    ada = await connected(realtime_url, tokens.mint())
    grace = await connected(realtime_url, tokens.mint(user_id=tokens.GRACE))

    sent = (
        await ada.call(
            "send_message",
            {"channelId": channel["id"], "body": "the eagle has landed"},
            timeout=WAIT,
        )
    )["data"]

    ack = await grace.call(
        "edit_message",
        {"messageId": sent["id"], "body": "the pigeon has landed", "version": sent["version"]},
        timeout=WAIT,
    )

    assert ack["ok"] is False
    assert ack["problem"]["status"] == 403

    await ada.disconnect()
    await grace.disconnect()


async def test_delete_message_acks_the_tombstone_and_broadcasts_it(realtime_url, tokens):
    channel = await make_channel(realtime_url, tokens.header())
    ada = await connected(realtime_url, tokens.mint())
    grace = await connected(realtime_url, tokens.mint(user_id=tokens.GRACE))
    assert (await grace.call("join_channel", channel["id"], timeout=WAIT))["ok"]

    sent = (
        await ada.call(
            "send_message",
            {"channelId": channel["id"], "body": "wrong channel, sorry"},
            timeout=WAIT,
        )
    )["data"]
    assert (await grace.receive(timeout=WAIT))[0] == "message_received"

    ack = await ada.call("delete_message", {"messageId": sent["id"]}, timeout=WAIT)
    event, payload = await grace.receive(timeout=WAIT)

    # The tombstone, not an id: the row stays in the history and the client that
    # issued the delete has to render it like everyone else.
    assert ack["ok"] is True
    assert ack["data"]["id"] == sent["id"]
    assert ack["data"]["body"] == ""
    assert ack["data"]["deletedAt"] is not None

    assert event == "message_deleted"
    assert payload["body"] == ""
    assert payload["deletedAt"] is not None

    await ada.disconnect()
    await grace.disconnect()


async def test_deleting_someone_elses_message_as_a_non_admin_acks_a_403(realtime_url, tokens):
    channel = await make_channel(realtime_url, tokens.header())
    ada = await connected(realtime_url, tokens.mint())
    grace = await connected(realtime_url, tokens.mint(user_id=tokens.GRACE))

    sent = (
        await ada.call(
            "send_message",
            {"channelId": channel["id"], "body": "the eagle has landed"},
            timeout=WAIT,
        )
    )["data"]

    ack = await grace.call("delete_message", {"messageId": sent["id"]}, timeout=WAIT)

    assert ack["ok"] is False
    assert ack["problem"]["status"] == 403

    await ada.disconnect()
    await grace.disconnect()


# --- the token behind the connection ---------------------------------------


async def test_an_expired_principal_cannot_write(realtime_url, tokens):
    """A connection is verified once and can outlive its token by hours.

    The handshake accepts a token with seconds left on it; by the time the write
    arrives it is spent. Without this check the socket would be a weaker door
    than the REST route it replaces.
    """
    channel = await make_channel(realtime_url, tokens.header())
    ada = await connected(realtime_url, tokens.mint(lifetime=timedelta(seconds=1)))

    import asyncio

    await asyncio.sleep(1.2)
    ack = await ada.call(
        "send_message", {"channelId": channel["id"], "body": "too late"}, timeout=WAIT
    )

    assert ack["ok"] is False
    assert ack["problem"]["status"] == 401

    await ada.disconnect()


async def test_a_revoked_token_cannot_write(realtime_url, tokens, redis_client):
    from shared import Denylist

    channel = await make_channel(realtime_url, tokens.header())
    token = tokens.mint()
    ada = await connected(realtime_url, token)

    import jwt

    jti = jwt.decode(token, options={"verify_signature": False}, audience="collabhub")["jti"]
    await Denylist(redis_client).revoke(jti, ttl_seconds=900)

    ack = await ada.call(
        "send_message", {"channelId": channel["id"], "body": "still here"}, timeout=WAIT
    )

    assert ack["ok"] is False
    assert ack["problem"]["status"] == 401

    await ada.disconnect()


# --- typing ----------------------------------------------------------------


async def test_typing_reaches_the_room_but_not_the_sender(realtime_url, tokens, engine):
    channel = await make_channel(realtime_url, tokens.header())
    ada = await connected(realtime_url, tokens.mint())
    grace = await connected(realtime_url, tokens.mint(user_id=tokens.GRACE))
    assert (await ada.call("join_channel", channel["id"], timeout=WAIT))["ok"]
    assert (await grace.call("join_channel", channel["id"], timeout=WAIT))["ok"]

    await ada.emit("typing", {"channelId": channel["id"]})
    event, payload = await grace.receive(timeout=WAIT)

    assert event == "user_typing"
    assert payload == {"channelId": channel["id"], "userId": str(tokens.ADA)}

    # `skip_sid` keeps the sender out of their own fan-out.
    with pytest.raises(socketio.exceptions.TimeoutError):
        await ada.receive(timeout=2)

    # Ephemeral, and never persisted.
    async with engine.connect() as connection:
        assert await connection.scalar(text("SELECT count(*) FROM messages")) == 0

    await ada.disconnect()
    await grace.disconnect()


async def test_a_typing_event_for_an_unknown_channel_is_simply_dropped(realtime_url, tokens):
    """No ack to give, so nothing to report — and nothing to crash on either."""
    ada = await connected(realtime_url, tokens.mint())

    await ada.emit("typing", {"channelId": str(uuid.uuid4())})

    assert ada.connected

    await ada.disconnect()
