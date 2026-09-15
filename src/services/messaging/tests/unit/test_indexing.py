"""The `jobs:index` producer contract, Messaging's side (register D25, D32 decision 7).

What Messaging enqueues has to be what the Worker reads: a
`contracts.MessageIndexPayload` on `jobs:index`, with the job type saying upsert
or delete. The Worker's side of the same contract is
`worker/tests/unit/test_message_handlers.py`.

`RecordingJobQueue` stands in for `shared.JobQueue` — a class of ours at the
edge, not a fake Redis.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from contracts import JOBS_INDEX, MESSAGE_DELETE, MESSAGE_UPSERT, MessageIndexPayload
from messaging import indexing
from messaging.routers.messages import _as_message
from testkit.fakes import RecordingJobQueue

WORKSPACE = uuid.uuid4()
DELETED_AT = datetime(2026, 9, 15, 10, 0, tzinfo=UTC)
SECRET = "the launch is on friday"


async def test_an_upsert_goes_to_the_index_stream_as_message_upsert(a_message):
    jobs = RecordingJobQueue()

    await indexing.enqueue_upsert(jobs, _as_message(a_message()), workspace_id=WORKSPACE)

    [(stream, job_type, _payload)] = jobs.enqueued
    assert (stream, job_type) == (JOBS_INDEX, MESSAGE_UPSERT)


async def test_a_delete_goes_to_the_index_stream_as_message_delete(a_message):
    jobs = RecordingJobQueue()

    await indexing.enqueue_delete(
        jobs, _as_message(a_message(deleted_at=DELETED_AT)), workspace_id=WORKSPACE
    )

    [(stream, job_type, _payload)] = jobs.enqueued
    assert (stream, job_type) == (JOBS_INDEX, MESSAGE_DELETE)


async def test_the_payload_carries_every_field_from_the_committed_message(a_message):
    """Breaks if a field is dropped, renamed or read from the wrong attribute.

    The workspace is the argument — the caller's `wsp` claim — because
    `messages` has no workspace column. `version` is the committed row's, which
    the Worker uses as the Elasticsearch external version.
    """
    message = a_message(body="hello", version=3)
    jobs = RecordingJobQueue()

    await indexing.enqueue_upsert(jobs, _as_message(message), workspace_id=WORKSPACE)

    [(_stream, _type, payload)] = jobs.enqueued
    assert isinstance(payload, MessageIndexPayload)
    assert payload.model_dump() == {
        "message_id": message.id,
        "channel_id": message.channel_id,
        "workspace_id": WORKSPACE,
        "author_id": message.author_id,
        "body": "hello",
        "created_at": message.created_at,
        "version": 3,
    }


async def test_the_payload_is_camel_case_on_the_wire(a_message):
    """What the Worker validates is the JSON form, so the aliases are the contract."""
    jobs = RecordingJobQueue()

    await indexing.enqueue_upsert(jobs, _as_message(a_message()), workspace_id=WORKSPACE)

    [(_stream, _type, payload)] = jobs.enqueued
    wire = payload.model_dump(mode="json", by_alias=True)
    assert set(wire) == {
        "messageId",
        "channelId",
        "workspaceId",
        "authorId",
        "body",
        "createdAt",
        "version",
    }
    assert MessageIndexPayload.model_validate(wire) == payload


async def test_a_delete_job_carries_no_text(a_message):
    """The DTO is redacted, and the job is built from the DTO — breaks if it is built from the row."""
    jobs = RecordingJobQueue()

    await indexing.enqueue_delete(
        jobs, _as_message(a_message(body=SECRET, deleted_at=DELETED_AT)), workspace_id=WORKSPACE
    )

    [(_stream, _type, payload)] = jobs.enqueued
    assert payload.body == ""


async def test_a_failed_enqueue_is_swallowed_and_logged_without_the_body(a_message, caplog):
    """Fire-and-forget (Conventions §7): the committed write stands.

    Breaks if the exception escapes — the client would get a 500 for a message
    that was saved — or if the log line carries the text (CH008).
    """
    message = a_message(body=SECRET)
    jobs = RecordingJobQueue(fail_with=ConnectionError(f"redis said no about {SECRET}"))

    with caplog.at_level(logging.WARNING, logger="collabhub.messaging.indexing"):
        await indexing.enqueue_upsert(jobs, _as_message(message), workspace_id=WORKSPACE)

    [record] = caplog.records
    assert record.levelno == logging.WARNING
    assert MESSAGE_UPSERT in record.getMessage()
    assert "ConnectionError" in record.getMessage()
    assert SECRET not in caplog.text
