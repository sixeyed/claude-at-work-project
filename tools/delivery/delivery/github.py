"""The GitHub backend, through the `gh` CLI.

`gh` brings its own authentication — the developer's login locally, `GH_TOKEN`
in GitHub Actions — so there is no token handling here. Every call names the
repo as `HOST/OWNER/REPO`, which is all GitHub Enterprise needs.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable, Sequence
from urllib.parse import urlsplit

from delivery.errors import BackendError
from delivery.model import Issue, PullRequest

#: Runs a command with optional stdin and returns its stdout; raises
#: `BackendError` when the command fails.
Runner = Callable[[list[str], str | None], str]

#: GitHub refuses an issue body longer than this many characters.
BODY_LIMIT = 65536
KEY = re.compile(r"gh-([0-9]+)")
CAN_WRITE = frozenset({"ADMIN", "MAINTAIN", "WRITE"})
ISSUE_FIELDS = "number,title,body,url,labels"
PR_FIELDS = "number,url,isDraft"
#: The workflow that previews a PR, dispatched because a PR opened with GITHUB_TOKEN fires
#: no `pull_request` workflow.
PREVIEW_WORKFLOW = "preview.yml"


def run_gh(args: list[str], input: str | None = None) -> str:  # noqa: A002
    try:
        done = subprocess.run(  # noqa: S603 — fixed program, argument list.
            args, input=input, capture_output=True, text=True, check=False
        )
    except FileNotFoundError as e:
        raise BackendError("the GitHub backend needs the gh CLI on PATH") from e
    if done.returncode != 0:
        raise BackendError(done.stderr.strip() or f"{' '.join(args[:3])} failed")
    return done.stdout


class GitHubBackend:
    """Issues on a GitHub repo. Keys are `gh-N`."""

    opens_pull_requests = True

    def __init__(self, url: str, run: Runner | None = None) -> None:
        parts = urlsplit(url)
        self.url = url
        self.repo = f"{parts.netloc}{parts.path}"
        self.run = run or run_gh

    def check(self) -> None:
        found = json.loads(
            self._gh(["repo", "view", self.repo, "--json", "hasIssuesEnabled,viewerPermission"])
        )
        if not found.get("hasIssuesEnabled"):
            raise BackendError(f"{self.url} has issues turned off")
        if found.get("viewerPermission") not in CAN_WRITE:
            raise BackendError(
                f"you need write access to {self.url} to create issues and labels"
                f" — you have {found.get('viewerPermission') or 'none'}"
            )

    def create(self, title: str, body: str, labels: Sequence[str] = ()) -> Issue:
        check_length(body)
        args = ["issue", "create", "--repo", self.repo, "--title", title, "--body-file", "-"]
        for label in labels:
            args += ["--label", label]
        created = self._gh(args, body).strip()
        number = created.rsplit("/", 1)[-1]
        if not number.isdigit():
            raise BackendError(f"gh issue create printed no issue URL: {created!r}")
        # Read back, rather than echo the draft: the issue as GitHub now holds it.
        return self.get(f"gh-{number}")

    def get(self, key: str) -> Issue:
        number = self._number(key)
        found = json.loads(
            self._gh(["issue", "view", str(number), "--repo", self.repo, "--json", ISSUE_FIELDS])
        )
        return Issue(
            key=f"gh-{found['number']}",
            number=found["number"],
            title=found["title"],
            body=found["body"],
            url=found["url"],
            labels=[label["name"] for label in found["labels"]],
        )

    def edit(self, key: str, title: str, body: str) -> Issue:
        number = self._number(key)
        args = ["issue", "edit", str(number), "--repo", self.repo, "--title", title]
        self._gh([*args, "--body-file", "-"], body)
        return self.get(key)

    def ensure_label(self, name: str, description: str, color: str) -> None:
        args = ["label", "create", name, "--repo", self.repo, "--description", description]
        self._gh([*args, "--color", color, "--force"])

    def find_pull_request(self, head: str) -> PullRequest | None:
        args = ["pr", "list", "--repo", self.repo, "--head", head, "--state", "open"]
        found = json.loads(self._gh([*args, "--json", PR_FIELDS]) or "[]")
        return pull_request(found[0]) if found else None

    def open_pull_request(self, head: str, base: str, title: str, body: str) -> PullRequest:
        check_length(body)
        args = ["pr", "create", "--repo", self.repo, "--head", head, "--base", base]
        created = self._gh([*args, "--title", title, "--body-file", "-"], body).strip()
        number = created.rsplit("/", 1)[-1]
        if not number.isdigit():
            raise BackendError(f"gh pr create printed no PR URL: {created!r}")
        return self._pull_request(int(number))

    def update_pull_request(
        self,
        number: int,
        *,
        title: str | None = None,
        body: str | None = None,
        draft: bool | None = None,
    ) -> PullRequest:
        if title is not None or body is not None:
            args = ["pr", "edit", str(number), "--repo", self.repo]
            if title is not None:
                args += ["--title", title]
            if body is not None:
                check_length(body)
                args += ["--body-file", "-"]
            self._gh(args, body)
        if draft is not None:
            undo = ["--undo"] if draft else []
            self._gh(["pr", "ready", str(number), "--repo", self.repo, *undo])
        return self._pull_request(number)

    def comment_on_pull_request(self, number: int, body: str) -> None:
        self._gh(["pr", "comment", str(number), "--repo", self.repo, "--body-file", "-"], body)

    def start_preview(self, number: int) -> None:
        args = ["workflow", "run", PREVIEW_WORKFLOW, "--repo", self.repo]
        self._gh([*args, "-f", f"pr={number}"])

    def blob_url(self, sha: str, path: str) -> str:
        return f"{self.url.rstrip('/')}/blob/{sha}/{path}?raw=true"

    def _pull_request(self, number: int) -> PullRequest:
        args = ["pr", "view", str(number), "--repo", self.repo, "--json", PR_FIELDS]
        return pull_request(json.loads(self._gh(args)))

    def _gh(self, args: list[str], stdin: str | None = None) -> str:
        return self.run(["gh", *args], stdin)

    @staticmethod
    def _number(key: str) -> int:
        match = KEY.fullmatch(key)
        if match is None:
            raise BackendError(f"'{key}' is not a GitHub issue key — they look like gh-N")
        return int(match.group(1))


def check_length(body: str) -> None:
    if len(body) > BODY_LIMIT:
        raise BackendError(f"the body is {len(body)} characters; GitHub takes at most {BODY_LIMIT}")


def pull_request(found: dict) -> PullRequest:
    return PullRequest(number=found["number"], url=found["url"], draft=bool(found["isDraft"]))
