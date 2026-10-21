"""`delivery prereqs`: what a delivery needs, checked — docs/delivery/prerequisites.md says why.

Each check is one of the doc's sections, linked by its anchor, so a missing one prints where
the fix is. It reads names and settings only, never a secret's value: `gh secret list` gives
names, and the repo's settings come from the REST API as the signed-in `gh` user. Settings an
admin alone may read fail with GitHub's own reason.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from delivery.errors import BackendError
from delivery.github import GitHubBackend
from delivery.run.preflight import problems, runs_quietly

DOC = "docs/delivery/prerequisites.md"
OK, MISSING, OPTIONAL = "ok", "missing", "optional"
MARKS = {OK: "✔", MISSING: "✗", OPTIONAL: "○"}
ANCHORS = (
    "the-machine",
    "gh-signed-in",
    "the-repo",
    "claudes-secret",
    "actions-may-open-pull-requests",
    "squash-merges-only",
    "the-workflows-on-the-default-branch",
    "slack-optional",
)
CLAUDE_SECRETS = ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY")
SLACK = ("SLACK_BOT_TOKEN", "SLACK_CHANNEL")
WORKFLOWS = ("deliver.yml", "preview.yml")


@dataclass(frozen=True)
class Check:
    name: str
    state: str
    detail: str
    anchor: str


def machine_checks(
    backend: str,
    *,
    env: Mapping[str, str],
    root: Path,
    which: Callable[[str], str | None] | None = None,
    runs: Callable[[list[str]], bool] | None = None,
) -> list[Check]:
    """The runner's own pre-flight, plus htpasswd where Slack gives previews a password."""
    which = which or shutil.which
    found = problems(backend, root=root, which=which, runs=runs or runs_quietly)
    if all(env.get(name) for name in SLACK) and which("htpasswd") is None:
        found.append(
            "'htpasswd' is not on PATH — with Slack set up, each preview's password needs it"
        )
    if found:
        return [Check("the machine", MISSING, "; ".join(found), "the-machine")]
    return [Check("the machine", OK, "everything a run needs is here", "the-machine")]


def github_checks(backend: GitHubBackend) -> list[Check]:
    """The repo's side. Signed out, nothing else can be read, so that is all it reports."""
    host = urlsplit(backend.url).netloc
    api = f"repos/{urlsplit(backend.url).path.strip('/')}"

    def get(path: str) -> Any:
        return json.loads(backend.run(["gh", "api", path, "--hostname", host], None) or "{}")

    try:
        login = backend.run(["gh", "api", "user", "--hostname", host, "--jq", ".login"], None)
    except BackendError as e:
        return [Check("gh, signed in", MISSING, str(e), "gh-signed-in")]
    found = [Check("gh, signed in", OK, f"signed in as {login.strip()}", "gh-signed-in")]
    found.append(attempt("the repo", "the-repo", lambda: repo(backend)))
    found.append(attempt("Actions", "the-repo", lambda: actions(get(f"{api}/actions/permissions"))))
    try:
        names = {s["name"] for s in json.loads(backend.run(secret_list(backend), None) or "[]")}
    except BackendError as e:
        names = None
        why = f"can't list the repo's secrets: {e}"
        found += [Check("Claude's secret", MISSING, why, "claudes-secret")]
        found += [Check("Slack", MISSING, why, "slack-optional")]
    if names is not None:
        found += [claude_secret(names), slack(names)]
    found.append(
        attempt(
            "Actions may open pull requests",
            "actions-may-open-pull-requests",
            lambda: may_open_prs(get(f"{api}/actions/permissions/workflow")),
        )
    )
    try:
        settings = get(api)
    except BackendError as e:
        settings = e
    found.append(attempt("squash merges only", "squash-merges-only", lambda: merges(settings)))
    found.append(
        attempt(
            "the workflows, on the default branch",
            "the-workflows-on-the-default-branch",
            lambda: workflows(settings, lambda path: get(f"{api}/{path}")),
        )
    )
    return found


def attempt(name: str, anchor: str, check: Callable[[], tuple[str, str]]) -> Check:
    try:
        state, detail = check()
    except BackendError as e:
        state, detail = MISSING, str(e)
    return Check(name, state, detail, anchor)


def secret_list(backend: GitHubBackend) -> list[str]:
    return ["gh", "secret", "list", "--repo", backend.repo, "--json", "name"]


def repo(backend: GitHubBackend) -> tuple[str, str]:
    backend.check()
    return OK, "issues on, and you can write to it"


def actions(found: dict) -> tuple[str, str]:
    if found.get("enabled"):
        return OK, "enabled"
    return MISSING, "Actions are turned off for the repo"


def claude_secret(names: set[str]) -> Check:
    have = [n for n in CLAUDE_SECRETS if n in names]
    if have:
        return Check("Claude's secret", OK, f"{have[0]} is set", "claudes-secret")
    detail = f"neither {' nor '.join(CLAUDE_SECRETS)} is set — a stub run needs neither"
    return Check("Claude's secret", MISSING, detail, "claudes-secret")


def slack(names: set[str]) -> Check:
    have = [n for n in SLACK if n in names]
    if len(have) == len(SLACK):
        return Check("Slack", OK, "both secrets are set", "slack-optional")
    if not have:
        detail = "not set up — nothing is posted, and previews keep the shared password collabhub"
        return Check("Slack", OPTIONAL, detail, "slack-optional")
    other = next(n for n in SLACK if n not in names)
    return Check(
        "Slack", MISSING, f"{have[0]} is set but {other} isn't — set both", "slack-optional"
    )


def may_open_prs(found: dict) -> tuple[str, str]:
    if found.get("can_approve_pull_request_reviews"):
        return OK, "allowed"
    return MISSING, "the job's token can't open the delivery's PR"


def merges(settings: dict | BackendError) -> tuple[str, str]:
    if isinstance(settings, BackendError):
        raise settings
    wrong = [
        text
        for setting, bad, text in (
            ("allow_merge_commit", True, "merge commits are allowed"),
            ("allow_rebase_merge", True, "rebase merges are allowed"),
            ("allow_squash_merge", False, "squash merges are off"),
            ("delete_branch_on_merge", False, "head branches aren't deleted on merge"),
        )
        if bool(settings.get(setting)) == bad
    ]
    if wrong:
        return MISSING, "; ".join(wrong)
    return OK, "squash only, and head branches are deleted"


def workflows(settings: dict | BackendError, get: Callable[[str], Any]) -> tuple[str, str]:
    if isinstance(settings, BackendError):
        raise settings
    branch = settings.get("default_branch") or "main"
    missing = []
    for name in WORKFLOWS:
        try:
            get(f"contents/.github/workflows/{name}?ref={branch}")
        except BackendError:
            missing.append(name)
    if missing:
        return MISSING, f"not on {branch}: {', '.join(missing)}"
    return OK, f"{' and '.join(WORKFLOWS)} are on {branch}"


def render(checks: list[Check]) -> str:
    lines = []
    for check in checks:
        lines.append(f"{MARKS[check.state]} {check.name} — {check.detail}")
        if check.state == MISSING:
            lines.append(f"    fix: {DOC}#{check.anchor}")
    return "\n".join(lines)
