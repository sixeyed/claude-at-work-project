"""`StreamConsumer` against a real R3 stream (doc 05 §5.1, Conventions §7).

Every test drives the consumer the way production does — entries added with
`XADD`, read through the `worker` consumer group — and then looks at Redis:
what is left in the stream, the pending list and `jobs:index:dead`.

**What is not here, on purpose.** Which entries are dead-lettered before any
handler runs — malformed, over `max_attempts`, unknown type — is `triage`, a
pure function unit-tested in `tests/unit/test_consumer_triage.py`. These tests
prove what only a real stream can: that acks, reclaims, delivery counts,
dead-letter entries and recovery from a Redis error actually happen.

The handlers here are stand-ins that record or fail on purpose. The message
handlers, and the idempotency they give, are in `test_message_index.py`.
"""

from __future__ import annotations

import asyncio

from shared import JobEnvelope
from worker.consumer import PermanentJobError

JOB = "test.job"
#: The consumer group `CONSUMER_DEFAULTS` uses.
GROUP = "worker"


async def test_a_handled_job_is_acknowledged_and_leaves_the_pending_list(run_consumer, jobs):
    handled = []

    async def handler(envelope):
        handled.append(envelope.job_id)

    # A long visibility timeout, so no reclaim pass runs during the test: XAUTOCLAIM
    # drops deleted entries from the pending list, and would hide a missing XACK.
    async with run_consumer({JOB: handler}, visibility_timeout_seconds=60):
        envelope = await jobs.enqueue(JOB, {"n": 1})
        await jobs.drained()

    assert handled == [envelope.job_id]
    # Acked, and deleted rather than kept: an index job carries a message body.
    assert await jobs.pending() == 0
    assert await jobs.client.xlen(jobs.stream) == 0
    assert await jobs.dead_letters() == []


async def test_a_transient_failure_is_retried_and_then_succeeds(run_consumer, jobs):
    attempts = []

    async def flaky(envelope):
        attempts.append(envelope.job_id)
        if len(attempts) == 1:
            raise ConnectionError("the index is briefly away")

    async with run_consumer({JOB: flaky}, visibility_timeout_seconds=1, max_attempts=3):
        envelope = await jobs.enqueue(JOB, {})
        await jobs.drained()

    assert attempts == [envelope.job_id, envelope.job_id]
    assert await jobs.dead_letters() == []


async def test_a_permanent_error_is_dead_lettered_at_once_with_its_fixed_reason(run_consumer, jobs):
    calls = []

    async def refuses(envelope):
        calls.append(envelope.job_id)
        try:
            int("secret message text")
        except ValueError as exc:
            raise PermanentJobError("unparseable") from exc

    async with run_consumer({JOB: refuses}, max_attempts=5):
        envelope = await jobs.enqueue(JOB, {"n": 1})
        entry_id = (await jobs.client.xrange(jobs.stream))[0][0]
        await jobs.drained()

    [dead] = await jobs.dead_letters()
    assert len(calls) == 1
    assert dead["error"] == "permanent:unparseable"
    assert dead["deliveries"] == "1"
    assert dead["sourceId"] == entry_id
    assert JobEnvelope.decode(dead["data"]).job_id == envelope.job_id
    # The fixed reason only — never the text of the exception behind it.
    assert "secret message text" not in dead["error"]
    assert "invalid literal" not in dead["error"]


async def test_a_job_that_keeps_failing_is_dead_lettered_after_max_attempts(run_consumer, jobs):
    """The count is Redis's: `XAUTOCLAIM` bumps it and `XPENDING` reports it."""
    calls = []

    async def always_fails(envelope):
        calls.append(envelope.job_id)
        raise RuntimeError("secret message text")

    async with run_consumer({JOB: always_fails}, visibility_timeout_seconds=1, max_attempts=2):
        await jobs.enqueue(JOB, {})
        await jobs.drained(within=30)

    [dead] = await jobs.dead_letters()
    # Two deliveries ran the handler; the third is over the limit and never does.
    assert len(calls) == 2
    assert dead["error"] == "max-attempts"
    assert dead["deliveries"] == "3"
    assert "secret message text" not in dead["error"]


async def test_an_entry_a_crashed_consumer_left_pending_is_reclaimed(run_consumer, jobs):
    """Read by a consumer that died before acking: only `XAUTOCLAIM` can deliver it again."""
    handled = []

    async def handler(envelope):
        handled.append(envelope.job_id)

    envelope = await jobs.enqueue(JOB, {})
    await jobs.client.xgroup_create(jobs.stream, GROUP, id="0")
    await jobs.client.xreadgroup(GROUP, "crashed-consumer", {jobs.stream: ">"}, count=1)
    assert await jobs.pending() == 1

    async with run_consumer({JOB: handler}, visibility_timeout_seconds=2):
        # Not before the visibility timeout: the crashed consumer might only be slow.
        await asyncio.sleep(0.5)
        assert handled == []

        await jobs.drained()

    assert handled == [envelope.job_id]
    assert await jobs.dead_letters() == []


async def test_the_consumer_recovers_when_its_stream_and_group_are_lost(run_consumer, jobs):
    """R3 flushed, or the stream key deleted, under a running Worker.

    A producer's next `XADD` recreates the stream — without the `worker` group,
    so every read fails with `NOGROUP`. That is a Redis error, which the loop
    backs off from; the consumer has to create its group again when it retries,
    or it logs the same error every two seconds and never consumes again.
    """
    handled = []

    async def handler(envelope):
        handled.append(envelope.job_id)

    async with run_consumer({JOB: handler}):
        before = await jobs.enqueue(JOB, {})
        await jobs.drained()

        await jobs.client.delete(jobs.stream)
        after = await jobs.enqueue(JOB, {})
        await jobs.drained(within=15)

    assert handled == [before.job_id, after.job_id]
