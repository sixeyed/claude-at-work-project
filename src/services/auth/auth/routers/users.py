"""User profile endpoints (spec §3).

MVP scope is the caller's own profile. `PATCH /users/me` and the public
`GET /users/{id}` are deferred until something needs them — the SPA's avatar and
mention rendering.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from auth import identities
from auth.db import session as db_session
from auth.schemas import UserResponse
from shared import ProblemException, UserPrincipal, require_user

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def me(
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
) -> UserResponse:
    user = await identities.find_user(session, principal.user_id)
    if user is None:
        # A valid token for an account that has since been deleted.
        raise ProblemException.not_found("This account no longer exists.")

    return UserResponse.model_validate(user, from_attributes=True)
