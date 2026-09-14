#!/usr/bin/env python3
"""Static checks for the CollabHub conventions that generic linters cannot know.

Every rule here comes from CLAUDE.md or `docs/design/00-platform-conventions.md`.
Ruff, semgrep and gitleaks catch the language-level and credential problems; these
catch the ones that are only wrong *in this codebase* — a workspace id read from
the path instead of the token claim, a 403 that confirms a resource exists, an
`OFFSET` in a user-facing list.

Run it on specific files, or with no arguments to check everything changed since
HEAD (what the Stop hook does):

    python3 .claude/hooks/checks/conventions.py [file.py ...]

Every finding can be waived on its own line, or the line above it, with

    # conventions: ok — <why>

Exit status is 1 when anything is reported, 0 when clean.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]

# Names that carry a user identity or their words. `userId` alone is allowed by
# the logging convention; everything here is not.
PII_KEYS = frozenset(
    {"email", "password", "secret", "token", "body", "text", "phone", "ip", "address", "name"}
)
LOG_METHODS = frozenset({"debug", "info", "warning", "warn", "error", "exception", "critical"})
EXC_NAMES = frozenset({"exc", "e", "err", "error", "ex", "exception"})
ROUTER_OBJECTS = frozenset({"router", "app", "internal_router", "internal"})
HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options"})

# `messages` keeps deleted rows as tombstones and `channels` archives instead of
# soft-deleting, so neither read path filters `deleted_at` — Conventions §3, and
# docs 02 §3.1.4 and §4.
SOFT_DELETE_EXEMPT = frozenset({"Message", "Channel"})

WAIVER = "conventions: ok"


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    rule: str
    message: str

    def __str__(self) -> str:
        rel = self.path.relative_to(REPO) if self.path.is_relative_to(REPO) else self.path
        return f"{rel}:{self.line}: {self.rule} {self.message}"


def _decorator_route(node: ast.AST) -> str | None:
    """The path of an `@router.get("/x")`-style decorator, or None."""
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return None
    if node.func.attr not in HTTP_METHODS:
        return None
    value = node.func.value
    if not isinstance(value, ast.Name) or value.id not in ROUTER_OBJECTS:
        return None
    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
        return node.args[0].value
    return ""


def _depends_names(func: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """Names passed to `Depends(...)` anywhere in the signature."""
    names: set[str] = set()
    args = func.args
    for default in [*args.defaults, *args.kw_defaults]:
        if not isinstance(default, ast.Call):
            continue
        if not (isinstance(default.func, ast.Name) and default.func.id == "Depends"):
            continue
        for dep in default.args:
            if isinstance(dep, ast.Name):
                names.add(dep.id)
            elif isinstance(dep, ast.Call) and isinstance(dep.func, ast.Name):
                names.add(dep.func.id)
    return names


def _param_names(func: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    a = func.args
    return {arg.arg for arg in [*a.posonlyargs, *a.args, *a.kwonlyargs]}


def _compares_param_to_claim(func: ast.AST, params: set[str]) -> bool:
    """Does this function body compare one of `params` against a `.workspace_id`?"""
    for node in ast.walk(func):
        if not isinstance(node, ast.Compare):
            continue
        operands = [node.left, *node.comparators]
        names = {n.id for o in operands for n in ast.walk(o) if isinstance(n, ast.Name)}
        claims = {a.attr for o in operands for a in ast.walk(o) if isinstance(a, ast.Attribute)}
        if names & params and "workspace_id" in claims:
            return True
    return False


def _guard_helpers(tree: ast.Module) -> set[str]:
    """Module-level functions whose body compares an argument to the claim.

    Handlers usually delegate this to a one-line guard (`_same_workspace`), so
    the comparison is rarely in the handler itself.
    """
    helpers = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and _compares_param_to_claim(
            node, _param_names(node)
        ):
            helpers.add(node.name)
    return helpers


def _compared_to_claim(
    func: ast.FunctionDef | ast.AsyncFunctionDef, params: set[str], helpers: set[str]
) -> bool:
    """Is a request-supplied workspace id checked against the token claim?

    Auth's own membership routes take the workspace in the path and refuse
    anything that is not the `wsp` claim (doc 01 §5). That comparison is exactly
    what makes taking it from the path safe, so it is not a leak.
    """
    if _compares_param_to_claim(func, params):
        return True
    for node in ast.walk(func):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in helpers
            and any(isinstance(a, ast.Name) and a.id in params for a in node.args)
        ):
            return True
    return False


def _in_not_found_branch(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> bool:
    """Is this call inside an `if <something> is None` / `if not <something>` branch?

    That is the shape of the mistake: a lookup came back empty and the handler
    answers 403, which confirms to the caller that the row exists somewhere.
    A role check on a resource already fetched is a different thing and stays
    silent.
    """
    current: ast.AST = node
    while current in parents:
        parent = parents[current]
        if isinstance(parent, ast.If) and current in parent.body:
            for test in ast.walk(parent.test):
                if (
                    isinstance(test, ast.UnaryOp)
                    and isinstance(test.op, ast.Not)
                    and isinstance(test.operand, ast.Name | ast.Attribute)
                ):
                    return True
                if isinstance(test, ast.Compare) and any(
                    isinstance(c, ast.Constant) and c.value is None for c in test.comparators
                ):
                    return True
        current = parent
    return False


def _is_exc_ref(node: ast.AST) -> bool:
    """Does this expression carry exception or traceback text?"""
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id in EXC_NAMES:
            return True
        if isinstance(child, ast.Attribute) and child.attr in {"format_exc", "__traceback__"}:
            return True
    return False


def _parents(tree: ast.Module) -> dict[ast.AST, ast.AST]:
    parents: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    return parents


def _enclosing_stmt(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> ast.AST:
    current = node
    while current in parents and not isinstance(current, ast.stmt):
        current = parents[current]
    return current


@lru_cache(maxsize=32)
def _soft_delete_models(models_file: Path) -> frozenset[str]:
    """Classes in a service's models.py that declare a `deleted_at` column."""
    try:
        tree = ast.parse(models_file.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return frozenset()
    found = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for stmt in node.body:
            target = stmt.target if isinstance(stmt, ast.AnnAssign) else None
            if isinstance(target, ast.Name) and target.id == "deleted_at":
                found.add(node.name)
    return frozenset(found)


def _models_for(path: Path) -> frozenset[str]:
    for parent in path.parents:
        candidate = parent / "models.py"
        if candidate.exists():
            return _soft_delete_models(candidate)
        if parent == REPO:
            break
    return frozenset()


def _waived(lines: list[str], line_no: int) -> bool:
    """Is the marker on this line, or anywhere in the comment block above it?"""
    index = line_no - 1
    if 0 <= index < len(lines) and WAIVER in lines[index]:
        return True
    index -= 1
    while index >= 0 and lines[index].strip().startswith("#"):
        if WAIVER in lines[index]:
            return True
        index -= 1
    return False


def check_file(path: Path) -> list[Finding]:  # noqa: C901 — one branch per rule, read top to bottom
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, SyntaxError):
        return []

    lines = source.splitlines()
    parents = _parents(tree)
    helpers = _guard_helpers(tree)
    soft_delete = _models_for(path)
    findings: list[Finding] = []

    def report(node: ast.AST, rule: str, message: str) -> None:
        line = getattr(node, "lineno", 1)
        if not _waived(lines, line):
            findings.append(Finding(path, line, rule, message))

    for node in ast.walk(tree):
        # --- route-handler rules -------------------------------------------
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            routes = [
                r for r in (_decorator_route(d) for d in node.decorator_list) if r is not None
            ]
            if routes:
                deps = _depends_names(node)
                user_auth = {"require_user", "require_user_sensitive"} & deps
                service_auth = "require_service" in deps

                if user_auth and service_auth:
                    report(
                        node,
                        "CH002",
                        f"`{node.name}` puts user auth and require_service on one route; "
                        "internal routes are a separate audience (Conventions §5.5).",
                    )

                is_internal = any("/internal" in route for route in routes) or (
                    "internal" in str(path).lower() and "routers" in str(path).lower()
                )
                if is_internal and not service_auth:
                    report(
                        node,
                        "CH003",
                        f"`{node.name}` looks like an internal endpoint but has no "
                        "`Depends(require_service(...))` (Conventions §5.5).",
                    )

                if user_auth:
                    leaked = {"workspace_id", "workspace", "workspace_slug"} & _param_names(node)
                    if leaked and not _compared_to_claim(node, leaked, helpers):
                        report(
                            node,
                            "CH001",
                            f"`{node.name}` takes {min(leaked)} from the request. "
                            "Authorization must read the `wsp` claim "
                            "(`principal.workspace_id`) — taking it from the path or body "
                            "is a tenancy leak.",
                        )

        if not isinstance(node, ast.Call):
            continue

        func = node.func
        attr = func.attr if isinstance(func, ast.Attribute) else None
        name = func.id if isinstance(func, ast.Name) else None

        # --- CH004: a 403 confirms the resource exists ----------------------
        is_403 = attr == "forbidden" or (
            any(isinstance(a, ast.Constant) and a.value == 403 for a in node.args)
            and (name == "ProblemException" or attr in {"ProblemException", "_of"})
        )
        if not is_403 and name == "HTTPException":
            is_403 = any(
                kw.arg == "status_code"
                and isinstance(kw.value, ast.Constant)
                and kw.value.value == 403
                for kw in node.keywords
            )
        if is_403 and _in_not_found_branch(node, parents):
            report(
                node,
                "CH004",
                "403 answers a lookup that came back empty, which confirms the "
                "resource exists to someone with no access. Return 404 "
                "(CLAUDE.md, Conventions §4.2).",
            )

        # --- CH005: cursor pagination only ----------------------------------
        if attr == "offset":
            report(
                node,
                "CH005",
                "user-facing lists are cursor-paginated; `OFFSET` is not allowed (Conventions §6).",
            )

        # --- CH006: SQL built by string interpolation -----------------------
        if name == "text" or attr in {"execute", "exec_driver_sql"}:
            for arg in node.args:
                interpolated = isinstance(arg, ast.JoinedStr) or (
                    isinstance(arg, ast.BinOp) and isinstance(arg.op, ast.Mod)
                )
                if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Attribute):
                    interpolated = interpolated or arg.func.attr == "format"
                if interpolated:
                    report(
                        node,
                        "CH006",
                        "SQL assembled by string interpolation. Bind parameters instead.",
                    )
                    break

        # --- CH007: Problem Details must not carry internals ----------------
        for kw in node.keywords:
            if kw.arg == "detail" and _is_exc_ref(kw.value):
                report(
                    node,
                    "CH007",
                    "`detail` carries exception or traceback text. Problem Details "
                    "are client-facing — never put internal messages in them "
                    "(Conventions §4).",
                )

        # --- CH008: no PII in structured logs -------------------------------
        if attr in LOG_METHODS:
            for kw in node.keywords:
                if kw.arg and kw.arg.lower().replace("_", "") in PII_KEYS:
                    report(
                        node,
                        "CH008",
                        f"log field `{kw.arg}` looks like PII or message content. "
                        "Logs carry no PII beyond user IDs (Conventions §12).",
                    )

        # --- CH009: soft-deleted rows must be filtered out ------------------
        if name == "select" and node.args:
            target = node.args[0]
            model = (
                target.id
                if isinstance(target, ast.Name)
                else target.value.id
                if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name)
                else None
            )
            if model in soft_delete and model not in SOFT_DELETE_EXEMPT:
                stmt = _enclosing_stmt(node, parents)
                has_filter = any(
                    isinstance(child, ast.Attribute) and child.attr == "deleted_at"
                    for child in ast.walk(stmt)
                )
                if not has_filter:
                    report(
                        node,
                        "CH009",
                        f"`select({model})` with no `deleted_at IS NULL` filter (Conventions §3).",
                    )

    return findings


def changed_python_files() -> list[Path]:
    """Python files that differ from HEAD, tracked or not."""
    try:
        tracked = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=d", "HEAD"],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    paths = [REPO / f for f in [*tracked, *untracked] if f.endswith(".py")]
    return [p for p in paths if p.exists()]


def main(argv: list[str]) -> int:
    files = [Path(a).resolve() for a in argv[1:]] if len(argv) > 1 else changed_python_files()
    files = [
        f
        for f in files
        if f.suffix == ".py" and "alembic" not in f.parts and "tests" not in f.parts
    ]

    findings = [f for path in files for f in check_file(path)]
    for finding in sorted(findings, key=lambda f: (str(f.path), f.line)):
        print(finding)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
