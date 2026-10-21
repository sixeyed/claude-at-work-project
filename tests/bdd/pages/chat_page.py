"""The chat shell, as the scenarios talk about it.

Every selector in the suite lives in a page object; no step definition contains
one. That is the rule that keeps browser tests from rotting — when a component
is restructured, one file changes rather than twenty.

Selectors are `data-testid` only. Text and CSS classes are things a designer
should be free to change without breaking a test about channels.

Only what a kept journey uses is here. The suite is key journeys only (register
D32), so a method nothing calls is deleted with the scenario that used it.

**A question about the screen is answered by a retrying expectation**, not by
reading the DOM once. `count()` and `inner_text()` report whatever is there at
the instant they run, and in an app that renders from a cache which a socket
event, a refetch or an ack can change a moment later, that instant is a race.
The `has_*` and `is_*` methods wrap Playwright's `expect`, which polls until the
condition holds or its timeout runs out, and return whether it held — so the
steps still read `assert ada.has_tombstone()`. The plain readers
(`channel_names`, `message_bodies`, `count_of`) are kept for failure messages.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from playwright.sync_api import Locator, Page, expect
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

#: How long `appears_once` keeps checking the count after it first reads 1.
#: The sender's own broadcast lands after her ack, and a blind append turns
#: one row into two only when it does — so a count taken the instant the
#: confirmed row appears proves nothing about duplicates.
_ONCE_HOLD_MS = 1_500
_ONCE_POLL_MS = 100


def _holds(check: Callable[[], None]) -> bool:
    """Whether a retrying expectation passed within its timeout."""
    try:
        check()
    except AssertionError:
        return False
    return True


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

    # --- session ----------------------------------------------------------

    def sign_out(self) -> None:
        """Sign out, and wait until the app has let go of the session.

        Waiting on the sign-in page rather than on the click: the SPA shows it
        only after `/auth/logout` has answered, so a reload straight after this
        cannot race the revocation and spend a cookie the server was about to
        clear.
        """
        self.page.get_by_test_id("sign-out").click()
        expect(self.page.get_by_test_id("sign-in")).to_be_visible()

    def switch_workspace(self, name: str) -> None:
        """Move to another workspace and wait until the shell says so.

        Double quotes in the attribute selector, because a personal workspace is
        called "ada's Workspace" and a single quote would end the value.
        """
        self.page.locator(f'[data-testid="workspace-option"][data-workspace-name="{name}"]').click()
        expect(self.page.get_by_test_id("workspace-name")).to_have_text(name)

    # --- settings ---------------------------------------------------------

    def open_settings(self) -> None:
        """Click your name in the sidebar and wait until the Settings page is up."""
        self.page.get_by_test_id("current-user").click()
        expect(self.page.get_by_test_id("settings-page")).to_be_visible()

    def change_display_name(self, name: str) -> None:
        """Type a new display name on Settings, save it, and wait for "Saved".

        The field appears once this visit's read of the profile has landed, so
        waiting for it is waiting for the real name. A name the account already
        holds leaves Save disabled (unchanged), so there is nothing to click and
        nothing to wait for: that is what keeps a rerun against a kept stack, where
        Alan already has the name, passing.
        """
        field = self.page.get_by_test_id("settings-display-name-input")
        expect(field).to_be_visible()
        if field.input_value() == name:
            return
        field.fill(name)
        save = self.page.get_by_test_id("settings-display-name-save")
        expect(save).to_be_enabled()
        save.click()
        expect(self.page.get_by_test_id("settings-saved")).to_be_visible()

    def has_current_user(self, name: str) -> bool:
        """Whether the sidebar names the signed-in user `name`, waiting for it to."""
        return _holds(lambda: expect(self.page.get_by_test_id("current-user")).to_have_text(name))

    # --- reading ----------------------------------------------------------

    def workspace_name(self) -> str:
        return self.page.get_by_test_id("workspace-name").inner_text()

    def channel_names(self) -> list[str]:
        """Every channel in the sidebar, in the order it is displayed.

        A single read, for failure messages — assert with `has_channel` and
        `lacks_channel`, which wait.
        """
        self._settle()
        items = self.page.get_by_test_id("channel-list-item")
        return [
            (items.nth(i).get_attribute("data-channel-name") or "").strip()
            for i in range(items.count())
        ]

    def has_channel(self, name: str) -> bool:
        """Whether a channel is in the sidebar, waiting for it to arrive."""
        self._settle()
        return _holds(lambda: expect(self._channel_item(name)).to_have_count(1))

    def lacks_channel(self, name: str) -> bool:
        """Whether a channel is *not* in the sidebar, once the list has loaded.

        Settling first is what stops this passing vacuously: a list still
        loading has no channels in it at all.
        """
        self._settle()
        return _holds(lambda: expect(self._channel_item(name)).to_have_count(0))

    def open_channel(self, name: str) -> None:
        """Click a channel in the sidebar and wait until it is the open one."""
        self._settle()
        self._channel_item(name).click()
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

    def has_unread_badge(self, name: str, count: int) -> bool:
        """Whether a channel's sidebar badge shows `count`, waiting for it to.

        Read from `data-count`, the number as displayed, so the assertion does
        not depend on how the pill is laid out.
        """
        self._settle()
        return _holds(lambda: expect(self._badge(name)).to_have_attribute("data-count", str(count)))

    def lacks_unread_badge(self, name: str) -> bool:
        """Whether a channel shows no badge, once its item is on screen.

        The item is the anchor: the badge renders in the same render as the
        item, so a list still loading cannot pass this by having nothing in it.
        """
        self._settle()
        if not _holds(lambda: expect(self._channel_item(name)).to_be_visible()):
            return False
        return _holds(lambda: expect(self._badge(name)).to_have_count(0))

    def _badge(self, name: str) -> Locator:
        return self._channel_item(name).get_by_test_id("channel-unread-badge")

    def _channel_item(self, name: str) -> Locator:
        return self.page.locator(f"[data-testid='channel-list-item'][data-channel-name='{name}']")

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
        """Create a channel and wait until the app has navigated into it.

        The view **named** after the channel, not any `channel-view`: when
        several channels are created in a row the previous one is still open, so
        waiting on any view passes at once.
        """
        self.create_channel(name)
        expect(self._view_of(name)).to_be_visible()

    def create_private_channel_and_wait(self, name: str) -> None:
        self.create_channel(name, kind="private")
        expect(self._view_of(name)).to_be_visible()

    def _view_of(self, name: str) -> Locator:
        return self.page.locator(f"[data-testid='channel-view'][data-channel-name='{name}']")

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
        """Send, and wait until the server has the message — not just the screen.

        The optimistic row is on screen the moment the button is clicked, so
        waiting for the text alone passes before anything has left the browser,
        and a send the server refused would pass too. `MessageItem` marks the
        optimistic row `data-pending="true"` until the ack replaces it, so this
        waits for a confirmed row and then for the optimistic one to be gone:
        a send that settles leaves nothing pending behind.

        `.first` on the confirmed row, because a duplicate is `appears_once`'s
        failure to report, not a strict-mode error here.
        """
        self.send_message(text)
        expect(self._confirmed(text).first).to_be_visible()
        expect(self._pending(text)).to_have_count(0)

    def draft(self) -> str:
        return self.page.get_by_test_id("message-composer-input").input_value()

    def message_bodies(self) -> list[str]:
        """Every message body on screen — a single read, for failure messages."""
        self._settle_messages()
        bodies = self.page.get_by_test_id("message-body")
        return [(bodies.nth(i).inner_text() or "").strip() for i in range(bodies.count())]

    def has_message(self, text: str) -> bool:
        self._settle_messages()
        return _holds(lambda: expect(self._message(text).first).to_be_visible())

    def author_of(self, text: str) -> str:
        """Whatever the author label says right now — for failure messages."""
        return self._item_for(text).get_by_test_id("message-author").inner_text().strip()

    def has_author(self, text: str, name: str) -> bool:
        """Whether a message is shown as written by `name`, waiting for it.

        The label is resolved from the workspace directory, which loads on its
        own schedule; until it does the row shows a shortened id. A single read
        would race that load.
        """
        author = self._item_for(text).get_by_test_id("message-author")
        return _holds(lambda: expect(author).to_have_text(name))

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
        marker = self._item_for(text).get_by_test_id("message-edited")
        return _holds(lambda: expect(marker).to_be_visible())

    def has_tombstone(self) -> bool:
        self._settle_messages()
        return _holds(
            lambda: expect(self.page.get_by_test_id("message-deleted").first).to_be_visible()
        )

    def _message(self, text: str) -> Locator:
        return self.page.get_by_test_id("message-body").filter(has_text=text)

    def _item_for(self, text: str) -> Locator:
        return self.page.get_by_test_id("message-item").filter(has_text=text).first

    def _confirmed(self, text: str) -> Locator:
        return self.page.locator("[data-testid='message-item'][data-pending='false']").filter(
            has=self._message(text)
        )

    def _pending(self, text: str) -> Locator:
        return self.page.locator("[data-testid='message-item'][data-pending='true']").filter(
            has=self._message(text)
        )

    def _settle_messages(self) -> None:
        """Wait for the history's first load, as `_settle` does for the sidebar.

        Reading through the loading state returns an empty list that looks
        exactly like "no messages".
        """
        self.page.get_by_test_id("message-list-loading").wait_for(state="detached", timeout=10_000)

    # --- reactions --------------------------------------------------------

    def react_to(self, text: str, emoji: str) -> None:
        """Open a message's picker and choose an emoji, waiting for the chip.

        Hovering first because the controls live behind `group-hover`. Playwright
        would click through the transparency anyway — opacity is not visibility
        to it — but a hover is what a person does, and it costs nothing.

        Waiting on the chip rather than on the request covers the cache write
        too: a reaction the server accepted and the SPA never applied would
        leave nothing on screen, and that is worth failing for.
        """
        item = self._item_for(text)
        item.hover()
        item.get_by_test_id("reaction-picker").click()
        self.page.locator(f"[data-testid='reaction-option'][data-emoji='{emoji}']").click()
        expect(self._chip(text, emoji)).to_be_visible()

    def has_reaction_count(self, text: str, emoji: str, count: int) -> bool:
        """Whether a message shows `count` of one emoji, waiting for it to get there.

        The count is read from an attribute rather than the chip's text, so the
        assertion does not depend on how the number is rendered beside the
        glyph.
        """
        self._settle_messages()
        return _holds(
            lambda: expect(self._chip(text, emoji)).to_have_attribute("data-count", str(count))
        )

    def _chip(self, text: str, emoji: str) -> Locator:
        return self._item_for(text).locator(f"[data-testid='reaction-chip'][data-emoji='{emoji}']")

    # --- threads ----------------------------------------------------------

    def reply_in_thread(self, body: str, reply: str) -> None:
        """Open the thread on a channel message, reply, and wait for the server's copy.

        The confirmed row *inside the panel*: the optimistic reply is on screen
        the moment the button is clicked, so waiting on the text alone passes
        before anything has left the browser. `data-pending='false'` is the ack
        or the echo replacing the `temp:` row.

        Hovering first because the action lives behind `group-hover`.
        """
        item = self._channel_item_for(body)
        item.hover()
        item.get_by_test_id("thread-open").click()
        self.page.get_by_test_id("thread-composer-input").fill(reply)
        self.page.get_by_test_id("thread-composer-send").click()
        panel = self.page.get_by_test_id("thread-panel")
        confirmed = panel.locator("[data-testid='message-item'][data-pending='false']").filter(
            has_text=reply
        )
        expect(confirmed.first).to_be_visible()

    def has_reply_count(self, body: str, count: int) -> bool:
        """Whether a channel message shows `count` replies, waiting for it to get there.

        Read from `data-reply-count` on the summary inside the channel's own
        list: the open panel's root carries the same text, and has no summary.
        """
        self._settle_messages()
        summary = self._channel_item_for(body).get_by_test_id("thread-summary")
        return _holds(lambda: expect(summary).to_have_attribute("data-reply-count", str(count)))

    def open_thread(self, body: str) -> None:
        """Open a thread from the root's reply summary, as someone who didn't write it would."""
        self._channel_item_for(body).get_by_test_id("thread-summary").click()
        expect(self.page.get_by_test_id("thread-panel")).to_be_visible()

    def thread_has_message(self, text: str) -> bool:
        """Whether the open panel shows a message — fetched from the server on open."""
        panel = self.page.get_by_test_id("thread-panel")
        message = panel.get_by_test_id("message-body").filter(has_text=text)
        return _holds(lambda: expect(message.first).to_be_visible())

    def _channel_item_for(self, text: str) -> Locator:
        """A message in the channel's list, never the panel's copy of the root."""
        return (
            self.page.get_by_test_id("message-list")
            .get_by_test_id("message-item")
            .filter(has_text=text)
            .first
        )

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
        """How many times a message is on screen — a single read, for failure messages."""
        self._settle_messages()
        return self._message(text).count()

    def appears_once(self, text: str) -> bool:
        """Whether a message is on screen exactly once, and stays that way.

        The sender receives her own broadcast — there is no `sid` to skip it by,
        because the REST write is not a socket — so "exactly once" is the
        assertion that a blind append would fail. But the broadcast lands
        *after* the ack, so a count taken as soon as the confirmed row shows is
        1 whether or not the bug is there.

        So: wait for the confirmed row, wait for the count to be 1, then keep
        checking for a short window in which the broadcast has had time to land.
        That window is the one fixed interval in this file, and it is bounded
        by a claim — "it does not become 2" — rather than by a guess at how
        long something takes to appear.
        """
        self._settle_messages()
        expect(self._confirmed(text).first).to_be_visible()
        messages = self._message(text)
        if not _holds(lambda: expect(messages).to_have_count(1)):
            return False
        for _ in range(_ONCE_HOLD_MS // _ONCE_POLL_MS):
            self.page.wait_for_timeout(_ONCE_POLL_MS)
            if messages.count() != 1:
                return False
        return True

    def is_absent(self, text: str) -> bool:
        """Whether a message is *not* on screen, waiting for it to go.

        Used after the change that removes it has already been seen to land —
        an edit's new words, a tombstone — so what is being waited out is the
        old row lingering, and a retrying count of zero says so without a fixed
        pause.
        """
        self._settle_messages()
        return _holds(lambda: expect(self._message(text)).to_have_count(0))

    def wait_for_channel_joined(self, timeout: int = 30_000) -> None:
        """Wait until the server has put this connection in the open channel's room.

        Not merely "the socket is up". The server enters a room only after it
        has checked the channel is visible, and anything broadcast before that
        never reaches this connection — so waiting on `connected` let a scenario
        send into a room its reader had not entered yet, and fail now and then.
        The SPA reports the join once the server acknowledges it.

        Generous, because a reconnect goes through Socket.IO's backoff, and a
        flaky assertion here would be blamed on the feature rather than on the
        wait.
        """
        expect(self.page.get_by_test_id("connection-status")).to_have_attribute(
            "data-joined-channel", self.current_channel_id(), timeout=timeout
        )

    def wait_for_disconnected(self, timeout: int = 60_000) -> None:
        """Wait until the SPA reports that its socket has gone down.

        Without this a "connection drops" scenario proves nothing about
        recovery: if the socket stayed up through the outage, the message would
        simply arrive live and the scenario would pass for the wrong reason.

        Generous, because a silently dead transport is only noticed when the
        server's heartbeat goes missing — python-socketio's defaults allow up to
        25s between pings and 20s more for the answer.
        """
        expect(self.page.get_by_test_id("connection-status")).to_have_attribute(
            "data-status", "disconnected", timeout=timeout
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

    # --- search -----------------------------------------------------------

    def search(self, query: str) -> None:
        """Search from the sidebar box, waiting for an answer.

        Indexing is asynchronous and has no stated lag (D29), so the first
        search can land before the Worker has indexed the message. A resubmit
        refetches (the box's own rule), so the retry is inside the act — no
        `Then` performs an action. Gives up after ten seconds, leaving whatever
        the page shows for the `Then` to fail on.
        """
        box = self.page.get_by_test_id("search-box")
        box.fill(query)
        box.press("Enter")
        results = self.page.get_by_test_id("search-result")
        empty = self.page.get_by_test_id("search-empty")
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            expect(results.or_(empty).first).to_be_visible()
            if results.count() > 0:
                return
            box.press("Enter")
            self.page.wait_for_timeout(500)

    def has_search_result(self, body: str) -> bool:
        """Whether a result row shows `body`, waiting for it."""
        return _holds(lambda: expect(self._result(body)).to_be_visible())

    def open_search_result(self, body: str) -> None:
        self._result(body).click()

    def has_highlighted(self, body: str) -> bool:
        """Whether the message is highlighted — it holds for two seconds only."""
        highlighted = self.page.locator(
            "[data-testid='message-item'][data-highlighted='true']"
        ).filter(has_text=body)
        return _holds(lambda: expect(highlighted).to_be_visible())

    def _result(self, body: str) -> Locator:
        return self.page.get_by_test_id("search-result").filter(has_text=body).first

    # --- attachments ------------------------------------------------------

    def attach_files(self, files: list[dict[str, object]]) -> None:
        """Pick files through the composer's file input, and wait until each is uploaded.

        `files` are Playwright payloads — `{name, mimeType, buffer}` — so nothing
        touches the disk. Ready means every chip says so: Send stays off until
        then, and a step that sent early would be testing the disabled button.
        The count is checked as well, so zero chips (an input that took nothing)
        cannot pass as "all of them ready".
        """
        self.page.get_by_test_id("attach-files").set_input_files(files)
        chips = self.page.get_by_test_id("attachment-chip")
        expect(chips).to_have_count(len(files))
        expect(
            self.page.locator("[data-testid='attachment-chip']:not([data-status='ready'])")
        ).to_have_count(0, timeout=30_000)

    def has_inline_image(self, text: str, file_name: str) -> bool:
        """Whether a message shows an attachment as an image that really loaded.

        `naturalWidth > 0` is what separates a picture from a broken-image icon:
        the element is visible either way, and a URL Garage refused would still
        leave an `<img>` in the page. The wait is Playwright's own polling
        `wait_for_function`, because there is no retrying `expect` for a
        property being greater than zero.
        """
        self._settle_messages()
        image = self._attachment("message-attachment-image", text, file_name)
        if not _holds(lambda: expect(image).to_be_visible()):
            return False
        try:
            self.page.wait_for_function(
                "(el) => el.complete && el.naturalWidth > 0",
                arg=image.element_handle(),
                timeout=15_000,
            )
        except PlaywrightTimeoutError:
            return False
        return True

    def has_file_chip(self, text: str, file_name: str) -> bool:
        """Whether a message shows an attachment as a file chip with a download control."""
        self._settle_messages()
        chip = self._attachment("message-attachment-file", text, file_name)
        return _holds(lambda: expect(chip).to_be_visible()) and _holds(
            lambda: expect(chip.get_by_test_id("message-attachment-download")).to_be_visible()
        )

    def download_attachment(self, text: str, file_name: str) -> bytes:
        """Click a file chip's download and return the bytes the browser received."""
        chip = self._attachment("message-attachment-file", text, file_name)
        with self.page.expect_download() as download:
            chip.get_by_test_id("message-attachment-download").click()
        return Path(download.value.path()).read_bytes()

    def _attachment(self, testid: str, text: str, file_name: str) -> Locator:
        return self._item_for(text).locator(
            f"[data-testid='{testid}'][data-file-name='{file_name}']"
        )

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

    # --- direct messages --------------------------------------------------

    def start_dm(self, name: str) -> None:
        """Pick someone from the sidebar's **+** and wait until their DM is the open view.

        The view **named** after the person, and then the room join: the DM's first
        message is what lists it in the other sidebar, and a send before the server
        has put this connection in the room would race its own arrangement.
        """
        self.page.get_by_test_id("dm-new").click()
        self.page.locator(f"[data-testid='dm-pick'][data-member-name='{name}']").click()
        expect(self._view_of(name)).to_be_visible()
        self.wait_for_channel_joined()

    def open_dm(self, name: str) -> None:
        """Click a person's row under *Direct messages* and wait for their view."""
        self._settle()
        self._dm_item(name).click()
        expect(self._view_of(name)).to_be_visible()

    def has_dm_unread_badge(self, name: str, count: int) -> bool:
        """Whether a DM's row shows `count` unread, waiting for the row and the badge.

        Settled first, so a list still loading cannot stand in for "no row"; the retrying
        expectation then covers the row arriving by `channel_added` on a page nobody reloaded.
        """
        self._settle()
        badge = self._dm_item(name).get_by_test_id("channel-unread-badge")
        return _holds(lambda: expect(badge).to_have_attribute("data-count", str(count)))

    def _dm_item(self, name: str) -> Locator:
        return self.page.locator(f"[data-testid='dm-list-item'][data-dm-name='{name}']")
