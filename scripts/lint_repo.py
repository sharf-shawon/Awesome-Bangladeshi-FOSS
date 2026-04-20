#!/usr/bin/env python3
"""Run the repository lint checks used by CI and local git hooks."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKS = [
    ["npx", "-y", "awesome-lint", "README.md"],
    [sys.executable, str(REPO_ROOT / "scripts" / "validate_readme_links.py")],
]


def main() -> int:
    for command in CHECKS:
        completed = subprocess.run(command, cwd=REPO_ROOT)
        if completed.returncode != 0:
            return completed.returncode
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())