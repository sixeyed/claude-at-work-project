"""The acceptance-reviewer's preview, deployed by the workflow rather than the agent.

A cold build and three Helm waits can run past the longest command an agent's Bash tool
allows, and a deploy killed half-way leaves Helm mid-operation. Retried once, as a stage is.
The outcome reaches the agent as its `Preview:` line; it judges a failure — the branch's,
or the environment's. `scripts/deploy.sh preview up` does the work; this only calls it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from delivery.run.invoke import agent_env


def deploy_preview(
    worktree: Path,
    *,
    evidence: str,
    branch: str,
    deploy_sh: str,
    retry_wait: float,
    sleep: Callable[[float], None],
    log: Callable[[str], None],
    password: str = "",
) -> str:
    """Deploys the branch's preview and returns the `Preview:` line's text. A `password`
    is Dex's for this preview; without one it keeps the k3d values' own."""
    rel = f"{evidence}/preview-up.log"
    path = worktree / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("")
    # As the bash ran it from the worktree: a path with a slash is relative to it, a bare
    # name is found on PATH.
    if "/" in deploy_sh:
        deploy = deploy_sh if Path(deploy_sh).is_absolute() else str(worktree / deploy_sh)
    else:
        deploy = shutil.which(deploy_sh) or deploy_sh
    for attempt in (1, 2):
        log(f"deploying the preview of {branch} (try {attempt}, log: {rel})")
        with path.open("a") as out:
            try:
                code = subprocess.run(  # noqa: S603 — the repo's own script.
                    [deploy, "preview", "up"],
                    cwd=worktree,
                    env={
                        **agent_env(os.environ),
                        **({"PREVIEW_PASSWORD": password} if password else {}),
                    },
                    stdout=out,
                    stderr=subprocess.STDOUT,
                    check=False,
                ).returncode
            except OSError as e:
                # A missing or unrunnable script fails the try, as the bash's did.
                out.write(f"{deploy}: {e.strerror}\n")
                code = 127
        if code == 0:
            origins = [
                line[len("APP_ORIGIN=") :]
                for line in path.read_text().splitlines()
                if line.startswith("APP_ORIGIN=")
            ]
            return f"up at {origins[-1] if origins else ''} — log: {rel}"
        if attempt == 1:
            sleep(retry_wait)
    log(f"the preview of {branch} failed twice — the acceptance-reviewer will judge why")
    return f"failed twice — log: {rel}"
