"""The `delivery` CLI — what the issue-writer skill and, next, `deliver.sh` call."""

from __future__ import annotations

import json

import pytest
from delivery.cli import main

BODY = "## Summary\n\nPins a message.\n"
GITHUB = ["--backend", "github", "--url", "https://github.com/sixeyed/claude-at-work-project"]


@pytest.fixture
def body_file(tmp_path):
    path = tmp_path / "draft.md"
    path.write_text(BODY)
    return str(path)


def cli(capsys, root, *argv, env=None, run=None):
    """Runs the CLI; returns (exit code, stdout, stderr)."""
    code = main(list(argv), env=env or {}, root=root, run=run)
    out, err = capsys.readouterr()
    return code, out, err


# --- local -----------------------------------------------------------------


def test_check_passes_for_local(capsys, issues_root):
    code, out, _ = cli(capsys, issues_root, "check")

    assert code == 0
    assert "local" in out


def test_create_prints_the_issue_as_json(capsys, issues_root, body_file):
    code, out, _ = cli(
        capsys, issues_root, "issue", "create", "--title", "Pin a message", "--body-file", body_file
    )

    assert code == 0
    assert json.loads(out) == {
        "key": "issue-9",
        "number": 9,
        "title": "Pin a message",
        "body": BODY,
        "url": "docs/issues/009.md",
        "labels": [],
    }


def test_get_prints_the_issue_as_json(capsys, issues_root):
    code, out, _ = cli(capsys, issues_root, "issue", "get", "issue-8")

    assert code == 0
    assert json.loads(out)["title"] == "Better mobile experience"


def test_edit_prints_the_edited_issue(capsys, issues_root, body_file):
    code, out, _ = cli(
        capsys,
        issues_root,
        "issue",
        "edit",
        "issue-8",
        "--title",
        "Mobile",
        "--body-file",
        body_file,
    )

    assert code == 0
    assert json.loads(out)["title"] == "Mobile"
    assert json.loads(out)["body"] == BODY


def test_verify_exits_0_when_the_issue_matches_the_draft(capsys, issues_root, body_file):
    cli(
        capsys, issues_root, "issue", "create", "--title", "Pin a message", "--body-file", body_file
    )

    code, _, _ = cli(
        capsys, issues_root, "issue", "verify", "issue-9", "--title", "Pin a message",
        "--body-file", body_file,
    )  # fmt: skip

    assert code == 0


def test_verify_exits_1_and_lists_differences_when_it_does_not(capsys, issues_root, body_file):
    code, out, _ = cli(
        capsys, issues_root, "issue", "verify", "issue-8", "--title", "Pin a message",
        "--body-file", body_file,
    )  # fmt: skip

    assert code == 1
    assert "title" in out


def test_ensure_label_succeeds_locally(capsys, issues_root):
    code, _, _ = cli(capsys, issues_root, "ensure-label", "delivery")

    assert code == 0


def test_the_environment_selects_the_backend(capsys, issues_root, gh):
    env = {
        "DELIVERY_BACKEND": "github",
        "DELIVERY_URL": "https://github.com/sixeyed/claude-at-work-project",
    }

    code, out, _ = cli(capsys, issues_root, "check", env=env, run=gh)

    assert code == 0
    assert "github" in out
    gh.call("repo view")


# --- github, through the fake gh -------------------------------------------


def test_create_on_github_prints_the_key_and_url(capsys, issues_root, gh, body_file):
    code, out, _ = cli(
        capsys, issues_root, *GITHUB, "issue", "create", "--title", "Pin a message",
        "--body-file", body_file, "--label", "delivery", run=gh,
    )  # fmt: skip

    assert code == 0
    issue = json.loads(out)
    assert issue["key"] == "gh-5"
    assert issue["url"] == "https://github.com/sixeyed/claude-at-work-project/issues/5"
    args, stdin = gh.call("issue create")
    assert args[-2:] == ["--label", "delivery"]
    assert stdin == BODY


def test_ensure_label_on_github_has_a_default_description_and_colour(capsys, issues_root, gh):
    code, _, _ = cli(capsys, issues_root, *GITHUB, "ensure-label", "delivery", run=gh)

    assert code == 0
    args, _ = gh.call("label create")
    assert "--description" in args
    assert "--color" in args


# --- failures --------------------------------------------------------------


def test_bad_configuration_exits_2_with_a_message_and_no_traceback(capsys, issues_root):
    code, _, err = cli(capsys, issues_root, "--backend", "github", "check")

    assert code == 2
    assert "URL" in err
    assert "Traceback" not in err


def test_a_backend_failure_exits_1_with_a_message_and_no_traceback(capsys, issues_root):
    code, _, err = cli(capsys, issues_root, "issue", "get", "issue-42")

    assert code == 1
    assert "issue-42" in err
    assert "Traceback" not in err


def test_check_fails_with_1_when_the_backend_is_not_usable(capsys, tmp_path):
    code, _, err = cli(capsys, tmp_path, "check")

    assert code == 1
    assert "docs/issues" in err


# --- notify ----------------------------------------------------------------

SLACK = {"SLACK_BOT_TOKEN": "xoxb-1", "SLACK_CHANNEL": "C0DELIVER"}


class FakeSlack:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok
        self.payloads: list[dict] = []

    def __call__(self, url, headers, payload):
        self.payloads.append(payload)
        return {"ok": True, "ts": "2.2"} if self.ok else {"ok": False, "error": "not_in_channel"}


def notify(capsys, root, *argv, env=SLACK, slack=None):
    code = main(["notify", *argv], env=env, root=root, slack_transport=slack)
    out, err = capsys.readouterr()
    return code, out, err


def test_notify_replies_in_the_thread_its_state_names(capsys, tmp_path):
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"stage": "done", "slack_thread": "1.1"}))
    slack = FakeSlack()

    code, _, _ = notify(
        capsys, tmp_path, "--state", str(state), "--broadcast", "Preview up", slack=slack
    )

    assert code == 0
    assert slack.payloads == [
        {
            "channel": "C0DELIVER",
            "text": "Preview up",
            "thread_ts": "1.1",
            "reply_broadcast": True,
            "unfurl_links": False,
            "unfurl_media": False,
        }
    ]


@pytest.mark.parametrize("state", ['{"stage": "done"}', None])
def test_notify_with_no_thread_posts_to_the_channel(capsys, tmp_path, state):
    path = tmp_path / "state.json"
    if state is not None:
        path.write_text(state)
    slack = FakeSlack()

    code, _, _ = notify(capsys, tmp_path, "--state", str(path), "--broadcast", "Up", slack=slack)

    assert code == 0
    assert slack.payloads == [
        {"channel": "C0DELIVER", "text": "Up", "unfurl_links": False, "unfurl_media": False}
    ]


def test_notify_without_slack_posts_nothing_and_says_so(capsys, tmp_path):
    slack = FakeSlack()

    code, _, err = notify(capsys, tmp_path, "Up", env={}, slack=slack)

    assert code == 0
    assert slack.payloads == []
    assert "Slack" in err


def test_a_failed_notify_is_reported_and_still_exits_0(capsys, tmp_path):
    code, _, err = notify(capsys, tmp_path, "Up", slack=FakeSlack(ok=False))

    assert code == 0
    assert "not_in_channel" in err
