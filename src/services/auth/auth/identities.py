"""Users, workspaces and membership — the authorization source of truth (spec §1).

Nothing here knows about HTTP or tokens. It answers two questions: who is this
person, and which workspaces do they belong to in what role. The `roles` claim
on every access token on the platform comes from `membership()`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, func, select, text, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from auth.models import ExternalIdentity, User, Workspace, WorkspaceMember
from shared import Page, PageRequest, build_page, uuid7

OWNER = "owner"
ADMIN = "admin"
MEMBER = "member"
GUEST = "guest"

ROLES = (OWNER, ADMIN, MEMBER, GUEST)
# Who may change membership. Kept here rather than in the router because it is a
# fact about the authorization model, not about HTTP.
MANAGING_ROLES = (OWNER, ADMIN)


class UnverifiedEmailError(Exception):
    """An unrecognised identity claimed an email that already has an account.

    Refused rather than linked. Some providers let a user set any address on
    their profile without proving it, so honouring the claim would let anyone
    who can register at such a provider take over an existing CollabHub account
    by naming its email.
    """


class LastOwnerError(Exception):
    """The change would leave a workspace with nobody able to administer it."""


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
    session: AsyncSession, *, email: str, display_name: str, demo_workspace_name: str | None
) -> User:
    """Return the account for `email`, creating it and its workspaces if new.

    A brand-new user gets their own workspace, which they own. Locally they also
    join the shared demo workspace as a member, so there are always two and the
    workspace switcher is exercisable from the first sign-in; pass
    `demo_workspace_name=None` to skip that, which is what every environment
    other than a laptop does.
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

    if demo_workspace_name:
        demo = await ensure_demo_workspace(session, demo_workspace_name)
        session.add(WorkspaceMember(workspace_id=demo.id, user_id=user.id, role=MEMBER))

    return user


async def find_identity(
    session: AsyncSession, *, provider: str, subject: str
) -> ExternalIdentity | None:
    result = await session.execute(
        select(ExternalIdentity).where(
            ExternalIdentity.provider == provider, ExternalIdentity.subject == subject
        )
    )
    return result.scalar_one_or_none()


async def link_identity(
    session: AsyncSession,
    *,
    provider: str,
    subject: str,
    email: str,
    email_verified: bool,
    display_name: str,
    demo_workspace_name: str | None,
) -> User | None:
    """Resolve a verified upstream identity to a CollabHub account.

    Three cases, in the order they are tried:

    1. **Known identity.** `(provider, subject)` has a row, so this is a return
       visit. The subject is the provider's stable identifier for the person —
       matching on it rather than on email means a user who changes their email
       upstream keeps their account.
    2. **Known email, new identity.** The person has an account but is arriving
       through a provider they have not used before. Link the two — but only if
       the provider says the email is verified, or this is an account-takeover
       path rather than a convenience.
    3. **Nobody.** Provision the account and its workspaces, then link.

    Returns None when the identity resolves to an account that has since been
    deleted: a valid upstream login with nothing left to sign in to.
    """
    identity = await find_identity(session, provider=provider, subject=subject)
    if identity is not None:
        return await find_user(session, identity.user_id)

    existing = await find_user_by_email(session, email)
    if existing is not None:
        if not email_verified:
            raise UnverifiedEmailError(email)
        session.add(
            ExternalIdentity(id=uuid7(), user_id=existing.id, provider=provider, subject=subject)
        )
        return existing

    user = await provision_user(
        session,
        email=email,
        display_name=display_name,
        demo_workspace_name=demo_workspace_name,
    )
    session.add(ExternalIdentity(id=uuid7(), user_id=user.id, provider=provider, subject=subject))
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


# --- membership management (spec §3) --------------------------------------


@dataclass(frozen=True)
class Member:
    """A person in a workspace, as the members list reports them."""

    user: User
    role: str
    joined_at: datetime


def _members_query(workspace_id: uuid.UUID) -> Select:
    # Ordered by `(joined_at, user_id)` rather than `joined_at` alone: two people
    # added in the same transaction share a timestamp, and a cursor on a
    # non-unique key cannot say which of them it meant.
    return (
        select(User, WorkspaceMember.role, WorkspaceMember.joined_at)
        .join(WorkspaceMember, WorkspaceMember.user_id == User.id)
        .where(WorkspaceMember.workspace_id == workspace_id, User.deleted_at.is_(None))
        .order_by(WorkspaceMember.joined_at, User.id)
    )


async def find_member(
    session: AsyncSession, *, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> Member | None:
    """One member, in the shape the members endpoints report.

    Used to build the response after a write, so what comes back is what was
    actually stored rather than what the handler believes it just did.
    """
    result = await session.execute(_members_query(workspace_id).where(User.id == user_id))
    row = result.first()
    return Member(user=row[0], role=row[1], joined_at=row[2]) if row else None


async def members_page(
    session: AsyncSession, workspace_id: uuid.UUID, page: PageRequest
) -> Page[Member]:
    """One page of a workspace's members, keyset-paginated."""
    query = _members_query(workspace_id)

    if page.cursor:
        joined_at, user_id = page.cursor
        # Seek straight past the last row of the previous page. The row
        # comparison is the keyset predicate: strictly later timestamp, or the
        # same timestamp and a higher id.
        query = query.where(
            tuple_(WorkspaceMember.joined_at, User.id)
            > tuple_(datetime.fromisoformat(joined_at), uuid.UUID(user_id))
        )

    result = await session.execute(query.limit(page.fetch_limit))
    rows = [
        Member(user=user, role=role, joined_at=joined_at) for user, role, joined_at in result.all()
    ]
    return build_page(rows, page, key=lambda m: (m.joined_at.isoformat(), str(m.user.id)))


async def count_owners(session: AsyncSession, workspace_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(WorkspaceMember)
        .where(WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.role == OWNER)
    )
    return int(result.scalar_one())


async def _last_owner(session: AsyncSession, workspace_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """Whether removing or demoting this member would leave no owner behind.

    A workspace with no owner cannot be administered by anyone — nobody left can
    grant the role back — so it is a state to refuse to enter rather than one to
    recover from.
    """
    current = await membership(session, user_id, workspace_id)
    if current is None or current.role != OWNER:
        return False
    return await count_owners(session, workspace_id) <= 1


async def add_member(
    session: AsyncSession, *, workspace_id: uuid.UUID, user_id: uuid.UUID, role: str
) -> Membership:
    """Add an existing user to a workspace. Raises if they are already in it."""
    if await membership(session, user_id, workspace_id) is not None:
        raise ValueError("already a member")

    session.add(WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=role))
    await session.flush()

    added = await membership(session, user_id, workspace_id)
    if added is None:  # pragma: no cover — just written in this transaction
        raise RuntimeError("the membership just added could not be read back")
    return added


async def set_role(
    session: AsyncSession, *, workspace_id: uuid.UUID, user_id: uuid.UUID, role: str
) -> Membership | None:
    """Change a member's role, refusing to remove the workspace's last owner."""
    current = await membership(session, user_id, workspace_id)
    if current is None:
        return None
    if role != OWNER and await _last_owner(session, workspace_id, user_id):
        raise LastOwnerError(str(workspace_id))

    await session.execute(
        WorkspaceMember.__table__.update()
        .where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
        .values(role=role)
    )
    return await membership(session, user_id, workspace_id)


async def remove_member(
    session: AsyncSession, *, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    """Remove a member. Refuses to remove the workspace's last owner."""
    if await membership(session, user_id, workspace_id) is None:
        return False
    if await _last_owner(session, workspace_id, user_id):
        raise LastOwnerError(str(workspace_id))

    await session.execute(
        WorkspaceMember.__table__.delete().where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
    )
    return True


async def shares_workspace(
    session: AsyncSession, *, viewer_id: uuid.UUID, subject_id: uuid.UUID
) -> bool:
    """Whether two users have any workspace in common.

    What gates `GET /users/{id}`. Every access token names one workspace, so
    answering with any user in the installation would turn a workspace-scoped
    token into a directory of everyone.
    """
    theirs = select(WorkspaceMember.workspace_id).where(WorkspaceMember.user_id == subject_id)
    result = await session.execute(
        select(func.count())
        .select_from(WorkspaceMember)
        .where(WorkspaceMember.user_id == viewer_id, WorkspaceMember.workspace_id.in_(theirs))
    )
    return int(result.scalar_one()) > 0
