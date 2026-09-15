"""The `messages` index, built and filled for Messaging's search tests (register D34).

Search reads an index the Worker writes, and Messaging never imports the Worker.
So the index is built here, in the dev-only harness, **with the Worker's own
code**: `ensure_messages_index` for the mapping and alias, and the
`message.upsert` / `message.delete` handlers for the documents. A copy of either
in Messaging's tests would go on passing after the real one changed — a renamed
field, a mapping type — while production search broke.

Documents are written straight through the handlers rather than through the
stream and a consumer: the pipeline is the Worker's tests' business, and a
search test needs exact control over what the index holds, including an index
that lags the database.
"""

from __future__ import annotations

import uuid
from typing import Any

from elasticsearch import AsyncElasticsearch

from contracts import MESSAGE_DELETE, MESSAGE_UPSERT, MESSAGES_ALIAS, MessageIndexPayload
from shared import JobEnvelope
from worker.handlers.messages import build_message_handlers
from worker.index import ensure_messages_index


class MessagesIndex:
    """The Worker's view of the `messages` index, for seeding it."""

    def __init__(self, es: AsyncElasticsearch) -> None:
        self._es = es
        self._handlers = build_message_handlers(es)

    async def create(self) -> None:
        await ensure_messages_index(self._es)

    async def index(
        self, message: dict[str, Any], *, workspace_id: uuid.UUID, deleted: bool = False
    ) -> None:
        """Index a message as the Worker would, from its REST representation.

        `message` is Messaging's `Message` JSON, which is what its producer
        enqueues. `deleted=True` sends the delete job — pass the tombstone the
        delete call returned, so the version is the bumped one.
        """
        payload = MessageIndexPayload(
            message_id=message["id"],
            channel_id=message["channelId"],
            workspace_id=workspace_id,
            author_id=message["authorId"],
            body=message["body"],
            created_at=message["createdAt"],
            version=message["version"],
        )
        job_type = MESSAGE_DELETE if deleted else MESSAGE_UPSERT
        await self._handlers[job_type](JobEnvelope.new(job_type, payload))
        # Searchable now, not after the next refresh interval.
        await self._es.indices.refresh(index=MESSAGES_ALIAS)
