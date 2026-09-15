"""Read state — how far each person has read in each channel.

Same shape as `channels.py` and `messages.py`: plain async functions taking an
`AsyncSession`, no FastAPI imports, so the REST route and the `mark_read` socket
event share one set of rules.

**Visibility gates it, not membership.** Anyone who can see a channel can read
it, so anyone who can see it may say how far they have read. The row lives in
`channel_reads`, not on `channel_members`, for exactly that reason.

**The marker only moves forward.** The upsert is guarded, so an older message
arriving after a newer one — two tabs, or a slow request — is a no-op rather
than a step backwards. UUID v7 ids sort by time in Postgres as they do here.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from messaging import channels, messages
from messaging.models import ChannelRead


async def mark_read(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    channel_id: uuid.UUID,
    message_id: uuid.UUID,
) -> bool | None:
    """Move the caller's marker in a channel up to `message_id`.

    `None` when the caller cannot see the channel, or the message is not in it
    — one answer for both, so the router gives one 404 and an id cannot be
    probed. `True` when the marker moved; `False` when it was already there or
    further on, which callers use to skip a broadcast that would say nothing.

    A tombstone may be marked read: it is part of the history the caller is
    looking at.
    """
    visible = await channels.get_visible(
        session, workspace_id=workspace_id, user_id=user_id, channel_id=channel_id
    )
    if visible is None:
        return None

    message = await messages.get(session, message_id=message_id)
    if message is None or message.channel_id != channel_id:
        return None

    proposed = insert(ChannelRead).values(
        channel_id=channel_id, user_id=user_id, last_read_id=message_id
    )
    statement = proposed.on_conflict_do_update(
        index_elements=[ChannelRead.channel_id, ChannelRead.user_id],
        set_={"last_read_id": proposed.excluded.last_read_id, "updated_at": func.now()},
        where=ChannelRead.last_read_id < proposed.excluded.last_read_id,
    )
    result = await session.execute(statement)
    return result.rowcount == 1
