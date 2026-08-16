"""Sending and reading messages (spec §3.1).

The rule most of these defend is the one a builder following the design doc
literally would get wrong: **visibility gates reading and writing, membership
gates administration**. Doc 02 §3.1 says "channel member" against these
endpoints, and nothing in this scope lets anyone join a channel themselves — so
a membership guard would make a public channel readable by nobody but its
creator.

The case that discriminates between the two guards is *public plus non-member*:
`get_visible` says yes, `is_member` says no. The private-channel pair is here
too, positive and negative, because that is where the 404-not-403 rule bites.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration

PROBLEM = "application/problem+json"


async def make_channel(client, headers, name="general", **body):
    response = await client.post("/api/v1/channels", json={"name": name, **body}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def send(client, headers, channel_id, body):
    return await client.post(
        f"/api/v1/channels/{channel_id}/messages", json={"body": body}, headers=headers
    )


async def history(client, headers, channel_id, **params):
    return await client.get(
        f"/api/v1/channels/{channel_id}/messages", params=params, headers=headers
    )


async def test_a_sent_message_comes_back_in_the_history(client, ada, tokens):
    channel = await make_channel(client, ada)

    response = await send(client, ada, channel["id"], "morning all")

    assert response.status_code == 201
    created = response.json()
    assert created["body"] == "morning all"
    assert created["authorId"] == str(tokens.ADA)
    assert created["channelId"] == channel["id"]
    assert created["version"] == 0
    assert created["editedAt"] is None
    assert created["deletedAt"] is None
    # Ships as a column with the table; the Asset service is a skeleton.
    assert created["attachments"] == []
    # Threading is register D8a and unbuilt — the column exists, the value does
    # not vary.
    assert created["threadRootId"] is None

    listed = (await history(client, ada, channel["id"])).json()
    assert [m["id"] for m in listed["items"]] == [created["id"]]


async def test_history_is_newest_first(client, ada):
    channel = await make_channel(client, ada)
    for body in ("first", "second", "third"):
        await send(client, ada, channel["id"], body)

    listed = (await history(client, ada, channel["id"])).json()

    # Newest first on the wire. The SPA reverses once, on the way to the DOM.
    assert [m["body"] for m in listed["items"]] == ["third", "second", "first"]
    assert listed["nextCursor"] is None


async def test_a_message_can_be_read_on_its_own(client, ada):
    channel = await make_channel(client, ada)
    created = (await send(client, ada, channel["id"], "morning all")).json()

    response = await client.get(f"/api/v1/messages/{created['id']}", headers=ada)

    assert response.status_code == 200
    assert response.json() == created


async def test_an_unknown_message_is_a_404(client, ada):
    response = await client.get(f"/api/v1/messages/{uuid.uuid4()}", headers=ada)

    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM


@pytest.mark.parametrize("body", ["", "   ", "\n\t  \n"])
async def test_an_empty_message_is_rejected(client, ada, body):
    channel = await make_channel(client, ada)

    response = await send(client, ada, channel["id"], body)

    assert response.status_code == 400
    problem = response.json()
    assert problem["type"] == "https://collabhub.dev/problems/validation-error"
    assert problem["errors"]["body"] == ["A message cannot be empty."]
    assert (await history(client, ada, channel["id"])).json()["items"] == []


async def test_a_message_over_the_limit_is_rejected(client, ada):
    channel = await make_channel(client, ada)

    response = await send(client, ada, channel["id"], "a" * 8001)

    assert response.status_code == 400
    assert response.json()["errors"]["body"] == ["A message must be 8000 characters or fewer."]
    assert (await history(client, ada, channel["id"])).json()["items"] == []


async def test_a_message_at_exactly_the_limit_is_accepted(client, ada):
    channel = await make_channel(client, ada)

    assert (await send(client, ada, channel["id"], "a" * 8000)).status_code == 201


async def test_the_configured_limit_reports_before_the_static_field_bound(ada, client_for):
    """Lowering `MESSAGING_MAX_BODY_CHARS` must change which message is shown.

    `SendMessageRequest.body` also carries a static `max_length`, and it is
    there only to keep an unbounded string out of the domain. If the two ever
    crossed over, the rejection would come from Pydantic with a generic message
    instead of from the domain with the configured number in it — and nothing
    else in the suite would notice.
    """
    async with client_for(messaging_max_body_chars=10) as small:
        channel = await make_channel(small, ada)
        response = await send(small, ada, channel["id"], "a" * 11)

    assert response.status_code == 400
    assert response.json()["errors"]["body"] == ["A message must be 10 characters or fewer."]


async def test_the_body_is_stored_verbatim(client, ada):
    """Markdown is whitespace-sensitive, so unlike a channel name it is not trimmed."""
    channel = await make_channel(client, ada)
    body = "    indented code\n\nand a trailing space  "

    created = (await send(client, ada, channel["id"], body)).json()

    assert created["body"] == body


# --- who may read and write (ruling 12) -----------------------------------


async def test_a_non_member_can_read_and_write_a_public_channel(client, ada, grace, tokens):
    """The case that tells the two possible guards apart.

    `get_visible` says yes and `is_member` says no, so a membership guard would
    pass every other test in this file and fail exactly here — which is the bug
    the whole rule exists to prevent.
    """
    channel = await make_channel(client, ada)
    await send(client, ada, channel["id"], "the eagle has landed")

    posted = await send(client, grace, channel["id"], "shipping this afternoon")
    listed = await history(client, grace, channel["id"])

    assert posted.status_code == 201
    assert listed.status_code == 200
    assert [m["body"] for m in listed.json()["items"]] == [
        "shipping this afternoon",
        "the eagle has landed",
    ]


async def test_posting_does_not_make_you_a_member(client, ada, grace):
    """No implicit join: `myRole` stays null and the admin controls stay hidden.

    Whether posting *should* join you is a product question, and answering it
    here by accident is what this asserts against.
    """
    channel = await make_channel(client, ada)
    await send(client, grace, channel["id"], "shipping this afternoon")

    assert (await client.get(f"/api/v1/channels/{channel['id']}", headers=grace)).json()[
        "myRole"
    ] is None


async def test_a_member_can_read_and_write_a_private_channel(client, ada, grace, tokens):
    channel = await make_channel(client, ada, "launch-plans", kind="private")
    await client.post(
        f"/api/v1/channels/{channel['id']}/members",
        json={"userId": str(tokens.GRACE)},
        headers=ada,
    )

    posted = await send(client, grace, channel["id"], "ship on friday")

    assert posted.status_code == 201
    assert (await history(client, grace, channel["id"])).status_code == 200


async def test_a_non_member_cannot_read_or_write_a_private_channel(client, ada, grace):
    channel = await make_channel(client, ada, "launch-plans", kind="private")
    await send(client, ada, channel["id"], "ship on friday")

    posted = await send(client, grace, channel["id"], "who let me in")
    listed = await history(client, grace, channel["id"])

    # 404 and not 403 — a 403 would confirm the channel is there.
    assert posted.status_code == 404
    assert listed.status_code == 404
    assert listed.headers["content-type"] == PROBLEM
    assert (await history(client, ada, channel["id"])).json()["items"][0][
        "body"
    ] == "ship on friday"


async def test_a_message_in_a_private_channel_is_not_readable_by_id(client, ada, grace):
    """The message id is not an oracle: same 404, same wording, as an absent one."""
    channel = await make_channel(client, ada, "launch-plans", kind="private")
    created = (await send(client, ada, channel["id"], "ship on friday")).json()

    hidden = await client.get(f"/api/v1/messages/{created['id']}", headers=grace)
    absent = await client.get(f"/api/v1/messages/{uuid.uuid4()}", headers=grace)

    assert hidden.status_code == absent.status_code == 404
    assert hidden.json()["detail"] == absent.json()["detail"]


async def test_an_archived_channels_messages_are_unreachable(client, ada):
    """Deliberate, and a consequence of archiving going through `get_visible`."""
    channel = await make_channel(client, ada)
    created = (await send(client, ada, channel["id"], "morning all")).json()
    await client.delete(f"/api/v1/channels/{channel['id']}", headers=ada)

    assert (await history(client, ada, channel["id"])).status_code == 404
    assert (await send(client, ada, channel["id"], "anyone there")).status_code == 404
    assert (await client.get(f"/api/v1/messages/{created['id']}", headers=ada)).status_code == 404


# --- the tombstone read path ----------------------------------------------


async def test_a_deleted_row_reads_back_redacted(client, ada, engine):
    """The read path ships complete a slice before anything can delete.

    Arranged with raw SQL because no endpoint can set `deleted_at` yet. When the
    delete arrives it adds a write and changes nothing here — which is the point
    of shipping the redaction now.
    """
    channel = await make_channel(client, ada)
    created = (await send(client, ada, channel["id"], "wrong channel, sorry")).json()
    async with engine.begin() as connection:
        await connection.execute(
            text("UPDATE messages SET deleted_at = now() WHERE id = :id"),
            {"id": created["id"]},
        )

    listed = (await history(client, ada, channel["id"])).json()

    # Still in the history — a tombstone a reload erases is not a tombstone.
    assert len(listed["items"]) == 1
    tombstone = listed["items"][0]
    assert tombstone["id"] == created["id"]
    # Empty string and never null: the DTO types `body` non-null, so a null
    # would force a check at every render site in the SPA.
    assert tombstone["body"] == ""
    assert tombstone["deletedAt"] is not None

    single = (await client.get(f"/api/v1/messages/{created['id']}", headers=ada)).json()
    assert single["body"] == ""


# --- the usual guards ------------------------------------------------------


async def test_messages_require_a_token(client, ada):
    channel = await make_channel(client, ada)

    assert (await client.get(f"/api/v1/channels/{channel['id']}/messages")).status_code == 401
    assert (
        await client.post(f"/api/v1/channels/{channel['id']}/messages", json={"body": "hi"})
    ).status_code == 401


async def test_an_unknown_channel_is_a_404(client, ada):
    assert (await history(client, ada, uuid.uuid4())).status_code == 404
    assert (await send(client, ada, uuid.uuid4(), "hello?")).status_code == 404


# --- edit and delete (slice 4) ---------------------------------------------


async def edit(client, headers, message, body, version=None):
    return await client.patch(
        f"/api/v1/messages/{message['id']}",
        json={"body": body, "version": message["version"] if version is None else version},
        headers=headers,
    )


async def remove(client, headers, message):
    return await client.delete(f"/api/v1/messages/{message['id']}", headers=headers)


async def test_the_author_edits_their_own_message(client, ada):
    channel = await make_channel(client, ada)
    created = (await send(client, ada, channel["id"], "the eagle has landed")).json()

    response = await edit(client, ada, created, "the eagle has landed safely")

    assert response.status_code == 200
    edited = response.json()
    assert edited["body"] == "the eagle has landed safely"
    # The marker the UI reads, and the version the next edit has to send back.
    assert edited["editedAt"] is not None
    assert edited["version"] == created["version"] + 1

    listed = (await history(client, ada, channel["id"])).json()
    assert listed["items"][0]["body"] == "the eagle has landed safely"


async def test_an_edit_that_changes_nothing_still_bumps_the_version(client, ada):
    """No dirty-check.

    `version` feeds the Elasticsearch external version, which wants to move
    forward monotonically — and a no-op edit is not worth a special case.
    """
    channel = await make_channel(client, ada)
    created = (await send(client, ada, channel["id"], "unchanged")).json()

    edited = (await edit(client, ada, created, "unchanged")).json()

    assert edited["version"] == created["version"] + 1
    assert edited["editedAt"] is not None


async def test_a_non_author_cannot_edit(client, ada, grace):
    channel = await make_channel(client, ada)
    created = (await send(client, ada, channel["id"], "the eagle has landed")).json()

    response = await edit(client, grace, created, "the pigeon has landed")

    # 403 and not 404: Grace can see this message, so refusing the edit tells
    # her nothing the history did not.
    assert response.status_code == 403
    assert response.json()["type"] == "https://collabhub.dev/problems/forbidden"
    assert "author" in response.json()["detail"].lower()


async def test_a_channel_admin_cannot_edit_someone_elses_message(client, ada, grace):
    """Admins delete, they do not edit.

    Deleting someone's words is moderation; rewriting them under their name is
    forgery, and no role on this platform can do it.
    """
    channel = await make_channel(client, ada)
    graces = (await send(client, grace, channel["id"], "shipping this afternoon")).json()

    response = await edit(client, ada, graces, "shipping never")

    assert response.status_code == 403


async def test_an_edit_with_a_stale_version_is_a_conflict(client, ada):
    channel = await make_channel(client, ada)
    created = (await send(client, ada, channel["id"], "first")).json()
    assert (await edit(client, ada, created, "second")).status_code == 200

    response = await edit(client, ada, created, "third")

    assert response.status_code == 409
    assert response.json()["type"] == "https://collabhub.dev/problems/conflict"
    assert (await history(client, ada, channel["id"])).json()["items"][0]["body"] == "second"


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("   ", "A message cannot be empty."),
        ("a" * 8001, "A message must be 8000 characters or fewer."),
    ],
)
async def test_an_edit_is_held_to_the_same_body_rules_as_a_send(client, ada, body, expected):
    channel = await make_channel(client, ada)
    created = (await send(client, ada, channel["id"], "the eagle has landed")).json()

    response = await edit(client, ada, created, body)

    assert response.status_code == 400
    assert response.json()["errors"]["body"] == [expected]


async def test_editing_a_deleted_message_is_a_conflict(client, ada):
    """409 and not 404 — the tombstone is right there in the history."""
    channel = await make_channel(client, ada)
    created = (await send(client, ada, channel["id"], "wrong channel, sorry")).json()
    tombstone = (await remove(client, ada, created)).json()

    response = await edit(client, ada, tombstone, "actually the right channel")

    assert response.status_code == 409
    assert "deleted" in response.json()["detail"].lower()


async def test_the_author_deletes_their_own_message(client, ada, engine):
    channel = await make_channel(client, ada)
    created = (await send(client, ada, channel["id"], "wrong channel, sorry")).json()

    response = await remove(client, ada, created)

    assert response.status_code == 200
    tombstone = response.json()
    assert tombstone["body"] == ""
    assert tombstone["deletedAt"] is not None
    assert tombstone["version"] == created["version"] + 1

    # Still in the history, redacted — that is what a tombstone is.
    listed = (await history(client, ada, channel["id"])).json()
    assert [m["body"] for m in listed["items"]] == [""]
    assert (await client.get(f"/api/v1/messages/{created['id']}", headers=ada)).json()["body"] == ""


async def test_delete_redacts_on_the_way_out_and_never_clears_the_row(client, ada, engine):
    """Asserted against the database, because the API cannot show the difference.

    Blanking the column would look tidy, change nothing visible, and destroy
    data silently. Hard deletion belongs to a retention job whose window is
    still an open decision, and nothing in this scope may pre-empt it.
    """
    channel = await make_channel(client, ada)
    created = (await send(client, ada, channel["id"], "wrong channel, sorry")).json()

    await remove(client, ada, created)

    async with engine.connect() as connection:
        stored = await connection.scalar(
            text("SELECT body FROM messages WHERE id = :id"), {"id": created["id"]}
        )
    assert stored == "wrong channel, sorry"


async def test_deleting_twice_changes_nothing_the_second_time(client, ada):
    channel = await make_channel(client, ada)
    created = (await send(client, ada, channel["id"], "wrong channel, sorry")).json()

    first = (await remove(client, ada, created)).json()
    second = await remove(client, ada, created)

    assert second.status_code == 200
    # Same timestamp and same version: no second bump for a row that did not
    # change, which is what idempotent has to mean here.
    assert second.json() == first


async def test_a_channel_admin_deletes_another_users_message(client, ada, grace):
    """The interesting case: Grace posted without ever joining the channel.

    Visibility is what let her write, and being the channel's admin is what lets
    Ada moderate it.
    """
    channel = await make_channel(client, ada)
    graces = (await send(client, grace, channel["id"], "buy my newsletter")).json()

    response = await remove(client, ada, graces)

    assert response.status_code == 200
    assert response.json()["deletedAt"] is not None


async def test_a_non_admin_cannot_delete_someone_elses_message(client, ada, grace):
    channel = await make_channel(client, ada)
    created = (await send(client, ada, channel["id"], "the eagle has landed")).json()

    response = await remove(client, grace, created)

    assert response.status_code == 403
    assert (await history(client, ada, channel["id"])).json()["items"][0]["body"] == (
        "the eagle has landed"
    )


async def test_an_edited_then_deleted_message_keeps_both_timestamps(client, ada):
    """The client renders the tombstone from `deletedAt` and shows no edited marker.

    "This message was deleted (edited)" is not a thing anyone needs to read, so
    the rule lives in the client — the row keeps the honest record.
    """
    channel = await make_channel(client, ada)
    created = (await send(client, ada, channel["id"], "first")).json()
    edited = (await edit(client, ada, created, "second")).json()

    tombstone = (await remove(client, ada, edited)).json()

    assert tombstone["editedAt"] == edited["editedAt"]
    assert tombstone["deletedAt"] is not None


async def test_archiving_a_channel_freezes_its_messages(client, ada):
    """Not the author, not the admin, nobody — and there is no way back.

    A consequence of every read going through the channel visibility query, and
    the right default for an archive. Worth a test because it is the kind of
    thing that becomes a support ticket.
    """
    channel = await make_channel(client, ada)
    created = (await send(client, ada, channel["id"], "the eagle has landed")).json()
    await client.delete(f"/api/v1/channels/{channel['id']}", headers=ada)

    assert (await edit(client, ada, created, "too late")).status_code == 404
    assert (await remove(client, ada, created)).status_code == 404


async def test_editing_a_message_in_an_invisible_channel_is_a_404(client, ada, grace):
    """404 before 403: asking "are you the author?" first would leak the row."""
    channel = await make_channel(client, ada, "launch-plans", kind="private")
    created = (await send(client, ada, channel["id"], "ship on friday")).json()

    assert (await edit(client, grace, created, "ship never")).status_code == 404
    assert (await remove(client, grace, created)).status_code == 404
