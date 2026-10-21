"""Fixtures for the delivery library's tests."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import pytest

REPO_URL = "https://github.com/sixeyed/claude-at-work-project"


def gh_issue(number: int = 5, title: str = "Pin a message", body: str = "## Summary\n\nPins.\n"):
    """`gh issue view --json number,title,body,url,labels` output."""
    return json.dumps(
        {
            "number": number,
            "title": title,
            "body": body,
            "url": f"{REPO_URL}/issues/{number}",
            "labels": [{"id": "LA_1", "name": "delivery", "description": "", "color": "0e8a16"}],
        }
    )


@dataclass
class FakeGh:
    """Stands in for the `gh` CLI: answers by subcommand, records every call.

    `answers` maps the first two words after `gh` (`"issue view"`) to stdout,
    or to an exception (a `BackendError`) to raise as a failing `gh` would — or to a list
    of those, answered in turn, the last one for every call after it.
    """

    answers: dict[str, str | Exception | list[str | Exception]] = field(default_factory=dict)
    calls: list[tuple[list[str], str | None]] = field(default_factory=list)

    def __call__(self, args: list[str], input: str | None = None) -> str:  # noqa: A002
        self.calls.append((list(args), input))
        answer = self.answers.get(" ".join(args[1:3]), "")
        if isinstance(answer, list):
            answer = answer.pop(0) if len(answer) > 1 else answer[0]
        if isinstance(answer, Exception):
            raise answer
        return answer

    def call(self, subcommand: str) -> tuple[list[str], str | None]:
        """The one call made with this subcommand; fails the test if not exactly one."""
        made = [c for c in self.calls if " ".join(c[0][1:3]) == subcommand]
        assert len(made) == 1, f"expected one `gh {subcommand}`, got {len(made)}: {self.calls}"
        return made[0]


@pytest.fixture(name="gh_issue")
def gh_issue_fixture():
    """Builds `gh issue view` output: `gh_issue(title=..., body=...)`."""
    return gh_issue


@pytest.fixture
def gh() -> FakeGh:
    return FakeGh(
        answers={
            "repo view": json.dumps({"hasIssuesEnabled": True, "viewerPermission": "ADMIN"}),
            "issue create": f"{REPO_URL}/issues/5\n",
            "issue view": gh_issue(),
            "issue edit": f"{REPO_URL}/issues/5\n",
            "label create": "",
        }
    )


@pytest.fixture
def issues_root(tmp_path):
    """A repo root with today's `docs/issues/`: the exemplar and two numbered issues."""
    issues = tmp_path / "docs" / "issues"
    issues.mkdir(parents=True)
    (issues / "exemplar-issue.md").write_text("# Issue 0 — The exemplar\n\nNot a real one.\n")
    (issues / "001.md").write_text("Issue: 1\n\n# Issue 1 — First\n\n## Summary\n\nOne.\n")
    (issues / "008.md").write_text(
        "Issue: 8\n\n# Issue 8 — Better mobile experience\n\n## Summary\n\nCollabHub works on a phone.\n"
    )
    return tmp_path
