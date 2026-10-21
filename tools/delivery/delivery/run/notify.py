"""Slack: where a delivery tells people how it is going (handoff 09, decision 16).

One thread per delivery: a parent message naming the issue and its status, edited as the
status changes, and a reply as each stage starts and ends, at a stop, a failure, out of
time, a preview — with its password — and the PR. The thread's `ts` is kept in the run's
state, so a resumed run, on any machine, replies in the same thread.

Slack never fails a run: a post that can't be made is logged, and the run carries on.
Without both SLACK_BOT_TOKEN and SLACK_CHANNEL nothing is posted — a laptop's run, or a
repo with no Slack app.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from typing import Protocol

API = "https://slack.com/api"
SUMMARY_LIMIT = 300

#: Sends one Web API request — url, headers, JSON payload — and returns its JSON answer.
Transport = Callable[[str, dict, dict], dict]

MARKS = {
    "done": "✔",
    "approved": "✔",
    "changes_requested": "↩",
    "send_back": "↩",
    "needs_human": "✋",
}


class Notifier(Protocol):
    enabled: bool

    def post(self, text: str, *, thread: str = "", broadcast: bool = False) -> str:
        """Posts `text`, as a reply to `thread` if given; returns its `ts`, "" if none."""

    def edit(self, ts: str, text: str) -> None: ...


class NullNotifier:
    """Slack isn't set up: nothing is posted, and nothing needs to be."""

    enabled = False

    def post(self, text: str, *, thread: str = "", broadcast: bool = False) -> str:
        return ""

    def edit(self, ts: str, text: str) -> None:
        return None


class SlackNotifier:
    enabled = True

    def __init__(
        self, token: str, channel: str, transport: Transport, log: Callable[[str], None]
    ) -> None:
        self.token = token
        self.channel = channel
        self.transport = transport
        self.log = log

    def post(self, text: str, *, thread: str = "", broadcast: bool = False) -> str:
        # No link previews: each stage links its file on GitHub, and a card apiece buries the thread.
        payload: dict[str, object] = {
            "channel": self.channel,
            "text": text,
            "unfurl_links": False,
            "unfurl_media": False,
        }
        if thread:
            payload["thread_ts"] = thread
            if broadcast:
                payload["reply_broadcast"] = True
        answer = self.call("chat.postMessage", payload)
        return str(answer.get("ts", "")) if answer else ""

    def edit(self, ts: str, text: str) -> None:
        self.call("chat.update", {"channel": self.channel, "ts": ts, "text": text})

    def call(self, method: str, payload: dict) -> dict | None:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json; charset=utf-8",
        }
        try:
            answer = self.transport(f"{API}/{method}", headers, payload)
        except (OSError, ValueError) as e:
            self.log(f"Slack {method} failed, carrying on: {e}")
            return None
        if not answer.get("ok"):
            self.log(
                f"Slack {method} failed, carrying on: {answer.get('error', 'no reason given')}"
            )
            return None
        return answer


def send(url: str, headers: dict, payload: dict) -> dict:
    """The real transport: one POST, ten seconds at most."""
    request = urllib.request.Request(  # noqa: S310 — a fixed https URL.
        url, data=json.dumps(payload).encode(), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
            return json.loads(response.read())
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}"}


def notifier_from(
    env: Mapping[str, str],
    *,
    transport: Transport | None = None,
    log: Callable[[str], None] = lambda _: None,
) -> NullNotifier | SlackNotifier:
    token, channel = env.get("SLACK_BOT_TOKEN", ""), env.get("SLACK_CHANNEL", "")
    if not (token and channel):
        return NullNotifier()
    return SlackNotifier(token, channel, transport or send, log)


# --- the messages -----------------------------------------------------------


def thread_title(key: str, title: str, status: str, *, run_url: str = "") -> str:
    text = f"{key} · {title} — {status}"
    return f"{text} · <{run_url}|run>" if run_url else text


def stage_started(stage: str, round_: int, model: str) -> str:
    return f"▶ {stage} · round {round_} · {model}"


def stage_ended(
    stage: str,
    status: str,
    *,
    minutes: float,
    cost: float,
    summary: str,
    link: str = "",
) -> str:
    mark = MARKS.get(status, "✗")
    text = f"{mark} {stage} {status} · {minutes:.1f} min · ${cost:.2f} — {cut(summary)}"
    return f"{text} · <{link}|review>" if link else text


def cut(text: str, limit: int = SUMMARY_LIMIT) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"
