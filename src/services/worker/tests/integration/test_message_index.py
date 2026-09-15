"""`jobs:index` into the `messages` index — the Worker end to end (doc 05 §3, §4; D25).

The consumer reads real jobs off R3 and the real message handlers write to a
real Elasticsearch. What these pin is the property the whole pipeline leans on:
**`messages.version` is Elasticsearch's external version**, so a job that is
late, repeated or reclaimed can never move a document backwards — and a delete
is a tombstone, so not even a stale upsert after it can bring the text back.

**What is not here, on purpose.** The document and tombstone a job becomes, its
external version, and a payload that fails the contract are `index_request`,
unit-tested in `tests/unit/test_message_handlers.py`. These tests prove what
only Elasticsearch can: that the strict mapping accepts the document, that a
409 is treated as success, and that a 400 is permanent.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from contracts import MESSAGE_DELETE, MESSAGE_UPSERT, MESSAGES_ALIAS, MessageIndexPayload
from shared import JobEnvelope
from shared.ids import uuid7
from worker.handlers.messages import build_message_handlers
from worker.index import MESSAGES_INDEX, MESSAGES_MAPPINGS, ensure_messages_index


@pytest.fixture
async def index(elasticsearch):
    await ensure_messages_index(elasticsearch)
    return elasticsearch


def a_message(**overrides: Any) -> MessageIndexPayload:
    values: dict[str, Any] = {
        "message_id": uuid7(),
        "channel_id": uuid.uuid4(),
        "workspace_id": uuid.uuid4(),
        "author_id": uuid.uuid4(),
        "body": "the deploy is at noon",
        "created_at": datetime.now(UTC),
        "version": 1,
    }
    values.update(overrides)
    return MessageIndexPayload(**values)


def deleted(message: MessageIndexPayload) -> MessageIndexPayload:
    """What Messaging enqueues for a delete: the bumped version, the body redacted."""
    return message.model_copy(update={"body": "", "version": message.version + 1})


async def stored(es, message: MessageIndexPayload) -> dict[str, Any]:
    return await es.get(index=MESSAGES_ALIAS, id=str(message.message_id))


# --- the index ---------------------------------------------------------------


async def test_ensure_creates_the_versioned_index_behind_the_alias(elasticsearch):
    await ensure_messages_index(elasticsearch)

    aliases = await elasticsearch.indices.get_alias(name=MESSAGES_ALIAS)
    mapping = (await elasticsearch.indices.get_mapping(index=MESSAGES_INDEX))[MESSAGES_INDEX]

    assert list(aliases) == [MESSAGES_INDEX]
    assert mapping["mappings"]["dynamic"] == "strict"
    assert mapping["mappings"]["properties"] == MESSAGES_MAPPINGS["properties"]


async def test_ensuring_the_index_again_is_harmless(elasticsearch):
    """Every replica ensures the index at startup; all but the first find it there."""
    await ensure_messages_index(elasticsearch)
    await ensure_messages_index(elasticsearch)

    assert list(await elasticsearch.indices.get(index="messages*")) == [MESSAGES_INDEX]


# --- the handlers, through the consumer --------------------------------------


async def test_an_upsert_is_stored_at_the_messages_version(index, run_consumer, jobs):
    """The strict mapping accepts the document exactly as the handler builds it."""
    message = a_message(version=3)

    async with run_consumer(build_message_handlers(index)):
        await jobs.enqueue(MESSAGE_UPSERT, message)
        await jobs.drained()

    document = await stored(index, message)
    assert document["_index"] == MESSAGES_INDEX
    assert document["_version"] == 3
    assert document["_source"]["body"] == "the deploy is at noon"
    assert await jobs.dead_letters() == []


async def test_a_delete_leaves_a_tombstone_with_no_body(index, run_consumer, jobs):
    message = a_message()

    async with run_consumer(build_message_handlers(index)):
        await jobs.enqueue(MESSAGE_UPSERT, message)
        await jobs.enqueue(MESSAGE_DELETE, deleted(message))
        await jobs.drained()

    document = await stored(index, message)
    assert document["_version"] == 2
    assert document["_source"]["deleted"] is True
    assert "body" not in document["_source"]


async def test_an_older_version_arriving_late_is_ignored_and_still_completes(
    index, run_consumer, jobs
):
    edited = a_message(version=2, body="the deploy moved to three")
    original = edited.model_copy(update={"version": 1, "body": "the deploy is at noon"})

    async with run_consumer(build_message_handlers(index)):
        await jobs.enqueue(MESSAGE_UPSERT, edited)
        await jobs.enqueue(MESSAGE_UPSERT, original)
        await jobs.drained()

    document = await stored(index, edited)
    assert document["_version"] == 2
    assert document["_source"]["body"] == "the deploy moved to three"
    # A 409 from Elasticsearch is success here, not a failure to retry.
    assert await jobs.dead_letters() == []


async def test_a_stale_upsert_cannot_bring_a_deleted_message_back(index, run_consumer, jobs):
    message = a_message()

    async with run_consumer(build_message_handlers(index)):
        await jobs.enqueue(MESSAGE_UPSERT, message)
        await jobs.enqueue(MESSAGE_DELETE, deleted(message))
        await jobs.enqueue(MESSAGE_UPSERT, message)
        await jobs.drained()

    source = (await stored(index, message))["_source"]
    assert source["deleted"] is True
    assert "body" not in source


async def test_the_same_job_delivered_twice_has_one_effect(index, run_consumer, jobs):
    """`jobId` is the idempotency key; the external version is what makes it hold."""
    message = a_message(version=4)
    envelope = JobEnvelope.new(MESSAGE_UPSERT, message)

    async with run_consumer(build_message_handlers(index)):
        await jobs.enqueue_envelope(envelope)
        await jobs.enqueue_envelope(envelope)
        await jobs.drained()

    await index.indices.refresh(index=MESSAGES_ALIAS)
    assert (await index.count(index=MESSAGES_ALIAS))["count"] == 1
    assert (await stored(index, message))["_version"] == 4
    assert await jobs.dead_letters() == []


async def test_a_write_the_index_refuses_is_dead_lettered_at_once(
    elasticsearch, run_consumer, jobs
):
    """Two indices behind `messages` and neither the write index — a reindex left half done.

    Elasticsearch answers every write with a 400, and would answer every retry
    the same way, so the job goes to dead-letter on its first delivery.
    """
    await ensure_messages_index(elasticsearch)
    await elasticsearch.indices.create(
        index="messages-v2", mappings=MESSAGES_MAPPINGS, aliases={MESSAGES_ALIAS: {}}
    )

    async with run_consumer(build_message_handlers(elasticsearch), max_attempts=5):
        await jobs.enqueue(MESSAGE_UPSERT, a_message())
        await jobs.drained()

    [dead] = await jobs.dead_letters()
    assert dead["error"] == "permanent:rejected by index"
    assert dead["deliveries"] == "1"
