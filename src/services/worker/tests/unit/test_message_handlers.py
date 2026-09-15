"""The `jobs:index` consumer contract, the Worker's side (doc 05 §3, D32 decision 7).

An envelope built from the same `contracts.MessageIndexPayload` Messaging
enqueues is turned into one external-versioned `index` call. The call's
arguments are built by a pure function and asserted here; that Elasticsearch
applies them — and refuses an older version with a 409 — is integration.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest

from contracts import MESSAGE_DELETE, MESSAGE_UPSERT, MESSAGES_ALIAS, MessageIndexPayload
from shared import JobEnvelope
from worker.consumer import PermanentJobError
from worker.handlers.messages import index_request

PAYLOAD = MessageIndexPayload(
    message_id=uuid.uuid4(),
    channel_id=uuid.uuid4(),
    workspace_id=uuid.uuid4(),
    author_id=uuid.uuid4(),
    body="standup at ten",
    created_at=datetime(2026, 9, 15, 9, 0, tzinfo=UTC),
    version=4,
)


def _over_the_wire(job_type: str, payload: MessageIndexPayload = PAYLOAD) -> JobEnvelope:
    """Encode and decode, as the stream does, so the test sees what the Worker sees."""
    return JobEnvelope.decode(JobEnvelope.new(job_type, payload).encode())


def test_an_envelope_round_trips_a_message_payload():
    """Breaks if the envelope or the payload loses a field between producer and consumer."""
    envelope = _over_the_wire(MESSAGE_UPSERT)

    assert envelope.job_type == MESSAGE_UPSERT
    assert MessageIndexPayload.model_validate(envelope.payload) == PAYLOAD


def test_the_wire_form_is_camel_case():
    """Conventions §7.1: breaks if an alias generator is dropped from either model."""
    wire = json.loads(JobEnvelope.new(MESSAGE_UPSERT, PAYLOAD).encode())

    assert {"jobId", "type", "version", "occurredAt", "attempt", "payload"} == set(wire)
    assert {"messageId", "channelId", "workspaceId", "authorId", "createdAt"} <= set(
        wire["payload"]
    )


def test_an_upsert_indexes_the_body_under_the_alias():
    request = index_request(_over_the_wire(MESSAGE_UPSERT), deleted=False)

    assert request["index"] == MESSAGES_ALIAS
    assert request["id"] == str(PAYLOAD.message_id)
    assert request["document"] == {
        "messageId": str(PAYLOAD.message_id),
        "channelId": str(PAYLOAD.channel_id),
        "workspaceId": str(PAYLOAD.workspace_id),
        "authorId": str(PAYLOAD.author_id),
        "createdAt": "2026-09-15T09:00:00Z",
        "body": "standup at ten",
        "deleted": False,
    }


def test_a_delete_writes_a_tombstone_with_no_body():
    """Breaks if the text is kept in the index after the user deleted it."""
    request = index_request(_over_the_wire(MESSAGE_DELETE), deleted=True)

    assert "body" not in request["document"]
    assert request["document"]["deleted"] is True


@pytest.mark.parametrize("deleted", [False, True])
def test_the_payload_version_is_the_external_version(deleted):
    """What makes a redelivered or late job harmless: breaks if the version is internal."""
    request = index_request(_over_the_wire(MESSAGE_UPSERT), deleted=deleted)

    assert request["version"] == 4
    assert request["version_type"] == "external"
    assert "version" not in request["document"]


def test_an_invalid_payload_is_permanent():
    """Retrying cannot fix a payload that fails the contract — dead-letter it at once."""
    envelope = JobEnvelope.decode(
        JobEnvelope.new(MESSAGE_UPSERT, PAYLOAD)
        .model_copy(update={"payload": {"messageId": "not-a-uuid"}})
        .encode()
    )

    with pytest.raises(PermanentJobError):
        index_request(envelope, deleted=False)
