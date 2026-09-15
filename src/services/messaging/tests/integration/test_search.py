"""`GET /api/v1/search/messages` against real Elasticsearch and Postgres (doc 02 §3.1.6).

ADR 260914: **the index is a candidate list, Postgres decides what is shown.**
Elasticsearch returns ids filtered to the caller's workspace and visible
channels; the rows are hydrated from Postgres, which drops anything deleted or
no longer visible and supplies the current body.

The index is seeded with the Worker's own mapping and handlers, through
`testkit.search` — Messaging never imports the Worker (register D34). Seeding
directly, rather than by running a consumer, is what lets a test build an index
that lags the database, which is the case hydration exists for.
"""

from __future__ import annotations

import uuid

import pytest

from testkit.search import MessagesIndex

SEARCH = "/api/v1/search/messages"


@pytest.fixture
async def index(elasticsearch) -> MessagesIndex:
    messages = MessagesIndex(elasticsearch)
    await messages.create()
    return messages


@pytest.fixture
async def client(client_for, elasticsearch_url):
    """Messaging pointed at the real Elasticsearch — only these tests start it."""
    async with client_for(elasticsearch_url=elasticsearch_url) as c:
        yield c


async def make_channel(client, headers, name="general", **body):
    response = await client.post("/api/v1/channels", json={"name": name, **body}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def send(client, headers, channel_id, body):
    response = await client.post(
        f"/api/v1/channels/{channel_id}/messages", json={"body": body}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


async def search(client, headers, q, **params):
    return await client.get(SEARCH, params={"q": q, **params}, headers=headers)


async def found(client, headers, q, **params) -> list[str]:
    response = await search(client, headers, q, **params)
    assert response.status_code == 200, response.text
    return [m["body"] for m in response.json()["items"]]


# --- candidates, hydrated ------------------------------------------------------


async def test_a_match_comes_back_as_the_message_itself(client, ada, tokens, index):
    channel = await make_channel(client, ada)
    deploy = await send(client, ada, channel["id"], "deploy the api at noon")
    lunch = await send(client, ada, channel["id"], "lunch plans")
    for message in (deploy, lunch):
        await index.index(message, workspace_id=tokens.WORKSPACE)

    response = await search(client, ada, "deploy")

    assert response.status_code == 200
    single = await client.get(f"/api/v1/messages/{deploy['id']}", headers=ada)
    assert response.json() == {"items": [single.json()], "nextCursor": None}


async def test_the_body_shown_is_postgres_not_the_index(client, ada, tokens, index):
    """The index lags: the edit below was never re-indexed."""
    channel = await make_channel(client, ada)
    sent = await send(client, ada, channel["id"], "retro on thursday")
    await index.index(sent, workspace_id=tokens.WORKSPACE)
    await client.patch(
        f"/api/v1/messages/{sent['id']}",
        json={"body": "retro moved to friday", "version": sent["version"]},
        headers=ada,
    )

    [item] = (await search(client, ada, "thursday")).json()["items"]

    assert item["body"] == "retro moved to friday"
    assert item["editedAt"] is not None


async def test_results_are_newest_first_and_page_by_cursor(client, ada, tokens, index):
    channel = await make_channel(client, ada)
    for body in ("standup one", "standup two", "standup three"):
        await index.index(
            await send(client, ada, channel["id"], body), workspace_id=tokens.WORKSPACE
        )

    first = (await search(client, ada, "standup", limit=2)).json()
    second = (await search(client, ada, "standup", limit=2, cursor=first["nextCursor"])).json()

    assert [m["body"] for m in first["items"]] == ["standup three", "standup two"]
    assert [m["body"] for m in second["items"]] == ["standup one"]
    assert second["nextCursor"] is None


# --- who may see what ------------------------------------------------------------


async def test_a_private_channel_you_are_not_in_is_excluded(client, ada, grace, tokens, index):
    # Grace must see *some* channel, or search returns before it filters anything
    # and this test would pass with no channel filter at all.
    await make_channel(client, ada, "general")
    private = await make_channel(client, ada, "leadership", kind="private")
    await index.index(
        await send(client, ada, private["id"], "the reorg roadmap"), workspace_id=tokens.WORKSPACE
    )

    assert await found(client, grace, "roadmap") == []
    assert await found(client, ada, "roadmap") == ["the reorg roadmap"]


async def test_another_workspaces_messages_are_excluded(client, ada, tokens, index):
    alan = tokens.header(
        user_id=uuid.uuid4(), workspace_id=tokens.OTHER_WORKSPACE, name="Alan Turing"
    )
    ours = await make_channel(client, ada, "finance")
    theirs = await make_channel(client, alan, "finance")
    await index.index(
        await send(client, ada, ours["id"], "quarterly numbers are in"),
        workspace_id=tokens.WORKSPACE,
    )
    await index.index(
        await send(client, alan, theirs["id"], "quarterly numbers look odd"),
        workspace_id=tokens.OTHER_WORKSPACE,
    )

    assert await found(client, ada, "quarterly") == ["quarterly numbers are in"]
    assert await found(client, alan, "quarterly") == ["quarterly numbers look odd"]


# --- deleted messages ------------------------------------------------------------


async def test_a_message_deleted_after_it_was_indexed_is_not_returned(client, ada, tokens, index):
    """Hydration, not the index, keeps a deleted message's text out of results."""
    channel = await make_channel(client, ada)
    sent = await send(client, ada, channel["id"], "the wifi password is hunter2")
    await index.index(sent, workspace_id=tokens.WORKSPACE)
    await client.delete(f"/api/v1/messages/{sent['id']}", headers=ada)

    assert await found(client, ada, "password") == []


# --- failures and limits --------------------------------------------------------


async def test_before_anything_is_indexed_search_is_empty_not_an_error(client, ada, elasticsearch):
    """No `messages` alias yet — the Worker has never run."""
    await make_channel(client, ada)

    response = await search(client, ada, "anything")

    assert response.status_code == 200
    assert response.json() == {"items": [], "nextCursor": None}


async def test_elasticsearch_being_down_is_a_503(client_for, ada):
    async with client_for(elasticsearch_url="http://127.0.0.1:1") as client:
        # A visible channel, or the search never reaches Elasticsearch at all.
        await make_channel(client, ada)
        response = await search(client, ada, "anything")

    assert response.status_code == 503
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["type"] == "https://collabhub.dev/problems/service-unavailable"


async def test_a_blank_query_is_a_400(client, ada, index):
    response = await search(client, ada, "   ")

    assert response.status_code == 400
    assert "q" in response.json()["errors"]
