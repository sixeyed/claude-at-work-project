"""Pydantic DTOs and job payload models shared across CollabHub service boundaries.

Nothing lives here without a producer and a consumer. `indexing` is the first:
Messaging produces message index jobs, the Worker consumes them, and Messaging
reads the index the Worker writes. The job envelope itself is generic and lives
in `collabhub-shared`.

JSON is camelCase on the wire; models declare `alias_generator=to_camel`.
"""

from contracts.indexing import (
    JOBS_INDEX,
    MESSAGE_DELETE,
    MESSAGE_UPSERT,
    MESSAGES_ALIAS,
    MessageIndexPayload,
)

__all__ = [
    "JOBS_INDEX",
    "MESSAGES_ALIAS",
    "MESSAGE_DELETE",
    "MESSAGE_UPSERT",
    "MessageIndexPayload",
]
