"""Step definitions for phone_layout.feature.

Named `test_*` for the reason the other step modules give: `scenarios()` generates
its test functions into this module, and a module pytest does not collect is a
feature file that silently never runs.

**`ada` is overridden here**: Ada is on a 390 by 844 phone with touch
(`ada_phone_context`), and her `ChatPage` taps, and opens the drawer wherever a
step needs the sidebar. Grace is the shared desktop one. The phrases the journey
shares with other features (`Ada has created …`, `Ada opens the … channel`,
`Ada reacts to …`, `Ada replies … in the thread on …`, the `Grace sees …` pair and
`Grace has sent "…" in "…"`) are in `steps/conftest.py`.

The tour is an act and the check is a `Then`: a `Then` never performs an action. The
`When` keeps its answer in `tour`, a function-scoped fixture, so one scenario's
result cannot reach the next, and the `Then` only reads it. A `When` that never
ran leaves no `"result"` key, which is a `KeyError` — not a pass.

No selectors. A step says what a person did; `pages/chat_page.py` knows what to
tap.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from playwright.sync_api import BrowserContext
from pytest_bdd import given, parsers, scenarios, then, when

from bdd.pages.chat_page import ChatPage
from bdd.steps.conftest import GRACE_NAME

pytestmark = pytest.mark.bdd

scenarios("../features/phone_layout.feature")


# --- fixtures -------------------------------------------------------------


@pytest.fixture
def ada(ada_phone_context: BrowserContext, base_url: str) -> Iterator[ChatPage]:
    """Ada on a phone — see the module docstring."""
    page = ada_phone_context.new_page()
    yield ChatPage(page, base_url, touch=True, phone=True)
    page.close()


@pytest.fixture
def tour() -> dict[str, Any]:
    """What the 360px tour found; empty until the `When` has run."""
    return {}


@pytest.fixture
def filler() -> dict[str, int]:
    """How many filler messages this scenario has sent, so no body repeats."""
    return {"sent": 0}


# --- given ----------------------------------------------------------------


@given(parsers.parse('Grace has sent {count:d} messages in "{channel}"'))
def grace_has_sent_many(grace: ChatPage, filler: dict[str, int], count: int, channel: str) -> None:
    """Grace fills the channel from a window already in its room.

    Enough rows that the list scrolls: the journey's last-but-one check needs a
    position that is neither the top nor the bottom.
    """
    grace.open()
    grace.open_channel(channel)
    grace.wait_for_channel_joined()
    for _ in range(count):
        filler["sent"] += 1
        grace.send_message_and_wait(f"filler message {filler['sent']:03d}")


# --- when -----------------------------------------------------------------


@when("Ada goes Back")
def ada_goes_back(ada: ChatPage) -> None:
    ada.go_back()


@when("Ada visits every screen at 360 wide")
def ada_visits_every_screen(
    ada: ChatPage, signed_out_context: BrowserContext, tour: dict[str, Any]
) -> None:
    tour["result"] = ada.sideways_tour_at_360(signed_out_context, dm_partner=GRACE_NAME)


# --- then -----------------------------------------------------------------


@then(parsers.parse('Ada sees the "{name}" channel where she left it'))
def ada_sees_where_left(ada: ChatPage, name: str) -> None:
    assert ada.is_where_left(name)


@then("none of them scrolls sideways")
def none_scrolls_sideways(tour: dict[str, Any]) -> None:
    assert tour["result"] == {}, f"these scroll sideways at 360px: {tour['result']}"
