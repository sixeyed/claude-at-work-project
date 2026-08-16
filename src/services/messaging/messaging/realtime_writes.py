"""Inbound Socket.IO events — the write half of `/messaging` (spec §3.2).

A module of its own rather than more handlers in `realtime.py`: that file owns
the connection, the rooms and the outbound publishers, and this one owns what a
client can ask the server to do. `register_write_handlers` is the single export,
called once from `build_asgi_app`.

Four rules run through every handler here.

**Nothing raises.** A python-socketio handler that raises never sends its
acknowledgement, so the client's callback simply never fires and the optimistic
bubble hangs forever with no error to show. `@_acked` — S5's, imported — turns a
`ProblemException` into an error ack and anything unexpected into a 500-shaped
one. This is the single most important line in the module.

**Visibility authorizes the write, not room membership.** The delivery plan said
"a client may only act on a channel it has joined", and that is wrong twice
over. It is the wrong *test*: `POST /channels/{id}/messages` is open to anyone
who can see the channel, so gating the socket on membership would make it
stricter than the route it replaces and resurrect the bug that rule closed. And
it is not a durable *fact*: a room is per-`sid` in-memory state, lost on every
reconnect and re-established by the client's own `connect` handler — so a send
across a reconnect would race its own `join_channel` and fail for a reason no
user could act on. A room decides who *receives* a broadcast and nothing else.

**Every write re-checks the token.** A REST call verifies signature, expiry and
the denylist on every request; a socket connection is verified once and can
outlive its fifteen-minute token by hours. That was tolerable while the socket
could only read. Handing it a write path without re-checking would make moving
the composer onto it a security regression.

**The same domain functions the REST routers call.** Not a second copy of the
rules — `messages.create`, `messages.edit`, `messages.delete`, and the same
commit-then-publish order, so the two transports cannot drift on what is allowed.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import socketio
from pydantic import Field, ValidationError

from messaging import channels, messages, realtime
from messaging.realtime import NAMESPACE, RealtimeContext, _acked, _ok
from messaging.routers.messages import _as_message
from messaging.schemas import MAX_BODY_FIELD_LENGTH, CamelRequest
from shared import ProblemException, TokenState, UserPrincipal

_log = logging.getLogger("collabhub.messaging.realtime_writes")


class SendMessagePayload(CamelRequest):
    """`send_message`, narrowed from what spec §3.2 documents.

    The doc lists `threadRootId` and `attachmentIds` as optional. Both are out
    of scope — threading has a column and no API, and attachments are always
    empty because the Asset service is a skeleton — and accepting a field the
    handler drops on the floor is a claim the service does not honour. They
    return with the features that need them.

    Validated here rather than in `schemas.py`: these are not REST bodies, they
    never appear in the OpenAPI document, and they belong beside the handlers
    that read them.
    """

    channel_id: uuid.UUID
    body: str = Field(max_length=MAX_BODY_FIELD_LENGTH)


class EditMessagePayload(CamelRequest):
    """`edit_message` — **with `version`, which spec §3.2 omits.**

    The expected version is required on `PATCH /messages/{id}`, and a socket
    event without one would make this the way to lose someone else's edit
    silently. One rule, two transports.
    """

    message_id: uuid.UUID
    body: str = Field(max_length=MAX_BODY_FIELD_LENGTH)
    version: int


class DeleteMessagePayload(CamelRequest):
    """Unconditional, so no `version` — deleting a message someone else just
    edited is not a conflict worth surfacing."""

    message_id: uuid.UUID


class TypingPayload(CamelRequest):
    channel_id: uuid.UUID


def _parse(model: type[CamelRequest], payload: Any) -> Any:
    """Validate an inbound payload into a problem, never into an exception."""
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise ProblemException.validation_error(
            "The event payload is not valid.",
            errors={"payload": [e["msg"] for e in exc.errors()][:5]},
        ) from exc


def register_write_handlers(sio: socketio.AsyncServer, context: RealtimeContext) -> None:
    """Attach the inbound events to a server S5 already built."""

    async def principal_of(sid: str) -> UserPrincipal:
        """The connection's principal, plus the check the handshake cannot make.

        Expiry is re-tested on **every** inbound event including `typing`: it
        costs nothing and it is the difference between a connection that is
        authenticated and one that merely was.
        """
        session = await sio.get_session(sid, namespace=NAMESPACE)
        principal: UserPrincipal = session["principal"]

        if principal.expires_at <= datetime.now(UTC):
            raise ProblemException.unauthorized("The access token has expired.")
        return principal

    async def check_revoked(principal: UserPrincipal) -> None:
        """The denylist half, on writes only, and **fail-open** on an outage.

        Channel writes are outside the fail-closed set in Conventions §5.2 — the
        REST routers say so in their own docstrings — so an unreachable R1
        accepts the write exactly as it accepts a `GET`.

        `typing` skips this entirely: it persists nothing, and one Redis round
        trip per throttle window is real load for no authority gained.
        """
        state = await context.security.denylist.state(principal.token_id)
        if state is TokenState.REVOKED:
            raise ProblemException.unauthorized("The access token has been revoked.")

    async def authorized_channel(session, principal: UserPrincipal, channel_id: uuid.UUID) -> None:
        visible = await channels.get_visible(
            session,
            # From the principal, and from nothing in the payload — which has no
            # workspace field to be tempted by, exactly as the REST surface has
            # no workspace in a path.
            workspace_id=principal.workspace_id,
            user_id=principal.user_id,
            channel_id=channel_id,
        )
        if visible is None:
            raise ProblemException.not_found("No such channel.")

    @sio.event(namespace=NAMESPACE)
    @_acked
    async def send_message(sid: str, payload: Any) -> dict[str, Any]:
        event = _parse(SendMessagePayload, payload)
        principal = await principal_of(sid)
        await check_revoked(principal)

        async with context.sessions() as session:
            await authorized_channel(session, principal, event.channel_id)

            try:
                created = await messages.create(
                    session,
                    channel_id=event.channel_id,
                    author_id=principal.user_id,
                    body=event.body,
                    max_chars=context.settings.messaging_max_body_chars,
                )
            except messages.BodyRequiredError as exc:
                raise _body_problem("A message cannot be empty.") from exc
            except messages.BodyTooLongError as exc:
                raise _body_problem(
                    f"A message must be {context.settings.messaging_max_body_chars} "
                    "characters or fewer."
                ) from exc

            response = _as_message(created)
            await session.commit()

        # Commit, then publish. A broadcast for a row whose transaction failed
        # is a message that exists only in other people's windows.
        await realtime.publish_message_received(sio, response)
        return _ok(response.model_dump(mode="json", by_alias=True))

    @sio.event(namespace=NAMESPACE)
    @_acked
    async def edit_message(sid: str, payload: Any) -> dict[str, Any]:
        event = _parse(EditMessagePayload, payload)
        principal = await principal_of(sid)
        await check_revoked(principal)

        async with context.sessions() as session:
            try:
                edited = await messages.edit(
                    session,
                    workspace_id=principal.workspace_id,
                    user_id=principal.user_id,
                    message_id=event.message_id,
                    body=event.body,
                    expected_version=event.version,
                    max_chars=context.settings.messaging_max_body_chars,
                )
            except messages.BodyRequiredError as exc:
                raise _body_problem("A message cannot be empty.") from exc
            except messages.BodyTooLongError as exc:
                raise _body_problem(
                    f"A message must be {context.settings.messaging_max_body_chars} "
                    "characters or fewer."
                ) from exc
            except messages.AlreadyDeletedError as exc:
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
        return _ok(response.model_dump(mode="json", by_alias=True))

    @sio.event(namespace=NAMESPACE)
    @_acked
    async def delete_message(sid: str, payload: Any) -> dict[str, Any]:
        event = _parse(DeleteMessagePayload, payload)
        principal = await principal_of(sid)
        await check_revoked(principal)

        async with context.sessions() as session:
            try:
                deleted = await messages.delete(
                    session,
                    workspace_id=principal.workspace_id,
                    user_id=principal.user_id,
                    message_id=event.message_id,
                )
            except messages.NotDeletableError as exc:
                raise ProblemException.forbidden(
                    "Only the author or a channel admin can delete a message."
                ) from exc

            if deleted is None:
                raise ProblemException.not_found("No such channel.")

            response = _as_message(deleted)
            await session.commit()

        await realtime.publish_message_deleted(sio, response)
        # The tombstone, not an id — the row stays in the history and the client
        # that issued the delete has to render it like everyone else.
        return _ok(response.model_dump(mode="json", by_alias=True))

    @sio.event(namespace=NAMESPACE)
    async def typing(sid: str, payload: Any) -> None:
        """Fan out that someone is typing. Ephemeral, and never persisted.

        **No acknowledgement**: there is nothing to confirm. No `typing_stopped`
        either — the receiver expires an indicator on a timer, because a server
        tracking who is typing would need that state shared across pods through
        R2 for something the design calls ephemeral, and would still have to
        invent a timeout for the client that closed its laptop mid-word.

        The payload carries no display name. Messaging holds none, and the
        browser already has the workspace directory it resolves every other name
        from — two sources for one name is the drift that is worth avoiding even
        for an event that cannot go stale.
        """
        try:
            event = _parse(TypingPayload, payload)
            principal = await principal_of(sid)
        except ProblemException:
            # Nothing to ack, so nothing to tell. A malformed or expired typing
            # event is simply not fanned out.
            return

        await sio.emit(
            "user_typing",
            {"channelId": str(event.channel_id), "userId": str(principal.user_id)},
            room=realtime.room(event.channel_id),
            namespace=NAMESPACE,
            # The sender never sees their own indicator. The client also
            # discards its own `userId`, which covers the second tab that
            # `skip_sid` cannot.
            skip_sid=sid,
        )


def _body_problem(message: str) -> ProblemException:
    """The same shape the REST route produces, so one client parser serves both."""
    return ProblemException.validation_error(message, errors={"body": [message]})
