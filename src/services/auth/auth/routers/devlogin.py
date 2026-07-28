"""The local-only sign-in shortcut.

Its own module so that `main.create_app` can decide not to include it at all.
Nothing disables this route at runtime: outside `APP_ENV=local` it is never
registered, so there is no flag to flip back on by accident.

It stands in for the OIDC authorization-code flow in spec §5.1 until register
D5 — whether Auth federates to an upstream IdP or acts as a provider itself —
is settled. When that lands, this module is deleted and the callback writes the
same `users` and `external_identities` rows.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from auth import identities, sessions
from auth.db import session as db_session
from auth.schemas import DevLoginRequest, TokenResponse
from shared import ProblemException

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/dev-login", response_model=TokenResponse)
async def dev_login(
    body: DevLoginRequest, request: Request, session: AsyncSession = Depends(db_session)
) -> TokenResponse:
    """Sign in as any email address, with no credential whatsoever.

    A first sign-in creates the account, a workspace it owns, and membership of
    the shared demo workspace — so there is always something to switch to.
    """
    settings = request.app.state.settings
    display_name = body.display_name or body.email.split("@")[0]

    user = await identities.provision_user(
        session,
        email=body.email,
        display_name=display_name,
        demo_workspace_name=settings.auth_demo_workspace_name,
    )
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

    return TokenResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        expires_in=pair.expires_in,
    )
