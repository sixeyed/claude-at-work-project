"""User profile endpoints (spec §3).

Two audiences, two response models. `/users/me` returns the caller their own
record, email and all. `/users/{id}` returns what the SPA needs to draw someone
else — a name and an avatar — and is a separate type rather than the same model
with fields omitted, so that adding a field to the profile model later cannot
quietly start publishing it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth import identities, names
from auth.db import session as db_session
from auth.models import User
from auth.schemas import PublicUserResponse, UpdateUserRequest, UserResponse
from shared import ProblemException, UserPrincipal, require_user

router = APIRouter(prefix="/api/v1/users", tags=["users"])

_TAKEN = "That name is already taken."
_NAME_INDEX = "uq_users_display_name_key"


def _name_problem(message: str) -> ProblemException:
    return ProblemException.validation_error(message, errors={"displayName": [message]})


def _name_taken() -> ProblemException:
    # Names nobody: no id, email or workspace — the exception to the 404 rule (D46).
    return ProblemException.conflict(_TAKEN, errors={"displayName": [_TAKEN]})


async def _new_name(session: AsyncSession, user: User, raw: str) -> str | None:
    """The name to store, or None when it is the one the user already has."""
    try:
        name = names.clean(raw)
    except names.InvalidNameError as refused:
        raise _name_problem(str(refused)) from refused
    if name == user.display_name:
        return None

    # conventions: ok — a deleted account's name stays taken (D46), so no deleted_at filter.
    taken = select(User.id).where(User.display_name_key == names.name_key(name), User.id != user.id)
    if (await session.execute(taken)).first() is not None:
        raise _name_taken()
    return name


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


@router.patch("/me", response_model=UserResponse)
async def update_me(
    body: UpdateUserRequest,
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
) -> UserResponse:
    """Update the caller's own profile.

    Only ever the caller's own: there is no `PATCH /users/{id}`, and the row
    edited comes from the token's `sub`, so there is no id in the request for
    anyone to substitute.

    A field left out is left alone; `avatarAsset: null` clears the avatar. The
    two are told apart by what the request actually carried rather than by
    treating None as "no change", or an avatar could be set but never removed.

    A display name is trimmed and composed, then checked (`auth.names`). Saving the
    name you already have writes nothing. A name held by anyone else — deleted
    accounts too (D46) — is a 409 that names nobody. The pre-check is the quick
    answer; the unique index is the authority, and a conflict it raises at commit
    is the same 409, which is what settles two renames to one name at once.
    """
    user = await identities.find_user(session, principal.user_id)
    if user is None:
        raise ProblemException.not_found("This account no longer exists.")

    supplied = body.model_fields_set
    changed = False

    if "display_name" in supplied:
        if body.display_name is None:
            raise ProblemException.validation_error(
                "displayName cannot be null.",
                errors={"displayName": ["A display name is required"]},
            )
        new_name = await _new_name(session, user, body.display_name)
        if new_name is not None:
            user.display_name = new_name
            changed = True

    if "avatar_asset" in supplied:
        # No existence check against the Asset service: services do not read
        # each other's data, and a synchronous call here would put Asset on the
        # path of a profile edit. A dangling reference renders as no avatar.
        user.avatar_asset = body.avatar_asset
        changed = True

    if not changed:
        return UserResponse.model_validate(user, from_attributes=True)

    user.updated_at = datetime.now(UTC)
    user.version += 1
    try:
        await session.commit()
    except IntegrityError as conflict:
        await session.rollback()
        if _NAME_INDEX not in str(conflict.orig):
            raise
        raise _name_taken() from conflict

    return UserResponse.model_validate(user, from_attributes=True)


@router.get("/{user_id}", response_model=PublicUserResponse)
async def public_profile(
    user_id: uuid.UUID,
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
) -> PublicUserResponse:
    """Another user's public profile, for avatars and mentions.

    Restricted to people the caller shares a workspace with. Spec §3 says only
    "Bearer", but every access token is scoped to one workspace (Conventions
    §5.4), and answering for any user in the installation would make a
    workspace-scoped token a directory of every tenant.

    Not found and not visible give the same 404. Distinguishing them would
    confirm that an account exists for an address, which is the fact being
    withheld.
    """
    user = await identities.find_user(session, user_id)
    visible = user is not None and (
        user.id == principal.user_id
        or await identities.shares_workspace(
            session, viewer_id=principal.user_id, subject_id=user.id
        )
    )
    if user is None or not visible:
        raise ProblemException.not_found("No such user.")

    return PublicUserResponse.model_validate(user, from_attributes=True)
