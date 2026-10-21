"""The GitHub backend: what it asks `gh` to do, and what it makes of the answer."""

from __future__ import annotations

import json

import pytest
from delivery.errors import BackendError
from delivery.github import BODY_LIMIT, GitHubBackend
from delivery.model import Issue, PullRequest

REPO_URL = "https://github.com/sixeyed/claude-at-work-project"
REPO = "github.com/sixeyed/claude-at-work-project"


@pytest.fixture
def backend(gh):
    return GitHubBackend(REPO_URL, run=gh)


# --- check -----------------------------------------------------------------


def test_check_asks_for_the_repo_by_host_owner_and_name(backend, gh):
    backend.check()

    args, _ = gh.call("repo view")
    assert args == ["gh", "repo", "view", REPO, "--json", "hasIssuesEnabled,viewerPermission"]


@pytest.mark.parametrize("permission", ["ADMIN", "MAINTAIN", "WRITE"])
def test_check_passes_for_a_viewer_who_can_write(gh, permission):
    gh.answers["repo view"] = json.dumps({"hasIssuesEnabled": True, "viewerPermission": permission})

    GitHubBackend(REPO_URL, run=gh).check()


@pytest.mark.parametrize("permission", ["TRIAGE", "READ", ""])
def test_check_fails_for_a_viewer_who_cannot_create_labels(gh, permission):
    gh.answers["repo view"] = json.dumps({"hasIssuesEnabled": True, "viewerPermission": permission})

    with pytest.raises(BackendError, match="write"):
        GitHubBackend(REPO_URL, run=gh).check()


def test_check_fails_when_issues_are_disabled(gh):
    gh.answers["repo view"] = json.dumps({"hasIssuesEnabled": False, "viewerPermission": "ADMIN"})

    with pytest.raises(BackendError, match="issues"):
        GitHubBackend(REPO_URL, run=gh).check()


def test_a_failing_gh_surfaces_as_a_backend_error(gh):
    gh.answers["repo view"] = BackendError("gh: Could not resolve to a Repository")

    with pytest.raises(BackendError, match="Could not resolve"):
        GitHubBackend(REPO_URL, run=gh).check()


def test_an_enterprise_host_is_passed_through(gh):
    GitHubBackend("https://git.example.com/team/project", run=gh).check()

    args, _ = gh.call("repo view")
    assert args[3] == "git.example.com/team/project"


# --- create ----------------------------------------------------------------


def test_create_sends_the_body_on_stdin_with_title_and_labels(backend, gh):
    backend.create("Pin a message", "## Summary\n\nPins.\n", labels=["delivery"])

    args, stdin = gh.call("issue create")
    assert args == [
        "gh",
        "issue",
        "create",
        "--repo",
        REPO,
        "--title",
        "Pin a message",
        "--body-file",
        "-",
        "--label",
        "delivery",
    ]
    assert stdin == "## Summary\n\nPins.\n"


def test_create_returns_the_issue_as_github_holds_it(backend, gh):
    """Read back by the number in the URL `gh issue create` prints — not the
    draft echoed back, which would prove nothing."""
    issue = backend.create("Pin a message", "## Summary\n\nPins.\n")

    args, _ = gh.call("issue view")
    assert args[:4] == ["gh", "issue", "view", "5"]
    assert issue == Issue(
        key="gh-5",
        number=5,
        title="Pin a message",
        body="## Summary\n\nPins.\n",
        url=f"{REPO_URL}/issues/5",
        labels=["delivery"],
    )


def test_a_body_over_githubs_limit_is_refused_before_gh_runs(backend, gh):
    with pytest.raises(BackendError, match=str(BODY_LIMIT)):
        backend.create("Too long", "x" * (BODY_LIMIT + 1))

    assert gh.calls == []


def test_a_body_at_githubs_limit_is_sent(backend, gh):
    backend.create("Just fits", "x" * BODY_LIMIT)

    gh.call("issue create")


# --- get and edit ----------------------------------------------------------


def test_get_asks_for_every_field_the_model_holds(backend, gh):
    backend.get("gh-5")

    args, _ = gh.call("issue view")
    assert args == [
        "gh",
        "issue",
        "view",
        "5",
        "--repo",
        REPO,
        "--json",
        "number,title,body,url,labels",
    ]


@pytest.mark.parametrize("key", ["issue-5", "5", "gh-", "gh-five"])
def test_a_key_that_is_not_a_github_key_is_refused_before_gh_runs(backend, gh, key):
    with pytest.raises(BackendError, match="gh-N"):
        backend.get(key)

    assert gh.calls == []


def test_edit_sends_the_new_title_and_body_then_reads_back(backend, gh, gh_issue):
    gh.answers["issue view"] = gh_issue(title="Pin messages", body="## Summary\n\nSeveral.\n")

    issue = backend.edit("gh-5", "Pin messages", "## Summary\n\nSeveral.\n")

    args, stdin = gh.call("issue edit")
    assert args == [
        "gh",
        "issue",
        "edit",
        "5",
        "--repo",
        REPO,
        "--title",
        "Pin messages",
        "--body-file",
        "-",
    ]
    assert stdin == "## Summary\n\nSeveral.\n"
    assert issue.title == "Pin messages"


# --- ensure_label ----------------------------------------------------------


def test_ensure_label_creates_or_updates_it(backend, gh):
    """`--force` makes it idempotent: an existing label is updated, not an error."""
    backend.ensure_label("delivery", "Written for scripts/deliver.sh", "0e8a16")

    args, _ = gh.call("label create")
    assert args == [
        "gh",
        "label",
        "create",
        "delivery",
        "--repo",
        REPO,
        "--description",
        "Written for scripts/deliver.sh",
        "--color",
        "0e8a16",
        "--force",
    ]


# --- pull requests ---------------------------------------------------------


def gh_pr(number: int = 12, draft: bool = False) -> str:
    """`gh pr view --json number,url,isDraft` output."""
    return json.dumps({"number": number, "url": f"{REPO_URL}/pull/{number}", "isDraft": draft})


def test_it_opens_pull_requests(backend):
    assert backend.opens_pull_requests is True


def test_finding_a_pull_request_asks_for_open_ones_by_head_branch(backend, gh):
    gh.answers["pr list"] = json.dumps(
        [{"number": 12, "url": f"{REPO_URL}/pull/12", "isDraft": True}]
    )

    found = backend.find_pull_request("feature/gh-3")

    args, _ = gh.call("pr list")
    assert args == [
        "gh", "pr", "list", "--repo", REPO, "--head", "feature/gh-3",
        "--state", "open", "--json", "number,url,isDraft",
    ]  # fmt: skip
    assert found == PullRequest(number=12, url=f"{REPO_URL}/pull/12", draft=True)


def test_no_open_pull_request_is_none(backend, gh):
    gh.answers["pr list"] = "[]"

    assert backend.find_pull_request("feature/gh-3") is None


def test_a_pull_request_is_opened_with_its_body_on_stdin_and_read_back(backend, gh):
    gh.answers["pr create"] = f"{REPO_URL}/pull/12\n"
    gh.answers["pr view"] = gh_pr(12)

    opened = backend.open_pull_request("feature/gh-3", "main", "Display names (gh-3)", "The body")

    args, stdin = gh.call("pr create")
    assert args == [
        "gh", "pr", "create", "--repo", REPO, "--head", "feature/gh-3", "--base", "main",
        "--title", "Display names (gh-3)", "--body-file", "-",
    ]  # fmt: skip
    assert stdin == "The body"
    view, _ = gh.call("pr view")
    assert view == ["gh", "pr", "view", "12", "--repo", REPO, "--json", "number,url,isDraft"]
    assert opened == PullRequest(number=12, url=f"{REPO_URL}/pull/12", draft=False)


def test_a_body_over_the_limit_is_refused_before_gh_is_asked(backend, gh):
    with pytest.raises(BackendError, match=str(BODY_LIMIT)):
        backend.open_pull_request("feature/gh-3", "main", "T", "x" * (BODY_LIMIT + 1))

    assert gh.calls == []


def test_updating_a_pull_request_edits_its_title_and_body(backend, gh):
    gh.answers["pr view"] = gh_pr(12)

    backend.update_pull_request(12, title="New title", body="New body")

    args, stdin = gh.call("pr edit")
    assert args == [
        "gh", "pr", "edit", "12", "--repo", REPO, "--title", "New title", "--body-file", "-",
    ]  # fmt: skip
    assert stdin == "New body"
    assert not [c for c in gh.calls if c[0][1:3] == ["pr", "ready"]]


@pytest.mark.parametrize(("draft", "undo"), [(True, ["--undo"]), (False, [])])
def test_a_pull_request_is_made_a_draft_or_ready(backend, gh, draft, undo):
    gh.answers["pr view"] = gh_pr(12, draft=draft)

    updated = backend.update_pull_request(12, draft=draft)

    args, _ = gh.call("pr ready")
    assert args == ["gh", "pr", "ready", "12", "--repo", REPO, *undo]
    assert not [c for c in gh.calls if c[0][1:3] == ["pr", "edit"]]
    assert updated.draft is draft


def test_a_comment_goes_on_the_pull_request_by_stdin(backend, gh):
    backend.comment_on_pull_request(12, "A redelivery is running.")

    args, stdin = gh.call("pr comment")
    assert args == ["gh", "pr", "comment", "12", "--repo", REPO, "--body-file", "-"]
    assert stdin == "A redelivery is running."


def test_the_preview_is_started_by_dispatching_its_workflow(backend, gh):
    backend.start_preview(12)

    args, _ = gh.call("workflow run")
    assert args == ["gh", "workflow", "run", "preview.yml", "--repo", REPO, "-f", "pr=12"]


def test_a_file_at_a_commit_is_linked_raw_so_an_image_shows_inline(backend):
    url = backend.blob_url("abc123", "docs/plans/gh-3/proof/feature/sign-in.png")

    assert url == f"{REPO_URL}/blob/abc123/docs/plans/gh-3/proof/feature/sign-in.png?raw=true"
