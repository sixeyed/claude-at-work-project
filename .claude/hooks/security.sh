#!/usr/bin/env bash
# Stop hook: the end-of-turn security pass.
#
# Advisory, never blocking — it always exits 0 and reports what it found as a
# system message. False positives here would stall a session, and the judgement
# about whether a finding matters is the developer's.
#
# Four checks, measured on this repo (108 Python files, ~16k lines):
#
#   ruff --select S       ~0.1s   flake8-bandit, the static security rules
#   conventions.py        ~0.3s   the CollabHub rules no generic tool knows
#   gitleaks              ~0.6s   credentials in the working tree
#   semgrep               ~2.9s   p/python + p/secrets
#
# About 4 seconds against a 60s hook budget, so nothing is scoped down to
# changed files except conventions.py, which is about the work in progress by
# definition. gitleaks and semgrep are skipped if not installed rather than
# failing the pass:
#
#   brew install gitleaks     # semgrep runs via uvx, no install needed
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO" || exit 0

# Claude is already responding to a previous Stop hook; don't pile on.
if python3 -c '
import json, sys
try:
    sys.exit(0 if json.load(sys.stdin).get("stop_hook_active") else 1)
except (json.JSONDecodeError, ValueError):
    sys.exit(1)
' 2>/dev/null; then
    exit 0
fi

findings=""
section() {
    [ -n "$2" ] || return 0
    findings="${findings}
## $1
$2
"
}

# 1. flake8-bandit over the tree. Fast enough not to bother scoping. Keyed on
# the exit code, not the output: a clean run still prints "All checks passed!".
if ! ruff_out=$(uv run --quiet ruff check --select S --output-format concise . 2>/dev/null); then
    section "ruff (flake8-bandit)" "$ruff_out"
fi

# 2. The CollabHub conventions, over everything changed since HEAD.
conv_out=$(python3 "$REPO/.claude/hooks/checks/conventions.py" 2>/dev/null)
section "CollabHub conventions" "$conv_out"

# 3. Credentials in the working tree. gitleaks writes its report to a file —
# --report-path /dev/stdout silently produces nothing — so round-trip it.
if command -v gitleaks >/dev/null 2>&1; then
    report=$(mktemp -t gitleaks)
    gitleaks dir . --no-banner --redact --exit-code 0 \
        --report-format csv --report-path "$report" >/dev/null 2>&1
    leaks=$(tail -n +2 "$report" 2>/dev/null | cut -d, -f1,3,7 | sed 's/,/ /g')
    rm -f "$report"
    section "gitleaks" "$leaks"
fi

# 4. semgrep's Python and secrets rulesets. --metrics=off keeps it local.
if command -v uvx >/dev/null 2>&1; then
    raw=$(mktemp -t semgrep)
    uvx --quiet --from semgrep semgrep \
        --config p/python --config p/secrets \
        --metrics=off --quiet --no-git-ignore \
        --json src/services >"$raw" 2>/dev/null
    sem=$(python3 "$REPO/.claude/hooks/checks/semgrep_report.py" "$raw" 2>/dev/null)
    rm -f "$raw"
    section "semgrep" "$sem"
fi

if [ -z "$findings" ]; then
    printf '{"systemMessage": "Security pass clean: ruff-bandit, conventions, gitleaks, semgrep.", "suppressOutput": true}\n'
    exit 0
fi

# Hand the findings back as a system message. Advisory: the turn still ends.
python3 -c '
import json, sys
body = sys.stdin.read().strip()
print(json.dumps({
    "systemMessage": "Security pass found something worth a look:\n" + body,
    "suppressOutput": False,
}))
' <<< "$findings"
exit 0
