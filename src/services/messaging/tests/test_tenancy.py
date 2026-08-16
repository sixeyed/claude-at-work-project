"""Workspace isolation (Conventions §5.4, spec §3.1).

The rule these hold is the one whose failure is a tenancy leak rather than a
bug: a channel belongs to the workspace in the token's `wsp` claim, and there is
no request in which a caller can name a different one.

Worth stating why there is no "workspace in the body is ignored" test here: the
create request has no workspace field at all. That is the design — the shape
makes the leak unrepresentable rather than the handler refusing it.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


async def test_a_token_cannot_see_another_workspaces_channels(client, ada, tokens):
    await client.post("/api/v1/channels", json={"name": "general"}, headers=ada)
    elsewhere = tokens.header(workspace_id=tokens.OTHER_WORKSPACE)

    body = (await client.get("/api/v1/channels", headers=elsewhere)).json()

    assert body["items"] == []


async def test_a_token_cannot_read_another_workspaces_channel_by_id(client, ada, tokens):
    created = (await client.post("/api/v1/channels", json={"name": "general"}, headers=ada)).json()
    elsewhere = tokens.header(workspace_id=tokens.OTHER_WORKSPACE)

    response = await client.get(f"/api/v1/channels/{created['id']}", headers=elsewhere)

    # 404, not 403: from that token's point of view the channel does not exist.
    assert response.status_code == 404


async def test_the_same_name_is_free_in_another_workspace(client, ada, tokens):
    """Uniqueness is per workspace — every workspace gets its own #general."""
    assert (
        await client.post("/api/v1/channels", json={"name": "general"}, headers=ada)
    ).status_code == 201

    elsewhere = tokens.header(workspace_id=tokens.OTHER_WORKSPACE)
    response = await client.post("/api/v1/channels", json={"name": "general"}, headers=elsewhere)

    assert response.status_code == 201


async def test_a_channel_is_created_in_the_workspace_from_the_claim(client, tokens):
    elsewhere = tokens.header(workspace_id=tokens.OTHER_WORKSPACE)
    await client.post("/api/v1/channels", json={"name": "general"}, headers=elsewhere)

    mine = tokens.header()
    assert (await client.get("/api/v1/channels", headers=mine)).json()["items"] == []
    assert len((await client.get("/api/v1/channels", headers=elsewhere)).json()["items"]) == 1


# --- the slice 2 write surface --------------------------------------------


async def test_another_workspace_gets_404_not_403_on_every_channel_write(client, ada, tokens):
    """The whole slice-2 write surface, held to the same rule as the reads.

    404 on all of it. A 403 anywhere here would confirm to a token from another
    workspace that the channel exists and what its id refers to — and these are
    the routes where a role check makes reaching for 403 feel natural.
    """
    created = (await client.post("/api/v1/channels", json={"name": "general"}, headers=ada)).json()
    elsewhere = tokens.header(workspace_id=tokens.OTHER_WORKSPACE)
    channel = f"/api/v1/channels/{created['id']}"

    responses = {
        "patch": await client.patch(
            channel, json={"version": 0, "name": "hijacked"}, headers=elsewhere
        ),
        "delete": await client.delete(channel, headers=elsewhere),
        "list members": await client.get(f"{channel}/members", headers=elsewhere),
        "add member": await client.post(
            f"{channel}/members", json={"userId": str(tokens.GRACE)}, headers=elsewhere
        ),
        "remove member": await client.delete(f"{channel}/members/{tokens.ADA}", headers=elsewhere),
    }

    assert {name: r.status_code for name, r in responses.items()} == {
        "patch": 404,
        "delete": 404,
        "list members": 404,
        "add member": 404,
        "remove member": 404,
    }


async def test_a_write_from_another_workspace_changes_nothing(client, ada, tokens):
    created = (await client.post("/api/v1/channels", json={"name": "general"}, headers=ada)).json()
    elsewhere = tokens.header(workspace_id=tokens.OTHER_WORKSPACE)

    await client.patch(
        f"/api/v1/channels/{created['id']}",
        json={"version": 0, "name": "hijacked"},
        headers=elsewhere,
    )

    assert (await client.get(f"/api/v1/channels/{created['id']}", headers=ada)).json() == created


# --- messages --------------------------------------------------------------


async def test_another_workspace_cannot_reach_a_channels_messages(client, ada, tokens):
    created = (await client.post("/api/v1/channels", json={"name": "general"}, headers=ada)).json()
    message = (
        await client.post(
            f"/api/v1/channels/{created['id']}/messages",
            json={"body": "the eagle has landed"},
            headers=ada,
        )
    ).json()
    elsewhere = tokens.header(workspace_id=tokens.OTHER_WORKSPACE)

    assert (
        await client.get(f"/api/v1/channels/{created['id']}/messages", headers=elsewhere)
    ).status_code == 404
    assert (
        await client.get(f"/api/v1/messages/{message['id']}", headers=elsewhere)
    ).status_code == 404


async def test_a_post_from_another_workspace_writes_nothing(client, ada, tokens):
    created = (await client.post("/api/v1/channels", json={"name": "general"}, headers=ada)).json()
    elsewhere = tokens.header(workspace_id=tokens.OTHER_WORKSPACE)

    response = await client.post(
        f"/api/v1/channels/{created['id']}/messages",
        json={"body": "not from here"},
        headers=elsewhere,
    )

    assert response.status_code == 404
    listed = await client.get(f"/api/v1/channels/{created['id']}/messages", headers=ada)
    assert listed.json()["items"] == []


async def test_another_workspace_cannot_edit_or_delete_a_message(client, ada, tokens):
    """404, and the row is untouched.

    There is no workspace anywhere in either request to substitute — it comes
    only from the `wsp` claim — so what this holds is that the claim is actually
    read on the way through.
    """
    created = (await client.post("/api/v1/channels", json={"name": "general"}, headers=ada)).json()
    message = (
        await client.post(
            f"/api/v1/channels/{created['id']}/messages",
            json={"body": "the eagle has landed"},
            headers=ada,
        )
    ).json()
    elsewhere = tokens.header(workspace_id=tokens.OTHER_WORKSPACE)

    edited = await client.patch(
        f"/api/v1/messages/{message['id']}",
        json={"body": "hijacked", "version": 0},
        headers=elsewhere,
    )
    deleted = await client.delete(f"/api/v1/messages/{message['id']}", headers=elsewhere)

    assert edited.status_code == 404
    assert deleted.status_code == 404
    assert (await client.get(f"/api/v1/messages/{message['id']}", headers=ada)).json() == message
