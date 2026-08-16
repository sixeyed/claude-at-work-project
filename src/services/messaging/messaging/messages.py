"""Message domain logic (spec §3.1, §4).

Same shape as `channels.py`: plain async functions taking an `AsyncSession`
first, raising domain exceptions the router translates, no FastAPI imports — so
the same rules serve the REST routes today and the Socket.IO handlers later.

Two rules here are the ones worth stating before the code rather than after.

**Visibility gates reading and writing; membership gates administration.** The
guard on every route into this module is `channels.get_visible`, never
`channels.is_member`. The design doc says "channel member" against these
endpoints, and taken literally it recreates the bug slice 1 removed from channel
detail: nothing in this scope lets a user join a channel themselves, so a
public channel nobody could read would be a channel nobody could ever read.
Posting does not create a membership row either — `myRole` stays `null` for
someone who has said something in a public channel they never joined.

**The read path does not filter `deleted_at`.** A deleted message stays in
history as a tombstone, with its body redacted by the router on the way out. A
tombstone that a reload erases is not a tombstone, and the conversation around a
deleted message stops making sense if the row simply disappears. This is a
documented, message-specific exception to Conventions §3 — and it is why
`ix_messages_channel_time` has no `WHERE deleted_at IS NULL`.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from messaging import channels
from messaging.channels import VersionConflictError
from messaging.models import Message
from shared import Page, PageRequest, build_page, uuid7

__all__ = [
    "AlreadyDeletedError",
    "BodyRequiredError",
    "BodyTooLongError",
    "NotAuthorError",
    "NotDeletableError",
    "VersionConflictError",
    "create",
    "delete",
    "edit",
    "get",
    "history_page",
    "validate_body",
]


class BodyRequiredError(Exception):
    """Empty, or nothing but whitespace."""


class BodyTooLongError(Exception):
    """Longer than the configured maximum."""


class NotAuthorError(Exception):
    """Only the person who wrote a message may rewrite it.

    Deleting someone's words is moderation and a channel admin may do it;
    rewriting them under their name is forgery and nobody may.
    """


class NotDeletableError(Exception):
    """Neither the author nor an admin of the channel the message is in."""


class AlreadyDeletedError(Exception):
    """There is nothing left to edit — the row is a tombstone."""


def validate_body(raw: str, *, max_chars: int) -> str:
    """Return the body unchanged, or raise the specific rule it breaks.

    One exception per rule, so the composer can put a useful message under
    `errors.body` — the same shape `channels.validate_name` uses.

    **The body is not trimmed**, and that is the one real difference from a
    channel name. Markdown is whitespace-sensitive: an indented code block and a
    trailing double space both mean something. Emptiness is judged on the
    stripped string; length is judged on the raw one.

    `max_chars` is a parameter rather than a module constant because the limit
    is configuration (`MESSAGING_MAX_BODY_CHARS`). Passing it keeps send and
    edit from drifting on what "too long" means.
    """
    if not raw.strip():
        raise BodyRequiredError
    if len(raw) > max_chars:
        raise BodyTooLongError

    return raw


async def create(
    session: AsyncSession,
    *,
    channel_id: uuid.UUID,
    author_id: uuid.UUID,
    body: str,
    max_chars: int,
) -> Message:
    """Add a message to a channel.

    No `IntegrityError` branch, unlike `channels.create`: the only constraint
    that could fire is the channel foreign key, and the caller has already
    proved the channel is visible to get here.
    """
    body = validate_body(body, max_chars=max_chars)

    message = Message(
        id=uuid7(),
        channel_id=channel_id,
        author_id=author_id,
        body=body,
    )
    session.add(message)
    await session.flush()
    return message


async def history_page(
    session: AsyncSession, *, channel_id: uuid.UUID, page: PageRequest
) -> Page[Message]:
    """One page of a channel's history, newest first.

    Keyset on `id DESC` and one key part only: `messages.id` is UUID v7, so it
    is unique *and* time-ordered, which satisfies `shared/pagination.py`'s "the
    sort key must be unique" without a `(created_at, id)` pair. It also matches
    `ix_messages_channel_time` exactly. Never `OFFSET` — page 500 of a busy
    channel would make the database walk and discard everything before it.

    Newest-first is the wire order and not the screen order. The SPA reverses
    once, in `useMessages`'s `select`; nothing here or in the cache flips it,
    because two layers reversing is one layer too many.

    No `deleted_at` filter — see the module docstring.
    """
    query = (
        select(Message)
        .where(Message.channel_id == channel_id)
        .order_by(Message.id.desc())
        .limit(page.fetch_limit)
    )
    if page.cursor:
        (last_id,) = page.cursor
        query = query.where(Message.id < uuid.UUID(last_id))

    rows = (await session.execute(query)).scalars().all()
    return build_page(rows, page, key=lambda m: (str(m.id),))


async def get(session: AsyncSession, *, message_id: uuid.UUID) -> Message | None:
    """One message by id, with no workspace filter of its own.

    Workspace-blind on purpose. It is never called without the channel
    visibility guard behind it, and that guard is what turns "not yours" into
    the same 404 as "not there". Putting a half-check here as well would look
    like defence and would be one more place for the two rules to disagree.
    """
    return await session.get(Message, message_id)


async def _visible(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    message_id: uuid.UUID,
) -> Message | None:
    """The message, if the caller can see the channel it is in.

    `get` above is workspace-blind, and these two writers cannot rely on their
    caller having checked: an `edit` built on the assumption that loading the
    row proved something authorizes on nothing. So the visibility test is here,
    against the loaded row's own `channel_id`, and it is `get_visible` and never
    `is_member` — the same rule the reads follow.
    """
    message = await get(session, message_id=message_id)
    if message is None:
        return None

    visible = await channels.get_visible(
        session,
        workspace_id=workspace_id,
        user_id=user_id,
        channel_id=message.channel_id,
    )
    return message if visible else None


async def edit(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    message_id: uuid.UUID,
    body: str,
    expected_version: int,
    max_chars: int,
) -> Message | None:
    """Rewrite a message. Author only, no time window.

    **The order of the checks is the security property**, not a style choice.
    Visibility, then state, then authorship: asking "are you the author?" first
    would answer "no" for a message in a private channel the caller has never
    been in, which tells them the message is there.

    `edited_at` is what the "edited" marker reads, and it is set on every
    successful edit — including one that leaves the text identical. No
    dirty-check: `version` feeds the Elasticsearch external version, which wants
    to move forward monotonically, and a no-op edit is not worth a special case.

    There is no `updated_at` on this table, unlike `channels`. `edited_at` is
    the equivalent, and copying the channel pattern verbatim would not run.

    `None` means the caller may not see it — the router turns that into the same
    404 an absent id gets.
    """
    message = await _visible(
        session, workspace_id=workspace_id, user_id=user_id, message_id=message_id
    )
    if message is None:
        return None
    if message.deleted_at is not None:
        raise AlreadyDeletedError(message_id)
    if message.author_id != user_id:
        raise NotAuthorError(message_id)

    body = validate_body(body, max_chars=max_chars)

    # The guarded update from `channels.rename`, and the same reason the
    # existence checks came first: `rowcount == 0` has to mean one thing.
    # Folding `deleted_at IS NULL` in here would make a deleted row and a stale
    # version indistinguishable, and the client would be told "someone else
    # changed this" about a message that is gone.
    result = await session.execute(
        update(Message)
        .where(Message.id == message_id, Message.version == expected_version)
        .values(body=body, edited_at=func.now(), version=Message.version + 1)
    )
    if result.rowcount == 0:
        raise VersionConflictError(message_id)

    # The Core UPDATE left the loaded object holding the old version and body,
    # and serialising that would hand the client a version the row no longer
    # has — so their next edit would 409 for no reason they could see.
    await session.refresh(message)
    return message


async def delete(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    message_id: uuid.UUID,
) -> Message | None:
    """Tombstone a message. Author, or an admin of the channel it is in.

    **Unconditional on version** — deleting a message someone just edited is not
    a conflict worth surfacing — but conditional on not being deleted already.
    A second delete returns the existing tombstone untouched: no second
    timestamp and no second version bump, which is what idempotent has to mean
    and what keeps the Elasticsearch external version from moving for a document
    that did not change.

    **The stored `body` is left alone.** Blanking it looks tidy, changes nothing
    a client can see — the mapper redacts every deleted row on the way out — and
    destroys data silently. Hard deletion belongs to a retention job whose window
    is an open decision; a delete path that erased the text now would pre-empt
    it.

    `edited_at` is left alone too, so a message that was edited and then deleted
    carries both timestamps. The client renders the tombstone from `deletedAt`
    alone and never shows an edited marker on a deleted row.
    """
    message = await _visible(
        session, workspace_id=workspace_id, user_id=user_id, message_id=message_id
    )
    if message is None:
        return None

    is_author = message.author_id == user_id
    if not is_author and not await channels.is_admin(
        session, channel_id=message.channel_id, user_id=user_id
    ):
        raise NotDeletableError(message_id)

    if message.deleted_at is not None:
        return message

    await session.execute(
        update(Message)
        .where(Message.id == message_id, Message.deleted_at.is_(None))
        .values(deleted_at=func.now(), version=Message.version + 1)
    )
    await session.refresh(message)
    return message
