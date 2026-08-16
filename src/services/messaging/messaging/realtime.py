"""The Socket.IO `/messaging` namespace — handshake, rooms, and the broadcasts (spec §3.2).

This module owns the *read* half of real-time: authenticating a connection,
putting it in the right rooms, and publishing what the REST routes just wrote.
The inbound write events live in `realtime_writes.py`.

**The publishers no-op when there is no server.** `create_app` sets
`app.state.realtime = None`, and only `build_asgi_app` replaces it with a real
`AsyncServer`. So every integration test that drives the app over
`httpx.ASGITransport` exercises the same router code with the broadcast turned
into a return statement — one code path, tested with and without a socket behind
it, instead of a mock.

**A connection is authenticated once, at the handshake.** An access token lives
fifteen minutes (Conventions §5.1) and a connection can outlive it, so a revoked
user keeps receiving messages until their client reconnects. That is deliberate
and bounded rather than overlooked: the alternative is a denylist round trip on
every emit — on the hot path, for every recipient — or an R2 fan-out of
revocations, and the SPA re-establishes the socket whenever the access token
changes, which it does about a minute before every expiry. The exposure is at
most one token lifetime on a connection the client re-opens on that cadence
anyway.

**The workspace is the one the token opened with** (Conventions §5.4). No
handler reads a workspace from an event payload, for the same reason no router
reads one from a path.

**Handlers never raise.** A raising Socket.IO handler drops the client's
acknowledgement callback and the browser waits forever. `@_acked` converts a
`ProblemException` into an error ack instead — the same Problem Details document
the REST call would have returned, so the SPA has one error vocabulary and not
two.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from functools import wraps
from typing import Any
from urllib.parse import parse_qs

import socketio
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from messaging import channels
from messaging.schemas import MessageResponse
from messaging.settings import Settings
from shared import ProblemException, SecurityContext, problem_body, verify_user_token

_log = logging.getLogger("collabhub.messaging.realtime")

#: Conventions §6: one namespace per feature area.
NAMESPACE = "/messaging"

#: The R2 pub/sub channel this service's backplane uses.
#:
#: **Not the default.** `AsyncRedisManager`'s default is `channel="socketio"`,
#: the same string in every service — and Canvas puts its backplane on the same
#: R2 instance (doc 03 §4.1). Two managers on one channel means every Canvas
#: emit is delivered into this process and re-dispatched against these rooms.
#: `doc:{id}` does not match `channel:{id}` today, so nothing visibly breaks —
#: which is the worst kind of latent bug, because it becomes a cross-service
#: leak the first time either service names a room the other could name too.
BACKPLANE_CHANNEL = "messaging"


def room(channel_id: uuid.UUID | str) -> str:
    """The room every member of a channel shares (Conventions §6)."""
    return f"channel:{channel_id}"


@dataclass(frozen=True)
class RealtimeContext:
    """Everything the socket server needs, taken from the app that owns it.

    Built by `build_asgi_app` out of the FastAPI app's own state, so there is
    exactly one engine, one session factory and one JWKS cache in the process —
    not a second set living behind the socket server.
    """

    settings: Settings
    sessions: async_sessionmaker[AsyncSession]
    security: SecurityContext


# --- the ack envelope ------------------------------------------------------
#
# No design doc defines an error shape for a socket acknowledgement; Conventions
# §4.2 stops at HTTP. This is it, and it is deliberately the *same document* a
# REST call would have returned, under a key named for what it is.


def _ok(data: Any = None) -> dict[str, Any]:
    return {"ok": True} if data is None else {"ok": True, "data": data}


def _problem(exc: ProblemException) -> dict[str, Any]:
    # No `instance` and no `traceId`: a socket handler has no request path, and
    # an invented trace id correlates with nothing.
    return {"ok": False, "problem": problem_body(exc)}


def _acked(handler):
    """Turn a `ProblemException` into an error ack rather than a lost callback.

    Socket.IO swallows an exception from a handler, and the client's callback is
    simply never invoked — so a bug that would be a 500 over HTTP is a hung
    spinner here. Anything unexpected becomes a generic 500-shaped ack and goes
    to the log, exactly as `install_problem_handlers` does for HTTP.
    """

    @wraps(handler)
    async def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            return await handler(*args, **kwargs)
        except ProblemException as exc:
            return _problem(exc)
        except Exception:
            _log.exception("unhandled error in socket handler %s", handler.__name__)
            return _problem(ProblemException(500))

    return wrapper


def build_server(context: RealtimeContext) -> socketio.AsyncServer:
    """The `/messaging` namespace, wired to R2 and to this app's database."""
    server = socketio.AsyncServer(
        async_mode="asgi",
        client_manager=socketio.AsyncRedisManager(
            context.settings.redis_realtime_url, channel=BACKPLANE_CHANNEL
        ),
        # **`or None`, and the distinction is load-bearing.** Conventions §5.6
        # makes an empty list mean "install no CORS at all" — a service behind
        # one ingress shares its SPA's origin. engine.io reads an empty list as
        # an allow-list containing nothing and refuses every browser handshake
        # with a 400. `None` is its spelling of "same origin only".
        cors_allowed_origins=context.settings.cors_allowed_origins or None,
    )

    async def principal_for(sid: str):
        session = await server.get_session(sid, namespace=NAMESPACE)
        return session["principal"]

    @server.event(namespace=NAMESPACE)
    async def connect(sid: str, environ: dict[str, Any], auth: dict[str, Any] | None) -> None:
        """Authenticate the handshake, or refuse it.

        `ConnectionRefusedError` is the only way a Socket.IO `connect` handler
        can say no; the message reaches the browser as `connect_error`. Refusing
        by returning `False` would give the client nothing to distinguish "your
        token expired" from "the server is unwell", and the SPA needs that
        difference — a refusal it should stop retrying, a drop it should not.
        """
        token = _token_from(environ, auth)
        if token is None:
            raise ConnectionRefusedError("A Bearer access token is required.")

        try:
            # `sensitive=False`: this surface is outside the fail-closed set in
            # Conventions §5.2, so an unreachable R1 accepts the token exactly
            # as it does for `GET /channels`.
            principal = await verify_user_token(context.security, token, sensitive=False)
        except ProblemException as exc:
            raise ConnectionRefusedError(exc.detail or exc.title) from exc

        # `namespace=NAMESPACE` on every session and room call. The default is
        # `/`, and a session saved there is invisible to a `/messaging` handler
        # — which looks exactly like "the principal vanished".
        await server.save_session(sid, {"principal": principal}, namespace=NAMESPACE)
        _log.info("socket connected", extra={"userId": str(principal.user_id)})

    @server.event(namespace=NAMESPACE)
    async def disconnect(sid: str, *_: Any) -> None:
        # Rooms are released by Socket.IO itself; this exists so a disconnect is
        # visible in the logs beside the connect that preceded it.
        _log.info("socket disconnected")

    @server.event(namespace=NAMESPACE)
    @_acked
    async def join_channel(sid: str, channel_id: str) -> dict[str, Any]:
        """Subscribe this connection to a channel's broadcasts.

        **The room mirrors the read rule.** Authorized on
        `channels.get_visible`, never on `channels.is_member` — otherwise a
        public channel would broadcast only to the people who had been added to
        it, and nothing in this scope lets anyone add themselves. A channel the
        caller cannot see acks a 404 and never a 403.
        """
        principal = await principal_for(sid)

        async with context.sessions() as session:
            visible = await channels.get_visible(
                session,
                workspace_id=principal.workspace_id,
                user_id=principal.user_id,
                channel_id=uuid.UUID(channel_id),
            )
        if visible is None:
            raise ProblemException.not_found("No such channel.")

        await server.enter_room(sid, room(channel_id), namespace=NAMESPACE)
        return _ok()

    @server.event(namespace=NAMESPACE)
    @_acked
    async def leave_channel(sid: str, channel_id: str) -> dict[str, Any]:
        """Unsubscribe. No authorization — leaving a room you should not be in
        is the correct outcome, not something to refuse."""
        await server.leave_room(sid, room(channel_id), namespace=NAMESPACE)
        return _ok()

    return server


def _token_from(environ: dict[str, Any], auth: dict[str, Any] | None) -> str | None:
    """The handshake token, from the `auth` payload or the query string.

    Conventions §6 allows both. The `auth` payload is what the SPA sends; the
    query-string fallback is for clients that cannot set it, and it is worth
    remembering that a query string ends up in access logs — which is why it is
    the fallback and not the primary.
    """
    if auth and auth.get("token"):
        return str(auth["token"])

    query = parse_qs(environ.get("QUERY_STRING", ""))
    values = query.get("access_token")
    return values[0] if values else None


# --- the outbound half -----------------------------------------------------


async def _publish(sio: socketio.AsyncServer | None, event: str, message: MessageResponse) -> None:
    """Emit one message DTO to its channel's room, if there is a server at all.

    The payload is `model_dump(mode="json", by_alias=True)` — byte for byte the
    camelCase shape the REST route returns. The SPA writes these into the same
    TanStack cache entry as REST-loaded rows and reads both through one
    generated type, so two casings in one cache entry would be a render bug per
    message rather than a caught error. `mode="json"` is what turns the
    timestamps into ISO strings the JSON encoder will accept.
    """
    if sio is None:
        return

    await sio.emit(
        event,
        message.model_dump(mode="json", by_alias=True),
        room=room(message.channel_id),
        namespace=NAMESPACE,
    )


async def publish_message_received(
    sio: socketio.AsyncServer | None, message: MessageResponse
) -> None:
    await _publish(sio, "message_received", message)


async def publish_message_edited(
    sio: socketio.AsyncServer | None, message: MessageResponse
) -> None:
    await _publish(sio, "message_edited", message)


async def publish_message_deleted(
    sio: socketio.AsyncServer | None, message: MessageResponse
) -> None:
    """The **redacted message**, not `{messageId, channelId}` as spec §3.2 had it.

    A delete is a state transition of a row that stays in the history, so a
    client holding only an id could do nothing but remove the row — which is the
    behaviour the tombstone exists to prevent — or refetch, which defeats the
    point of the event.
    """
    await _publish(sio, "message_deleted", message)


def server(request: Request) -> socketio.AsyncServer | None:
    """FastAPI dependency: `sio = Depends(realtime.server)`.

    Shaped like `db.session` so the routers keep the `Depends` idiom instead of
    reaching into `request.app.state` inline. `None` under `ASGITransport`, which
    is what makes the publishers inert in the integration tests.

    **The `Request` annotation is load-bearing**, not decoration: FastAPI injects
    the request by *type*, and without it this reads as a query parameter named
    `request` and every write route starts answering 422.
    """
    return request.app.state.realtime
