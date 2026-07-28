"""Federated sign-in: send the user to a provider, take back an identity (§5.1).

The three endpoints here are one flow, which is why they share a module: the
state written by `/login` is the state read by `/callback`, and the code written
by `/callback` is the code spent by `/token`. Splitting them across files would
hide that they are three halves of the same handshake.

Two of them are *browser* endpoints — they answer with redirects, not JSON,
including when they fail. A user who denies consent at the provider must land
back in the SPA with something it can explain, not on a Problem Details document
in a bare browser tab. `/token` is a normal API endpoint and uses the normal
error envelope.

The single rule that shapes the rest: nothing the browser carries is trusted.
`state` is a key into R1, not data; the authorization code proves nothing on its
own; the workspace comes from a membership lookup. What the browser hands back
is only ever a lookup key for something this service wrote down earlier.
"""

from __future__ import annotations

import logging
import uuid
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from auth import cookies, identities, oidc, pkce, sessions
from auth.db import session as db_session
from auth.loginflow import LoginFlowStore, LoginStoreUnavailableError
from auth.schemas import TokenExchangeRequest, TokenResponse
from auth.settings import Settings
from shared import ProblemException

AUTHORIZATION_CODE = "authorization_code"

_log = logging.getLogger("collabhub.auth.federation")

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _store(request: Request) -> LoginFlowStore:
    return request.app.state.login_flow


def _client(request: Request, provider: str) -> oidc.OidcClient:
    client = request.app.state.oidc_clients.get(provider)
    if client is None:
        raise ProblemException.not_found(f"No identity provider named {provider!r}.")
    return client


def _callback_uri(request: Request, provider: str) -> str:
    """The redirect URI registered with the provider.

    Built from the configured issuer rather than from the incoming request's
    host: it has to match what the provider has registered *exactly*, and a
    request header is something a caller controls.
    """
    return f"{_settings(request).auth_issuer.rstrip('/')}/api/v1/auth/callback/{provider}"


def _to_spa(request: Request, **params: str) -> RedirectResponse:
    """Hand the browser back to the SPA, with either a code or an error."""
    target = _settings(request).spa_redirect_uri
    if not target:
        # Nothing to redirect to means the deployment is misconfigured, and
        # bouncing the user somewhere arbitrary would be worse than saying so.
        raise ProblemException(500, detail="No SPA redirect URI is configured.")
    return RedirectResponse(f"{target}?{urlencode(params)}", status_code=302)


@router.get("/login/{provider}")
async def login(
    provider: str,
    request: Request,
    code_challenge: str = Query(alias="codeChallenge", min_length=43, max_length=128),
    code_challenge_method: str = Query(default=pkce.METHOD_S256, alias="codeChallengeMethod"),
) -> RedirectResponse:
    """Begin a login: remember what it is, then send the browser onward.

    PKCE is required. RFC 7636 also permits `plain`, where the challenge is the
    verifier in clear — which proves nothing, and exists for clients that cannot
    compute a SHA-256. A browser can, so accepting `plain` would only add a way
    to turn the protection off from the query string.
    """
    if code_challenge_method != pkce.METHOD_S256:
        raise ProblemException.validation_error(
            f"Only {pkce.METHOD_S256} is supported.",
            errors={"codeChallengeMethod": ["Unsupported code challenge method"]},
        )

    client = _client(request, provider)

    try:
        state, pending = await _store(request).begin_login(
            provider=provider, code_challenge=code_challenge
        )
        target = await client.authorization_url(
            redirect_uri=_callback_uri(request, provider),
            state=state,
            nonce=pending.nonce,
            code_challenge=pkce.challenge_for(pending.verifier),
        )
    except LoginStoreUnavailableError as exc:
        # Starting a login we could not record is starting one the callback can
        # never finish, so refuse now rather than strand the user at the IdP.
        _log.warning("login store unavailable", extra={"error": str(exc)})
        raise ProblemException.service_unavailable("Sign-in is temporarily unavailable.") from exc
    except oidc.ProviderError as exc:
        _log.error("provider unusable", extra={"provider": provider, "error": str(exc)})
        raise ProblemException.service_unavailable(
            "The identity provider is temporarily unavailable."
        ) from exc

    return RedirectResponse(target, status_code=302)


@router.get("/callback/{provider}")
async def callback(
    request: Request,
    provider: str,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    session: AsyncSession = Depends(db_session),
) -> RedirectResponse:
    """Finish a login and hand the SPA a code it can exchange.

    Everything that can go wrong here redirects rather than raises: the caller
    is a browser mid-navigation, not the SPA's fetch layer.
    """
    settings = _settings(request)

    if error:
        # The provider refused — a denied consent, usually. Pass it on so the
        # SPA can say something better than "sign-in failed".
        return _to_spa(request, error=error)
    if not code or not state:
        return _to_spa(request, error="invalid_request")

    client = _client(request, provider)

    try:
        pending = await _store(request).claim_login(state)
    except LoginStoreUnavailableError as exc:
        _log.warning("login store unavailable", extra={"error": str(exc)})
        return _to_spa(request, error="temporarily_unavailable")

    # An unknown state is an expired login, a replayed callback, or a CSRF
    # attempt. They are indistinguishable from here and all end the same way.
    if pending is None or pending.provider != provider:
        return _to_spa(request, error="invalid_state")

    try:
        identity = await client.exchange(
            code=code,
            code_verifier=pending.verifier,
            redirect_uri=_callback_uri(request, provider),
            nonce=pending.nonce,
        )
    except oidc.IdentityRejectedError as exc:
        _log.warning("identity rejected", extra={"provider": provider, "error": str(exc)})
        return _to_spa(request, error="access_denied")
    except oidc.ProviderError as exc:
        _log.error("provider error", extra={"provider": provider, "error": str(exc)})
        return _to_spa(request, error="temporarily_unavailable")

    try:
        user = await identities.link_identity(
            session,
            provider=identity.provider_key,
            subject=identity.subject,
            email=identity.email,
            email_verified=identity.email_verified,
            display_name=identity.display_name,
            demo_workspace_name=(settings.auth_demo_workspace_name if settings.is_local else None),
        )
    except identities.UnverifiedEmailError:
        _log.warning(
            "refused to link an unverified email to an existing account",
            extra={"provider": provider},
        )
        return _to_spa(request, error="email_not_verified")

    if user is None:
        # A valid upstream login for an account that has since been deleted.
        return _to_spa(request, error="account_not_found")

    membership = identities.default_membership(await identities.memberships(session, user.id))
    if membership is None:
        return _to_spa(request, error="no_workspace")

    try:
        authorization_code = await _store(request).issue_code(
            user_id=user.id,
            workspace_id=membership.workspace.id,
            code_challenge=pending.code_challenge,
        )
    except LoginStoreUnavailableError as exc:
        _log.warning("login store unavailable", extra={"error": str(exc)})
        return _to_spa(request, error="temporarily_unavailable")

    # Committed only once there is a code to hand back: a user row written for a
    # login the SPA can never complete is a half-created account.
    await session.commit()

    return _to_spa(request, code=authorization_code)


@router.post("/token", response_model=TokenResponse)
async def token(
    body: TokenExchangeRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(db_session),
) -> TokenResponse:
    """Exchange the authorization code for a session (spec §3.1).

    The access token comes back in the body; the refresh token leaves as an
    `HttpOnly` cookie the SPA cannot read (register D22). This is the only
    endpoint that starts a session, so it is the only one that sets that cookie
    from nothing rather than rotating it.
    """
    settings = _settings(request)

    if body.grant_type != AUTHORIZATION_CODE:
        raise ProblemException.validation_error(
            f"Unsupported grantType; expected {AUTHORIZATION_CODE!r}.",
            errors={"grantType": ["Unsupported grant type"]},
        )

    try:
        issued = await _store(request).claim_code(body.code)
    except LoginStoreUnavailableError as exc:
        # Fail closed, unlike the denylist (Conventions §5.2). Issuing a session
        # for a code we cannot show was ever issued is worse than a failed login.
        _log.warning("login store unavailable", extra={"error": str(exc)})
        raise ProblemException.service_unavailable("Sign-in is temporarily unavailable.") from exc

    # One message for an unknown code, a spent code and a wrong verifier. Which
    # it was is useful only to someone holding a code that is not theirs.
    invalid = ProblemException.unauthorized("The authorization code is not valid.")
    if issued is None or not pkce.verifies(body.code_verifier, issued.code_challenge):
        raise invalid

    user = await identities.find_user(session, uuid.UUID(issued.user_id))
    if user is None:
        raise invalid

    membership = await identities.membership(session, user.id, uuid.UUID(issued.workspace_id))
    if membership is None:
        # Removed from the workspace between signing in and collecting the code.
        membership = identities.default_membership(await identities.memberships(session, user.id))
        if membership is None:
            raise ProblemException.forbidden("This account belongs to no workspace.")

    pair = await sessions.issue(
        session,
        issuer=request.app.state.token_issuer,
        user=user,
        membership=membership,
        refresh_token_days=settings.auth_refresh_token_days,
    )
    await session.commit()

    cookies.issue(
        response,
        pair.refresh_token,
        refresh_token_days=settings.auth_refresh_token_days,
        secure=settings.auth_cookie_secure,
    )
    return TokenResponse(access_token=pair.access_token, expires_in=pair.expires_in)
