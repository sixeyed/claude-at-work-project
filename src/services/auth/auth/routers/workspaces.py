"""Workspace membership endpoints (spec §3).

Two rules run through every route here.

**The workspace comes from the token.** Conventions §5.4 says authorization
never takes a workspace identifier from the request in place of the `wsp` claim.
These routes have a workspace in the path, so the rule is applied in its
strictest form: the path id must *equal* the claim, or it is a 403. A caller who
wants to administer a different workspace switches token first
(`POST /auth/switch-workspace`). Looking up membership for whatever id the path
happened to carry is exactly the tenancy leak the convention exists to prevent.

**Writes fail closed.** Membership changes are in the sensitive set from
Conventions §5.2, so they take `require_user_sensitive` and return 503 rather
than proceed on a token whose revocation status cannot be checked. The reads do
not: they are what the switcher and the member list render, and refusing them
whenever R1 blinks would buy very little for an outage.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth import identities, sessions
from auth.db import session as db_session
from auth.schemas import (
    AddMemberRequest,
    MemberListResponse,
    MemberResponse,
    PublicUserResponse,
    UpdateMemberRequest,
    WorkspaceListResponse,
    WorkspaceResponse,
)
from shared import (
    PageParams,
    ProblemException,
    UserPrincipal,
    require_user,
    require_user_sensitive,
)

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])


def _same_workspace(principal: UserPrincipal, workspace_id: uuid.UUID) -> None:
    """Refuse any workspace but the one this token is scoped to."""
    if workspace_id != principal.workspace_id:
        raise ProblemException.forbidden(
            "This token is not scoped to that workspace. Switch workspace first."
        )


def _must_manage(principal: UserPrincipal) -> None:
    if not principal.has_role(*identities.MANAGING_ROLES):
        raise ProblemException.forbidden("Only an owner or admin can change membership.")


def _valid_role(role: str) -> str:
    if role not in identities.ROLES:
        raise ProblemException.validation_error(
            f"Unknown role {role!r}.",
            errors={"role": [f"Must be one of: {', '.join(identities.ROLES)}"]},
        )
    return role


def _as_member(member: identities.Member) -> MemberResponse:
    return MemberResponse(
        user=PublicUserResponse.model_validate(member.user, from_attributes=True),
        role=member.role,
        joined_at=member.joined_at,
    )


async def _member_response(
    session: AsyncSession, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> MemberResponse:
    """Read the member back after a write, so the response reflects the row."""
    member = await identities.find_member(session, workspace_id=workspace_id, user_id=user_id)
    if member is None:  # pragma: no cover — written in this transaction
        raise RuntimeError("the membership just written could not be read back")
    return _as_member(member)


@router.get("", response_model=WorkspaceListResponse)
async def list_workspaces(
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
) -> WorkspaceListResponse:
    """Every workspace the caller belongs to — what the switcher offers.

    Derived from the token's `sub`, not from anything in the request, so it can
    never enumerate someone else's workspaces.
    """
    found = await identities.memberships(session, principal.user_id)

    return WorkspaceListResponse(
        items=[
            WorkspaceResponse(id=m.workspace.id, name=m.workspace.name, role=m.role) for m in found
        ]
    )


@router.get("/{workspace_id}/members", response_model=MemberListResponse)
async def list_members(
    workspace_id: uuid.UUID,
    page: PageParams,
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
) -> MemberListResponse:
    """The workspace's members, cursor-paginated (Conventions §4.1)."""
    _same_workspace(principal, workspace_id)

    found = await identities.members_page(session, workspace_id, page)
    return MemberListResponse(
        items=[_as_member(m) for m in found.items], next_cursor=found.next_cursor
    )


@router.post(
    "/{workspace_id}/members",
    response_model=MemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_member(
    workspace_id: uuid.UUID,
    body: AddMemberRequest,
    principal: UserPrincipal = Depends(require_user_sensitive),
    session: AsyncSession = Depends(db_session),
) -> MemberResponse:
    """Add an existing user to this workspace, by id or by email."""
    _same_workspace(principal, workspace_id)
    _must_manage(principal)
    role = _valid_role(body.role)

    if body.user_id is not None:
        user = await identities.find_user(session, body.user_id)
    else:
        user = await identities.find_user_by_email(session, str(body.email))

    if user is None:
        # No invitation is created for an unknown address — see AddMemberRequest.
        raise ProblemException.not_found("No such user.")

    try:
        await identities.add_member(session, workspace_id=workspace_id, user_id=user.id, role=role)
    except ValueError as exc:
        raise ProblemException.conflict("That user is already a member.") from exc

    response = await _member_response(session, workspace_id, user.id)
    await session.commit()
    return response


@router.patch("/{workspace_id}/members/{user_id}", response_model=MemberResponse)
async def update_member(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    body: UpdateMemberRequest,
    principal: UserPrincipal = Depends(require_user_sensitive),
    session: AsyncSession = Depends(db_session),
) -> MemberResponse:
    """Change a member's role."""
    _same_workspace(principal, workspace_id)
    _must_manage(principal)
    role = _valid_role(body.role)

    try:
        updated = await identities.set_role(
            session, workspace_id=workspace_id, user_id=user_id, role=role
        )
    except identities.LastOwnerError as exc:
        raise ProblemException.conflict(
            "This is the workspace's last owner; promote another owner first."
        ) from exc

    if updated is None:
        raise ProblemException.not_found("That user is not a member of this workspace.")

    response = await _member_response(session, workspace_id, user_id)
    await session.commit()
    return response


@router.delete("/{workspace_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    principal: UserPrincipal = Depends(require_user_sensitive),
    session: AsyncSession = Depends(db_session),
) -> Response:
    """Remove a member, and end the sessions this workspace granted them.

    Revoking their refresh tokens for this workspace is the part that matters:
    without it, removal only stops them obtaining a *new* session, while the
    refresh token they already hold goes on minting access tokens for a
    workspace they are no longer in, for up to thirty days.
    """
    _same_workspace(principal, workspace_id)
    _must_manage(principal)

    try:
        removed = await identities.remove_member(
            session, workspace_id=workspace_id, user_id=user_id
        )
    except identities.LastOwnerError as exc:
        raise ProblemException.conflict(
            "This is the workspace's last owner; promote another owner first."
        ) from exc

    if not removed:
        raise ProblemException.not_found("That user is not a member of this workspace.")

    await sessions.revoke_workspace_sessions(session, user_id=user_id, workspace_id=workspace_id)
    await session.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)
