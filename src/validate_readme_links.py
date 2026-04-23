#!/usr/bin/env python3
"""Validate README entries for contribution rule compliance."""

from __future__ import annotations

import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
README_PATH = REPO_ROOT / "README.md"

ENTRY_RE = re.compile(r"^- \[(?P<name>[^\]]+)\]\((?P<link>[^)]+)\) - (?P<desc>.+)$")
GITHUB_REPO_RE = re.compile(r"^https://github\.com/[^/\s)]+/[^/\s)#]+/?$")


def main() -> int:
    if not README_PATH.exists():
        print(f"README file not found: {README_PATH}")
        return 1

    errors: list[str] = []
    seen_links: dict[str, int] = {}

    for line_number, raw_line in enumerate(README_PATH.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()

        match = ENTRY_RE.match(line)
        if not match:
            continue

        link = match.group("link").strip()

        if not GITHUB_REPO_RE.match(link):
            errors.append(
                f"Line {line_number}: link must be a GitHub repository URL in the format "
                f"https://github.com/owner/repo (found: {link})."
            )

        if link in seen_links:
            errors.append(
                f"Line {line_number}: duplicate link found (already used at line {seen_links[link]}): {link}"
            )
        else:
            seen_links[link] = line_number

    if errors:
        print("README validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("README validation passed.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
