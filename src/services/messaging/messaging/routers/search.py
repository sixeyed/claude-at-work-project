"""`GET /api/v1/search/messages` (doc 02 §3.1, §3.1.6).

A thin proxy in Messaging rather than a search gateway (register D8c 🟡). All
the rules live in `messaging/search.py`; this module validates the query string
and translates failures.

**Plain `require_user`.** Searching is a read and is outside the fail-closed
denylist set (Conventions §5.2).

**No workspace parameter**, and there must never be one: the workspace is the
`wsp` claim, and the channel filter is computed from it on every request.
"""

from __future__ import annotations

from typing import Annotated

from elasticsearch import AsyncElasticsearch
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from messaging import search
from messaging.db import session as db_session
from messaging.routers.messages import _as_message
from messaging.schemas import MessageListResponse
from shared import PageParams, ProblemException, UserPrincipal, require_user

router = APIRouter(prefix="/api/v1/search", tags=["search"])


def _search_client(request: Request) -> AsyncElasticsearch:
    """The app's query-only client. `Request` is annotated so FastAPI injects it."""
    return request.app.state.search


@router.get("/messages", response_model=MessageListResponse)
async def search_messages(
    q: Annotated[str, Query(max_length=search.MAX_QUERY_CHARS)],
    page: PageParams,
    principal: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(db_session),
    es: AsyncElasticsearch = Depends(_search_client),
) -> MessageListResponse:
    """Messages matching every word of `q`, newest first, in channels the caller can see.

    **A short page is not the last page** — hydration can drop a hit whose row
    was deleted after it was indexed. Only `nextCursor: null` means the end.
    """
    query = q.strip()
    if not query:
        message = "Enter something to search for."
        raise ProblemException.validation_error(message, errors={"q": [message]})
    if page.cursor is not None and len(page.cursor) != 1:
        raise ProblemException.validation_error("The cursor is not valid.")

    try:
        found = await search.search_messages(
            es,
            session,
            workspace_id=principal.workspace_id,
            user_id=principal.user_id,
            query=query,
            page=page,
        )
    except search.SearchUnavailableError as exc:
        raise ProblemException.service_unavailable("Search is unavailable.") from exc

    return MessageListResponse(
        items=[_as_message(m) for m in found.items], next_cursor=found.next_cursor
    )
