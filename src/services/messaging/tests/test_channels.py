"""The channel surface: create, list, read back (spec §3.1).

These cover the rules the Gherkin cannot reach cheaply — the exact status and
`errors` map of each rejection, the case-folded uniqueness index, and the
cursor — plus the ones it should not have to, like a 409 racing two creates.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration

PROBLEM = "application/problem+json"


async def create(client, headers, name, **body):
    return await client.post("/api/v1/channels", json={"name": name, **body}, headers=headers)


async def test_create_returns_the_channel_with_the_caller_as_admin(client, ada):
    response = await create(client, ada, "general")

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "general"
    assert body["kind"] == "public"
    assert body["archivedAt"] is None
    assert body["version"] == 0
    # The creator administers what they create — nothing else could.
    assert body["myRole"] == "admin"


async def test_created_channel_is_readable_by_id(client, ada):
    created = (await create(client, ada, "general")).json()

    response = await client.get(f"/api/v1/channels/{created['id']}", headers=ada)

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


async def test_list_is_alphabetical(client, ada):
    for name in ("zulu", "alpha", "mike"):
        assert (await create(client, ada, name)).status_code == 201

    body = (await client.get("/api/v1/channels", headers=ada)).json()

    assert [c["name"] for c in body["items"]] == ["alpha", "mike", "zulu"]
    assert body["nextCursor"] is None


async def test_list_pages_by_cursor_without_repeating_or_skipping(client, ada):
    names = [f"channel-{i:02d}" for i in range(10)]
    for name in names:
        await create(client, ada, name)

    seen: list[str] = []
    cursor = None
    for _ in range(10):  # bounded so a broken cursor fails rather than hangs
        query = {"limit": 3, **({"cursor": cursor} if cursor else {})}
        body = (await client.get("/api/v1/channels", params=query, headers=ada)).json()
        seen.extend(c["name"] for c in body["items"])
        cursor = body["nextCursor"]
        if cursor is None:
            break

    assert seen == names


async def test_a_public_channel_is_visible_to_a_non_member(client, ada, grace):
    """Grace can see and open #general without having joined it.

    Doc 02 §3.1 marked channel detail "channel member"; that made a public
    channel unopenable by anyone but its creator until an admin added them.
    """
    created = (await create(client, ada, "general")).json()

    listed = (await client.get("/api/v1/channels", headers=grace)).json()
    detail = await client.get(f"/api/v1/channels/{created['id']}", headers=grace)

    assert [c["name"] for c in listed["items"]] == ["general"]
    assert detail.status_code == 200
    # Visible, but she is not in it — that is what gates the messages.
    assert listed["items"][0]["myRole"] is None


async def test_a_private_channel_is_invisible_to_a_non_member(client, ada, grace):
    created = (await create(client, ada, "secrets", kind="private")).json()

    listed = (await client.get("/api/v1/channels", headers=grace)).json()
    detail = await client.get(f"/api/v1/channels/{created['id']}", headers=grace)

    assert listed["items"] == []
    # 404 rather than 403: "that exists but is not yours" is itself a leak.
    assert detail.status_code == 404
    assert detail.headers["content-type"] == PROBLEM


async def test_a_private_channel_is_visible_to_its_creator(client, ada):
    created = (await create(client, ada, "secrets", kind="private")).json()

    listed = (await client.get("/api/v1/channels", headers=ada)).json()

    assert [c["name"] for c in listed["items"]] == ["secrets"]
    assert created["myRole"] == "admin"


@pytest.mark.parametrize("second", ["general", "General", "GENERAL"])
async def test_public_names_collide_regardless_of_case(client, ada, second):
    await create(client, ada, "general")

    response = await create(client, ada, second)

    assert response.status_code == 409
    assert response.headers["content-type"] == PROBLEM
    assert response.json()["type"] == "https://collabhub.dev/problems/conflict"


async def test_a_rejected_duplicate_leaves_one_channel(client, ada):
    await create(client, ada, "general")
    await create(client, ada, "General")

    body = (await client.get("/api/v1/channels", headers=ada)).json()

    assert [c["name"] for c in body["items"]] == ["general"]


async def test_the_stored_name_keeps_the_case_it_was_typed_with(client, ada):
    response = await create(client, ada, "Design-Review")

    assert response.json()["name"] == "Design-Review"


async def test_private_channels_may_repeat_a_public_name(client, ada):
    """The unique index is partial — only public names are reserved."""
    assert (await create(client, ada, "general")).status_code == 201
    assert (await create(client, ada, "general", kind="private")).status_code == 201


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("", "A channel name is required."),
        ("   ", "A channel name is required."),
        ("ab", "A channel name must be at least 3 characters."),
        ("a" * 81, "A channel name must be 80 characters or fewer."),
        ("1password", "A channel name must start with a letter."),
        ("-general", "A channel name must start with a letter."),
        ("dev team", "A channel name can only use letters, numbers and hyphens."),
        ("dev_team", "A channel name can only use letters, numbers and hyphens."),
        ("général", "A channel name can only use letters, numbers and hyphens."),
    ],
)
async def test_invalid_names_are_rejected_with_a_reason_per_rule(client, ada, name, expected):
    response = await create(client, ada, name)

    assert response.status_code == 400
    assert response.headers["content-type"] == PROBLEM
    body = response.json()
    assert body["type"] == "https://collabhub.dev/problems/validation-error"
    assert body["detail"] == expected
    # The form puts this against the field; one message per broken rule.
    assert body["errors"]["name"] == [expected]


async def test_a_rejected_name_creates_nothing(client, ada):
    await create(client, ada, "no")

    body = (await client.get("/api/v1/channels", headers=ada)).json()

    assert body["items"] == []


@pytest.mark.parametrize("name", ["general", "team-42", "Design-Review", "a1b"])
async def test_valid_names_are_accepted(client, ada, name):
    assert (await create(client, ada, name)).status_code == 201


async def test_a_name_is_trimmed_before_it_is_stored(client, ada):
    assert (await create(client, ada, "  general  ")).json()["name"] == "general"


async def test_dm_channels_cannot_be_created_through_this_api(client, ada):
    """`kind='dm'` exists in the schema (D8b) but a DM has no name to give."""
    response = await create(client, ada, "general", kind="dm")

    assert response.status_code == 400
    assert response.json()["errors"]["kind"] == ["Must be one of: public, private"]


async def test_archived_channels_are_not_listed(client, ada, engine):
    """Archive is `archived_at`, not `deleted_at` — the read filters on it."""
    created = (await create(client, ada, "general")).json()
    async with engine.begin() as connection:
        await connection.execute(
            text("UPDATE channels SET archived_at = now() WHERE id = :id"),
            {"id": created["id"]},
        )

    listed = (await client.get("/api/v1/channels", headers=ada)).json()
    detail = await client.get(f"/api/v1/channels/{created['id']}", headers=ada)

    assert listed["items"] == []
    assert detail.status_code == 404


async def test_an_unknown_channel_is_a_404(client, ada):
    response = await client.get(f"/api/v1/channels/{uuid.uuid4()}", headers=ada)

    assert response.status_code == 404


async def test_a_malformed_cursor_is_a_400(client, ada):
    response = await client.get("/api/v1/channels", params={"cursor": "not-a-cursor"}, headers=ada)

    assert response.status_code == 400
    assert response.json()["errors"]["cursor"] == ["Malformed cursor"]


async def test_a_limit_over_the_maximum_is_a_400(client, ada):
    response = await client.get("/api/v1/channels", params={"limit": 500}, headers=ada)

    assert response.status_code == 400


async def test_channels_require_a_token(client):
    assert (await client.get("/api/v1/channels")).status_code == 401
    assert (await client.post("/api/v1/channels", json={"name": "general"})).status_code == 401


async def test_a_service_token_cannot_use_a_user_endpoint(client, tokens):
    """The audience split is what keeps internal callers off this surface."""
    headers = tokens.header(aud="collabhub-internal", sub="service:worker")

    assert (await client.get("/api/v1/channels", headers=headers)).status_code == 401


# --- rename and archive (slice 2) -----------------------------------------


async def patch(client, headers, channel, **body):
    return await client.patch(
        f"/api/v1/channels/{channel['id']}",
        json={"version": channel["version"], **body},
        headers=headers,
    )


async def test_an_admin_renames_a_channel(client, ada):
    created = (await create(client, ada, "general")).json()

    response = await patch(client, ada, created, name="general-chat")

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "general-chat"
    # The version the next edit has to send back.
    assert body["version"] == created["version"] + 1
    # `updated_at` has a server default and no `onupdate`, so a rename that did
    # not set it explicitly would leave the column reading as the creation time.
    assert body["updatedAt"] > body["createdAt"]


async def test_a_rename_is_what_the_next_read_returns(client, ada, grace):
    created = (await create(client, ada, "general")).json()

    await patch(client, ada, created, name="general-chat")

    listed = (await client.get("/api/v1/channels", headers=grace)).json()
    assert [c["name"] for c in listed["items"]] == ["general-chat"]


async def test_a_stale_version_is_a_conflict(client, ada):
    created = (await create(client, ada, "general")).json()
    assert (await patch(client, ada, created, name="general-chat")).status_code == 200

    # `created` still carries version 0, which is now the version nobody holds.
    response = await patch(client, ada, created, name="something-else")

    assert response.status_code == 409
    assert response.json()["type"] == "https://collabhub.dev/problems/conflict"


async def test_renaming_onto_a_taken_name_is_a_conflict_whatever_its_case(client, ada):
    await create(client, ada, "general")
    other = (await create(client, ada, "random")).json()

    response = await patch(client, ada, other, name="GENERAL")

    assert response.status_code == 409
    listed = (await client.get("/api/v1/channels", headers=ada)).json()
    assert sorted(c["name"] for c in listed["items"]) == ["general", "random"]


async def test_a_rename_is_held_to_the_same_naming_rules_as_a_create(client, ada):
    created = (await create(client, ada, "general")).json()

    response = await patch(client, ada, created, name="dev team")

    assert response.status_code == 400
    assert response.json()["errors"]["name"] == [
        "A channel name can only use letters, numbers and hyphens."
    ]


async def test_a_topic_can_be_set_and_cleared(client, ada):
    created = (await create(client, ada, "general")).json()

    with_topic = (await patch(client, ada, created, topic="Ship it")).json()
    assert with_topic["topic"] == "Ship it"

    # An explicit null clears; an absent `topic` leaves it alone.
    unchanged = (await patch(client, ada, with_topic, name="general-chat")).json()
    assert unchanged["topic"] == "Ship it"

    cleared = (await patch(client, ada, unchanged, topic=None)).json()
    assert cleared["topic"] is None


async def test_a_non_admin_cannot_rename_a_channel_they_can_see(client, ada, grace):
    """403 and not 404: `#general` is public, so Grace can already read it.

    The SPA never makes this request — it hides the control from anyone whose
    `myRole` is not `admin` — which is exactly why the rule is held here.
    """
    created = (await create(client, ada, "general")).json()

    response = await patch(client, grace, created, name="hijacked")

    assert response.status_code == 403
    assert response.json()["type"] == "https://collabhub.dev/problems/forbidden"


async def test_a_non_member_renaming_a_private_channel_gets_a_404(client, ada, grace):
    created = (await create(client, ada, "secrets", kind="private")).json()

    response = await patch(client, grace, created, name="hijacked")

    # Never 403 here: that would confirm the channel exists.
    assert response.status_code == 404


async def test_an_admin_archives_a_channel_and_it_leaves_the_list(client, ada):
    created = (await create(client, ada, "general")).json()

    response = await client.delete(f"/api/v1/channels/{created['id']}", headers=ada)

    assert response.status_code == 200
    assert response.json()["archivedAt"] is not None
    assert (await client.get("/api/v1/channels", headers=ada)).json()["items"] == []
    assert (await client.get(f"/api/v1/channels/{created['id']}", headers=ada)).status_code == 404


async def test_archiving_twice_is_a_404(client, ada):
    """Archiving is one-way and every read filters it out, including this one."""
    created = (await create(client, ada, "general")).json()
    assert (
        await client.delete(f"/api/v1/channels/{created['id']}", headers=ada)
    ).status_code == 200

    response = await client.delete(f"/api/v1/channels/{created['id']}", headers=ada)

    assert response.status_code == 404


async def test_archiving_does_not_free_the_name(client, ada):
    """`ux_channels_public_name` covers every public row, archived or not.

    So a name is spent once and for all: archiving `#general` does not let
    anyone create a second one. Asserted rather than assumed, because it is the
    surprising half of "archiving is one-way" and the thing a later slice would
    otherwise change by accident.
    """
    created = (await create(client, ada, "general")).json()
    await client.delete(f"/api/v1/channels/{created['id']}", headers=ada)

    response = await create(client, ada, "general")

    assert response.status_code == 409


async def test_a_non_admin_cannot_archive_a_channel(client, ada, grace):
    created = (await create(client, ada, "general")).json()

    response = await client.delete(f"/api/v1/channels/{created['id']}", headers=grace)

    assert response.status_code == 403
    assert (await client.get("/api/v1/channels", headers=ada)).json()["items"] != []
