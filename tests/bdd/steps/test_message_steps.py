"""Step definitions for messages.feature.

Named `test_*` for the reason the other step modules give: `scenarios()`
generates its test functions into this module, and a module pytest does not
collect is a feature file that silently never runs. This is the **only** module
that calls `scenarios()` on `messages.feature` — two would run every scenario
twice.

The shared vocabulary — signing in, creating channels, sending, reading what is
on screen — lives in `steps/conftest.py`, because realtime.feature says most of
the same things. What is here is what this feature introduced and nothing else
uses.

No selectors. A step says what a person did; `pages/chat_page.py` knows what to
click.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from bdd.pages.chat_page import ChatPage
from bdd.steps.conftest import ADA_NAME

pytestmark = pytest.mark.bdd

scenarios("../features/messages.feature")

#: What `seed_history` labels the rows it writes. The oldest is index 000, and
#: the scenarios talk about "the oldest message" rather than about this string.
SEED_PREFIX = "old message"


def _seeded(index: int) -> str:
    return f"{SEED_PREFIX} {index:03d}"


# --- given ----------------------------------------------------------------


@given(parsers.parse('"{channel}" already holds {count:d} earlier messages'))
def channel_holds_history(
    seed_history: Callable[[str, int, str], None], channel: str, count: int
) -> None:
    """Fifty-one messages is where a second page begins, and sixty is past it.

    Seeded straight into Postgres rather than typed into the composer: sixty
    browser round trips to *arrange* a scroll is not a trade worth making, and
    the read path, the cursor and the scroll are all still exercised exactly as
    a person hits them. The write path has its own scenario.
    """
    seed_history(channel, count, SEED_PREFIX)


# --- when -----------------------------------------------------------------


@when("Ada tries to send a message that is nothing but spaces")
def ada_sends_whitespace(ada: ChatPage) -> None:
    ada.send_message_expecting_failure("   ")


@when("Ada scrolls to the top of the history")
def ada_scrolls_up(ada: ChatPage) -> None:
    ada.scroll_history_to_top()


# --- then -----------------------------------------------------------------


@then("Ada is told a message cannot be empty")
def ada_told_empty(ada: ChatPage) -> None:
    assert "empty" in ada.composer_error().lower()


@then(parsers.parse('Ada sees "{body}" written by Ada'))
def ada_sees_author(ada: ChatPage, body: str) -> None:
    assert ada.author_of(body) == ADA_NAME


@then(parsers.parse('Grace sees "{body}" written by Ada'))
def grace_sees_author(grace: ChatPage, body: str) -> None:
    """Grace resolves Ada's name from the workspace directory, not from the message.

    Messaging returns a bare `authorId` — it owns no user records — so a name
    appearing here at all is the browser having joined the two services
    together.
    """
    assert grace.author_of(body) == ADA_NAME


@then(parsers.parse('Ada sees "{body}" with the time it was sent'))
def ada_sees_timestamp(ada: ChatPage, body: str) -> None:
    # The machine-readable instant, not the rendered text: the visible form is
    # in the browser's locale and asserting on it would fail on another laptop.
    stamp = ada.timestamp_of(body)
    assert stamp, "the message carries no timestamp"

    sent = datetime.fromisoformat(stamp)
    assert sent.tzinfo is not None, f"{stamp!r} is not an absolute instant"
    # Sent moments ago, so anything wildly off means the wrong field was read.
    assert abs((datetime.now(UTC) - sent).total_seconds()) < 300


@then(parsers.parse('Ada does not see the oldest message in "{channel}"'))
def ada_cannot_see_oldest(ada: ChatPage, channel: str) -> None:
    assert not ada.has_message(_seeded(0)), "the first page should not reach back that far"


@then(parsers.parse('Ada sees the oldest message in "{channel}"'))
def ada_sees_oldest(ada: ChatPage, channel: str) -> None:
    assert ada.has_message(_seeded(0))


@then(parsers.parse('Ada sees all {count:d} messages in "{channel}"'))
def ada_sees_all(ada: ChatPage, count: int, channel: str) -> None:
    bodies = ada.message_bodies()
    assert len(bodies) == count, f"expected {count} messages, found {len(bodies)}"
    # Neither skipped nor repeated: the property the cursor is there to hold.
    assert len(set(bodies)) == count


# --- edit and delete (slice 4) --------------------------------------------


@given(parsers.parse('Grace has sent "{body}" in "{channel}"'))
def grace_has_sent(grace: ChatPage, body: str, channel: str) -> None:
    """Grace posts without ever joining the channel.

    Visibility is what entitles her to write, not membership — so there is no
    "add Grace to the channel" step here, and its absence is the point.
    """
    grace.open()
    grace.open_channel(channel)
    grace.send_message_and_wait(body)


@then(parsers.parse('Ada sees "{body}" marked as edited'))
def ada_sees_edited_marker(ada: ChatPage, body: str) -> None:
    assert ada.has_edited_marker(body)


@then(parsers.parse('Ada has no way to edit "{body}"'))
def ada_cannot_edit(ada: ChatPage, body: str) -> None:
    """No control is offered — and there is no role that would get one.

    A channel admin may delete somebody's message but never rewrite it: that
    asymmetry is deliberate, and Ada is this channel's admin, so this is the
    case that proves it.
    """
    assert not ada.can_edit(body)


@then(parsers.parse('Grace has no way to delete "{body}"'))
def grace_cannot_delete(grace: ChatPage, body: str) -> None:
    assert not grace.can_delete(body)


@then("Ada sees a deleted message in the channel")
def ada_sees_tombstone(ada: ChatPage) -> None:
    assert ada.has_tombstone()
