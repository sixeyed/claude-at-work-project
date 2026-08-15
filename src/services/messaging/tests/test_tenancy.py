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
