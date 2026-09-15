"""The Worker's integration harness: a real `StreamConsumer` on a real R3 stream.

The Worker's public boundary is the stream (design 01, "the service layer"). A
test puts entries on `jobs:index` the way a producer does, a consumer reads
them through the `worker` consumer group the way production does, and the test
looks at what is left: the stream, the pending list, the dead-letter stream, and
— for the message handlers — the documents in a real Elasticsearch.

Redis is R3's index on the session's shared server; Elasticsearch starts only
for the tests that request `elasticsearch`.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import pytest
import redis.asyncio as aioredis
from pydantic import BaseModel
from redis.exceptions import ResponseError

from contracts import JOBS_INDEX
from shared import JOB_DATA_FIELD, JobEnvelope
from shared.ids import uuid7
from testkit.containers import RedisRole, RedisServer
from worker.consumer import ConsumerConfig, Handler, StreamConsumer

GROUP = "worker"

#: Small enough that a test waits on nothing: `block_ms` of 100 rather than
#: 5000, and a one-second visibility timeout so a reclaim happens within a test.
CONSUMER_DEFAULTS: dict[str, Any] = {
    "consumer": "test-consumer",
    "batch_size": 16,
    "visibility_timeout_seconds": 1,
    "max_attempts": 3,
    "dead_letter_maxlen": 100,
    "block_ms": 100,
    "group": GROUP,
}

#: How long a test waits for a stream to empty before failing.
DRAIN_SECONDS = 15.0


class Jobs:
    """A producer's view of one stream, plus what a test needs to see after."""

    def __init__(self, client: aioredis.Redis, stream: str = JOBS_INDEX) -> None:
        self.client = client
        self.stream = stream

    @property
    def dead_stream(self) -> str:
        return f"{self.stream}:dead"

    async def enqueue(self, job_type: str, payload: BaseModel | dict[str, Any]) -> JobEnvelope:
        """Add a job as a producer would. A dict payload skips the contract model."""
        if isinstance(payload, BaseModel):
            envelope = JobEnvelope.new(job_type, payload)
        else:
            envelope = JobEnvelope(
                job_id=uuid7(), job_type=job_type, occurred_at=datetime.now(UTC), payload=payload
            )
        await self.enqueue_envelope(envelope)
        return envelope

    async def enqueue_envelope(self, envelope: JobEnvelope) -> str:
        return await self.client.xadd(self.stream, {JOB_DATA_FIELD: envelope.encode()})

    async def enqueue_raw(self, data: str) -> str:
        return await self.client.xadd(self.stream, {JOB_DATA_FIELD: data})

    async def pending(self) -> int:
        try:
            return (await self.client.xpending(self.stream, GROUP))["pending"]
        except ResponseError:  # NOGROUP: no consumer has started yet
            return 0

    async def is_drained(self) -> bool:
        """Nothing left to read and nothing read but unfinished."""
        return await self.client.xlen(self.stream) == 0 and await self.pending() == 0

    async def drained(self, within: float = DRAIN_SECONDS) -> None:
        await eventually(self.is_drained, within=within, what=f"{self.stream} to drain")

    async def dead_letters(self) -> list[dict[str, str]]:
        return [fields for _, fields in await self.client.xrange(self.dead_stream)]


async def eventually(
    condition: Callable[[], Any], *, within: float = DRAIN_SECONDS, what: str = "condition"
) -> None:
    """Poll an async condition until it is truthy, or fail after `within` seconds.

    A deadline check rather than `asyncio.timeout`, so the failure says what was
    being waited for instead of raising a bare `TimeoutError`.
    """
    deadline = asyncio.get_running_loop().time() + within
    while not await condition():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"timed out after {within}s waiting for {what}")
        await asyncio.sleep(0.05)


@pytest.fixture
def jobs(redis_streams: aioredis.Redis) -> Jobs:
    """`jobs:index` on R3's index, flushed before the test."""
    return Jobs(redis_streams)


@pytest.fixture
def run_consumer(
    redis_server: RedisServer, redis_streams: aioredis.Redis
) -> Callable[..., AbstractAsyncContextManager[StreamConsumer]]:
    """Run a `StreamConsumer` for the length of an `async with` block.

    `run_consumer(handlers, stream=JOBS_INDEX, **config)` — `config` overrides
    `CONSUMER_DEFAULTS`. The consumer gets its own client, as it does in
    production, and stops the way SIGTERM stops it: `stop` is set and the
    entry in hand is finished. A consumer that crashed re-raises here.
    """

    @asynccontextmanager
    async def run(
        handlers: Mapping[str, Handler], *, stream: str = JOBS_INDEX, **config: Any
    ) -> AsyncIterator[StreamConsumer]:
        client = aioredis.from_url(redis_server.url(RedisRole.STREAMS), decode_responses=True)
        consumer = StreamConsumer(
            client, stream, handlers, ConsumerConfig(**{**CONSUMER_DEFAULTS, **config})
        )
        stop = asyncio.Event()
        task = asyncio.create_task(consumer.run(stop))
        try:
            yield consumer
        finally:
            stop.set()
            try:
                await asyncio.wait_for(task, timeout=DRAIN_SECONDS)
            finally:
                await client.aclose()

    return run
