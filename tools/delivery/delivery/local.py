"""The local backend: an issue is `docs/issues/NNN.md`, as `scripts/deliver.sh` reads it."""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

from delivery.errors import BackendError
from delivery.model import Issue, PullRequest

ISSUES = Path("docs/issues")
KEY = re.compile(r"issue-([0-9]+)")
#: A local issue's branch goes to the forge, where a person opens its PR.
NO_PULL_REQUESTS = (
    "the local backend opens no pull request — open it by hand from the proof, with `tea pr create`"
)
#: `# Issue 8 — Better mobile experience`: the heading every local issue opens with.
HEADING = re.compile(r"^# Issue [0-9]+ — (.+)$", re.MULTILINE)


class LocalBackend:
    """Issues as files in the repo. Keys are `issue-N`, so every plan, branch and
    worktree made before backends existed keeps its name."""

    opens_pull_requests = False

    def __init__(self, root: Path) -> None:
        self.root = root

    @property
    def issues(self) -> Path:
        return self.root / ISSUES

    def check(self) -> None:
        if not self.issues.is_dir():
            raise BackendError(f"{ISSUES} does not exist under {self.root}")

    def create(self, title: str, body: str, labels: Sequence[str] = ()) -> Issue:
        # A file has nowhere to keep a label; the marker is for remote backends.
        self.check()
        numbers = [int(p.stem) for p in self.issues.glob("*.md") if p.stem.isdigit()]
        return self._write(max(numbers, default=0) + 1, title, body)

    def get(self, key: str) -> Issue:
        number = self._number(key)
        path = self._path(number)
        if not path.is_file():
            raise BackendError(f"{key} does not exist — no {ISSUES / path.name}")
        text = path.read_text()
        heading = HEADING.search(text)
        if heading is None:
            raise BackendError(f"{ISSUES / path.name} has no '# Issue {number} — <title>' heading")
        body = text[heading.end() :].strip("\n") + "\n"
        return self._issue(number, heading.group(1).strip(), body)

    def edit(self, key: str, title: str, body: str) -> Issue:
        number = self._number(key)
        self.get(key)
        return self._write(number, title, body)

    def ensure_label(self, name: str, description: str, color: str) -> None:
        """Nothing to do: local issues carry no labels."""

    def find_pull_request(self, head: str) -> PullRequest | None:
        raise BackendError(NO_PULL_REQUESTS)

    def open_pull_request(self, head: str, base: str, title: str, body: str) -> PullRequest:
        raise BackendError(NO_PULL_REQUESTS)

    def update_pull_request(
        self,
        number: int,
        *,
        title: str | None = None,
        body: str | None = None,
        draft: bool | None = None,
    ) -> PullRequest:
        raise BackendError(NO_PULL_REQUESTS)

    def comment_on_pull_request(self, number: int, body: str) -> None:
        raise BackendError(NO_PULL_REQUESTS)

    def start_preview(self, number: int) -> None:
        raise BackendError(NO_PULL_REQUESTS)

    def blob_url(self, sha: str, path: str) -> str:
        raise BackendError(NO_PULL_REQUESTS)

    def _write(self, number: int, title: str, body: str) -> Issue:
        body = body.strip("\n") + "\n"
        self._path(number).write_text(f"Issue: {number}\n\n# Issue {number} — {title}\n\n{body}")
        return self._issue(number, title, body)

    def _issue(self, number: int, title: str, body: str) -> Issue:
        return Issue(
            key=f"issue-{number}",
            number=number,
            title=title,
            body=body,
            url=str(ISSUES / self._path(number).name),
            labels=[],
        )

    def _path(self, number: int) -> Path:
        return self.issues / f"{number:03d}.md"

    @staticmethod
    def _number(key: str) -> int:
        match = KEY.fullmatch(key)
        if match is None:
            raise BackendError(f"'{key}' is not a local issue key — they look like issue-N")
        return int(match.group(1))
