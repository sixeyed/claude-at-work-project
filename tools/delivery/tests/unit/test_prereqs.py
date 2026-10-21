"""`delivery prereqs`: what a delivery needs from the machine and the repo, checked from names
and settings only — never a secret's value — each missing one linked to the section of
docs/delivery/prerequisites.md that says how to fix it."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from delivery.cli import main
from delivery.errors import BackendError
from delivery.github import GitHubBackend
from delivery.prereqs import ANCHORS, DOC, github_checks, machine_checks, render

URL = "https://github.com/caw-project/ch09"
API = "api repos/caw-project/ch09"
REPO_ROOT = Path(__file__).resolve().parents[4]
SLACK = ("SLACK_BOT_TOKEN", "SLACK_CHANNEL")


@pytest.fixture
def ready(gh):
    """A repo with everything in place."""
    gh.answers.update(
        {
            "api user": "sixeyed\n",
            "repo view": json.dumps({"hasIssuesEnabled": True, "viewerPermission": "ADMIN"}),
            "secret list": secrets("CLAUDE_CODE_OAUTH_TOKEN", *SLACK),
            f"{API}/actions/permissions": json.dumps({"enabled": True}),
            f"{API}/actions/permissions/workflow": json.dumps(
                {"default_workflow_permissions": "read", "can_approve_pull_request_reviews": True}
            ),
            API: json.dumps(
                {
                    "default_branch": "main",
                    "allow_squash_merge": True,
                    "allow_merge_commit": False,
                    "allow_rebase_merge": False,
                    "delete_branch_on_merge": True,
                }
            ),
            f"{API}/contents/.github/workflows/deliver.yml?ref=main": "{}",
            f"{API}/contents/.github/workflows/preview.yml?ref=main": "{}",
        }
    )
    return gh


def secrets(*names: str) -> str:
    return json.dumps([{"name": n, "updatedAt": "2026-10-19T08:50:11Z"} for n in names])


def checks(gh) -> dict[str, tuple[str, str, str]]:
    """By name: (state, detail, anchor)."""
    found = github_checks(GitHubBackend(URL, run=gh))
    return {c.name: (c.state, c.detail, c.anchor) for c in found}


def state_of(gh, name: str) -> str:
    return checks(gh)[name][0]


def api_answer(gh, path: str, **changes) -> None:
    gh.answers[path] = json.dumps({**json.loads(gh.answers[path]), **changes})


# --- GitHub ----------------------------------------------------------------


def test_a_repo_with_everything_in_place_passes_every_check(ready):
    found = checks(ready)

    assert {name: s for name, (s, _, _) in found.items()} == {
        "gh, signed in": "ok",
        "the repo": "ok",
        "Actions": "ok",
        "Claude's secret": "ok",
        "Slack": "ok",
        "Actions may open pull requests": "ok",
        "squash merges only": "ok",
        "the workflows, on the default branch": "ok",
    }
    assert "sixeyed" in found["gh, signed in"][1]


def test_gh_signed_out_or_missing_is_the_only_check_reported(ready):
    ready.answers["api user"] = BackendError("the GitHub backend needs the gh CLI on PATH")

    found = checks(ready)

    assert found == {
        "gh, signed in": ("missing", "the GitHub backend needs the gh CLI on PATH", "gh-signed-in")
    }


def test_settings_are_read_from_the_repo_by_owner_and_name_on_its_host(ready):
    checks(ready)

    asked = [args for args, _ in ready.calls if args[1] == "api"]
    assert ["gh", "api", "user", "--hostname", "github.com", "--jq", ".login"] in asked
    assert ["gh", "api", "repos/caw-project/ch09", "--hostname", "github.com"] in asked
    secret, _ = ready.call("secret list")
    assert secret == [
        "gh",
        "secret",
        "list",
        "--repo",
        "github.com/caw-project/ch09",
        "--json",
        "name",
    ]


@pytest.mark.parametrize(
    ("view", "says"),
    [
        ({"hasIssuesEnabled": False, "viewerPermission": "ADMIN"}, "issues"),
        ({"hasIssuesEnabled": True, "viewerPermission": "READ"}, "write"),
    ],
)
def test_issues_off_or_no_write_access_fails_the_repo(ready, view, says):
    ready.answers["repo view"] = json.dumps(view)

    state, detail, anchor = checks(ready)["the repo"]

    assert (state, anchor) == ("missing", "the-repo")
    assert says in detail


def test_actions_turned_off_fails(ready):
    ready.answers[f"{API}/actions/permissions"] = json.dumps({"enabled": False})

    assert checks(ready)["Actions"][0] == "missing"


@pytest.mark.parametrize("name", ["CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY"])
def test_either_claude_secret_will_do(ready, name):
    ready.answers["secret list"] = secrets(name)

    assert state_of(ready, "Claude's secret") == "ok"


def test_no_claude_secret_fails_and_links_its_section(ready):
    ready.answers["secret list"] = secrets(*SLACK)

    state, detail, anchor = checks(ready)["Claude's secret"]

    assert (state, anchor) == ("missing", "claudes-secret")
    assert "CLAUDE_CODE_OAUTH_TOKEN" in detail
    assert "ANTHROPIC_API_KEY" in detail


def test_secrets_that_cannot_be_listed_say_why(ready):
    ready.answers["secret list"] = BackendError("HTTP 403: Resource not accessible")

    state, detail, _ = checks(ready)["Claude's secret"]

    assert state == "missing"
    assert "403" in detail


def test_no_slack_is_optional(ready):
    ready.answers["secret list"] = secrets("CLAUDE_CODE_OAUTH_TOKEN")

    state, detail, anchor = checks(ready)["Slack"]

    assert (state, anchor) == ("optional", "slack-optional")
    assert "collabhub" in detail


@pytest.mark.parametrize("one", SLACK)
def test_one_slack_secret_without_the_other_fails(ready, one):
    ready.answers["secret list"] = secrets("CLAUDE_CODE_OAUTH_TOKEN", one)

    state, detail, _ = checks(ready)["Slack"]

    assert state == "missing"
    assert next(n for n in SLACK if n != one) in detail


def test_actions_that_may_not_open_prs_fail(ready):
    api_answer(ready, f"{API}/actions/permissions/workflow", can_approve_pull_request_reviews=False)

    state, _, anchor = checks(ready)["Actions may open pull requests"]

    assert (state, anchor) == ("missing", "actions-may-open-pull-requests")


@pytest.mark.parametrize(
    ("setting", "value", "says"),
    [
        ("allow_merge_commit", True, "merge commits"),
        ("allow_rebase_merge", True, "rebase merges"),
        ("allow_squash_merge", False, "squash merges"),
        ("delete_branch_on_merge", False, "delete"),
    ],
)
def test_any_merge_but_squash_or_branches_kept_fails(ready, setting, value, says):
    api_answer(ready, API, **{setting: value})

    state, detail, anchor = checks(ready)["squash merges only"]

    assert (state, anchor) == ("missing", "squash-merges-only")
    assert says in detail


def test_a_workflow_missing_from_the_default_branch_fails_and_names_it(ready):
    ready.answers[f"{API}/contents/.github/workflows/preview.yml?ref=main"] = BackendError(
        "HTTP 404"
    )

    state, detail, anchor = checks(ready)["the workflows, on the default branch"]

    assert (state, anchor) == ("missing", "the-workflows-on-the-default-branch")
    assert "preview.yml" in detail
    assert "deliver.yml" not in detail


def test_the_workflows_are_looked_for_on_the_default_branch(ready):
    api_answer(ready, API, default_branch="trunk")

    checks(ready)

    asked = [args[2] for args, _ in ready.calls if args[1] == "api"]
    assert f"{API[4:]}/contents/.github/workflows/preview.yml?ref=trunk" in asked


def test_a_setting_that_cannot_be_read_fails_with_why(ready):
    ready.answers[f"{API}/actions/permissions/workflow"] = BackendError("HTTP 403: admin only")

    state, detail, _ = checks(ready)["Actions may open pull requests"]

    assert state == "missing"
    assert "admin only" in detail


# --- the machine -----------------------------------------------------------


def machine(env=None, missing=(), tmp_path=None):
    root = tmp_path
    (root / ".env.example").write_text("")
    return machine_checks(
        "github",
        env=env or {},
        root=root,
        which=lambda cmd: None if cmd in missing else f"/usr/bin/{cmd}",
        runs=lambda args: True,
    )


def test_the_machine_passes_with_every_tool(tmp_path):
    [check] = machine(tmp_path=tmp_path)

    assert (check.name, check.state, check.anchor) == ("the machine", "ok", "the-machine")


def test_the_machine_lists_every_tool_missing_as_the_runners_preflight_does(tmp_path):
    [check] = machine(missing=("k3d", "gh"), tmp_path=tmp_path)

    assert check.state == "missing"
    assert "'k3d' is not on PATH" in check.detail
    assert "'gh' is not on PATH" in check.detail


def test_htpasswd_is_needed_only_where_slack_gives_previews_a_password(tmp_path):
    slack = dict.fromkeys(SLACK, "x")

    assert machine(missing=("htpasswd",), tmp_path=tmp_path)[0].state == "ok"
    [check] = machine(env=slack, missing=("htpasswd",), tmp_path=tmp_path)
    assert check.state == "missing"
    assert "htpasswd" in check.detail


# --- the report ------------------------------------------------------------


def test_the_report_marks_each_check_and_links_what_to_fix(ready):
    ready.answers["secret list"] = secrets()
    found = github_checks(GitHubBackend(URL, run=ready))

    text = render(found)

    assert "✔ gh, signed in — signed in as sixeyed" in text
    assert "✗ Claude's secret — " in text
    assert f"    fix: {DOC}#claudes-secret" in text
    assert "○ Slack — " in text
    assert f"{DOC}#slack-optional" not in text


def test_every_anchor_is_a_heading_of_the_doc():
    headings = re.findall(r"^## (.+)$", (REPO_ROOT / DOC).read_text(), re.MULTILINE)
    slugs = {re.sub(r"[^a-z0-9 -]", "", h.lower()).replace(" ", "-") for h in headings}

    assert set(ANCHORS) <= slugs


# --- the command -----------------------------------------------------------


def prereqs(capsys, root, gh, *argv):
    code = main([*argv, "prereqs"], env={}, root=root, run=gh)
    out, _ = capsys.readouterr()
    return code, out


GITHUB = ["--backend", "github", "--url", URL]


def test_the_command_exits_0_when_only_optional_checks_are_missing(
    capsys, tmp_path, ready, monkeypatch
):
    monkeypatch.setattr("delivery.prereqs.shutil.which", lambda cmd: f"/usr/bin/{cmd}")
    monkeypatch.setattr("delivery.prereqs.runs_quietly", lambda args: True)
    (tmp_path / ".env.example").write_text("")
    ready.answers["secret list"] = secrets("ANTHROPIC_API_KEY")

    code, out = prereqs(capsys, tmp_path, ready, *GITHUB)

    assert code == 0
    assert "○ Slack" in out
    assert "✔ the machine" in out


def test_the_command_exits_1_when_anything_required_is_missing(
    capsys, tmp_path, ready, monkeypatch
):
    monkeypatch.setattr("delivery.prereqs.shutil.which", lambda cmd: f"/usr/bin/{cmd}")
    monkeypatch.setattr("delivery.prereqs.runs_quietly", lambda args: True)
    (tmp_path / ".env.example").write_text("")
    api_answer(ready, API, allow_merge_commit=True)

    code, out = prereqs(capsys, tmp_path, ready, *GITHUB)

    assert code == 1
    assert "✗ squash merges only" in out


def test_the_local_backend_needs_only_the_machine(capsys, issues_root, gh, monkeypatch):
    monkeypatch.setattr("delivery.prereqs.shutil.which", lambda cmd: f"/usr/bin/{cmd}")
    monkeypatch.setattr("delivery.prereqs.runs_quietly", lambda args: True)
    (issues_root / ".env.example").write_text("")

    code, out = prereqs(capsys, issues_root, gh)

    assert code == 0
    assert out.strip().splitlines() == ["✔ the machine — everything a run needs is here"]
    assert gh.calls == []
