"""Channel membership (spec §3.1).

Membership is what gates *administering* a channel, not what gates seeing it —
so most of what these cover is the difference between the two: who may read the
member list (anyone who can see the channel), who may change it (an admin of
that channel), and what a caller who can see neither is told (404, never 403).

The two rules with no Gherkin behind them live here on purpose. Removing the
last admin is a state you cannot reach through the UI in two steps, and a
non-admin write is a request the SPA never makes because it does not render the
control — both are still worth holding the server to.
"""

from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.integration


async def create(client, headers, name, **body):
    response = await client.post("/api/v1/channels", json={"name": name, **body}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def add(client, headers, channel_id, user_id, **body):
    return await client.post(
        f"/api/v1/channels/{channel_id}/members",
        json={"userId": str(user_id), **body},
        headers=headers,
    )


async def test_an_admin_adds_a_member_and_the_list_shows_them(client, ada, tokens):
    channel = await create(client, ada, "launch-plans", kind="private")

    response = await add(client, ada, channel["id"], tokens.GRACE)

    assert response.status_code == 201
    assert response.json()["userId"] == str(tokens.GRACE)
    assert response.json()["role"] == "member"

    body = (await client.get(f"/api/v1/channels/{channel['id']}/members", headers=ada)).json()
    assert {m["userId"] for m in body["items"]} == {str(tokens.ADA), str(tokens.GRACE)}


async def test_adding_someone_twice_is_a_conflict(client, ada, tokens):
    channel = await create(client, ada, "launch-plans", kind="private")
    assert (await add(client, ada, channel["id"], tokens.GRACE)).status_code == 201

    response = await add(client, ada, channel["id"], tokens.GRACE)

    assert response.status_code == 409
    assert "already" in response.json()["detail"].lower()


async def test_adding_a_member_to_a_private_channel_makes_it_visible_to_them(
    client, ada, grace, tokens
):
    channel = await create(client, ada, "launch-plans", kind="private")
    assert (await client.get("/api/v1/channels", headers=grace)).json()["items"] == []

    await add(client, ada, channel["id"], tokens.GRACE)

    body = (await client.get("/api/v1/channels", headers=grace)).json()
    assert [c["name"] for c in body["items"]] == ["launch-plans"]
    # A member, not an admin — so the SPA offers her no controls.
    assert body["items"][0]["myRole"] == "member"


async def test_a_member_can_be_added_as_an_admin(client, ada, grace, tokens):
    channel = await create(client, ada, "launch-plans", kind="private")

    response = await add(client, ada, channel["id"], tokens.GRACE, role="admin")

    assert response.status_code == 201
    assert response.json()["role"] == "admin"
    assert (await client.get(f"/api/v1/channels/{channel['id']}", headers=grace)).json()[
        "myRole"
    ] == "admin"


async def test_an_unknown_role_is_rejected(client, ada, tokens):
    channel = await create(client, ada, "launch-plans", kind="private")

    response = await add(client, ada, channel["id"], tokens.GRACE, role="owner")

    assert response.status_code == 400
    assert "role" in response.json()["errors"]


async def test_removing_a_member_revokes_their_view(client, ada, grace, tokens):
    channel = await create(client, ada, "launch-plans", kind="private")
    await add(client, ada, channel["id"], tokens.GRACE)

    response = await client.delete(
        f"/api/v1/channels/{channel['id']}/members/{tokens.GRACE}", headers=ada
    )

    assert response.status_code == 204
    assert (await client.get("/api/v1/channels", headers=grace)).json()["items"] == []
    assert (await client.get(f"/api/v1/channels/{channel['id']}", headers=grace)).status_code == 404


async def test_removing_someone_who_is_not_a_member_is_a_404(client, ada):
    channel = await create(client, ada, "launch-plans", kind="private")

    response = await client.delete(
        f"/api/v1/channels/{channel['id']}/members/{uuid.uuid4()}", headers=ada
    )

    assert response.status_code == 404


async def test_removing_the_only_admin_is_refused(client, ada, tokens):
    """A channel with no admin can never be administered again by anyone.

    There is no route that grants the role back, so this is the one thing
    standing between a channel and being permanently unmanageable.
    """
    channel = await create(client, ada, "general")

    response = await client.delete(
        f"/api/v1/channels/{channel['id']}/members/{tokens.ADA}", headers=ada
    )

    assert response.status_code == 409
    assert "only admin" in response.json()["detail"].lower()


async def test_an_admin_can_leave_once_someone_else_administers(client, ada, tokens):
    channel = await create(client, ada, "general")
    await add(client, ada, channel["id"], tokens.GRACE, role="admin")

    response = await client.delete(
        f"/api/v1/channels/{channel['id']}/members/{tokens.ADA}", headers=ada
    )

    assert response.status_code == 204


async def test_a_non_admin_cannot_add_a_member(client, ada, grace, tokens):
    """403, not 404: the channel is public, so Grace can already see it.

    Refusing with "not found" for something in her own sidebar would be a lie;
    the disclosure rule only bites where the caller cannot see the channel.
    """
    channel = await create(client, ada, "general")

    response = await add(client, grace, channel["id"], uuid.uuid4())

    assert response.status_code == 403


async def test_a_non_member_cannot_add_a_member_to_a_private_channel(client, ada, grace):
    channel = await create(client, ada, "launch-plans", kind="private")

    response = await add(client, grace, channel["id"], uuid.uuid4())

    # 404 and not 403 — Grace is not entitled to learn the channel is there.
    assert response.status_code == 404


async def test_anyone_who_can_see_a_public_channel_can_read_its_members(client, ada, grace, tokens):
    """Visibility gates the member list, not membership.

    Grace has never joined `#general`. She can see it, she can read it, and
    asking who is in it tells her nothing the channel itself does not.
    """
    channel = await create(client, ada, "general")

    response = await client.get(f"/api/v1/channels/{channel['id']}/members", headers=grace)

    assert response.status_code == 200
    assert [m["userId"] for m in response.json()["items"]] == [str(tokens.ADA)]


async def test_a_non_member_cannot_read_a_private_channels_members(client, ada, grace):
    channel = await create(client, ada, "launch-plans", kind="private")

    response = await client.get(f"/api/v1/channels/{channel['id']}/members", headers=grace)

    assert response.status_code == 404


async def test_the_member_list_pages_by_cursor(client, ada, tokens):
    channel = await create(client, ada, "general")
    added = [uuid.uuid4() for _ in range(3)]
    for user_id in added:
        assert (await add(client, ada, channel["id"], user_id)).status_code == 201

    seen: list[str] = []
    cursor: str | None = None
    for _ in range(10):
        query = f"?limit=1{f'&cursor={cursor}' if cursor else ''}"
        body = (
            await client.get(f"/api/v1/channels/{channel['id']}/members{query}", headers=ada)
        ).json()
        seen.extend(m["userId"] for m in body["items"])
        cursor = body["nextCursor"]
        if cursor is None:
            break

    expected = sorted(str(u) for u in [*added, tokens.ADA])
    # Neither skipped nor repeated, and in the id order the endpoint documents.
    assert seen == expected
