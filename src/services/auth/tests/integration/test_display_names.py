"""Renaming yourself, and the names being unique (gh-5, issue Req 1 to 3).

`PATCH /users/me` trims and NFC-normalises, refuses what Req 1 lists with a 400 on
`displayName`, and answers a name that is taken with a 409 that names nobody. The
uniqueness is the database's: the races at the bottom hold one transaction open
while another waits on it, because a check made before the insert cannot see a
row that is not committed yet.

Special characters are built with `chr()`, never typed.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest
from sqlalchemy import select, text

from auth.identities import provision_user
from auth.models import User
from testkit import dexflow
from testkit.dex import ADA, ALAN, DEX_PASSWORD, GRACE

TAKEN = "That name is already taken."
REQUIRED = "A display name is required."
INVISIBLE = "A display name can't contain invisible or control characters."

ZWSP = chr(0x200B)
HANGUL_FILLER = chr(0x3164)
CGJ = chr(0x034F)
NBSP = "\xa0"
ACUTE = chr(0x0301)
JOSE = "Jos\xe9"  # precomposed
JOSE_DECOMPOSED = "Jose" + ACUTE


async def sign_in(client: httpx.AsyncClient, email: str = ADA) -> dict[str, Any]:
    return await dexflow.sign_in(client, email=email, password=DEX_PASSWORD)


def bearer(tokens: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['accessToken']}"}


async def me(client: httpx.AsyncClient, tokens: dict[str, Any]) -> dict[str, Any]:
    return (await client.get("/api/v1/users/me", headers=bearer(tokens))).json()


async def rename(client: httpx.AsyncClient, tokens: dict[str, Any], name: Any) -> httpx.Response:
    return await client.patch(
        "/api/v1/users/me", headers=bearer(tokens), json={"displayName": name}
    )


async def delete_account(sessions, email: str) -> None:
    async with sessions() as session:
        await session.execute(
            text("UPDATE users SET deleted_at = now() WHERE email = :email"), {"email": email}
        )
        await session.commit()


async def user_row(sessions, email: str) -> dict[str, Any]:
    async with sessions() as session:
        result = await session.execute(
            text("SELECT version, updated_at, display_name FROM users WHERE email = :e"),
            {"e": email},
        )
        return dict(result.mappings().one())


async def wait_for_a_blocked_backend(sessions, task: asyncio.Task, seconds: float = 3.0) -> bool:
    """Whether some backend is waiting on a lock within `seconds`, or `task` ends first.

    The holder of an open transaction must not commit until the other side is really
    waiting on it, or the race was never run. At red nothing waits (there is no
    index to wait on), so this gives up and the test fails on its assertion.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + seconds
    while loop.time() < deadline and not task.done():
        async with sessions() as session:
            waiting = (
                await session.execute(
                    text(
                        "SELECT count(*) FROM pg_stat_activity "
                        "WHERE datname = current_database() AND wait_event_type = 'Lock'"
                    )
                )
            ).scalar_one()
        if waiting:
            return True
        await asyncio.sleep(0.05)
    return False


# --------------------------------------------------------------------------
# Req 1 - what is stored, what is refused
# --------------------------------------------------------------------------


async def test_a_name_is_stored_trimmed_and_composed(client: httpx.AsyncClient) -> None:
    """Without trimming and NFC, `  Jose` + U+0301 is stored as typed."""
    tokens = await sign_in(client)

    resp = await rename(client, tokens, "  " + JOSE_DECOMPOSED + "  ")

    assert resp.status_code == 200
    assert resp.json()["displayName"] == JOSE
    assert (await me(client, tokens))["displayName"] == JOSE


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("Grace" + ZWSP, INVISIBLE),
        ("Grace" + HANGUL_FILLER, INVISIBLE),
        ("Gr" + CGJ + "ace", INVISIBLE),
        ("Grace\x07", INVISIBLE),
        (NBSP, REQUIRED),
    ],
    ids=["zwsp", "hangul-filler", "cgj", "bell", "nbsp-only"],
)
async def test_a_refused_name_is_400_on_display_name_and_changes_nothing(
    client: httpx.AsyncClient, raw: str, message: str
) -> None:
    tokens = await sign_in(client)

    resp = await rename(client, tokens, raw)

    assert resp.status_code == 400
    assert resp.json()["errors"]["displayName"] == [message]
    assert (await me(client, tokens))["displayName"] == "ada"


@pytest.mark.parametrize(
    ("raw", "stored"),
    [
        (JOSE, JOSE),
        (JOSE_DECOMPOSED, JOSE),
        ("Zo\xeb", "Zo\xeb"),
        ("李小龍", "李小龍"),
        ("O'Brien", "O'Brien"),
        ("Ada  Lovelace", "Ada  Lovelace"),
    ],
    ids=["precomposed", "decomposed", "diaeresis", "cjk", "apostrophe", "inner-spaces"],
)
async def test_every_accepted_example_is_stored(
    client: httpx.AsyncClient, raw: str, stored: str
) -> None:
    tokens = await sign_in(client)

    resp = await rename(client, tokens, raw)

    assert resp.status_code == 200, resp.text
    assert resp.json()["displayName"] == stored
    assert (await me(client, tokens))["displayName"] == stored


async def test_a_100_character_name_with_spaces_is_kept_and_101_refused(
    client: httpx.AsyncClient,
) -> None:
    """The limit counts the stored form: the padding around 100 characters is not one."""
    tokens = await sign_in(client)

    fits = await rename(client, tokens, " " + "a" * 100 + " ")
    assert fits.status_code == 200, fits.text
    assert fits.json()["displayName"] == "a" * 100

    too_long = await rename(client, tokens, "b" * 101)
    assert too_long.status_code == 400
    assert too_long.json()["errors"]["displayName"] == [
        "A display name can be at most 100 characters."
    ]
    assert (await me(client, tokens))["displayName"] == "a" * 100


async def test_saving_the_name_you_have_changes_nothing(
    client: httpx.AsyncClient, sessions
) -> None:
    """A re-save is a 200 that writes nothing: `version` and `updated_at` stay put."""
    tokens = await sign_in(client)
    before = await user_row(sessions, ADA)

    same = await rename(client, tokens, "ada")
    padded = await rename(client, tokens, "  ada ")

    assert same.status_code == 200
    assert padded.status_code == 200
    assert same.json()["displayName"] == "ada"
    after = await user_row(sessions, ADA)
    assert after["version"] == before["version"]
    assert after["updated_at"] == before["updated_at"]

    # The other side: a real rename does write.
    changed = await rename(client, tokens, "Ada B")
    assert changed.status_code == 200
    assert (await user_row(sessions, ADA))["version"] == before["version"] + 1


# --------------------------------------------------------------------------
# Req 2 - unique everywhere
# --------------------------------------------------------------------------


async def test_a_taken_name_is_409_naming_nobody(client: httpx.AsyncClient) -> None:
    ada, grace = await sign_in(client, ADA), await sign_in(client, GRACE)
    graces_id = (await me(client, grace))["id"]

    resp = await rename(client, ada, "GRACE")

    assert resp.status_code == 409
    body = resp.json()
    assert body["detail"] == TAKEN
    assert body["errors"] == {"displayName": [TAKEN]}
    assert "grace@" not in resp.text
    assert graces_id not in resp.text
    assert "Workspace" not in resp.text
    assert (await me(client, ada))["displayName"] == "ada"

    # And a name nobody holds is fine, so the 409 is about the name.
    assert (await rename(client, ada, "Ada B")).status_code == 200


async def test_a_refused_rename_changes_nothing_else_in_the_request(
    client: httpx.AsyncClient,
) -> None:
    """A 409 on the name leaves the avatar sent beside it unset."""
    ada, _grace = await sign_in(client, ADA), await sign_in(client, GRACE)

    resp = await client.patch(
        "/api/v1/users/me",
        headers=bearer(ada),
        json={"displayName": "grace", "avatarAsset": "6f9619ff-8b86-d011-b42d-00c04fc964ff"},
    )

    assert resp.status_code == 409
    profile = await me(client, ada)
    assert profile["displayName"] == "ada"
    assert profile["avatarAsset"] is None


async def test_names_that_differ_only_in_normal_form_collide(client: httpx.AsyncClient) -> None:
    ada, grace = await sign_in(client, ADA), await sign_in(client, GRACE)
    assert (await rename(client, ada, JOSE)).status_code == 200

    for variant in ("jos\xe9", "JOSE" + ACUTE, "JOS\xc9", JOSE_DECOMPOSED):
        resp = await rename(client, grace, variant)
        assert resp.status_code == 409, variant
        assert resp.json()["errors"]["displayName"] == [TAKEN]

    assert (await me(client, grace))["displayName"] == "grace"


async def test_changing_only_your_own_capitals_is_allowed(client: httpx.AsyncClient) -> None:
    ada, grace = await sign_in(client, ADA), await sign_in(client, GRACE)

    own = await rename(client, ada, "ADA")
    assert own.status_code == 200
    assert own.json()["displayName"] == "ADA"

    # The same request from another user is a collision.
    other = await rename(client, grace, "ADA")
    assert other.status_code == 409
    assert (await me(client, grace))["displayName"] == "grace"


async def test_a_deleted_accounts_name_stays_taken(client: httpx.AsyncClient, sessions) -> None:
    ada, _grace = await sign_in(client, ADA), await sign_in(client, GRACE)
    await delete_account(sessions, GRACE)

    taken = await rename(client, ada, "grace")
    assert taken.status_code == 409
    assert taken.json()["detail"] == TAKEN

    assert (await rename(client, ada, "Grace Hopper")).status_code == 200


async def test_two_renames_to_one_name_at_once_one_wins(
    client: httpx.AsyncClient, sessions
) -> None:
    """The database never holds two, whichever request commits first."""
    grace, alan = await sign_in(client, GRACE), await sign_in(client, ALAN)

    first, second = await asyncio.gather(rename(client, grace, "Sam"), rename(client, alan, "Sam"))

    assert sorted([first.status_code, second.status_code]) == [200, 409]
    async with sessions() as session:
        holders = (
            await session.execute(text("SELECT count(*) FROM users WHERE display_name_key = 'sam'"))
        ).scalar_one()
    assert holders == 1


async def test_a_rename_racing_an_uncommitted_first_sign_in(
    client: httpx.AsyncClient, sessions
) -> None:
    """A check before the write cannot see a first sign-in that has not committed.

    The holder has provisioned "Sam" and not committed. Grace's rename to "Sam"
    must wait for it: 409 when the holder commits, 200 when it rolls back.
    """
    grace = await sign_in(client, GRACE)

    committed = await _rename_while_a_sign_in_is_open(client, sessions, grace, commit=True)
    assert committed[0].status_code == 409, committed[0].text
    assert committed[0].json()["detail"] == TAKEN
    assert committed[1], "Grace's rename never waited on the open sign-in"
    assert (await user_row(sessions, GRACE))["display_name"] == "grace"


async def test_a_rename_waits_out_a_first_sign_in_that_rolls_back(
    client: httpx.AsyncClient, sessions
) -> None:
    grace = await sign_in(client, GRACE)

    rolled_back = await _rename_while_a_sign_in_is_open(client, sessions, grace, commit=False)

    assert rolled_back[0].status_code == 200, rolled_back[0].text
    assert rolled_back[1], "Grace's rename never waited on the open sign-in"
    assert (await user_row(sessions, GRACE))["display_name"] == "Sam"


async def _rename_while_a_sign_in_is_open(
    client: httpx.AsyncClient, sessions, tokens: dict[str, Any], *, commit: bool
) -> tuple[httpx.Response, bool]:
    holder = sessions()
    try:
        await provision_user(
            holder, email="newbie@example.com", display_name="Sam", demo_workspace_name=None
        )
        task = asyncio.create_task(rename(client, tokens, "Sam"))
        waited = await wait_for_a_blocked_backend(sessions, task)
        if commit:
            await holder.commit()
        else:
            await holder.rollback()
        return await task, waited
    finally:
        await holder.close()


async def test_a_first_sign_in_racing_an_uncommitted_rename(
    client: httpx.AsyncClient, sessions
) -> None:
    """The mirror: a rename to "Sam" is open, and a first sign-in named "Sam" arrives."""
    await sign_in(client, GRACE)

    committed = await _sign_in_while_a_rename_is_open(client, sessions, commit=True)
    assert committed[0] == "Sam 2"
    assert committed[1], "the first sign-in never waited on the open rename"


async def test_a_first_sign_in_takes_the_name_when_the_rename_rolls_back(
    client: httpx.AsyncClient, sessions
) -> None:
    await sign_in(client, GRACE)

    rolled_back = await _sign_in_while_a_rename_is_open(client, sessions, commit=False)

    assert rolled_back[0] == "Sam"
    assert rolled_back[1], "the first sign-in never waited on the open rename"


async def _sign_in_while_a_rename_is_open(
    client: httpx.AsyncClient, sessions, *, commit: bool
) -> tuple[str, bool]:
    async def first_sign_in() -> str:
        async with sessions.begin() as session:
            user = await provision_user(
                session, email="newbie@example.com", display_name="Sam", demo_workspace_name=None
            )
            return user.display_name

    holder = sessions()
    try:
        grace = (await holder.execute(select(User).where(User.email == GRACE))).scalar_one()
        grace.display_name = "Sam"
        await holder.flush()
        task = asyncio.create_task(first_sign_in())
        waited = await wait_for_a_blocked_backend(sessions, task)
        if commit:
            await holder.commit()
        else:
            await holder.rollback()
        return await task, waited
    finally:
        await holder.close()


# --------------------------------------------------------------------------
# Req 3 - first sign-in
# --------------------------------------------------------------------------


async def test_two_first_sign_ins_with_one_name_both_succeed(sessions) -> None:
    async def sign_up(email: str) -> str:
        async with sessions.begin() as session:
            user = await provision_user(
                session, email=email, display_name="Sam", demo_workspace_name=None
            )
            return user.display_name

    given = await asyncio.gather(sign_up("one@example.com"), sign_up("two@example.com"))

    assert set(given) == {"Sam", "Sam 2"}
    async with sessions() as session:
        stored = (await session.execute(text("SELECT display_name FROM users"))).scalars().all()
    assert sorted(stored) == ["Sam", "Sam 2"]


async def test_a_first_sign_in_with_a_taken_name_takes_the_next_suffix(
    client: httpx.AsyncClient,
) -> None:
    grace, alan = await sign_in(client, GRACE), await sign_in(client, ALAN)
    assert (await rename(client, grace, "ada")).status_code == 200
    assert (await rename(client, alan, "ada 2")).status_code == 200

    ada = await sign_in(client, ADA)

    assert (await me(client, ada))["displayName"] == "ada 3"
    listed = await client.get("/api/v1/workspaces", headers=bearer(ada))
    owned = [w["name"] for w in listed.json()["items"] if w["role"] == "owner"]
    assert owned == ["ada 3's Workspace"]


async def test_an_unusable_idp_name_still_signs_in(sessions) -> None:
    """A name Req 1 would refuse is repaired, not a failed sign-in."""
    async with sessions.begin() as session:
        user = await provision_user(
            session, email="zed@collabhub.dev", display_name=ZWSP, demo_workspace_name=None
        )
        stored = user.display_name

    assert stored == "zed"
    async with sessions() as session:
        workspace = (await session.execute(text("SELECT name FROM workspaces"))).scalar_one()
    assert workspace == "zed's Workspace"


async def test_a_sign_in_never_overwrites_an_existing_name(client: httpx.AsyncClient) -> None:
    """Passes at red: pins the last clause of Req 3."""
    tokens = await sign_in(client, ADA)
    assert (await rename(client, tokens, "Ada L")).status_code == 200

    again = await sign_in(client, ADA)

    assert (await me(client, again))["displayName"] == "Ada L"


async def test_a_rename_leaves_the_workspace_name_alone(client: httpx.AsyncClient) -> None:
    """Passes at red: a workspace's name is not its owner's."""
    tokens = await sign_in(client, ADA)

    assert (await rename(client, tokens, "Ada L")).status_code == 200

    listed = await client.get("/api/v1/workspaces", headers=bearer(tokens))
    owned = [w["name"] for w in listed.json()["items"] if w["role"] == "owner"]
    assert owned == ["ada's Workspace"]
