"""Message endpoints (spec §3.1).

A separate module from `routers/channels.py` even though two of the three routes
hang off `/channels/{id}`: these are a different resource with a different
authority rule, and they own different rows of the design doc's endpoint table.

**Visibility is the guard, for reading and for writing.** Every route here goes
through `channels.get_visible` and never through `channels.is_member`. Spec §3.1
says "channel member" against these rows; taken literally it would make a public
channel readable only by whoever created it, because nothing in this scope lets
anyone join a channel themselves. Membership gates administering a channel, not
talking in one.

**A channel you cannot see is a 404, and so is a message in it.** The two misses
raise the same wording deliberately: a caller must not be able to tell "no such
message" from "not your channel", or the id becomes an oracle.

**Plain `require_user`.** Messages are not in the fail-closed denylist set
(Conventions §5.2, spec §3.1), so an unreachable R1 fails open here as it does
for ordinary reads.

**Every write publishes to the channel's room after it commits, never before.**
A broadcast for a row whose transaction then fails is a message that exists only
in other people's windows. `sio` is `None` under `ASGITransport`, so the
publisher is a return statement in every integration test — the router code is
the same either way.
"""

from __future__ import annotations

import uuid

import socketio
from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from messaging import channels, messages, realtime
from messaging.db import session as db_session
from messaging.models import Message
from messaging.schemas import (
    EditMessageRequest,
    MessageListResponse,
    MessageResponse,
    SendMessageRequest,
)
from messaging.settings import Settings
from shared import PageParams, ProblemException, UserPrincipal, require_user

#: Two prefixes, one surface. History and sending hang off the channel that owns
#: them; a single message is addressable on its own.
channel_router = APIRouter(prefix="/api/v1/channels", tags=["messages"])
router = APIRouter(prefix="/api/v1/messages", tags=["messages"])

#: One message per rule, so the composer can put it against the field rather
#: than showing "invalid message" and leaving the user to guess.
_BODY_PROBLEMS: dict[type[Exception], str] = {
    messages.BodyRequiredError: "A message cannot be empty.",
    messages.BodyTooLongError: "A message must be {max_chars} characters or fewer.",
}


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _body_problem(exc: Exception, *, max_chars: int) -> ProblemException:
    message = _BODY_PROBLEMS[type(exc)].format(max_chars=max_chars)
    return ProblemException.validation_error(message, errors={"body": [message]})


def _as_message(row: Message) -> MessageResponse:
    """The DTO, with a deleted row's body redacted here rather than in the query.

    Server-side, and `""` rather than `null`: the DTO types `body` as a non-null
    string, so a null would force a check at every render site in the SPA. The
    client renders the tombstone from `deletedAt`.

    Nothing in this slice can set `deleted_at` — the delete arrives next — but
    the read path ships complete, so that slice adds writes and changes no
    reads.
    """
    response = MessageResponse.model_validate(row, from_attributes=True)
    return response.model_copy(update={"body": ""}) if row.deleted_at else response


async def _visible_channel(
    session: AsyncSession, principal: UserPrincipal, channel_id: uuid.UUID
) -> channels.VisibleChannel:
    found = await channels.get_visible(
        session,
        workspace_id=principal.workspace_id,
        user_id=principal.user_id,
        channel_id=channel_id,
    )
    if found is None:
        raise ProblemException.not_found("No such channel.")
    return found


async def _visible_message(
    session: AsyncSession, principal: UserPrincipal, message_id: uuid.UUID
) -> Message:
    """A message, if the caller can see the channel it is in.

    Both halves raise the same 404 wording on purpose — see the module
    docstring.
    """
    found = await messages.get(session, message_id=message_id)
    if found is None:
        raise ProblemException.not_found("No such channel.")

    await _visible_channel(session, principal, found.channel_id)
    return found


@channel_router.get("/{channel_id}/messages", response_model=MessageListResponse)
async def list_messages(
    channel_id: uuid.UUID,
    page: PageParams,
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
) -> MessageListResponse:
    """A channel's history, newest first, cursor-paginated (Conventions §4.1).

    Deleted messages are included, with their bodies redacted — the tombstone is
    part of the history, not something the client reconstructs.
    """
    await _visible_channel(session, principal, channel_id)

    found = await messages.history_page(session, channel_id=channel_id, page=page)
    return MessageListResponse(
        items=[_as_message(m) for m in found.items], next_cursor=found.next_cursor
    )


@channel_router.post(
    "/{channel_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def send_message(
    channel_id: uuid.UUID,
    body: SendMessageRequest,
    request: Request,
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
    sio: socketio.AsyncServer | None = Depends(realtime.server),
) -> MessageResponse:
    """Say something in a channel the caller can see.

    Spec §3.1 keeps this as the REST fallback once the Socket.IO send exists;
    both call the same domain function, so the rules cannot drift between them.
    """
    await _visible_channel(session, principal, channel_id)
    max_chars = _settings(request).messaging_max_body_chars

    try:
        created = await messages.create(
            session,
            channel_id=channel_id,
            author_id=principal.user_id,
            body=body.body,
            max_chars=max_chars,
        )
    except tuple(_BODY_PROBLEMS) as exc:
        raise _body_problem(exc, max_chars=max_chars) from exc

    response = _as_message(created)
    await session.commit()
    await realtime.publish_message_received(sio, response)
    return response


@router.get("/{message_id}", response_model=MessageResponse)
async def get_message(
    message_id: uuid.UUID,
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
) -> MessageResponse:
    """One message, if the caller can see the channel it is in."""
    return _as_message(await _visible_message(session, principal, message_id))


@router.patch("/{message_id}", response_model=MessageResponse)
async def edit_message(
    message_id: uuid.UUID,
    body: EditMessageRequest,
    request: Request,
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
    sio: socketio.AsyncServer | None = Depends(realtime.server),
) -> MessageResponse:
    """Rewrite a message. **The author, and nobody else.**

    Not even a channel admin, who *can* delete this message. That asymmetry is
    the point rather than an oversight: deleting someone's words is moderation,
    and rewriting them under their name is forgery.

    403 here and not 404, which is the opposite of the channel rules two files
    over — and correct. A message the caller cannot see never reaches this
    check; one they can see is already on their screen, so refusing the edit
    discloses nothing, and a 404 would be a lie about a row they are looking at.

    There is no time window (register D8d).
    """
    max_chars = _settings(request).messaging_max_body_chars

    try:
        edited = await messages.edit(
            session,
            workspace_id=principal.workspace_id,
            user_id=principal.user_id,
            message_id=message_id,
            body=body.body,
            expected_version=body.version,
            max_chars=max_chars,
        )
    except tuple(_BODY_PROBLEMS) as exc:
        raise _body_problem(exc, max_chars=max_chars) from exc
    except messages.AlreadyDeletedError as exc:
        # 409, not 404: the tombstone is right there in the history the caller
        # is reading, so "no such message" would be untrue. The request is
        # well-formed and the resource's state refuses it, which is what 409 is
        # for.
        raise ProblemException.conflict("This message was deleted.") from exc
    except messages.NotAuthorError as exc:
        raise ProblemException.forbidden("Only the author can edit a message.") from exc
    except messages.VersionConflictError as exc:
        raise ProblemException.conflict(
            "This message was changed by someone else. Reload and try again."
        ) from exc

    if edited is None:
        raise ProblemException.not_found("No such channel.")

    response = _as_message(edited)
    await session.commit()
    await realtime.publish_message_edited(sio, response)
    return response


@router.delete("/{message_id}", response_model=MessageResponse)
async def delete_message(
    message_id: uuid.UUID,
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
    sio: socketio.AsyncServer | None = Depends(realtime.server),
) -> MessageResponse:
    """Tombstone a message. The author, or an admin of its channel.

    **200 with the tombstoned message, not 204.** A delete here does not remove
    a row from the list — it stays with `body: ""` and `deletedAt` set, and the
    client has to render it. With 204 the client would have to refetch a page it
    is already holding to learn what to draw; with the row in hand it replaces
    one entry in its cache. The same argument as returning the created row from
    a `POST`, and a deliberate deviation from "DELETE returns 204" rather than a
    surprise in the OpenAPI document.

    Deleting twice returns the same tombstone, unchanged.
    """
    try:
        deleted = await messages.delete(
            session,
            workspace_id=principal.workspace_id,
            user_id=principal.user_id,
            message_id=message_id,
        )
    except messages.NotDeletableError as exc:
        raise ProblemException.forbidden(
            "Only the author or a channel admin can delete a message."
        ) from exc

    if deleted is None:
        raise ProblemException.not_found("No such channel.")

    response = _as_message(deleted)
    await session.commit()
    # The redacted DTO, not an id: the row stays in the history and every
    # recipient has to render the tombstone.
    await realtime.publish_message_deleted(sio, response)
    return response
