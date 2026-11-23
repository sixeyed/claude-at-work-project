"""Steps shared by more than one feature file.

pytest-bdd resolves a step from the module that called `scenarios()` and from
`conftest.py` — **not** from a sibling `test_*.py`. So the moment a second
feature file needs `Given Ada is signed in`, the choice is to copy the
definition or to move it down here. Copying is how a suite ends up with four
subtly different versions of its most-used step.

What belongs here is the vocabulary every feature speaks: who is signed in,
which channels exist, what is in whose sidebar. What stays in a
`test_*_steps.py` is the phrasing that feature introduced — adding a member
belongs to `permissions.feature`, dropping the network to `realtime.feature`.

No selectors here either. A step says what a person did; the page object
(`tests/bdd/pages/`) knows what to click.
"""

from __future__ import annotations

from pytest_bdd import given, parsers, then, when

from bdd.pages.chat_page import ChatPage

#: What Auth stores as these accounts' display names.
#:
#: Dex issues its `username` as the name claim and `provision_user` keeps it, so
#: the demo accounts are called "ada" and "grace" rather than "Ada Lovelace".
#: The member panel renders those, and a scenario that adds "Grace" has to pick
#: the option the UI actually shows.
ADA_NAME = "ada"
GRACE_NAME = "grace"


# --- given ----------------------------------------------------------------


@given("Ada is signed in")
def ada_is_signed_in(ada: ChatPage) -> None:
    # The context is signed in for the whole session; this loads the app fresh
    # so each scenario starts from the same place.
    ada.open()


@given(parsers.parse('Ada has created a public channel named "{name}"'))
def ada_has_created(ada: ChatPage, name: str) -> None:
    ada.create_channel_and_wait(name)


@given(parsers.parse('Ada has created a private channel named "{name}"'))
def ada_has_created_private(ada: ChatPage, name: str) -> None:
    ada.create_private_channel_and_wait(name)


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


@when("Grace opens CollabHub")
def grace_opens(grace: ChatPage) -> None:
    grace.open()


@when(parsers.parse('Grace opens the "{name}" channel'))
def grace_opens_channel(grace: ChatPage, name: str) -> None:
    grace.open_channel(name)


# --- then -----------------------------------------------------------------


@then(parsers.parse('Ada is looking at the "{name}" channel'))
def ada_is_looking_at(ada: ChatPage, name: str) -> None:
    assert ada.open_channel_name() == name


@then(parsers.parse('Grace is looking at the "{name}" channel'))
def grace_is_looking_at(grace: ChatPage, name: str) -> None:
    assert grace.open_channel_name() == name


@then(parsers.parse('Ada sees the "{name}" workspace'))
def ada_sees_workspace(ada: ChatPage, name: str) -> None:
    assert ada.workspace_name() == name


@then(parsers.parse('"{name}" is in Ada\'s channel list'))
def in_adas_list(ada: ChatPage, name: str) -> None:
    assert ada.has_channel(name), ada.channel_names()


@then(parsers.parse('"{name}" is not in Ada\'s channel list'))
def not_in_adas_list(ada: ChatPage, name: str) -> None:
    assert ada.lacks_channel(name), ada.channel_names()


@then(parsers.parse('"{name}" is in Grace\'s channel list'))
def in_graces_list(grace: ChatPage, name: str) -> None:
    assert grace.has_channel(name), grace.channel_names()


@then(parsers.parse('"{name}" is not in Grace\'s channel list'))
def not_in_graces_list(grace: ChatPage, name: str) -> None:
    assert grace.lacks_channel(name), grace.channel_names()


@given(parsers.parse('Ada has sent "{body}" in "{channel}"'))
def ada_has_sent(ada: ChatPage, body: str, channel: str) -> None:
    ada.open_channel(channel)
    ada.send_message_and_wait(body)


@when(parsers.parse('Ada opens the "{name}" channel'))
def ada_opens_channel(ada: ChatPage, name: str) -> None:
    ada.open_channel(name)


@when("Ada reloads CollabHub")
def ada_reloads(ada: ChatPage) -> None:
    ada.open()


@when("Grace reloads CollabHub")
def grace_reloads(grace: ChatPage) -> None:
    grace.open()


#: `parsers.re` rather than `parsers.parse`: `parse`'s `{body}` will happily
#: swallow a closing quote, and `[^"]*` cannot cross one, so a later
#: `Ada sends "…" in "…"` phrase cannot be matched by this step by accident.
@when(parsers.re(r'Ada sends "(?P<body>[^"]*)"'))
def ada_sends(ada: ChatPage, body: str) -> None:
    ada.send_message_and_wait(body)


@then(parsers.parse('Ada sees "{body}" in the channel'))
def ada_sees(ada: ChatPage, body: str) -> None:
    assert ada.has_message(body), ada.message_bodies()


@then(parsers.parse('Grace sees "{body}" in the channel'))
def grace_sees(grace: ChatPage, body: str) -> None:
    assert grace.has_message(body), grace.message_bodies()


@then(parsers.parse('Grace sees "{body}" in the channel without reloading'))
def grace_sees_live(grace: ChatPage, body: str) -> None:
    """Grace's page never navigates, so only an inbound event can have put it there."""
    grace.wait_for_message(body)


@then(parsers.parse('"{body}" appears in Ada\'s channel exactly once'))
def appears_once_for_ada(ada: ChatPage, body: str) -> None:
    """The sender receives her own broadcast, and must not render it twice.

    There is no `sid` to skip it by — the write went over REST, which is not a
    socket — so the cache helper has to be idempotent on the message id. A blind
    append passes every other scenario that sends and fails this one.
    """
    assert ada.appears_once(body), ada.count_of(body)


@then(parsers.parse('Ada does not see "{body}" in the channel'))
def ada_does_not_see(ada: ChatPage, body: str) -> None:
    assert ada.is_absent(body), ada.message_bodies()


@then("Ada's message box is empty")
def adas_box_is_empty(ada: ChatPage) -> None:
    assert ada.draft() == ""


@when(parsers.parse('Ada edits "{old}" to say "{new}"'))
def ada_edits(ada: ChatPage, old: str, new: str) -> None:
    ada.edit_message(old, new)


@when(parsers.parse('Ada deletes "{body}"'))
def ada_deletes(ada: ChatPage, body: str) -> None:
    ada.delete_message(body)


# --- reactions and threads, shared with message_actions.feature ------------
#
# These four moved here, unchanged, from `test_reaction_steps.py` and
# `test_thread_steps.py`: pytest-bdd finds a step in the module that called
# `scenarios()` or in `conftest.py`, and `message_actions.feature` speaks the
# same phrases to prove the same journeys on a touch screen.


@when(parsers.parse('Ada reacts to "{body}" with "{emoji}"'))
def ada_reacts(ada: ChatPage, body: str, emoji: str) -> None:
    ada.react_to(body, emoji)


@then(parsers.parse('Grace sees "{body}" with {count:d} "{emoji}" reaction'))
def grace_sees_reaction(grace: ChatPage, body: str, count: int, emoji: str) -> None:
    assert grace.has_reaction_count(body, emoji, count)


@when(parsers.parse('Ada replies "{reply}" in the thread on "{body}"'))
def ada_replies(ada: ChatPage, reply: str, body: str) -> None:
    ada.reply_in_thread(body, reply)


#: `parsers.re`, so "1 reply" and "2 replies" are one phrase and `[^"]*` cannot
#: swallow a closing quote.
@then(parsers.re(r'Grace sees (?P<count>\d+) repl(?:y|ies) on "(?P<body>[^"]*)" without reloading'))
def grace_sees_count(grace: ChatPage, count: str, body: str) -> None:
    assert grace.has_reply_count(body, int(count))
