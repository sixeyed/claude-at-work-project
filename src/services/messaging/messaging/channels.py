"""Channel domain logic (spec §3.1, §4).

Plain async functions taking an `AsyncSession` first and raising domain
exceptions the router translates — no FastAPI imports, so the same rules serve
the REST routes today and the Socket.IO handlers in a later slice.

Two rules here are the ones a bug would turn into a tenancy leak, so they are
stated once and applied everywhere:

* **The workspace comes from the token.** Every function takes `workspace_id`
  from the caller's `wsp` claim (Conventions §5.4) and filters on it. Nothing in
  this module reads a workspace from anywhere else.
* **Invisible is indistinguishable from absent.** A channel in another
  workspace, or a private channel you are not in, is a 404 and never a 403 —
  telling someone "that exists but is not yours" is itself a disclosure.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import Select, func, or_, select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from messaging.models import ADMIN, CREATABLE_KINDS, PUBLIC, Channel, ChannelMember
from shared import Page, PageRequest, build_page, uuid7

MIN_NAME_LENGTH = 3
MAX_NAME_LENGTH = 80

# Letters, numbers and hyphens, starting with a letter. ASCII only, which is a
# real narrowing — `#café` is not a channel name — and is why the rule is
# written into doc 02 §3.1 rather than left implicit in a regex here.
_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9-]*$")
_LEADING_ALPHA = re.compile(r"^[A-Za-z]")


class NameRequiredError(Exception):
    """The name was empty, or nothing but whitespace."""


class NameTooShortError(Exception):
    """Shorter than a name anyone would recognise in a sidebar."""


class NameTooLongError(Exception):
    """Longer than the column and the UI are willing to carry."""


class NameMustStartWithLetterError(Exception):
    """Leading digit or hyphen — sorts badly and reads like an id."""


class NameCharactersError(Exception):
    """Something outside letters, numbers and hyphens."""


class UnknownKindError(Exception):
    """A kind this API does not create."""


class DuplicateNameError(Exception):
    """A public channel in this workspace already owns the name."""


@dataclass(frozen=True)
class VisibleChannel:
    """A channel plus the caller's relationship to it.

    The role is part of the read rather than a second query, because the sidebar
    needs it for every row and the UI decides what to offer from it.
    """

    channel: Channel
    my_role: str | None


def validate_name(raw: str) -> str:
    """Return the trimmed name, or raise the specific rule it breaks.

    One exception per rule so the router can put a useful message against the
    `name` field. A single "invalid name" would make the form say nothing.
    """
    name = raw.strip()

    if not name:
        raise NameRequiredError
    if len(name) < MIN_NAME_LENGTH:
        raise NameTooShortError
    if len(name) > MAX_NAME_LENGTH:
        raise NameTooLongError
    if not _LEADING_ALPHA.match(name):
        raise NameMustStartWithLetterError
    if not _NAME_PATTERN.match(name):
        raise NameCharactersError

    return name


def validate_kind(kind: str) -> str:
    if kind not in CREATABLE_KINDS:
        raise UnknownKindError(kind)
    return kind


async def create(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    created_by: uuid.UUID,
    name: str,
    topic: str | None = None,
    kind: str = PUBLIC,
) -> VisibleChannel:
    """Create a channel and make its creator an admin of it.

    The membership row is not a convenience: `PATCH`/`DELETE` require a channel
    admin (spec §3.1), so a channel created without one could never be
    administered, and a private channel created without one would be invisible
    to the person who just made it.

    Uniqueness is left to the partial unique index rather than checked first.
    A `SELECT` then `INSERT` is two statements with a gap between them, and two
    people naming a channel at the same moment is exactly the case that matters.
    """
    name = validate_name(name)
    kind = validate_kind(kind)

    channel = Channel(
        id=uuid7(),
        workspace_id=workspace_id,
        name=name,
        topic=topic,
        kind=kind,
        created_by=created_by,
    )
    session.add(channel)
    session.add(ChannelMember(channel_id=channel.id, user_id=created_by, role=ADMIN))

    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise DuplicateNameError(name) from exc

    return VisibleChannel(channel=channel, my_role=ADMIN)


def _visible_query(workspace_id: uuid.UUID, user_id: uuid.UUID) -> Select:
    """Channels in this workspace the caller is allowed to know about.

    Public channels are visible to the whole workspace whether or not the caller
    has joined; anything else needs a membership row. The outer join carries the
    caller's role in the same pass, so a list of fifty channels is one query.

    Ordered by `(name, id)` rather than `name` alone: private channels may
    repeat a name, and a cursor on a non-unique key cannot say which row it
    meant.
    """
    return (
        select(Channel, ChannelMember.role)
        .outerjoin(
            ChannelMember,
            (ChannelMember.channel_id == Channel.id) & (ChannelMember.user_id == user_id),
        )
        .where(
            Channel.workspace_id == workspace_id,
            Channel.archived_at.is_(None),
            or_(Channel.kind == PUBLIC, ChannelMember.user_id.is_not(None)),
        )
        .order_by(Channel.name, Channel.id)
    )


async def list_page(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    page: PageRequest,
) -> Page[VisibleChannel]:
    """One page of the caller's visible channels, keyset-paginated."""
    query = _visible_query(workspace_id, user_id)

    if page.cursor:
        name, channel_id = page.cursor
        # Seek straight past the last row of the previous page: a later name, or
        # the same name and a higher id.
        query = query.where(tuple_(Channel.name, Channel.id) > tuple_(name, uuid.UUID(channel_id)))

    result = await session.execute(query.limit(page.fetch_limit))
    rows = [VisibleChannel(channel=channel, my_role=role) for channel, role in result.all()]
    return build_page(rows, page, key=lambda v: (v.channel.name, str(v.channel.id)))


async def get_visible(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    channel_id: uuid.UUID,
) -> VisibleChannel | None:
    """One channel, if this caller is allowed to know it exists.

    `None` covers every negative case — wrong workspace, archived, private and
    not a member, or simply absent — because the router turns them all into the
    same 404 on purpose.
    """
    query = _visible_query(workspace_id, user_id).where(Channel.id == channel_id)
    row = (await session.execute(query)).first()
    return VisibleChannel(channel=row[0], my_role=row[1]) if row else None


async def is_member(session: AsyncSession, *, channel_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    return await _role(session, channel_id=channel_id, user_id=user_id) is not None


async def is_admin(session: AsyncSession, *, channel_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    return await _role(session, channel_id=channel_id, user_id=user_id) == ADMIN


async def _role(session: AsyncSession, *, channel_id: uuid.UUID, user_id: uuid.UUID) -> str | None:
    result = await session.execute(
        select(ChannelMember.role).where(
            ChannelMember.channel_id == channel_id, ChannelMember.user_id == user_id
        )
    )
    return result.scalar_one_or_none()


async def count_in_workspace(session: AsyncSession, workspace_id: uuid.UUID) -> int:
    """Used by the tests to assert nothing was written on a rejected create."""
    result = await session.execute(
        select(func.count()).select_from(Channel).where(Channel.workspace_id == workspace_id)
    )
    return result.scalar_one()
