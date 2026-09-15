"""The `messages` index: its mapping and its creation (doc 05 §4).

The Worker owns index lifecycle. Readers — Messaging's search route — use the
alias `messages` and never name `messages-v1`, so a reindex can build
`messages-v2` beside it and move the alias in one step.

**`dynamic: strict`.** A field nobody mapped is a bug in a producer, and a
strict index rejects it loudly instead of guessing a type that a later reindex
would have to live with.

**`deleted` is a field, not an absence.** A deleted message is a tombstone
document with no `body` (register D8d, and the ADR for message search):
hard-deleting it would let a late, stale upsert recreate it once Elasticsearch
forgets the deleted version (`index.gc_deletes`, 60 s by default).
"""

from __future__ import annotations

from typing import Any

from elasticsearch import AsyncElasticsearch, BadRequestError

from contracts import MESSAGES_ALIAS

MESSAGES_INDEX = "messages-v1"

MESSAGES_MAPPINGS: dict[str, Any] = {
    "dynamic": "strict",
    "properties": {
        "messageId": {"type": "keyword"},
        "channelId": {"type": "keyword"},
        "workspaceId": {"type": "keyword"},
        "authorId": {"type": "keyword"},
        "body": {"type": "text"},
        "createdAt": {"type": "date"},
        "deleted": {"type": "boolean"},
    },
}


async def ensure_messages_index(es: AsyncElasticsearch) -> None:
    """Create `messages-v1` with its alias, or accept that a replica already did."""
    try:
        await es.indices.create(
            index=MESSAGES_INDEX,
            mappings=MESSAGES_MAPPINGS,
            aliases={MESSAGES_ALIAS: {}},
        )
    except BadRequestError as exc:
        if exc.error != "resource_already_exists_exception":
            raise
