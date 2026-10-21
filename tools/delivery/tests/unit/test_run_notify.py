"""Slack: what a delivery posts, and how — one thread per delivery, against a fake transport.
A post that fails is logged and never raised: Slack never fails a run."""

from __future__ import annotations

import pytest
from delivery.run.notify import (
    NullNotifier,
    SlackNotifier,
    notifier_from,
    stage_ended,
    stage_started,
    thread_title,
)

ENV = {"SLACK_BOT_TOKEN": "xoxb-1", "SLACK_CHANNEL": "C0DELIVER"}


class FakeSlack:
    """Answers each request with `answer`, or raises it; records (url, headers, payload)."""

    def __init__(self, answer: dict | Exception | None = None) -> None:
        self.answer = answer if answer is not None else {"ok": True, "ts": "1700000000.000100"}
        self.requests: list[tuple[str, dict, dict]] = []

    def __call__(self, url: str, headers: dict, payload: dict) -> dict:
        self.requests.append((url, headers, payload))
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


@pytest.fixture
def slack() -> FakeSlack:
    return FakeSlack()


@pytest.fixture
def said() -> list[str]:
    return []


def notifier(slack, said, env=ENV):
    return notifier_from(env, transport=slack, log=said.append)


# --- which notifier --------------------------------------------------------


@pytest.mark.parametrize(
    "env",
    [
        {},
        {"SLACK_BOT_TOKEN": "xoxb-1"},
        {"SLACK_CHANNEL": "C0DELIVER"},
        {**ENV, "SLACK_CHANNEL": ""},
    ],
)
def test_without_both_a_token_and_a_channel_nothing_is_posted(slack, said, env):
    n = notifier(slack, said, env)

    assert isinstance(n, NullNotifier)
    assert n.enabled is False
    assert n.post("hello") == ""
    n.edit("1.2", "hello")
    assert slack.requests == []


def test_with_both_it_posts_to_slack(slack, said):
    n = notifier(slack, said)

    assert isinstance(n, SlackNotifier)
    assert n.enabled is True


# --- the requests ----------------------------------------------------------

NO_PREVIEWS = {"unfurl_links": False, "unfurl_media": False}


def test_a_post_goes_to_the_channel_with_the_bot_token_and_returns_its_ts(slack, said):
    ts = notifier(slack, said).post("gh-3 started")

    url, headers, payload = slack.requests[0]
    assert url == "https://slack.com/api/chat.postMessage"
    assert headers["Authorization"] == "Bearer xoxb-1"
    assert headers["Content-Type"].startswith("application/json")
    assert payload == {"channel": "C0DELIVER", "text": "gh-3 started", **NO_PREVIEWS}
    assert ts == "1700000000.000100"


def test_a_post_shows_no_link_previews(slack, said):
    """Every stage links its file on GitHub: unfurled, each would be a card in the thread."""
    notifier(slack, said).post("✔ plan-writer done · <https://github.com/o/r/blob/s/p.md|review>")

    _, _, payload = slack.requests[0]
    assert (payload["unfurl_links"], payload["unfurl_media"]) == (False, False)


def test_a_reply_names_its_thread_and_is_broadcast_only_when_asked(slack, said):
    n = notifier(slack, said)

    n.post("a stage", thread="1.1")
    n.post("the PR", thread="1.1", broadcast=True)

    assert slack.requests[0][2] == {
        "channel": "C0DELIVER",
        "text": "a stage",
        "thread_ts": "1.1",
        **NO_PREVIEWS,
    }
    assert slack.requests[1][2] == {
        "channel": "C0DELIVER",
        "text": "the PR",
        "thread_ts": "1.1",
        "reply_broadcast": True,
        **NO_PREVIEWS,
    }


def test_an_edit_updates_the_message_by_its_ts(slack, said):
    notifier(slack, said).edit("1.1", "gh-3 — accepted")

    url, _, payload = slack.requests[0]
    assert url == "https://slack.com/api/chat.update"
    assert payload == {"channel": "C0DELIVER", "ts": "1.1", "text": "gh-3 — accepted"}


@pytest.mark.parametrize(
    ("answer", "says"),
    [
        (OSError("connection refused"), "connection refused"),
        ({"ok": False, "error": "not_in_channel"}, "not_in_channel"),
    ],
)
def test_a_failed_post_is_logged_and_returns_no_ts(said, answer, says):
    slack = FakeSlack(answer)

    ts = notifier(slack, said).post("hello")

    assert ts == ""
    assert len(said) == 1
    assert "Slack" in said[0]
    assert says in said[0]


def test_a_failed_edit_is_logged_not_raised(said):
    notifier(FakeSlack(OSError("timed out")), said).edit("1.1", "x")

    assert "timed out" in said[0]


def test_the_token_is_never_in_what_is_logged(said):
    notifier(FakeSlack({"ok": False, "error": "invalid_auth"}), said).post("x")

    assert "xoxb-1" not in said[0]


# --- the messages ----------------------------------------------------------


def test_a_stage_starting_names_its_round_and_model():
    assert stage_started("plan-reviewer", 2, "opus") == "▶ plan-reviewer · round 2 · opus"


@pytest.mark.parametrize(
    ("status", "mark"),
    [
        ("done", "✔"),
        ("approved", "✔"),
        ("changes_requested", "↩"),
        ("send_back", "↩"),
        ("needs_human", "✋"),
        ("failed", "✗"),
    ],
)
def test_a_stage_ending_is_marked_by_its_verdict(status, mark):
    text = stage_ended("code-reviewer", status, minutes=4.25, cost=1.5, summary="Two findings.")

    assert text == f"{mark} code-reviewer {status} · 4.2 min · $1.50 — Two findings."


def test_a_long_summary_is_cut_at_300_characters():
    text = stage_ended("plan-writer", "done", minutes=1, cost=0, summary="x" * 400)

    summary = text.split(" — ", 1)[1]
    assert len(summary) == 300
    assert summary.endswith("…")


def test_a_stage_ending_links_its_own_file_when_it_has_one():
    text = stage_ended(
        "plan-reviewer", "approved", minutes=2, cost=0.5, summary="Fine.", link="https://x/r.md"
    )

    assert text.endswith("Fine. · <https://x/r.md|review>")


def test_the_threads_title_names_the_issue_its_status_and_the_run():
    assert (
        thread_title("gh-3", "Display names", "running", run_url="https://x/runs/9")
        == "gh-3 · Display names — running · <https://x/runs/9|run>"
    )
    assert thread_title("gh-3", "Display names", "accepted") == "gh-3 · Display names — accepted"
