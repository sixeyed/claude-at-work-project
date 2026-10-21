"""The PR an accepted delivery opens, made from its proof (handoff 09, decisions 6 and 7).

The proof is already shaped as a PR body, and every word of the body stays the
acceptance-reviewer's: the runner only makes it readable on GitHub. The proof links its
screenshots relative to itself, into build/acceptance/, which only a worktree has; the
runner commits the ones it cites and links each at that commit instead. The agent never
sees a SHA or a URL.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

#: Where the proof's links into the evidence start, relative to docs/plans/<key>/.
EVIDENCE_LINK = "../../../build/acceptance/"
IMAGES = (".png", ".jpg", ".jpeg", ".gif", ".webp")
LINK = re.compile(r"(!?)\[([^\]]*)\]\(([^)\s]+)\)")
SQUASH_NOTE = (
    "Squash merge this PR: its screenshots are in two commits of their own, and only a"
    " squash keeps them out of `main`'s history."
)


def cited_screenshots(proof: str) -> list[str]:
    """The images the proof links into build/acceptance/, as paths under it, each once."""
    cited: list[str] = []
    for match in LINK.finditer(proof):
        path = evidence_path(match.group(3))
        if path and path.lower().endswith(IMAGES) and path not in cited:
            cited.append(path)
    return cited


def evidence_path(target: str) -> str:
    """The path under build/acceptance/ a link points at, or "" for anything else —
    including a link that climbs back out of it."""
    if not target.startswith(EVIDENCE_LINK):
        return ""
    path = target[len(EVIDENCE_LINK) :]
    return "" if ".." in path.split("/") else path


def pr_title(issue_title: str, key: str) -> str:
    return f"{issue_title} ({key})"


def pr_body(proof: str, *, issue_number: int, links: Mapping[str, str]) -> str:
    """The proof as a PR body. `links` maps each cited screenshot to where it is served."""
    lines = proof.splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    text = "\n".join(lines).strip("\n")
    text = LINK.sub(lambda m: relink(m, links), text)
    text = show_screenshots(text, unshown(proof, text, links))
    text = collapse_run(text)
    return f"{text.rstrip()}\n\n---\n\nCloses #{issue_number}\n\n{SQUASH_NOTE}\n"


def unshown(proof: str, body: str, links: Mapping[str, str]) -> list[tuple[str, str, str]]:
    """(label, path, url) for each screenshot the proof only links to — a reviewer reads the
    PR, so each is shown as well, labelled as the proof first linked it."""
    found = []
    for match in LINK.finditer(proof):
        path = evidence_path(match.group(3))
        url = links.get(path)
        shown = url and re.search(rf"!\[[^\]]*\]\({re.escape(url)}\)", body)
        if url and not shown and all(seen != path for _, seen, _ in found):
            found.append((match.group(2), path, url))
    return found


def show_screenshots(text: str, shots: list[tuple[str, str, str]]) -> str:
    """Appends `shots` to the Screenshots section, or adds that section before For the human
    — or at the end, without one."""
    if not shots:
        return text
    shown = "\n\n".join(
        f"**{label}** · `{path}`\n\n![{label}]({url})" for label, path, url in shots
    )
    section = re.search(r"^## Screenshots[ \t]*\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    if section:
        at = section.end()
        return f"{text[:at].rstrip()}\n\n{shown}\n\n{text[at:].lstrip()}".rstrip()
    human = re.search(r"^## For the human", text, re.MULTILINE)
    at = human.start() if human else len(text)
    return f"{text[:at].rstrip()}\n\n## Screenshots\n\n{shown}\n\n{text[at:]}".rstrip()


def relink(match: re.Match[str], links: Mapping[str, str]) -> str:
    bang, label, target = match.groups()
    if not target.startswith(EVIDENCE_LINK):
        return match.group(0)
    path = evidence_path(target)
    if path in links:
        return f"{bang}[{label}]({links[path]})"
    # Nothing serves the rest of build/acceptance/: say where it was, as text.
    where = f"build/acceptance/{path}"
    return f"`{where}`" if label.strip() in (where, path, "") else f"{label} (`{where}`)"


def collapse_run(text: str) -> str:
    """`## The run`, to the next section or the end, folded into <details>."""
    match = re.search(r"^## The run[ \t]*\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    if match is None:
        return text
    folded = f"<details><summary>The run</summary>\n\n{match.group(1).strip()}\n\n</details>\n\n"
    return text[: match.start()] + folded + text[match.end() :]
