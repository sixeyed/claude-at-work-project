"""Walking a channel's history a page at a time (Conventions §4.1).

Its own module rather than three more cases in `test_messages.py`, because
what it holds is a property of the cursor and not of messages: **walk it to
exhaustion and you see every row exactly once, in order**. That is the claim
keyset pagination makes and the one an `OFFSET` quietly breaks the moment
anything is inserted mid-walk.

120 rows against a default page of 50, so the walk crosses three pages and the
last one is short — the boundary where an off-by-one in `fetch_limit` shows up.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

TOTAL = 120


async def make_channel(client, headers, name="general"):
    response = await client.post("/api/v1/channels", json={"name": name}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def fill(client, headers, channel_id, count=TOTAL):
    for i in range(count):
        response = await client.post(
            f"/api/v1/channels/{channel_id}/messages",
            json={"body": f"message {i:03d}"},
            headers=headers,
        )
        assert response.status_code == 201, response.text


async def walk(client, headers, channel_id, **params):
    """Every page of history, following `nextCursor` until it runs out."""
    pages = []
    cursor = None
    # Bounded, so a cursor that never advances fails the test rather than
    # hanging the suite.
    for _ in range(20):
        query = {**params, **({"cursor": cursor} if cursor else {})}
        body = (
            await client.get(
                f"/api/v1/channels/{channel_id}/messages", params=query, headers=headers
            )
        ).json()
        pages.append(body)
        cursor = body["nextCursor"]
        if cursor is None:
            return pages

    raise AssertionError("the cursor never reached the end of the history")


async def test_the_walk_sees_every_message_exactly_once_newest_first(client, ada):
    channel = await make_channel(client, ada)
    await fill(client, ada, channel["id"])

    pages = await walk(client, ada, channel["id"])
    bodies = [m["body"] for page in pages for m in page["items"]]

    assert len(pages) == 3
    assert len(bodies) == TOTAL
    assert len(set(bodies)) == TOTAL
    assert bodies == [f"message {i:03d}" for i in reversed(range(TOTAL))]


async def test_the_first_page_is_the_default_limit_and_the_last_is_short(client, ada):
    channel = await make_channel(client, ada)
    await fill(client, ada, channel["id"])

    pages = await walk(client, ada, channel["id"])

    assert [len(page["items"]) for page in pages] == [50, 50, 20]
    # Null on the last page, not an empty string and not a cursor pointing at
    # nothing: the client stops on null.
    assert [page["nextCursor"] is None for page in pages] == [False, False, True]


async def test_a_smaller_limit_walks_the_same_rows_in_the_same_order(client, ada):
    channel = await make_channel(client, ada)
    await fill(client, ada, channel["id"], count=25)

    default = await walk(client, ada, channel["id"])
    by_sevens = await walk(client, ada, channel["id"], limit=7)

    assert [m["id"] for p in default for m in p["items"]] == [
        m["id"] for p in by_sevens for m in p["items"]
    ]


async def test_a_message_sent_mid_walk_does_not_shift_the_pages(client, ada):
    """The reason there is no `OFFSET` here.

    A newer message sorts above the whole walk — the cursor names a row rather
    than a position, so the pages after it are unmoved. With `OFFSET` the insert
    would push one row across every boundary and the walk would show it twice.
    """
    channel = await make_channel(client, ada)
    await fill(client, ada, channel["id"], count=60)

    first = (
        await client.get(
            f"/api/v1/channels/{channel['id']}/messages", params={"limit": 50}, headers=ada
        )
    ).json()
    await client.post(
        f"/api/v1/channels/{channel['id']}/messages",
        json={"body": "sent mid-walk"},
        headers=ada,
    )
    second = (
        await client.get(
            f"/api/v1/channels/{channel['id']}/messages",
            params={"limit": 50, "cursor": first["nextCursor"]},
            headers=ada,
        )
    ).json()

    bodies = [m["body"] for m in first["items"]] + [m["body"] for m in second["items"]]
    assert len(bodies) == len(set(bodies)) == 60
    assert "sent mid-walk" not in bodies


async def test_an_empty_channel_pages_to_nothing(client, ada):
    channel = await make_channel(client, ada)

    body = (await client.get(f"/api/v1/channels/{channel['id']}/messages", headers=ada)).json()

    assert body == {"items": [], "nextCursor": None}


async def test_a_malformed_cursor_is_a_400(client, ada):
    channel = await make_channel(client, ada)

    response = await client.get(
        f"/api/v1/channels/{channel['id']}/messages",
        params={"cursor": "not-a-cursor"},
        headers=ada,
    )

    assert response.status_code == 400
    assert response.json()["errors"]["cursor"] == ["Malformed cursor"]


async def test_a_limit_over_the_maximum_is_a_400(client, ada):
    channel = await make_channel(client, ada)

    response = await client.get(
        f"/api/v1/channels/{channel['id']}/messages", params={"limit": 500}, headers=ada
    )

    assert response.status_code == 400
