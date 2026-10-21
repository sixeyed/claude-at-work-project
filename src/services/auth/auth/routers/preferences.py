"""Per-user preferences (register D28).

Under `/api/v1/users/me`, so the caller's own row is the only one reachable: the
user comes from the token's `sub`, with no id in the path to substitute. Both
routes fail open when R1 is down — they are not in Conventions §5.2's set.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from auth import identities, preferences
from auth.db import session as db_session
from auth.schemas import PreferencesResponse, UpdatePreferencesRequest
from shared import ProblemException, UserPrincipal, require_user

router = APIRouter(prefix="/api/v1/users", tags=["users"])

_GONE = "This account no longer exists."
_CLOCKS = ("12h", "24h")


def _known(prefs: dict[str, Any]) -> PreferencesResponse:
    """The keys the API offers, from a row that may hold more."""
    clock = prefs.get("clock")
    return PreferencesResponse(clock=clock if clock in _CLOCKS else None)


@router.get("/me/preferences", response_model=PreferencesResponse, response_model_exclude_none=True)
async def my_preferences(
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
) -> PreferencesResponse:
    if await identities.find_user(session, principal.user_id) is None:
        raise ProblemException.not_found(_GONE)

    return _known(await preferences.read(session, principal.user_id))


@router.patch(
    "/me/preferences", response_model=PreferencesResponse, response_model_exclude_none=True
)
async def update_my_preferences(
    body: UpdatePreferencesRequest,
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
) -> PreferencesResponse:
    """Merge the keys the request carries; a `null` removes its key."""
    if await identities.find_user(session, principal.user_id) is None:
        raise ProblemException.not_found(_GONE)

    set_: dict[str, Any] = {}
    removed: list[str] = []
    for name in body.model_fields_set:
        value = getattr(body, name)
        if value is None:
            removed.append(name)
        else:
            set_[name] = value

    if not set_ and not removed:
        # Nothing carried, nothing written — not even an empty row.
        return _known(await preferences.read(session, principal.user_id))

    merged = await preferences.merge(session, principal.user_id, set_, removed)
    await session.commit()
    return _known(merged)
