"""The `jobs:index` producer (doc 02 §5 step 4, register D25).

Called after every committed message write — send, edit and delete, over REST
and over the socket — right after the room broadcast. Order everywhere:
commit → broadcast → enqueue.

**Fire-and-forget, as Conventions §7 says.** The write has already succeeded
and the client is owed its response; an unreachable R3 must not turn that into
an error. So a failed enqueue is logged and swallowed, and search misses that
change until a reindex path exists (register D29, 🔴). `JobQueue.from_url` keeps
the socket timeouts short so the attempt cannot hang a request either.

**It enqueues the response DTO, not the ORM row.** The DTO is what was
committed and already has a deleted message's body redacted to `""`, so a
delete job cannot carry text the user asked to remove.

**The workspace is the caller's `wsp` claim.** `messages` has no workspace
column; the visibility check that let the write happen is what proved the
channel belongs to that workspace.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import Request

from contracts import JOBS_INDEX, MESSAGE_DELETE, MESSAGE_UPSERT, MessageIndexPayload
from messaging.schemas import MessageResponse
from shared import JobQueue

_log = logging.getLogger("collabhub.messaging.indexing")


def queue(request: Request) -> JobQueue:
    """FastAPI dependency: `jobs = Depends(indexing.queue)`.

    The `Request` annotation is load-bearing, as it is on `realtime.server`.
    """
    return request.app.state.jobs


async def enqueue_upsert(
    jobs: JobQueue, message: MessageResponse, *, workspace_id: uuid.UUID
) -> None:
    await _enqueue(jobs, MESSAGE_UPSERT, message, workspace_id)


async def enqueue_delete(
    jobs: JobQueue, message: MessageResponse, *, workspace_id: uuid.UUID
) -> None:
    await _enqueue(jobs, MESSAGE_DELETE, message, workspace_id)


async def _enqueue(
    jobs: JobQueue, job_type: str, message: MessageResponse, workspace_id: uuid.UUID
) -> None:
    payload = MessageIndexPayload(
        message_id=message.id,
        channel_id=message.channel_id,
        workspace_id=workspace_id,
        author_id=message.author_id,
        body=message.body,
        created_at=message.created_at,
        version=message.version,
    )
    try:
        await jobs.enqueue(JOBS_INDEX, job_type, payload)
    # BLE001: fire-and-forget — whatever went wrong, the committed write stands.
    except Exception as exc:  # noqa: BLE001
        _log.warning(
            "%s not enqueued for message %s (%s); search will miss this change",
            job_type,
            message.id,
            type(exc).__name__,
        )
