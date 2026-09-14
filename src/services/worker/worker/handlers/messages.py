"""`message.upsert` and `message.delete` → the `messages` index (doc 05 §3).

Both are one external-versioned `index` call, which is what makes them
idempotent and order-safe with no bookkeeping of our own: Elasticsearch refuses
a version that is not newer than the one it holds, with a 409. That 409 is
**success** here — it means the index already reflects this change or a later
one, whether the job was delivered twice or arrived after a newer edit.

A delete writes a tombstone at the bumped version: identifiers, `deleted: true`,
and no `body`, so the text leaves the index the moment the job runs.
"""

from __future__ import annotations

from elasticsearch import AsyncElasticsearch, BadRequestError, ConflictError
from pydantic import ValidationError

from contracts import MESSAGE_DELETE, MESSAGE_UPSERT, MESSAGES_ALIAS, MessageIndexPayload
from shared import JobEnvelope
from worker.consumer import Handler, PermanentJobError


def build_message_handlers(es: AsyncElasticsearch) -> dict[str, Handler]:
    async def upsert(envelope: JobEnvelope) -> None:
        await _write(es, envelope, deleted=False)

    async def delete(envelope: JobEnvelope) -> None:
        await _write(es, envelope, deleted=True)

    return {MESSAGE_UPSERT: upsert, MESSAGE_DELETE: delete}


async def _write(es: AsyncElasticsearch, envelope: JobEnvelope, *, deleted: bool) -> None:
    try:
        payload = MessageIndexPayload.model_validate(envelope.payload)
    except ValidationError as exc:
        raise PermanentJobError("invalid payload") from exc

    document = payload.model_dump(mode="json", by_alias=True, exclude={"body", "version"})
    document["deleted"] = deleted
    if not deleted:
        document["body"] = payload.body

    try:
        await es.index(
            index=MESSAGES_ALIAS,
            id=str(payload.message_id),
            document=document,
            version=payload.version,
            version_type="external",
        )
    except ConflictError:
        # Already at this version or newer — see the module docstring.
        return
    except BadRequestError as exc:
        # A mapping rejection will be rejected identically on every retry.
        raise PermanentJobError("rejected by index") from exc
