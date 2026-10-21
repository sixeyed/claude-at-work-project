"""The local backend: `docs/issues/NNN.md`, exactly as `deliver.sh` reads it today."""

from __future__ import annotations

import re

import pytest
from delivery.errors import BackendError
from delivery.local import LocalBackend
from delivery.model import Issue

BODY = "## Summary\n\nPins a message.\n\n## Requirements\n\n1. At most one pin.\n"


def test_a_new_issue_takes_the_number_after_the_highest(issues_root):
    """The exemplar is issue 0 and isn't counted; gaps are not filled."""
    issue = LocalBackend(issues_root).create("Pin a message", BODY)

    assert (issue.key, issue.number) == ("issue-9", 9)
    assert (issues_root / "docs/issues/009.md").exists()


def test_the_first_issue_is_1(tmp_path):
    (tmp_path / "docs/issues").mkdir(parents=True)

    assert LocalBackend(tmp_path).create("First", BODY).key == "issue-1"


def test_the_file_is_rendered_as_deliver_sh_reads_it(issues_root):
    LocalBackend(issues_root).create("Pin a message", BODY)

    text = (issues_root / "docs/issues/009.md").read_text()
    assert text == f"Issue: 9\n\n# Issue 9 — Pin a message\n\n{BODY}"


def test_deliver_sh_finds_the_number_in_the_first_20_lines(issues_root):
    """The same grep `scripts/deliver.sh` runs on the issue file."""
    LocalBackend(issues_root).create("Pin a message", BODY)

    head = "\n".join((issues_root / "docs/issues/009.md").read_text().splitlines()[:20])
    match = re.search(r"issue[\s:#]*[0-9]+", head, re.IGNORECASE)
    assert match is not None
    assert re.search(r"[0-9]+", match.group()).group() == "9"


def test_create_returns_what_get_reads_back(issues_root):
    backend = LocalBackend(issues_root)

    created = backend.create("Pin a message", BODY)

    assert backend.get("issue-9") == created
    assert created == Issue(
        key="issue-9",
        number=9,
        title="Pin a message",
        body=BODY,
        url="docs/issues/009.md",
        labels=[],
    )


def test_labels_are_ignored_locally(issues_root):
    """A file has nowhere to keep a label; the marker is for remote backends."""
    assert LocalBackend(issues_root).create("Pin", BODY, labels=["delivery"]).labels == []


def test_an_existing_issue_reads_in_todays_format(issues_root):
    issue = LocalBackend(issues_root).get("issue-8")

    assert issue.title == "Better mobile experience"
    assert issue.body == "## Summary\n\nCollabHub works on a phone.\n"


def test_edit_rewrites_the_file_in_place(issues_root):
    backend = LocalBackend(issues_root)
    backend.create("Pin a message", BODY)

    edited = backend.edit("issue-9", "Pin messages", "## Summary\n\nPins several.\n")

    assert edited.title == "Pin messages"
    assert backend.get("issue-9").body == "## Summary\n\nPins several.\n"
    assert sorted(p.name for p in (issues_root / "docs/issues").iterdir()) == [
        "001.md",
        "008.md",
        "009.md",
        "exemplar-issue.md",
    ]


def test_an_issue_that_does_not_exist_is_a_backend_error(issues_root):
    with pytest.raises(BackendError, match="issue-42"):
        LocalBackend(issues_root).get("issue-42")


@pytest.mark.parametrize("key", ["gh-8", "8", "issue-", "issue-x"])
def test_a_key_that_is_not_a_local_key_is_a_backend_error(issues_root, key):
    with pytest.raises(BackendError, match="issue-N"):
        LocalBackend(issues_root).get(key)


def test_check_passes_with_docs_issues(issues_root):
    LocalBackend(issues_root).check()


def test_check_fails_without_docs_issues(tmp_path):
    with pytest.raises(BackendError, match="docs/issues"):
        LocalBackend(tmp_path).check()


def test_ensure_label_does_nothing_locally(issues_root):
    before = sorted((issues_root / "docs/issues").iterdir())

    LocalBackend(issues_root).ensure_label("delivery", "Written for delivery", "0e8a16")

    assert sorted((issues_root / "docs/issues").iterdir()) == before


# --- pull requests ---------------------------------------------------------


def test_it_opens_no_pull_requests(issues_root):
    assert LocalBackend(issues_root).opens_pull_requests is False


@pytest.mark.parametrize(
    "call",
    [
        lambda b: b.find_pull_request("feature/issue-8"),
        lambda b: b.open_pull_request("feature/issue-8", "main", "T", "B"),
        lambda b: b.update_pull_request(1, draft=True),
        lambda b: b.comment_on_pull_request(1, "B"),
        lambda b: b.start_preview(1),
        lambda b: b.blob_url("abc", "x.png"),
    ],
)
def test_every_pull_request_call_says_to_open_one_by_hand(issues_root, call):
    with pytest.raises(BackendError, match="tea pr create"):
        call(LocalBackend(issues_root))
