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
        "state": "OPEN",
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


# --- trigger and ensure-labels ---------------------------------------------------

PERMISSION = "api repos/sixeyed/claude-at-work-project/collaborators/octo/permission"


def trigger(capsys, root, gh, *extra):
    return cli(capsys, root, *GITHUB, "trigger", "gh-5", "--sender", "octo", *extra, run=gh)


def edits(gh):
    return [c[0] for c in gh.calls if c[0][1:3] == ["issue", "edit"]]


def dispatches(gh):
    return [c[0] for c in gh.calls if c[0][1:3] == ["workflow", "run"]]


def test_trigger_swaps_the_label_then_dispatches_the_delivery(capsys, issues_root, gh, gh_issue):
    gh.answers["issue view"] = gh_issue(labels=("delivery", "delivery:ready"))
    gh.answers[PERMISSION] = "write\n"

    code, out, _ = trigger(capsys, issues_root, gh)

    assert code == 0
    assert edits(gh) == [
        ["gh", "issue", "edit", "5", "--repo", "github.com/sixeyed/claude-at-work-project",
         "--add-label", "delivery:in-progress", "--remove-label", "delivery:ready"],
    ]  # fmt: skip
    assert dispatches(gh) == [
        ["gh", "workflow", "run", "deliver.yml", "--repo", "github.com/sixeyed/claude-at-work-project",
         "-f", "key=gh-5", "-f", "restart=false", "-f", "stub=false"],
    ]  # fmt: skip
    # The labels change before the dispatch: a second event must find no trigger.
    order = [c[0][1:3] for c in gh.calls]
    assert order.index(["issue", "edit"]) < order.index(["workflow", "run"])
    assert "started" in out


def test_trigger_takes_restart_from_the_label_and_stub_from_the_flag(
    capsys, issues_root, gh, gh_issue
):
    gh.answers["issue view"] = gh_issue(labels=("delivery:restart",))
    gh.answers[PERMISSION] = "admin\n"

    trigger(capsys, issues_root, gh, "--stub")

    assert dispatches(gh)[0][-4:] == ["-f", "restart=true", "-f", "stub=true"]


def test_trigger_refuses_a_closed_issue_and_takes_the_label_off(capsys, issues_root, gh, gh_issue):
    gh.answers["issue view"] = gh_issue(labels=("delivery:ready",), state="CLOSED")
    gh.answers[PERMISSION] = "admin\n"

    code, out, _ = trigger(capsys, issues_root, gh)

    assert code == 0
    assert dispatches(gh) == []
    assert edits(gh)[0][-2:] == ["--remove-label", "delivery:ready"]
    assert "closed" in out


def test_trigger_refuses_a_sender_who_cannot_write(capsys, issues_root, gh, gh_issue):
    gh.answers["issue view"] = gh_issue(labels=("delivery:ready",))
    gh.answers[PERMISSION] = "read\n"

    code, out, _ = trigger(capsys, issues_root, gh)

    assert code == 0
    assert dispatches(gh) == []
    assert "--add-label" not in edits(gh)[0]
    assert "octo" in out


def test_trigger_with_no_trigger_label_does_nothing(capsys, issues_root, gh, gh_issue):
    gh.answers["issue view"] = gh_issue(labels=("delivery", "delivery:in-progress"))
    gh.answers[PERMISSION] = "admin\n"

    code, out, _ = trigger(capsys, issues_root, gh)

    assert code == 0
    assert edits(gh) == []
    assert dispatches(gh) == []
    assert "no trigger label" in out


def test_trigger_that_cannot_dispatch_exits_1(capsys, issues_root, gh, gh_issue):
    from delivery.errors import BackendError

    gh.answers["issue view"] = gh_issue(labels=("delivery:ready",))
    gh.answers[PERMISSION] = "write\n"
    gh.answers["workflow run"] = BackendError("HTTP 403: Resource not accessible")

    code, _, err = trigger(capsys, issues_root, gh)

    assert code == 1
    assert "403" in err
    # No run is coming: the issue mustn't say one is.
    assert edits(gh)[-1][-4:] == [
        "--add-label", "delivery:failed", "--remove-label", "delivery:in-progress",
    ]  # fmt: skip


def test_ensure_labels_makes_all_eight(capsys, issues_root, gh):
    code, _, _ = cli(capsys, issues_root, *GITHUB, "ensure-labels", run=gh)

    made = [c[0][3] for c in gh.calls if c[0][1:3] == ["label", "create"]]
    assert code == 0
    assert sorted(made) == sorted(
        [
            "delivery",
            "delivery:ready",
            "delivery:restart",
            "delivery:in-progress",
            "delivery:accepted",
            "delivery:needs-human",
            "delivery:out-of-time",
            "delivery:failed",
        ]
    )
