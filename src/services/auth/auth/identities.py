"""Users, workspaces and membership — the authorization source of truth (spec §1).

Nothing here knows about HTTP or tokens. It answers two questions: who is this
person, and which workspaces do they belong to in what role. The `roles` claim
on every access token on the platform comes from `membership()`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from auth.models import User, Workspace, WorkspaceMember
from shared import uuid7

OWNER = "owner"
MEMBER = "member"

# A fixed lock id for the demo-workspace check, so two processes signing in a
# first user at the same moment cannot both create it.
_DEMO_WORKSPACE_LOCK = 0x0C011AB1


@dataclass(frozen=True)
class Membership:
    workspace: Workspace
    role: str


async def find_user(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await session.execute(
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    )
    return result.scalar_one_or_none()


async def find_user_by_email(session: AsyncSession, email: str) -> User | None:
    # `email` is citext, so this comparison is already case-insensitive.
    result = await session.execute(
        select(User).where(User.email == email, User.deleted_at.is_(None))
    )
    return result.scalar_one_or_none()


async def ensure_demo_workspace(session: AsyncSession, name: str) -> Workspace:
    """Find, or create once, the shared workspace every local user joins."""
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _DEMO_WORKSPACE_LOCK})

    result = await session.execute(select(Workspace).where(Workspace.name == name))
    existing = result.scalars().first()
    if existing is not None:
        return existing

    workspace = Workspace(id=uuid7(), name=name)
    session.add(workspace)
    await session.flush()
    return workspace


async def provision_user(
    session: AsyncSession, *, email: str, display_name: str, demo_workspace_name: str
) -> User:
    """Return the account for `email`, creating it and its workspaces if new.

    A brand-new user gets their own workspace, which they own, and joins the
    shared demo workspace as a member — so there are always two, and switching
    between them is exercisable from the first sign-in.
    """
    user = await find_user_by_email(session, email)
    if user is not None:
        return user

    user = User(id=uuid7(), email=email, display_name=display_name)
    session.add(user)
    await session.flush()

    own = Workspace(id=uuid7(), name=f"{display_name}'s Workspace")
    session.add(own)
    await session.flush()
    session.add(WorkspaceMember(workspace_id=own.id, user_id=user.id, role=OWNER))

    demo = await ensure_demo_workspace(session, demo_workspace_name)
    session.add(WorkspaceMember(workspace_id=demo.id, user_id=user.id, role=MEMBER))

    return user


def default_membership(found: list[Membership]) -> Membership | None:
    """Which workspace a session starts in when the caller names none.

    A workspace the user owns wins over one they were merely added to: signing
    in should land you in your own space, not in whichever shared workspace
    happens to be the oldest row you belong to. Ties break on join order.
    """
    return next((m for m in found if m.role == OWNER), None) or next(iter(found), None)


async def memberships(session: AsyncSession, user_id: uuid.UUID) -> list[Membership]:
    """Every workspace the user belongs to, oldest first."""
    result = await session.execute(
        select(Workspace, WorkspaceMember.role)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(WorkspaceMember.user_id == user_id)
        .order_by(WorkspaceMember.joined_at, Workspace.id)
    )
    return [Membership(workspace=workspace, role=role) for workspace, role in result.all()]


async def membership(
    session: AsyncSession, user_id: uuid.UUID, workspace_id: uuid.UUID
) -> Membership | None:
    """The user's role in one workspace, or None if they are not a member.

    Returning None is what makes a workspace switch fail: the target comes from
    the request, so it is only ever trusted after this lookup (Conventions §5.4).
    """
    result = await session.execute(
        select(Workspace, WorkspaceMember.role)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(WorkspaceMember.user_id == user_id, WorkspaceMember.workspace_id == workspace_id)
    )
    row = result.first()
    return Membership(workspace=row[0], role=row[1]) if row else None
