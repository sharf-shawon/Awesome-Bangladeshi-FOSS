#!/usr/bin/env python3
"""Generate a JSON index of projects from README.md."""

from __future__ import annotations

import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
README_PATH = REPO_ROOT / "README.md"
OUTPUT_PATH = REPO_ROOT / "data" / "projects.json"

ENTRY_RE = re.compile(r"^- \[(?P<name>[^\]]+)\]\((?P<link>[^)]+)\) - (?P<desc>.+)$")

PROJECT_SECTIONS = {
    "Web Applications",
    "Mobile Apps",
    "Developer Tools & Libraries",
    "Government & Utility Services",
    "Fintech & Payments",
    "Other FOSS Projects",
    "Awesome Lists & Resource Collections",
}


def generate_projects() -> dict[str, list[dict[str, str]]]:
    content = README_PATH.read_text(encoding="utf-8").splitlines()
    current_section: str | None = None
    projects: list[dict[str, str]] = []

    for raw_line in content:
        line = raw_line.strip()

        if line.startswith("## "):
            section = line[3:].strip()
            current_section = section if section in PROJECT_SECTIONS else None
            continue

        if not current_section:
            continue

        match = ENTRY_RE.match(line)
        if not match:
            continue

        projects.append(
            {
                "category": current_section,
                "name": match.group("name").strip(),
                "repository": match.group("link").strip(),
                "description": match.group("desc").strip(),
            }
        )

    return {"projects": projects}


def main() -> int:
    if not README_PATH.exists():
        raise FileNotFoundError(f"README not found at {README_PATH}")

    data = generate_projects()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Generated {OUTPUT_PATH.relative_to(REPO_ROOT)} with {len(data['projects'])} projects")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
