"""Token endpoints — issue, refresh, switch, revoke (spec §3, §3.1).

Everything that creates or destroys a session lives here. The rules that keep
coming up:

* the workspace on a new token comes from a membership lookup, never from what
  the caller asked for (Conventions §5.4);
* refresh rotates, and a replayed token takes its whole family down with it;
* service tokens are a different audience entirely, so nothing issued here can
  be used as the other kind.
"""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth import identities, sessions
from auth.db import session as db_session
from auth.models import RefreshToken
from auth.schemas import (
    LogoutRequest,
    RefreshRequest,
    ServiceTokenRequest,
    ServiceTokenResponse,
    SwitchWorkspaceRequest,
    TokenResponse,
    UserInfoResponse,
)
from auth.settings import Settings
from shared import ProblemException, UserPrincipal, require_user

CLIENT_CREDENTIALS = "client_credentials"

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _issuer(request: Request):
    return request.app.state.token_issuer


def _invalid_grant() -> ProblemException:
    """One message for every credential failure.

    Which of "no such token", "already used" and "expired" applies is useful to
    whoever is holding a token they should not have, and to nobody else.
    """
    return ProblemException.unauthorized("The credentials presented are not valid.")


def _as_response(pair: sessions.TokenPair) -> TokenResponse:
    return TokenResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        expires_in=pair.expires_in,
    )


async def _spend(session: AsyncSession, token: str) -> RefreshToken:
    """Consume a refresh token, committing the fallout if it has been replayed.

    Reuse detection revokes the token's whole family, and that revocation has to
    survive the 401 that follows it. Letting the exception unwind an open
    transaction would roll the revocation back — leaving a session live that we
    have already concluded is compromised.
    """
    try:
        return await sessions.spend(session, token)
    except sessions.InvalidRefreshTokenError:
        await session.commit()
        raise _invalid_grant() from None


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest, request: Request, session: AsyncSession = Depends(db_session)
) -> TokenResponse:
    """Exchange a refresh token for a new pair, keeping the same workspace."""
    settings = _settings(request)

    presented = await _spend(session, body.refresh_token)

    user = await identities.find_user(session, presented.user_id)
    if user is None:
        raise _invalid_grant()

    membership = await identities.membership(session, user.id, presented.workspace_id)
    if membership is None:
        # The session's workspace is gone, or the user was removed from it;
        # fall back rather than strand them with no way back in.
        membership = identities.default_membership(await identities.memberships(session, user.id))
        if membership is None:
            raise ProblemException.forbidden("This account belongs to no workspace.")

    pair = await sessions.rotate(
        session,
        presented=presented,
        issuer=_issuer(request),
        user=user,
        membership=membership,
        refresh_token_days=settings.auth_refresh_token_days,
    )
    await session.commit()

    return _as_response(pair)


@router.post("/switch-workspace", response_model=TokenResponse)
async def switch_workspace(
    body: SwitchWorkspaceRequest, request: Request, session: AsyncSession = Depends(db_session)
) -> TokenResponse:
    """Re-scope a session to another workspace (Conventions §5.4).

    Same rotation as `/refresh`; the only difference is the `wsp` and `roles`
    claims on the new token — and that the target workspace is checked against
    the *refresh token's* user, so holding someone else's workspace id gets you
    nothing.
    """
    settings = _settings(request)

    presented = await _spend(session, body.refresh_token)

    user = await identities.find_user(session, presented.user_id)
    if user is None:
        raise _invalid_grant()

    membership = await identities.membership(session, user.id, body.workspace_id)
    if membership is None:
        raise ProblemException.forbidden("You are not a member of that workspace.")

    pair = await sessions.rotate(
        session,
        presented=presented,
        issuer=_issuer(request),
        user=user,
        membership=membership,
        refresh_token_days=settings.auth_refresh_token_days,
    )
    await session.commit()

    return _as_response(pair)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    body: LogoutRequest,
    request: Request,
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
) -> Response:
    """Revoke this access token now, and the refresh token if one is supplied.

    The access token stays cryptographically valid until it expires — that is
    what stateless verification means — so revocation is the denylist entry
    every service checks (Conventions §5.2).
    """
    await sessions.revoke_access_token(
        request.app.state.denylist,
        token_id=principal.token_id,
        expires_at=principal.expires_at,
    )

    if body.refresh_token:
        await sessions.revoke_refresh_token(session, body.refresh_token)
        await session.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/userinfo", response_model=UserInfoResponse)
async def userinfo(principal: UserPrincipal = Depends(require_user)) -> UserInfoResponse:
    """The claims on the caller's own token — no database read needed."""
    return UserInfoResponse(
        sub=str(principal.user_id),
        name=principal.display_name,
        email=principal.email,
        wsp=str(principal.workspace_id),
        roles=list(principal.roles),
    )


@router.post("/service-token", response_model=ServiceTokenResponse)
async def service_token(body: ServiceTokenRequest, request: Request) -> ServiceTokenResponse:
    """Client-credentials grant for internal calls (Conventions §5.5).

    Not exposed through the public ingress. The token it returns carries
    `aud: collabhub-internal`, which is the whole boundary between background
    work and a user's session.
    """
    if body.grant_type != CLIENT_CREDENTIALS:
        raise ProblemException.validation_error(
            f"Unsupported grant_type; expected {CLIENT_CREDENTIALS!r}.",
            errors={"grant_type": ["Unsupported grant type"]},
        )

    client = _settings(request).service_client(body.client_id)
    # Compare even when the client is unknown, so a wrong id and a wrong secret
    # take the same time to refuse.
    expected = client.secret if client else ""
    presented_ok = secrets.compare_digest(expected, body.client_secret)
    if client is None or not expected or not presented_ok:
        raise _invalid_grant()

    token = _issuer(request).service_token(client_id=client.client_id, scopes=client.scopes)
    return ServiceTokenResponse(access_token=token.value, expires_in=token.expires_in)
