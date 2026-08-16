"""Channel endpoints (spec §3.1).

Three rules run through every route here.

**The workspace comes from the token.** `principal.workspace_id` is the only
source of a workspace on this surface — there is no workspace in a path, query
or body to be tempted by (Conventions §5.4). Substituting one would be a tenancy
leak, so there is nothing to substitute.

**Plain `require_user`, never `require_user_sensitive`.** Channel membership is
not workspace membership, so these writes are outside the fail-closed set in
Conventions §5.2 (spec §3.1 says so explicitly). An unreachable denylist
therefore fails open here, as it does for ordinary reads.

**A channel you cannot see is a 404.** Not a 403: distinguishing "no such
channel" from "not yours" tells an outsider that a private channel exists and
what it is called.

Those last two combine into one order, applied by every write here:
`_visible_or_404` and only then `_admin_or_403`. Visibility decides the 404 and
the role decides the 403, in that sequence, so a private channel is always
"absent" before it can be "not yours". The 403 that remains is safe on its own
terms — it can only be reached for a channel the caller can already read, where
"you are not an admin of it" discloses nothing new.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from messaging import channels
from messaging.db import session as db_session
from messaging.models import ADMIN, CREATABLE_KINDS
from messaging.schemas import (
    AddChannelMemberRequest,
    ChannelListResponse,
    ChannelMemberListResponse,
    ChannelMemberResponse,
    ChannelResponse,
    CreateChannelRequest,
    UpdateChannelRequest,
)
from shared import PageParams, ProblemException, UserPrincipal, require_user

router = APIRouter(prefix="/api/v1/channels", tags=["channels"])

#: One message per rule, so the form can put it against the field rather than
#: showing "invalid name" and leaving the user to guess which part was wrong.
_NAME_PROBLEMS: dict[type[Exception], str] = {
    channels.NameRequiredError: "A channel name is required.",
    channels.NameTooShortError: (
        f"A channel name must be at least {channels.MIN_NAME_LENGTH} characters."
    ),
    channels.NameTooLongError: (
        f"A channel name must be {channels.MAX_NAME_LENGTH} characters or fewer."
    ),
    channels.NameMustStartWithLetterError: "A channel name must start with a letter.",
    channels.NameCharactersError: ("A channel name can only use letters, numbers and hyphens."),
}


def _name_problem(exc: Exception) -> ProblemException:
    message = _NAME_PROBLEMS[type(exc)]
    return ProblemException.validation_error(message, errors={"name": [message]})


def _as_channel(visible: channels.VisibleChannel) -> ChannelResponse:
    response = ChannelResponse.model_validate(visible.channel, from_attributes=True)
    return response.model_copy(update={"my_role": visible.my_role})


async def _visible_or_404(
    session: AsyncSession, principal: UserPrincipal, channel_id: uuid.UUID
) -> channels.VisibleChannel:
    """The channel, or the 404 that covers every reason it is not available."""
    found = await channels.get_visible(
        session,
        workspace_id=principal.workspace_id,
        user_id=principal.user_id,
        channel_id=channel_id,
    )
    if found is None:
        raise ProblemException.not_found("No such channel.")
    return found


def _admin_or_403(visible: channels.VisibleChannel) -> None:
    """Administering a channel needs the admin role in *that channel*.

    Never called before `_visible_or_404`, so this can only refuse someone who
    can already see what they are being refused.
    """
    if visible.my_role != ADMIN:
        raise ProblemException.forbidden("Only a channel admin can do that.")


@router.get("", response_model=ChannelListResponse)
async def list_channels(
    page: PageParams,
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
) -> ChannelListResponse:
    """Channels in the caller's workspace that the caller may know about.

    Public channels regardless of membership, plus anything else they have
    joined; archived channels are excluded. Alphabetical, cursor-paginated
    (Conventions §4.1) — never `OFFSET`.
    """
    found = await channels.list_page(
        session,
        workspace_id=principal.workspace_id,
        user_id=principal.user_id,
        page=page,
    )
    return ChannelListResponse(
        items=[_as_channel(v) for v in found.items], next_cursor=found.next_cursor
    )


@router.post("", response_model=ChannelResponse, status_code=status.HTTP_201_CREATED)
async def create_channel(
    body: CreateChannelRequest,
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
) -> ChannelResponse:
    """Create a channel, with the caller as its admin."""
    try:
        created = await channels.create(
            session,
            workspace_id=principal.workspace_id,
            created_by=principal.user_id,
            name=body.name,
            topic=body.topic,
            kind=body.kind,
        )
    except tuple(_NAME_PROBLEMS) as exc:
        raise _name_problem(exc) from exc
    except channels.UnknownKindError as exc:
        raise ProblemException.validation_error(
            f"A channel cannot be created with kind {body.kind!r}.",
            errors={"kind": [f"Must be one of: {', '.join(CREATABLE_KINDS)}"]},
        ) from exc
    except channels.DuplicateNameError as exc:
        raise ProblemException.conflict(
            "A channel with that name already exists in this workspace."
        ) from exc

    response = _as_channel(created)
    await session.commit()
    return response


@router.get("/{channel_id}", response_model=ChannelResponse)
async def get_channel(
    channel_id: uuid.UUID,
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
) -> ChannelResponse:
    """One channel, if the caller may know it exists."""
    found = await channels.get_visible(
        session,
        workspace_id=principal.workspace_id,
        user_id=principal.user_id,
        channel_id=channel_id,
    )
    if found is None:
        raise ProblemException.not_found("No such channel.")

    return _as_channel(found)


@router.patch("/{channel_id}", response_model=ChannelResponse)
async def update_channel(
    channel_id: uuid.UUID,
    body: UpdateChannelRequest,
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
) -> ChannelResponse:
    """Rename a channel, or change its topic. Channel admins only.

    The response is re-read through `get_visible` rather than built from the
    object in the session: the update went through Core, so the in-session row
    is stale and would report the old name back to the client that just changed
    it. What comes back is what was stored.
    """
    visible = await _visible_or_404(session, principal, channel_id)
    _admin_or_403(visible)

    try:
        await channels.rename(
            session,
            channel_id=channel_id,
            expected_version=body.version,
            name=body.name,
            topic=body.topic,
            set_topic="topic" in body.model_fields_set,
        )
    except tuple(_NAME_PROBLEMS) as exc:
        raise _name_problem(exc) from exc
    except channels.DuplicateNameError as exc:
        raise ProblemException.conflict(
            "A channel with that name already exists in this workspace."
        ) from exc
    except channels.VersionConflictError as exc:
        raise ProblemException.conflict(
            "This channel was changed by someone else. Reload and try again."
        ) from exc

    # Expire first, or the re-read comes back out of the identity map still
    # holding the pre-update values — the Core `UPDATE` never touched the object.
    session.expire(visible.channel)
    updated = await _visible_or_404(session, principal, channel_id)
    response = _as_channel(updated)
    await session.commit()
    return response


@router.delete("/{channel_id}", response_model=ChannelResponse)
async def archive_channel(
    channel_id: uuid.UUID,
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
) -> ChannelResponse:
    """Archive a channel — the soft delete from spec §4. Channel admins only.

    Unconditional and one-way. Every read in this service goes through
    `get_visible`, which filters `archived_at IS NULL`, so an archived channel
    and its messages are unreachable afterwards by anyone including the admin
    who archived it. Archiving a second time is therefore a 404, which is
    consistent rather than a case to special-case into a 204.

    The archived channel is returned, since it is the last chance anyone gets to
    see it and the SPA needs the row it is navigating away from. It is re-read
    with `refresh` rather than through `get_visible`, which by now filters it
    out — that being the whole point of the write.
    """
    visible = await _visible_or_404(session, principal, channel_id)
    _admin_or_403(visible)

    await channels.archive(session, channel_id=channel_id)
    await session.refresh(visible.channel)
    response = _as_channel(visible)
    await session.commit()
    return response


@router.get("/{channel_id}/members", response_model=ChannelMemberListResponse)
async def list_members(
    channel_id: uuid.UUID,
    page: PageParams,
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
) -> ChannelMemberListResponse:
    """Who is in a channel the caller can see.

    Guarded by visibility, not by membership — spec §3.1 says "channel member",
    and taken literally that would let Grace see `#general` in her sidebar, read
    every word in it, and get a 403 for asking who else is there. A private
    channel is invisible to non-members already, so the only case this widens is
    a public one, where the membership is not a secret from a workspace that can
    already read the conversation.

    Ordered by user id, which is arbitrary to a human on purpose: Messaging
    holds no display names, so it has no meaningful order to offer. The panel
    sorts the page it receives.
    """
    await _visible_or_404(session, principal, channel_id)

    found = await channels.members_page(session, channel_id=channel_id, page=page)
    return ChannelMemberListResponse(
        items=[ChannelMemberResponse.model_validate(m, from_attributes=True) for m in found.items],
        next_cursor=found.next_cursor,
    )


@router.post(
    "/{channel_id}/members",
    response_model=ChannelMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_member(
    channel_id: uuid.UUID,
    body: AddChannelMemberRequest,
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
) -> ChannelMemberResponse:
    """Add someone to a channel. Channel admins only, including adding yourself.

    There is no self-join in this scope: joining a channel is something an admin
    does to you, not something you do.
    """
    visible = await _visible_or_404(session, principal, channel_id)
    _admin_or_403(visible)

    try:
        member = await channels.add_member(
            session, channel_id=channel_id, user_id=body.user_id, role=body.role
        )
    except channels.AlreadyMemberError as exc:
        raise ProblemException.conflict("That user is already in this channel.") from exc

    response = ChannelMemberResponse.model_validate(member, from_attributes=True)
    await session.commit()
    return response


@router.delete("/{channel_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    channel_id: uuid.UUID,
    user_id: uuid.UUID,
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
) -> None:
    """Remove someone from a channel. Channel admins only.

    Nothing else is revoked: channel membership is in no token, so unlike Auth's
    workspace removal there are no sessions to end here. A reviewer who
    remembers that route will look for the equivalent — there is none to write.
    """
    visible = await _visible_or_404(session, principal, channel_id)
    _admin_or_403(visible)

    try:
        removed = await channels.remove_member(session, channel_id=channel_id, user_id=user_id)
    except channels.LastAdminError as exc:
        raise ProblemException.conflict(
            "This is the channel's only admin; make someone else an admin first."
        ) from exc

    if not removed:
        raise ProblemException.not_found("That user is not in this channel.")

    await session.commit()
