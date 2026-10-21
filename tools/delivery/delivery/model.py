"""An issue, as every backend holds it, and the interface every backend implements."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class Issue:
    """One issue, whichever backend holds it.

    `key` names it across backends — `issue-8` locally, `gh-5` on GitHub — and is
    what branches, worktrees and plan folders are named from. `title` and `body`
    are kept apart: each backend renders them its own way, and the body is the
    exemplar's sections with no title and no number in it.
    """

    key: str
    number: int
    title: str
    body: str
    url: str
    labels: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PullRequest:
    """An open pull request, as the backend holds it."""

    number: int
    url: str
    draft: bool


class Backend(Protocol):
    """Where issues live. Every method raises `BackendError` when it can't do its job."""

    #: Whether a delivery's approval can end in a PR here. One that can't raises on every
    #: PR method, saying how to open one by hand.
    opens_pull_requests: bool

    def check(self) -> None:
        """Fails unless this backend can take a new issue — before anyone spends a grilling on it."""

    def create(self, title: str, body: str, labels: Sequence[str] = ()) -> Issue:
        """A new issue, returned as the backend now holds it, not as it was sent."""

    def get(self, key: str) -> Issue: ...

    def edit(self, key: str, title: str, body: str) -> Issue:
        """Replaces the title and body; returns the issue as the backend now holds it."""

    def ensure_label(self, name: str, description: str, color: str) -> None:
        """Creates the label, or updates it if it exists. A backend with no labels does nothing."""

    def find_pull_request(self, head: str) -> PullRequest | None:
        """The open PR from branch `head`, if there is one."""

    def open_pull_request(self, head: str, base: str, title: str, body: str) -> PullRequest: ...

    def update_pull_request(
        self,
        number: int,
        *,
        title: str | None = None,
        body: str | None = None,
        draft: bool | None = None,
    ) -> PullRequest:
        """Changes what is given — title and body together, or draft and ready — and
        returns the PR as the backend now holds it."""

    def comment_on_pull_request(self, number: int, body: str) -> None: ...

    def start_preview(self, number: int) -> None:
        """Starts the PR's preview, which holds itself open for the review."""

    def blob_url(self, sha: str, path: str) -> str:
        """Where a file at a commit is served raw, so an image shows inline."""
