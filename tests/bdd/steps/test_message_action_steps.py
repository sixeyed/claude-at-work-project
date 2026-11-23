"""Step definitions for message_actions.feature.

Named `test_*` for the reason the other step modules give: `scenarios()` generates
its test functions into this module, and a module pytest does not collect is a
feature file that silently never runs. This is the only module that calls
`scenarios()` on `message_actions.feature`.

**`ada` is overridden here**: Ada is on a 1024 by 768 touchscreen with no hover
(`ada_touch_context`), and her `ChatPage` taps where the others click. The
shared contexts are session-scoped and used by every journey, so changing their
device would change all of them; this module's override replaces `ada` for the
tests it generates and no others. The phrases the journey shares with the
reaction and thread features (`Ada reacts to …`, `Ada replies … in the thread
on …`, and the two `Grace sees …`) are in `steps/conftest.py`.

No selectors. A step says what a person did; `pages/chat_page.py` knows what to
tap.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from playwright.sync_api import BrowserContext
from pytest_bdd import given, parsers, scenarios

from bdd.pages.chat_page import ChatPage

pytestmark = pytest.mark.bdd

scenarios("../features/message_actions.feature")


# --- fixtures -------------------------------------------------------------


@pytest.fixture
def ada(ada_touch_context: BrowserContext, base_url: str) -> Iterator[ChatPage]:
    """Ada on a touch tablet — see the module docstring."""
    page = ada_touch_context.new_page()
    yield ChatPage(page, base_url, touch=True)
    page.close()


# --- given ----------------------------------------------------------------


@given(parsers.re(r'Grace has sent "(?P<body>[^"]*)" in "(?P<channel>[^"]*)"'))
def grace_has_sent(grace: ChatPage, body: str, channel: str) -> None:
    """Grace sends from a window that is already in the channel's room.

    The wait for the join is the point: Ada's reaction and reply are broadcast to
    the room, and a Grace who had not been admitted to it yet would miss them for
    a reason that has nothing to do with message actions.
    """
    grace.open()
    grace.open_channel(channel)
    grace.wait_for_channel_joined()
    grace.send_message_and_wait(body)
