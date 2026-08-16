"""Authentication dependencies used by every service (Conventions §5).

`Depends(require_user)` on user routes, `Depends(require_service("scope"))` on
`/api/v1/internal/` routes, and never both on one route. Verification is local:
the token's signature is checked against a key from the service's `KeySource`,
then the issuer, audience and expiry, then the denylist.

The audience is what keeps the two worlds apart. A user token carries
`aud: collabhub` and a service token `aud: collabhub-internal`, so the check
that already runs on every request is what stops a stolen user token reaching an
internal endpoint — no route-level allowlist to keep in sync.

The workspace comes from the `wsp` claim and nowhere else. Reading a workspace
id out of a path or body and trusting it is the tenancy leak this platform is
most exposed to, so `UserPrincipal` simply has no way to express it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import jwt
from fastapi import FastAPI, Request

from shared.denylist import Denylist, TokenState
from shared.keys import KeySource, UnknownKeyError
from shared.problems import ProblemException

ALGORITHM = "RS256"
SERVICE_SUBJECT_PREFIX = "service:"
_UNAUTHENTICATED_HEADERS = {"WWW-Authenticate": "Bearer"}


@dataclass(frozen=True)
class SecurityConfig:
    issuer: str
    audience: str = "collabhub"
    internal_audience: str = "collabhub-internal"


@dataclass(frozen=True)
class UserPrincipal:
    """An authenticated end user, in exactly one workspace."""

    user_id: uuid.UUID
    workspace_id: uuid.UUID
    roles: tuple[str, ...]
    token_id: str
    display_name: str
    email: str
    expires_at: datetime
    claims: dict[str, Any]

    def has_role(self, *roles: str) -> bool:
        return bool(set(roles) & set(self.roles))


@dataclass(frozen=True)
class ServicePrincipal:
    """Another CollabHub service calling an internal endpoint."""

    name: str
    scopes: tuple[str, ...]
    token_id: str
    expires_at: datetime
    claims: dict[str, Any]


@dataclass(frozen=True)
class SecurityContext:
    key_source: KeySource
    config: SecurityConfig
    denylist: Denylist


def install_security(
    app: FastAPI,
    *,
    key_source: KeySource,
    config: SecurityConfig,
    denylist: Denylist,
) -> None:
    """Give this app what `require_user` / `require_service` need to work."""
    app.state.security = SecurityContext(key_source=key_source, config=config, denylist=denylist)


def _context(request: Request) -> SecurityContext:
    context: SecurityContext | None = getattr(request.app.state, "security", None)
    if context is None:
        raise RuntimeError("install_security() was never called for this app")
    return context


def _unauthorized(detail: str) -> ProblemException:
    return ProblemException.unauthorized(detail, headers=_UNAUTHENTICATED_HEADERS)


def _bearer_token(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise _unauthorized("A Bearer access token is required.")
    return token.strip()


async def decode_claims(context: SecurityContext, token: str, *, audience: str) -> dict[str, Any]:
    """Verify a token string and return its claims.

    Request-free, and that is the whole reason it exists: a Socket.IO handshake
    arrives with a token and no `Request`, so the verification core cannot be
    reachable only through a FastAPI dependency. `_verified_claims` below is now
    a two-line adapter over this.

    Nothing about the checks changed when this moved — the existing tests
    covering `require_user` over HTTP are the evidence.
    """
    try:
        kid = jwt.get_unverified_header(token).get("kid")
    except jwt.PyJWTError:
        raise _unauthorized("The access token is malformed.") from None

    try:
        key = await context.key_source.key_for(kid)
    except UnknownKeyError:
        raise _unauthorized("The access token was signed with an unknown key.") from None

    try:
        return jwt.decode(
            token,
            key,
            algorithms=[ALGORITHM],
            issuer=context.config.issuer,
            audience=audience,
            options={"require": ["exp", "iat", "iss", "aud", "sub", "jti"]},
        )
    except jwt.PyJWTError:
        # Signature, expiry, issuer and audience failures are deliberately one
        # message: which of them failed is useful to an attacker and to nobody
        # else. The detail is in the logs.
        raise _unauthorized("The access token is not valid.") from None


async def _verified_claims(request: Request, *, audience: str) -> dict[str, Any]:
    return await decode_claims(_context(request), _bearer_token(request), audience=audience)


async def verify_user_token(
    context: SecurityContext, token: str, *, sensitive: bool = False
) -> UserPrincipal:
    """Turn a token string into a `UserPrincipal`, or raise a `ProblemException`.

    The request-free half of `require_user`. It raises rather than returning a
    response, so the caller decides how to render the refusal — an HTTP handler
    turns it into a problem document, and the Socket.IO handshake turns it into
    a `ConnectionRefusedError`. That separation is the point of the extraction.

    `sensitive` marks the fail-closed set from Conventions §5.2. A socket
    handshake passes `False`: channel membership is not workspace membership, so
    none of that surface is in the fail-closed set, and an unreachable denylist
    accepts the token exactly as it does for an ordinary read.
    """
    claims = await decode_claims(context, token, audience=context.config.audience)

    subject = str(claims["sub"])
    if subject.startswith(SERVICE_SUBJECT_PREFIX):
        raise _unauthorized("A user access token is required.")

    try:
        user_id = uuid.UUID(subject)
        workspace_id = uuid.UUID(str(claims["wsp"]))
    except (KeyError, ValueError, TypeError):
        raise _unauthorized("The access token is not scoped to a workspace.") from None

    await _check_denylist(context, claims["jti"], sensitive=sensitive)

    return UserPrincipal(
        user_id=user_id,
        workspace_id=workspace_id,
        roles=tuple(claims.get("roles") or ()),
        token_id=claims["jti"],
        display_name=claims.get("name", ""),
        email=claims.get("email", ""),
        expires_at=_expires_at(claims),
        claims=claims,
    )


async def _check_denylist(context: SecurityContext, token_id: str, *, sensitive: bool) -> None:
    state = await context.denylist.state(token_id)

    if state is TokenState.REVOKED:
        raise _unauthorized("The access token has been revoked.")

    if state is TokenState.UNKNOWN and sensitive:
        raise ProblemException.service_unavailable(
            "Token revocation cannot be checked right now; try again shortly."
        )


def _expires_at(claims: dict[str, Any]) -> datetime:
    return datetime.fromtimestamp(claims["exp"], tz=UTC)


class RequireUser:
    """Dependency yielding the authenticated `UserPrincipal`.

    `sensitive=True` marks the fail-closed set from Conventions §5.2 — workspace
    membership changes, role grants, asset deletion — which return 503 rather
    than proceed on a token whose revocation status is unknown.
    """

    def __init__(self, *, sensitive: bool = False) -> None:
        self._sensitive = sensitive

    async def __call__(self, request: Request) -> UserPrincipal:
        return await verify_user_token(
            _context(request), _bearer_token(request), sensitive=self._sensitive
        )


class RequireService:
    """Dependency yielding the calling `ServicePrincipal`, if it holds the scope."""

    def __init__(self, scope: str) -> None:
        self._scope = scope

    async def __call__(self, request: Request) -> ServicePrincipal:
        context = _context(request)
        claims = await _verified_claims(request, audience=context.config.internal_audience)

        subject = str(claims["sub"])
        if not subject.startswith(SERVICE_SUBJECT_PREFIX):
            raise _unauthorized("A service access token is required.")

        scopes = tuple(claims.get("scp") or ())
        if self._scope not in scopes:
            raise ProblemException.forbidden(f"This client lacks the {self._scope!r} scope.")

        # Service tokens live for minutes and are revoked by rotating the client
        # secret, not through the denylist (Conventions §5.5).
        return ServicePrincipal(
            name=subject.removeprefix(SERVICE_SUBJECT_PREFIX),
            scopes=scopes,
            token_id=claims["jti"],
            expires_at=_expires_at(claims),
            claims=claims,
        )


require_user = RequireUser()
require_user_sensitive = RequireUser(sensitive=True)


def require_service(scope: str) -> RequireService:
    return RequireService(scope)
