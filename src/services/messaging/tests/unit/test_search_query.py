"""Search query rules and the Elasticsearch request they build (doc 02 §3.1.6).

The request body is the security property of search: the index holds nothing
about who may see what, so the workspace and visible-channel filters in it are
the whole of the authorization. Built by a pure function, it is asserted here
with no Elasticsearch. That ES *honours* the request, and that hydration drops
deleted rows, is integration.
"""

from __future__ import annotations

import uuid

import pytest

from contracts import MESSAGES_ALIAS
from messaging import search
from messaging.main import create_app
from messaging.settings import Settings
from shared import PageRequest

WORKSPACE = uuid.uuid4()
CHANNELS = [uuid.uuid4(), uuid.uuid4()]


def _settings() -> Settings:
    """Syntactically valid and unreachable — nothing in this file dials them."""
    return Settings(
        postgres_dsn="postgresql+asyncpg://collabhub:collabhub@postgres:5432/collabhub_messaging",
        redis_cache_url="redis://redis-cache:6379/0",
        redis_realtime_url="redis://redis-rt:6379/0",
        redis_streams_url="redis://redis-streams:6379/0",
        elasticsearch_url="http://elasticsearch:9200",
        auth_issuer="http://localhost:8001",
        auth_jwks_url="http://auth:8000/.well-known/jwks.json",
    )


def _request(query: str = "standup notes", cursor: tuple[str, ...] | None = None) -> dict:
    return search.candidate_query(WORKSPACE, CHANNELS, query, PageRequest(limit=20, cursor=cursor))


# --- the query string ------------------------------------------------------


@pytest.mark.parametrize("raw", ["", "   ", "\t\n"])
def test_a_blank_query_is_refused(raw):
    """Breaks if a blank query reaches Elasticsearch, where `match` on "" finds nothing."""
    with pytest.raises(search.QueryRequiredError):
        search.validate_query(raw)


def test_the_query_is_trimmed():
    assert search.validate_query("  standup  ") == "standup"


def test_the_route_caps_the_query_at_200_characters():
    """The cap is declared on the route, so FastAPI refuses it before any code runs.

    Breaks if `max_length` is dropped from `q` or `MAX_QUERY_CHARS` moves.
    """
    operation = create_app(_settings()).openapi()["paths"]["/api/v1/search/messages"]["get"]
    (q,) = [p for p in operation["parameters"] if p["name"] == "q"]

    assert search.MAX_QUERY_CHARS == 200
    assert q["required"] is True
    assert q["schema"]["maxLength"] == 200


# --- the Elasticsearch request --------------------------------------------


def test_the_request_is_filtered_to_the_workspace_and_the_visible_channels():
    """The tenancy filter: breaks if either term is dropped or takes the wrong ids."""
    filters = _request()["query"]["bool"]["filter"]

    assert {"term": {"workspaceId": str(WORKSPACE)}} in filters
    assert {"terms": {"channelId": [str(c) for c in CHANNELS]}} in filters


def test_the_request_excludes_deleted_messages():
    """Breaks if tombstones in the index can be matched."""
    assert {"term": {"deleted": False}} in _request()["query"]["bool"]["filter"]


def test_every_word_must_match_and_no_query_syntax_is_exposed():
    """`match` with `operator: and`, never `query_string`."""
    assert _request("standup notes")["query"]["bool"]["must"] == [
        {"match": {"body": {"query": "standup notes", "operator": "and"}}}
    ]


def test_hits_are_ids_only_newest_first_from_the_alias():
    """Breaks if the request reads a concrete index, returns sources or sorts otherwise."""
    request = _request()

    assert request["index"] == MESSAGES_ALIAS
    assert request["sort"] == [{"messageId": "desc"}]
    assert request["source"] is False
    assert request["track_total_hits"] is False


def test_one_more_hit_than_the_page_is_asked_for():
    """`fetch_limit`, so whether a next page exists is known from the hits in hand."""
    assert _request()["size"] == 21


def test_a_first_page_has_no_search_after():
    assert "search_after" not in _request()


def test_a_later_page_resumes_after_the_cursor():
    """Keyset, not offset: breaks if the cursor is ignored."""
    last = str(uuid.uuid4())
    assert _request(cursor=(last,))["search_after"] == [last]
