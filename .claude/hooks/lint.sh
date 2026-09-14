#!/usr/bin/env bash
# PostToolUse hook (Write|Edit|Bash): lint and format the files that just changed.
#
# Blocking by design. Exit 2 hands the remaining errors back to Claude as
# something to fix before it moves on, which is the right trade for lint:
# the findings are mechanical and always fixable. The end-of-turn security
# pass in security.sh is the advisory one.
#
# Write and Edit name one file. Bash is here because a heredoc, `sed -i` or a
# redirect changes files just as surely as the Edit tool does — Claude Code
# reports those in `tool_response.bashEditDiff.changedFiles` (it needs
# `bashEditDiff` on, which is the default when Bash handles file edits).
# A Bash command that touched no files costs one python startup and exits.
#
# Scoped to the files that changed, so it costs 50-300ms for Python and about
# a second for TypeScript, rather than linting the tree on every edit.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# The hook payload arrives on stdin. Write reports the path it wrote in
# tool_response; Edit only has it in tool_input; Bash lists everything the
# command changed.
files=$(python3 -c '
import json, sys

try:
    payload = json.load(sys.stdin)
except (json.JSONDecodeError, ValueError):
    sys.exit(0)

response = payload.get("tool_response")
response = response if isinstance(response, dict) else {}
paths = []

diff = response.get("bashEditDiff")
if isinstance(diff, dict):
    # changedFiles is the whole list; files[] is capped for a big diff.
    changed = diff.get("changedFiles")
    if isinstance(changed, list):
        paths += [p for p in changed if isinstance(p, str)]
    else:
        paths += [
            f.get("filePath")
            for f in diff.get("files", [])
            if isinstance(f, dict) and f.get("filePath")
        ]

single = response.get("filePath") or payload.get("tool_input", {}).get("file_path")
if single:
    paths.append(single)

seen = set()
for path in paths:
    if path not in seen:
        seen.add(path)
        print(path)
' 2>/dev/null)

[ -n "$files" ] || exit 0

problems=""
note() {
    problems="${problems}
${1}"
}

while IFS= read -r file; do
    # Skip deletes, renames away, and paths we could not read.
    [ -n "$file" ] && [ -f "$file" ] || continue

    case "$file" in
        *.py)
            cd "$REPO" || exit 0
            # Format and autofix silently — those need no conversation — then
            # report whatever is left.
            uv run --quiet ruff format "$file" >/dev/null 2>&1
            uv run --quiet ruff check --fix --quiet "$file" >/dev/null 2>&1
            if ! output=$(uv run --quiet ruff check "$file" 2>&1); then
                note "$(printf 'ruff found problems in %s that it could not fix:\n\n%s' \
                    "${file#"$REPO"/}" "$output")"
            fi
            ;;
        *.ts|*.tsx)
            cd "$REPO/src/frontend" || exit 0
            # A checkout with no npm install yet should not block every edit.
            [ -x node_modules/.bin/eslint ] || continue
            node_modules/.bin/eslint --fix "$file" >/dev/null 2>&1
            if ! output=$(node_modules/.bin/eslint --max-warnings 0 "$file" 2>&1); then
                note "$(printf 'eslint found problems in %s that it could not fix:\n\n%s' \
                    "${file#"$REPO"/}" "$output")"
            fi
            ;;
    esac
done <<< "$files"

if [ -n "${problems// /}" ]; then
    printf '%s\n' "$problems" >&2
    exit 2
fi
exit 0
