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
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from messaging import channels
from messaging.db import session as db_session
from messaging.models import CREATABLE_KINDS
from messaging.schemas import ChannelListResponse, ChannelResponse, CreateChannelRequest
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
