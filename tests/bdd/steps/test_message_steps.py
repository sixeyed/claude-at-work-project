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

The body rules, the author and timestamp rendering, pagination and who may edit
or delete are proven lower down (register D32): unit `validate_body` and the
message policy, Messaging's integration tests, and the Vitest `MessageItem`,
`MessageComposer` and `MessageList` tests.

No selectors. A step says what a person did; `pages/chat_page.py` knows what to
click.
"""

from __future__ import annotations

import pytest
from pytest_bdd import parsers, scenarios, then

from bdd.pages.chat_page import ChatPage
from bdd.steps.conftest import ADA_NAME

pytestmark = pytest.mark.bdd

scenarios("../features/messages.feature")


# --- then -----------------------------------------------------------------


@then(parsers.parse('Grace sees "{body}" written by Ada'))
def grace_sees_author(grace: ChatPage, body: str) -> None:
    """Grace resolves Ada's name from the workspace directory, not from the message.

    Messaging returns a bare `authorId` — it owns no user records — so a name
    appearing here at all is the browser having joined the two services
    together.
    """
    assert grace.author_of(body) == ADA_NAME


@then(parsers.parse('Ada sees "{body}" marked as edited'))
def ada_sees_edited_marker(ada: ChatPage, body: str) -> None:
    assert ada.has_edited_marker(body)


@then("Ada sees a deleted message in the channel")
def ada_sees_tombstone(ada: ChatPage) -> None:
    assert ada.has_tombstone()
