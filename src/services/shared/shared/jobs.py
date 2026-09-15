"""The job envelope and the producer half of Redis Streams (Conventions §7).

Every stream entry has one field, `data`, holding this envelope as JSON. The
envelope is generic — `payload` is a plain dict here — and the typed payload
models live in `collabhub-contracts`, beside the stream names both sides agree
on. `shared` knows how a job travels; `contracts` knows what a job says.

**`attempt` is informational.** Producers write `1` and nothing ever rewrites
it: a stream entry is immutable once added, so the Worker counts retries with
Redis's own delivery count instead. The field stays because Conventions §7.1
names it and a reader of a dead-lettered entry should not find it missing.

**The producer never blocks on the Worker, and must not block on Redis either.**
`from_url` sets short socket timeouts, so an unreachable R3 costs a write about
a second and an exception the caller logs and swallows — not a request that
hangs until the client gives up.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as aioredis
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from shared.ids import uuid7

#: The single field every stream entry carries (Conventions §7.1).
JOB_DATA_FIELD = "data"

#: Envelope schema version — not the source row's version, which is payload.
ENVELOPE_VERSION = 1


class JobEnvelope(BaseModel):
    """Conventions §7.1, camelCase on the wire."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    job_id: uuid.UUID
    # `type` on the wire; `job_type` in Python so no attribute shadows a builtin.
    job_type: str = Field(alias="type")
    version: int = ENVELOPE_VERSION
    occurred_at: datetime
    attempt: int = 1
    payload: dict[str, Any]

    @classmethod
    def new(cls, job_type: str, payload: BaseModel) -> JobEnvelope:
        return cls(
            job_id=uuid7(),
            job_type=job_type,
            occurred_at=datetime.now(UTC),
            payload=payload.model_dump(mode="json", by_alias=True),
        )

    def encode(self) -> str:
        return self.model_dump_json(by_alias=True)

    @classmethod
    def decode(cls, raw: str | bytes) -> JobEnvelope:
        return cls.model_validate_json(raw)


class JobQueue:
    """`XADD` one envelope onto a stream. Fire-and-forget: callers catch."""

    def __init__(self, client: aioredis.Redis) -> None:
        self._client = client

    @classmethod
    def from_url(cls, url: str, *, timeout_seconds: float = 1.0) -> JobQueue:
        return cls(
            aioredis.from_url(
                url,
                decode_responses=True,
                socket_connect_timeout=timeout_seconds,
                socket_timeout=timeout_seconds,
            )
        )

    async def enqueue(self, stream: str, job_type: str, payload: BaseModel) -> JobEnvelope:
        envelope = JobEnvelope.new(job_type, payload)
        await self._client.xadd(stream, {JOB_DATA_FIELD: envelope.encode()})
        return envelope

    async def aclose(self) -> None:
        await self._client.aclose()
