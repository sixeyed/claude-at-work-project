"""Workspace membership endpoints (spec §3).

MVP scope is the read the workspace switcher needs. The three member-management
writes are deferred; when they land they take `require_user_sensitive`, because
membership changes are in the fail-closed set (Conventions §5.2).

The list is derived from the caller's `sub`, not from anything in the request —
this endpoint is how the SPA discovers what it may switch to, so it must never
enumerate someone else's workspaces.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from auth import identities
from auth.db import session as db_session
from auth.schemas import WorkspaceListResponse, WorkspaceResponse
from shared import UserPrincipal, require_user

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])


@router.get("", response_model=WorkspaceListResponse)
async def list_workspaces(
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
) -> WorkspaceListResponse:
    found = await identities.memberships(session, principal.user_id)

    return WorkspaceListResponse(
        items=[
            WorkspaceResponse(id=m.workspace.id, name=m.workspace.name, role=m.role) for m in found
        ]
    )
