"""Message indexing: the job Messaging produces and the index the Worker writes.

Both ends import these names, so a renamed stream or alias is one edit that
breaks loudly rather than two that drift. Worker doc 05 §3 and §4, register D25.

**The payload carries the whole document** because the producer already holds
it and the Worker connects to no service database (D25). On `message.delete`
the producer sends `body: ""` — a stream is not a place to keep text somebody
asked to remove — and the Worker writes a tombstone with no body at all.

There is no `op` field. The envelope's `type` already says upsert or delete, and
two fields that could disagree would need a rule for when they do.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

JOBS_INDEX = "jobs:index"

#: What readers query and writers write. The concrete index behind it is the
#: Worker's business (`messages-v1` today), so a reindex can swap it.
MESSAGES_ALIAS = "messages"

MESSAGE_UPSERT = "message.upsert"
MESSAGE_DELETE = "message.delete"


class MessageIndexPayload(BaseModel):
    """The `payload` of both message job types."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    message_id: uuid.UUID
    channel_id: uuid.UUID
    workspace_id: uuid.UUID
    author_id: uuid.UUID
    body: str
    created_at: datetime
    #: `messages.version` — the Elasticsearch external version, so an older
    #: document arriving late is rejected instead of applied.
    version: int = Field(ge=0)
