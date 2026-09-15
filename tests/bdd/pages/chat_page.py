"""The chat shell, as the scenarios talk about it.

Every selector in the suite lives in a page object; no step definition contains
one. That is the rule that keeps browser tests from rotting — when a component
is restructured, one file changes rather than twenty.

Selectors are `data-testid` only. Text and CSS classes are things a designer
should be free to change without breaking a test about channels.

Only what a kept journey uses is here. The suite is key journeys only (register
D32), so a method nothing calls is deleted with the scenario that used it.
"""

from __future__ import annotations

from playwright.sync_api import Page, expect


class ChatPage:
    def __init__(self, page: Page, base_url: str) -> None:
        self.page = page
        self.base_url = base_url

    # --- navigation -------------------------------------------------------

    def open(self) -> None:
        """Load the app fresh, as someone arriving would.

        `networkidle` matters here: the session restores from the refresh cookie
        and *then* fetches channels, so a test that looked immediately after
        load would race the list it is about to assert on.
        """
        self.page.goto(self.base_url)
        self.page.wait_for_load_state("networkidle")

    # --- reading ----------------------------------------------------------

    def workspace_name(self) -> str:
        return self.page.get_by_test_id("workspace-name").inner_text()

    def channel_names(self) -> list[str]:
        """Every channel in the sidebar, in the order it is displayed."""
        self._settle()
        items = self.page.get_by_test_id("channel-list-item")
        return [
            (items.nth(i).get_attribute("data-channel-name") or "").strip()
            for i in range(items.count())
        ]

    def open_channel(self, name: str) -> None:
        """Click a channel in the sidebar and wait until it is the open one."""
        self._settle()
        self.page.locator(f"[data-testid='channel-list-item'][data-channel-name='{name}']").click()
        expect(
            self.page.locator(f"[data-testid='channel-view'][data-channel-name='{name}']")
        ).to_be_visible()

    def current_channel_id(self) -> str:
        """The id out of the address bar.

        A URL is not a selector, but it is still the page object's business: a
        step should be able to say "the link to that channel" without knowing
        that channels live at `/c/{id}`.
        """
        return self.page.url.rstrip("/").rsplit("/", 1)[-1]

    def open_channel_by_id(self, channel_id: str) -> None:
        """Follow a link straight to a channel, as someone sent it would."""
        self.page.goto(f"{self.base_url}/c/{channel_id}")
        self.page.wait_for_load_state("networkidle")

    def open_channel_name(self) -> str:
        return self.page.get_by_test_id("channel-header-name").inner_text().lstrip("# ").strip()

    def channel_error(self) -> str:
        """What the open channel is complaining about."""
        error = self.page.get_by_test_id("channel-error")
        error.wait_for(state="visible", timeout=10_000)
        return error.inner_text()

    def _settle(self) -> None:
        """Wait for the channel list to finish its first load.

        The sidebar renders a loading state before either a list or an empty
        message, and reading through it would return an empty list that looks
        exactly like "no channels".
        """
        self.page.get_by_test_id("channel-list-loading").wait_for(state="detached", timeout=10_000)

    # --- creating ---------------------------------------------------------

    def create_channel(self, name: str, kind: str = "public") -> None:
        self.page.get_by_test_id("create-channel-kind").select_option(kind)
        self.page.get_by_test_id("create-channel-name").fill(name)
        self.page.get_by_test_id("create-channel-submit").click()

    def create_channel_and_wait(self, name: str) -> None:
        """Create a channel and wait until the app has navigated into it."""
        self.create_channel(name)
        expect(self.page.get_by_test_id("channel-view")).to_be_visible()

    def create_private_channel_and_wait(self, name: str) -> None:
        self.create_channel(name, kind="private")
        expect(self.page.get_by_test_id("channel-view")).to_be_visible()

    # --- messages ---------------------------------------------------------

    def send_message(self, text: str) -> None:
        """Fill and send.

        The composer is disabled until the socket is up, and `fill` waits for an
        editable element, so this also absorbs the connection race that would
        otherwise need a wait in every sending step.
        """
        self.page.get_by_test_id("message-composer-input").fill(text)
        self.page.get_by_test_id("message-composer-send").click()

    def send_message_and_wait(self, text: str) -> None:
        """Send, and wait until the message is on screen — mirrors create.

        `.first`, because for a moment there are legitimately two: the
        optimistic row and the confirmed one, while the ack is being reconciled.
        A strict locator turns that overlap into a hard failure rather than
        waiting through it — and the overlap is correct behaviour, not the bug.
        """
        self.send_message(text)
        expect(self._message(text).first).to_be_visible()

    def draft(self) -> str:
        return self.page.get_by_test_id("message-composer-input").input_value()

    def message_bodies(self) -> list[str]:
        self._settle_messages()
        bodies = self.page.get_by_test_id("message-body")
        return [(bodies.nth(i).inner_text() or "").strip() for i in range(bodies.count())]

    def has_message(self, text: str) -> bool:
        self._settle_messages()
        return self._message(text).count() > 0

    def author_of(self, text: str) -> str:
        return self._item_for(text).get_by_test_id("message-author").inner_text().strip()

    def edit_message(self, old: str, new: str) -> None:
        """Rewrite a message and wait until the new text is on screen.

        Waiting on the text rather than on the request means the step covers the
        cache write too: an edit the server accepted but the SPA never applied
        would leave the old words showing, and that is worth failing for.
        """
        self._item_for(old).get_by_test_id("message-edit").click()
        editor = self.page.get_by_test_id("message-editor-input")
        editor.fill(new)
        self.page.get_by_test_id("message-editor-save").click()
        expect(self._message(new)).to_be_visible()

    def delete_message(self, text: str) -> None:
        self._item_for(text).get_by_test_id("message-delete").click()
        expect(self.page.get_by_test_id("message-deleted").first).to_be_visible()

    def has_edited_marker(self, text: str) -> bool:
        return self._item_for(text).get_by_test_id("message-edited").count() > 0

    def has_tombstone(self) -> bool:
        self._settle_messages()
        return self.page.get_by_test_id("message-deleted").count() > 0

    def _message(self, text: str):
        return self.page.get_by_test_id("message-body").filter(has_text=text)

    def _item_for(self, text: str):
        return self.page.get_by_test_id("message-item").filter(has_text=text).first

    def _settle_messages(self) -> None:
        """Wait for the history's first load, as `_settle` does for the sidebar.

        Reading through the loading state returns an empty list that looks
        exactly like "no messages".
        """
        self.page.get_by_test_id("message-list-loading").wait_for(state="detached", timeout=10_000)

    # --- live delivery ----------------------------------------------------

    def wait_for_message(self, text: str, timeout: int = 10_000) -> None:
        """Wait for a message to appear on a page nobody navigated.

        This is what "without reloading" means as an assertion: the page object
        never calls `goto` or `reload`, so the only thing that could have put
        the text there is an inbound event.

        `.first` for the same reason `send_message_and_wait` needs it: a
        sender's own window briefly holds the optimistic row and the confirmed
        one at once.
        """
        expect(self._message(text).first).to_be_visible(timeout=timeout)

    def wait_for_tombstone(self, timeout: int = 10_000) -> None:
        expect(self.page.get_by_test_id("message-deleted").first).to_be_visible(timeout=timeout)

    def count_of(self, text: str) -> int:
        """How many times a message is on screen.

        The sender receives its own broadcast — there is no `sid` to skip it by,
        because the REST write is not a socket — so "exactly once" is the
        assertion that a blind append would fail.
        """
        self._settle_messages()
        return self._message(text).count()

    def is_absent(self, text: str) -> bool:
        """Whether a message is *not* on screen, after giving it time to arrive.

        Proving an absence needs a wait, and there is no event to wait for — the
        claim is that nothing happens. So this is the one deliberate pause in
        the suite: long enough that a broadcast on a healthy stack would have
        landed, short enough not to dominate the run.
        """
        self.page.wait_for_timeout(1_000)
        return self._message(text).count() == 0

    def wait_for_connection(self, timeout: int = 30_000) -> None:
        """Wait for the socket to be up.

        Generous, because a reconnect goes through Socket.IO's backoff, and a
        flaky assertion here would be blamed on the feature rather than on the
        wait.
        """
        expect(self.page.get_by_test_id("connection-status")).to_have_attribute(
            "data-status", "connected", timeout=timeout
        )

    def go_offline(self) -> None:
        """Cut this user's network.

        Context-wide, not page-wide — which is why the fixtures restore it on
        teardown. A scenario that failed while offline would otherwise take
        every later one with it.
        """
        self.page.context.set_offline(True)

    def go_online(self) -> None:
        self.page.context.set_offline(False)

    # --- membership -------------------------------------------------------

    def add_member(self, display_name: str) -> None:
        """Add someone to the open channel, by the name the panel shows.

        Selected by label rather than by value: the value is a user id the
        scenario has no way to know, and the name is what a person would click.
        """
        self.page.get_by_test_id("member-add-select").select_option(label=display_name)
        self.page.get_by_test_id("member-add-submit").click()
        expect(
            self.page.locator(f"[data-testid='member-item'][data-member-name='{display_name}']")
        ).to_be_visible()

    def remove_member(self, display_name: str) -> None:
        self.page.locator(
            f"[data-testid='member-remove'][data-member-name='{display_name}']"
        ).click()
        expect(
            self.page.locator(f"[data-testid='member-item'][data-member-name='{display_name}']")
        ).to_have_count(0)
