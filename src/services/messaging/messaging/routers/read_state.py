"""Marking a channel read (spec §3.1).

Its own module because it is its own resource: a per-person pointer, not a
channel attribute and not a message. The rules are the service's usual ones —
workspace from the token, a channel you cannot see is a 404, plain
`require_user`, commit then publish.
"""

from __future__ import annotations

import uuid

import socketio
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from messaging import read_state, realtime
from messaging.db import session as db_session
from messaging.schemas import MarkReadRequest
from shared import ProblemException, UserPrincipal, require_user

router = APIRouter(prefix="/api/v1/channels", tags=["read-state"])


@router.post("/{channel_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(
    channel_id: uuid.UUID,
    body: MarkReadRequest,
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
    sio: socketio.AsyncServer | None = Depends(realtime.server),
) -> None:
    """Mark a channel read up to and including one message.

    **204 either way** — whether the marker moved or was already further on.
    The client sent the newest message it has shown, and "you had already read
    that" is not an error it could act on.

    The receipt goes to the caller's *other* sessions only, and only when the
    marker moved. Nobody else is told how far anyone has read.
    """
    advanced = await read_state.mark_read(
        session,
        workspace_id=principal.workspace_id,
        user_id=principal.user_id,
        channel_id=channel_id,
        message_id=body.message_id,
    )
    if advanced is None:
        raise ProblemException.not_found("No such channel.")

    await session.commit()
    if advanced:
        await realtime.publish_read_receipt(
            sio,
            workspace_id=principal.workspace_id,
            user_id=principal.user_id,
            channel_id=channel_id,
            message_id=body.message_id,
        )
