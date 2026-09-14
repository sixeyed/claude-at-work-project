#!/usr/bin/env python3
"""Render semgrep's JSON as one line per finding, for the Stop hook's report."""

import json
import sys
from pathlib import Path

MAX_FINDINGS = 25


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        return 0
    try:
        report = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return 0

    for result in report.get("results", [])[:MAX_FINDINGS]:
        path = result.get("path", "?")
        line = result.get("start", {}).get("line", 0)
        check = result.get("check_id", "?")
        message = (result.get("extra", {}).get("message") or "").strip().splitlines()
        first = message[0] if message else ""
        print(f"{path}:{line}: {check} {first}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
