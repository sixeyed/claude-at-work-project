"""Step definitions for realtime.feature.

Named `test_*` for the reason the other step modules give: `scenarios()`
generates its test functions into this module, and a module pytest does not
collect is a feature file that silently never runs. This is the only module that
calls `scenarios()` on `realtime.feature`.

The shared vocabulary — signing in, creating channels, sending, editing,
deleting — is in `steps/conftest.py`, and these scenarios reuse it rather than
spelling the same acts a second way. What is here is what "live" adds:
watching a channel, asserting on something that arrived without a reload, and
dropping the network.

**"Without reloading" is a property of the page object, not of a phrase.**
Nothing in these steps navigates or reloads, so a message appearing on Grace's
screen can only have got there over the socket. If a step here ever called
`open()`, the scenario would still pass and would stop testing anything.

Rooms, typing and the optimistic send are proven lower down (register D32):
Messaging's `test_realtime.py` and `test_realtime_writes.py`, and the Vitest
`useChannelSocket`, `useTyping`, `TypingIndicator` and `useSendMessage` tests.
"""

from __future__ import annotations

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from bdd.pages.chat_page import ChatPage

pytestmark = pytest.mark.bdd

scenarios("../features/realtime.feature")


# --- given ----------------------------------------------------------------


@given(parsers.parse('Grace is looking at the "{name}" channel'))
def grace_is_watching(grace: ChatPage, name: str) -> None:
    """Grace opens the channel and waits until she is actually in its room.

    The wait is the point. Without it the scenario races its own arrangement:
    Ada sends, the broadcast goes to a room Grace has not joined yet, and the
    failure looks like "real-time does not work" rather than "the test was
    early". A connected socket is not enough — the join is acknowledged later.
    """
    grace.open()
    grace.open_channel(name)
    grace.wait_for_channel_joined()


# --- when -----------------------------------------------------------------


@when("Grace's network drops")
def graces_network_drops(grace: ChatPage) -> None:
    grace.go_offline()


@when("Grace's network comes back")
def graces_network_returns(grace: ChatPage) -> None:
    grace.go_online()


# --- then -----------------------------------------------------------------


@then(parsers.parse('Grace sees "{body}" in the channel without reloading'))
def grace_sees_live(grace: ChatPage, body: str) -> None:
    grace.wait_for_message(body)


@then("Grace sees a deleted message in the channel without reloading")
def grace_sees_tombstone_live(grace: ChatPage) -> None:
    grace.wait_for_tombstone()


@then(parsers.parse('Grace sees "{body}" marked as edited'))
def grace_sees_edited_marker(grace: ChatPage, body: str) -> None:
    assert grace.has_edited_marker(body)


@then(parsers.parse('Grace does not see "{body}" in the channel'))
def grace_does_not_see(grace: ChatPage, body: str) -> None:
    assert grace.is_absent(body), grace.message_bodies()


@then(parsers.parse('"{body}" appears in Ada\'s channel exactly once'))
def appears_once_for_ada(ada: ChatPage, body: str) -> None:
    """The sender receives her own broadcast, and must not render it twice.

    There is no `sid` to skip it by — the write went over REST, which is not a
    socket — so the cache helper has to be idempotent on the message id. A blind
    append passes every other scenario in this file and fails this one.
    """
    assert ada.count_of(body) == 1


@then("Grace's connection is restored")
def graces_connection_restored(grace: ChatPage) -> None:
    # Restored means back in the room, which is also when the SPA refetches
    # what was said while the connection was down.
    grace.wait_for_channel_joined()
