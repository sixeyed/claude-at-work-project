"""One Redis Streams consumer loop, reusable by every job stream (doc 05 §5.1).

Read → dispatch by envelope `type` → on success `XACK` and `XDEL`. A handler
that raises leaves its entry pending; a reclaim pass re-delivers entries idle
longer than the visibility timeout, and an entry delivered more than
`max_attempts` times goes to `<stream>:dead` instead of running again.

Four rules worth reading before changing this file:

**The attempt count is Redis's, not the envelope's.** Stream entries cannot be
edited, so `attempt` in the envelope stays at 1 forever. `XAUTOCLAIM` bumps the
entry's delivery count, and `XPENDING` reports it — that is the number compared
with `max_attempts`.

**Acked entries are deleted.** Index jobs carry message bodies (doc 05 §8), and
an acked entry left in the stream is user content kept for no reason. `XDEL`
after `XACK` removes it without a producer-side `MAXLEN`, which would drop
*unread* jobs whenever the Worker was down for long enough.

**Some failures are not worth retrying.** A malformed envelope, an unknown
`type`, or a handler raising `PermanentJobError` go to dead-letter on the first
delivery — five identical failures teach nobody anything.

**Nothing logged here carries job content.** Job ids, types and exception
class names only; the payload may hold a message body.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

import redis.asyncio as aioredis
from pydantic import ValidationError
from redis.exceptions import RedisError, ResponseError

from shared import JOB_DATA_FIELD, JobEnvelope

_log = logging.getLogger("collabhub.worker.consumer")

Handler = Callable[[JobEnvelope], Awaitable[None]]

#: Pause after a Redis error before trying the loop again.
_REDIS_BACKOFF_SECONDS = 2.0


class PermanentJobError(Exception):
    """Retrying this job cannot succeed; dead-letter it now.

    The message is a short fixed reason written by a handler — it lands in the
    dead-letter entry and the log, so never pass exception text through it.
    """


@dataclass(frozen=True)
class ConsumerConfig:
    consumer: str
    batch_size: int
    visibility_timeout_seconds: int
    max_attempts: int
    dead_letter_maxlen: int
    block_ms: int = 5000
    group: str = "worker"


class StreamConsumer:
    def __init__(
        self,
        client: aioredis.Redis,
        stream: str,
        handlers: Mapping[str, Handler],
        config: ConsumerConfig,
    ) -> None:
        self._client = client
        self._stream = stream
        self._handlers = handlers
        self._config = config

    @property
    def dead_stream(self) -> str:
        return f"{self._stream}:dead"

    async def run(self, stop: asyncio.Event) -> None:
        """Consume until `stop` is set, finishing the entry in hand first."""
        loop = asyncio.get_running_loop()
        reclaim_every = max(1.0, self._config.visibility_timeout_seconds / 2)
        next_reclaim = 0.0
        group_ready = False

        while not stop.is_set():
            try:
                if not group_ready:
                    await self._ensure_group()
                    group_ready = True
                if loop.time() >= next_reclaim:
                    await self._reclaim(stop)
                    next_reclaim = loop.time() + reclaim_every
                await self._read_new(stop)
            except RedisError as exc:
                _log.warning(
                    "redis error on %s (%s); retrying in %ss",
                    self._stream,
                    type(exc).__name__,
                    _REDIS_BACKOFF_SECONDS,
                )
                await asyncio.sleep(_REDIS_BACKOFF_SECONDS)

    async def _ensure_group(self) -> None:
        try:
            await self._client.xgroup_create(
                self._stream, self._config.group, id="0", mkstream=True
            )
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def _read_new(self, stop: asyncio.Event) -> None:
        response = await self._client.xreadgroup(
            self._config.group,
            self._config.consumer,
            {self._stream: ">"},
            count=self._config.batch_size,
            block=self._config.block_ms,
        )
        for _stream, entries in response or []:
            for entry_id, fields in entries:
                # First delivery: nothing to compare against max_attempts yet.
                await self._process(entry_id, fields, deliveries=1)
                if stop.is_set():
                    return

    async def _reclaim(self, stop: asyncio.Event) -> None:
        start = "0-0"
        while not stop.is_set():
            result = await self._client.xautoclaim(
                self._stream,
                self._config.group,
                self._config.consumer,
                min_idle_time=self._config.visibility_timeout_seconds * 1000,
                start_id=start,
                count=self._config.batch_size,
            )
            next_start, claimed = result[0], result[1]
            claimed = [(entry_id, fields) for entry_id, fields in claimed if fields]
            if claimed:
                counts = await self._delivery_counts([entry_id for entry_id, _ in claimed])
                for entry_id, fields in claimed:
                    deliveries = counts.get(entry_id, self._config.max_attempts + 1)
                    await self._process(entry_id, fields, deliveries=deliveries)
            if next_start == "0-0":
                return
            start = next_start

    async def _delivery_counts(self, entry_ids: list[str]) -> dict[str, int]:
        pending = await self._client.xpending_range(
            self._stream,
            self._config.group,
            min=entry_ids[0],
            max=entry_ids[-1],
            count=len(entry_ids),
        )
        return {row["message_id"]: row["times_delivered"] for row in pending}

    async def _process(self, entry_id: str, fields: Mapping[str, str], *, deliveries: int) -> None:
        raw = fields.get(JOB_DATA_FIELD)
        try:
            envelope = JobEnvelope.decode(raw) if raw is not None else None
        except ValidationError:
            envelope = None
        if envelope is None:
            await self._dead_letter(entry_id, raw, "malformed-envelope", deliveries)
            return

        if deliveries > self._config.max_attempts:
            await self._dead_letter(entry_id, raw, "max-attempts", deliveries)
            return

        handler = self._handlers.get(envelope.job_type)
        if handler is None:
            await self._dead_letter(entry_id, raw, "unknown-type", deliveries)
            return

        try:
            await handler(envelope)
        except PermanentJobError as exc:
            await self._dead_letter(entry_id, raw, f"permanent:{exc}", deliveries)
            return
        # BLE001: any other failure is retryable by definition — the entry stays
        # pending and the reclaim pass delivers it again.
        except Exception as exc:  # noqa: BLE001
            _log.warning(
                "job %s (%s) failed on delivery %d: %s",
                envelope.job_id,
                envelope.job_type,
                deliveries,
                type(exc).__name__,
            )
            return

        await self._complete(entry_id)

    async def _complete(self, entry_id: str) -> None:
        async with self._client.pipeline(transaction=True) as pipe:
            pipe.xack(self._stream, self._config.group, entry_id)
            pipe.xdel(self._stream, entry_id)
            await pipe.execute()

    async def _dead_letter(
        self, entry_id: str, raw: str | None, reason: str, deliveries: int
    ) -> None:
        _log.warning(
            "dead-lettering %s entry %s: %s after %d deliveries",
            self._stream,
            entry_id,
            reason,
            deliveries,
        )
        async with self._client.pipeline(transaction=True) as pipe:
            pipe.xadd(
                self.dead_stream,
                {
                    JOB_DATA_FIELD: raw or "",
                    "error": reason,
                    "deliveries": str(deliveries),
                    "sourceId": entry_id,
                },
                maxlen=self._config.dead_letter_maxlen,
                approximate=True,
            )
            pipe.xack(self._stream, self._config.group, entry_id)
            pipe.xdel(self._stream, entry_id)
            await pipe.execute()
