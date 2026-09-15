"""The `jobs:index` producer, seen from the real R3 stream (doc 02 §5 step 4, D25).

Every committed message write — send, edit, delete, over REST or the socket —
puts one job on `jobs:index`, for that message, at its committed version.

**What is not here, on purpose.** The payload's fields, a delete carrying
`body: ""`, and a failed enqueue being swallowed are unit-tested against a
recording queue in `tests/unit/test_indexing.py`. These prove what only the
routes and a real Redis can: which writes enqueue, which do not, and that an
unreachable R3 really does not fail the write.
"""

from __future__ import annotations

import uuid

import httpx
import socketio

from contracts import JOBS_INDEX, MESSAGE_DELETE, MESSAGE_UPSERT, MessageIndexPayload
from shared import JOB_DATA_FIELD, JobEnvelope

WAIT = 5


async def make_channel(client, headers, name="general"):
    response = await client.post("/api/v1/channels", json={"name": name}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def send(client, headers, channel_id, body):
    response = await client.post(
        f"/api/v1/channels/{channel_id}/messages", json={"body": body}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


async def enqueued(redis_streams) -> list[tuple[JobEnvelope, MessageIndexPayload]]:
    entries = await redis_streams.xrange(JOBS_INDEX)
    envelopes = [JobEnvelope.decode(fields[JOB_DATA_FIELD]) for _, fields in entries]
    return [(e, MessageIndexPayload.model_validate(e.payload)) for e in envelopes]


async def test_a_send_enqueues_an_upsert_for_that_message(client, ada, redis_streams):
    channel = await make_channel(client, ada)
    sent = await send(client, ada, channel["id"], "ship it on friday")

    [(envelope, payload)] = await enqueued(redis_streams)

    assert envelope.job_type == MESSAGE_UPSERT
    assert payload.message_id == uuid.UUID(sent["id"])
    assert payload.version == sent["version"]


async def test_an_edit_enqueues_an_upsert_at_the_committed_version(client, ada, redis_streams):
    channel = await make_channel(client, ada)
    sent = await send(client, ada, channel["id"], "ship it on friday")
    edited = await client.patch(
        f"/api/v1/messages/{sent['id']}",
        json={"body": "ship it on monday", "version": sent["version"]},
        headers=ada,
    )
    assert edited.status_code == 200, edited.text

    [_, (envelope, payload)] = await enqueued(redis_streams)

    assert envelope.job_type == MESSAGE_UPSERT
    assert payload.message_id == uuid.UUID(sent["id"])
    assert payload.version == edited.json()["version"] > sent["version"]


async def test_a_delete_enqueues_a_delete_at_the_committed_version(client, ada, redis_streams):
    channel = await make_channel(client, ada)
    sent = await send(client, ada, channel["id"], "the launch code is 0000")
    tombstone = await client.delete(f"/api/v1/messages/{sent['id']}", headers=ada)
    assert tombstone.status_code == 200, tombstone.text

    [_, (envelope, payload)] = await enqueued(redis_streams)

    assert envelope.job_type == MESSAGE_DELETE
    assert payload.message_id == uuid.UUID(sent["id"])
    assert payload.version == tombstone.json()["version"]


async def test_a_rejected_write_enqueues_nothing(client, ada, redis_streams):
    channel = await make_channel(client, ada)

    response = await client.post(
        f"/api/v1/channels/{channel['id']}/messages", json={"body": "   "}, headers=ada
    )

    assert response.status_code == 400
    assert await enqueued(redis_streams) == []


async def test_a_socket_send_enqueues_an_upsert_too(realtime_url, tokens, redis_streams):
    async with httpx.AsyncClient(base_url=realtime_url, headers=tokens.header()) as http:
        channel = await make_channel(http, {})
    ada = socketio.AsyncSimpleClient()
    await ada.connect(
        realtime_url,
        namespace="/messaging",
        auth={"token": tokens.mint()},
        transports=["websocket"],
    )

    ack = await ada.call(
        "send_message", {"channelId": channel["id"], "body": "over the socket"}, timeout=WAIT
    )
    await ada.disconnect()

    [(envelope, payload)] = await enqueued(redis_streams)
    assert ack["ok"] is True
    assert envelope.job_type == MESSAGE_UPSERT
    assert payload.message_id == uuid.UUID(ack["data"]["id"])


async def test_an_unreachable_stream_does_not_fail_the_write(client_for, ada, redis_streams):
    """R3 down costs search a change, never the user their message.

    A real client against a closed port, so the exception is redis-py's own and
    the short socket timeouts in `JobQueue.from_url` are what keep it quick.
    """
    async with client_for(redis_streams_url="redis://127.0.0.1:1/2") as client:
        channel = await make_channel(client, ada)
        response = await client.post(
            f"/api/v1/channels/{channel['id']}/messages", json={"body": "still sent"}, headers=ada
        )
        history = await client.get(f"/api/v1/channels/{channel['id']}/messages", headers=ada)

    assert response.status_code == 201, response.text
    assert [m["body"] for m in history.json()["items"]] == ["still sent"]
    assert await enqueued(redis_streams) == []
