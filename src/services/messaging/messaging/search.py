"""Message search: Elasticsearch finds candidates, Postgres decides what is shown.

`GET /search/messages` (doc 02 §3.1.6, register D8c) in three steps.

1. **Authorize before asking.** The caller's visible channel ids come from the
   same query every other read uses, and the Elasticsearch query is filtered to
   them and to the `wsp` workspace. Nothing about who may see what is stored in
   the index, so nothing in the index can be stale about it.
2. **Ask for ids only**, newest first — `messageId` descending, because UUID v7
   in fixed-length lowercase hex sorts in time order — with `search_after` as
   the cursor. The same keyset shape as history (Conventions §4.1).
3. **Hydrate from Postgres**, dropping anything deleted or no longer visible, and
   keep Elasticsearch's order. The index lags the database by however long the
   Worker takes; hydration is what stops that lag from showing a deleted
   message's text.

**A page can be shorter than `limit`** when hydration drops rows. `nextCursor`
comes from the Elasticsearch hits, not the survivors, so no match is ever
skipped — only `nextCursor: null` means there is nothing more.
"""

from __future__ import annotations

import uuid
from typing import Any

from elasticsearch import ApiError, AsyncElasticsearch, NotFoundError, TransportError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contracts import MESSAGES_ALIAS
from messaging import channels
from messaging.models import Message
from shared import Page, PageRequest, encode_cursor

__all__ = [
    "MAX_QUERY_CHARS",
    "QueryRequiredError",
    "SearchUnavailableError",
    "candidate_query",
    "search_messages",
    "validate_query",
]

MAX_QUERY_CHARS = 200


class QueryRequiredError(Exception):
    """Empty, or nothing but whitespace. The router turns this into a 400 on `q`."""


class SearchUnavailableError(Exception):
    """Elasticsearch could not answer. The router turns this into a 503."""


async def search_messages(
    es: AsyncElasticsearch,
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    query: str,
    page: PageRequest,
) -> Page[Message]:
    channel_ids = await channels.visible_ids(session, workspace_id=workspace_id, user_id=user_id)
    if not channel_ids:
        return Page(items=[], next_cursor=None)

    hit_ids = await _candidate_ids(es, workspace_id, channel_ids, query, page)
    has_more = len(hit_ids) > page.limit
    hit_ids = hit_ids[: page.limit]
    next_cursor = encode_cursor(str(hit_ids[-1])) if has_more else None

    return Page(items=await _hydrate(session, hit_ids, channel_ids), next_cursor=next_cursor)


def validate_query(raw: str) -> str:
    """Return the trimmed query, or raise `QueryRequiredError` if nothing is left.

    The length cap is not here: it is `max_length` on the route's `q`, so
    FastAPI refuses an over-long query before any of this runs.
    """
    query = raw.strip()
    if not query:
        raise QueryRequiredError
    return query


def candidate_query(
    workspace_id: uuid.UUID,
    channel_ids: list[uuid.UUID],
    query: str,
    page: PageRequest,
) -> dict[str, Any]:
    """The `es.search` arguments for one page of candidate ids.

    A pure function so the filters — the whole of search's authorization, since
    the index stores nothing about who may see what — are unit tested without
    Elasticsearch (register D32).
    """
    request: dict[str, Any] = {
        "index": MESSAGES_ALIAS,
        "query": {
            "bool": {
                # `operator: and` — every word must match. `match`, not
                # `query_string`: no query syntax is exposed to users.
                "must": [{"match": {"body": {"query": query, "operator": "and"}}}],
                "filter": [
                    {"term": {"workspaceId": str(workspace_id)}},
                    {"terms": {"channelId": [str(c) for c in channel_ids]}},
                    {"term": {"deleted": False}},
                ],
            }
        },
        "sort": [{"messageId": "desc"}],
        "size": page.fetch_limit,
        "source": False,
        "track_total_hits": False,
    }
    if page.cursor:
        request["search_after"] = list(page.cursor)
    return request


async def _candidate_ids(
    es: AsyncElasticsearch,
    workspace_id: uuid.UUID,
    channel_ids: list[uuid.UUID],
    query: str,
    page: PageRequest,
) -> list[uuid.UUID]:
    request = candidate_query(workspace_id, channel_ids, query, page)

    try:
        result = await es.search(**request)
    except NotFoundError as exc:
        # The Worker has never run, so the alias does not exist yet: nothing
        # has been indexed, which is an empty result and not an outage.
        if exc.error == "index_not_found_exception":
            return []
        raise SearchUnavailableError from exc
    except (ApiError, TransportError) as exc:
        raise SearchUnavailableError from exc

    return [uuid.UUID(hit["_id"]) for hit in result["hits"]["hits"]]


async def _hydrate(
    session: AsyncSession, ids: list[uuid.UUID], channel_ids: list[uuid.UUID]
) -> list[Message]:
    """The rows behind the hits, in hit order.

    `deleted_at IS NULL` is right here and is not the history exception from
    Conventions §3: search does not return tombstones.
    """
    if not ids:
        return []
    query = select(Message).where(
        Message.id.in_(ids),
        Message.channel_id.in_(channel_ids),
        Message.deleted_at.is_(None),
    )
    rows = {m.id: m for m in (await session.execute(query)).scalars()}
    return [rows[i] for i in ids if i in rows]
