"""What the consumer does with an entry before any handler runs (doc 05 §5.1).

Three decisions come before a handler is called — is it an envelope, has it
been delivered too often, is there a handler for its type — and all three are a
function of the entry and a count. Pulled out as `triage`, they are unit tested
here. Delivery counts, retries and the dead-letter stream itself are Redis's,
and the integration handoff proves them against a real stream.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from contracts import MESSAGE_DELETE, MESSAGE_UPSERT, MessageIndexPayload
from shared import JOB_DATA_FIELD, JobEnvelope
from worker.consumer import DeadLetter, Run, triage

MAX_ATTEMPTS = 5


async def _upsert(envelope: JobEnvelope) -> None:
    return None


async def _delete(envelope: JobEnvelope) -> None:
    return None


HANDLERS = {MESSAGE_UPSERT: _upsert, MESSAGE_DELETE: _delete}


def _entry(job_type: str = MESSAGE_UPSERT) -> dict[str, str]:
    payload = MessageIndexPayload(
        message_id=uuid.uuid4(),
        channel_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        author_id=uuid.uuid4(),
        body="hello",
        created_at=datetime(2026, 9, 15, 9, 0, tzinfo=UTC),
        version=1,
    )
    return {JOB_DATA_FIELD: JobEnvelope.new(job_type, payload).encode()}


def _triage(fields: dict[str, str], deliveries: int = 1):
    return triage(fields, deliveries=deliveries, max_attempts=MAX_ATTEMPTS, handlers=HANDLERS)


def test_an_entry_with_no_data_field_is_malformed():
    assert _triage({"other": "x"}) == DeadLetter("malformed-envelope")


def test_an_entry_that_is_not_an_envelope_is_malformed():
    """Breaks if a validation error escapes, which would retry it forever."""
    assert _triage({JOB_DATA_FIELD: '{"hello": "world"}'}) == DeadLetter("malformed-envelope")
    assert _triage({JOB_DATA_FIELD: "not json"}) == DeadLetter("malformed-envelope")


def test_a_job_on_its_last_allowed_delivery_still_runs():
    """Breaks if `max_attempts` is off by one."""
    assert isinstance(_triage(_entry(), deliveries=MAX_ATTEMPTS), Run)


def test_a_job_delivered_more_than_max_attempts_is_dead_lettered():
    """Even a valid job with a handler: breaks if the attempts check is dropped."""
    assert _triage(_entry(), deliveries=MAX_ATTEMPTS + 1) == DeadLetter("max-attempts")


def test_a_malformed_entry_says_malformed_whatever_its_delivery_count():
    """The order of the checks: breaks if attempts are judged before the envelope."""
    assert _triage({JOB_DATA_FIELD: "not json"}, deliveries=MAX_ATTEMPTS + 1) == DeadLetter(
        "malformed-envelope"
    )


def test_an_unknown_type_is_dead_lettered():
    """Retrying cannot conjure a handler: breaks if an unknown type is left pending."""
    assert _triage(_entry("message.unheard-of")) == DeadLetter("unknown-type")


def test_a_known_type_runs_its_own_handler():
    """Breaks if dispatch picks the wrong handler for the envelope's `type`."""
    upsert = _triage(_entry(MESSAGE_UPSERT))
    delete = _triage(_entry(MESSAGE_DELETE))

    assert isinstance(upsert, Run)
    assert upsert.handler is _upsert
    assert upsert.envelope.job_type == MESSAGE_UPSERT
    assert isinstance(delete, Run)
    assert delete.handler is _delete
