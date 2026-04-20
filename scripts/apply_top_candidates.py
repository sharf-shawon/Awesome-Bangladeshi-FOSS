#!/usr/bin/env python3
"""Apply ranked candidates to README and data/projects.json-compatible source.

Usage:
  python scripts/apply_top_candidates.py --input data/top10_to_add.json --readme README.md --pr-body-output data/monthly_pr_body.md

Notes:
  - Inserts entries in alphabetical order inside each section.
  - Enforces the repository entry format:
      - [Name](https://github.com/owner/repo) - Short, meaningful description.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from reject_list import normalize_repo_ref, update_rejected_projects

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = REPO_ROOT / "data" / "top10_to_add.json"
DEFAULT_README = REPO_ROOT / "README.md"
DEFAULT_PR_BODY = REPO_ROOT / "data" / "monthly_pr_body.md"
DEFAULT_REJECTS = REPO_ROOT / "data" / "rejected_projects.json"

ENTRY_RE = re.compile(r"^- \[(?P<name>[^\]]+)\]\((?P<link>[^)]+)\) - (?P<desc>.+)$")
GITHUB_REPO_RE = re.compile(r"^https://github\.com/[^/\s)]+/[^/\s)#]+/?$")

ALLOWED_SECTIONS = {
    "Web Applications",
    "Mobile Apps",
    "Developer Tools & Libraries",
    "Government & Utility Services",
    "Fintech & Payments",
    "Other FOSS Projects",
    "Awesome Lists & Resource Collections",
}
SECTION_MAP = {
    "Datasets & Resources": "Awesome Lists & Resource Collections",
}


def normalize_section(section: str) -> str:
    section = (section or "").strip()
    if section in ALLOWED_SECTIONS:
        return section
    return SECTION_MAP.get(section, "Other FOSS Projects")


def normalize_repo_url(url: str) -> str:
    return (url or "").strip().rstrip("/")


def shorten_description(description: str, max_chars: int = 120) -> str:
    text = re.sub(r"\s+", " ", (description or "").strip())
    if not text:
        return "Open source project related to Bangladesh or Bangla language."
    if len(text) <= max_chars:
        if text[-1] not in ".!?":
            return text + "."
        return text
    cut = text[: max_chars - 1].rstrip()
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    cut = cut.rstrip(".,;:!?")
    return f"{cut}."


def build_entry(name: str, url: str, description: str) -> str:
    final_url = normalize_repo_url(url)
    if not GITHUB_REPO_RE.match(final_url):
        raise ValueError(f"Invalid GitHub repository URL: {url}")
    final_desc = shorten_description(description)
    return f"- [{name}]({final_url}) - {final_desc}"


def load_existing_links(lines: list[str]) -> set[str]:
    existing: set[str] = set()
    for line in lines:
        match = ENTRY_RE.match(line.strip())
        if match:
            existing.add(normalize_repo_url(match.group("link")).lower())
    return existing


def insert_entry_in_section(lines: list[str], section: str, entry: str) -> tuple[list[str], bool]:
    section_start = None
    section_end = None
    for idx, line in enumerate(lines):
        if line.strip() == f"## {section}":
            section_start = idx
            continue
        if section_start is not None and line.startswith("## "):
            section_end = idx
            break

    if section_start is None:
        raise ValueError(f"Section not found: {section}")
    if section_end is None:
        section_end = len(lines)

    section_lines = lines[section_start + 1 : section_end]
    entries: list[tuple[int, str]] = []
    for offset, line in enumerate(section_lines):
        match = ENTRY_RE.match(line.strip())
        if not match:
            continue
        entries.append((section_start + 1 + offset, match.group("name").strip()))

    entry_match = ENTRY_RE.match(entry)
    if not entry_match:
        raise ValueError("Invalid entry format")
    target_name = entry_match.group("name").strip()

    insert_at = section_end
    for line_index, existing_name in entries:
        if existing_name.casefold() > target_name.casefold():
            insert_at = line_index
            break

    updated = list(lines)
    updated.insert(insert_at, entry)
    return updated, True


def _entry_url(item: dict[str, Any]) -> str:
    return str(item.get("url") or item.get("html_url") or "").strip()


def build_pr_body(month_tag: str, added_entries: list[dict[str, Any]]) -> str:
    lines = [
        f"## Summary",
        "",
        f"This automated monthly discovery run for **{month_tag}**:",
        "- Discovered candidates from GitHub location/topic search.",
        "- Augmented candidates from social/web mentions.",
        "- Applied hard filters and AI-assisted ranking.",
        "- Prepared a review bundle for manual selection.",
        "",
        "## Review instructions",
        "",
        "Edit `data/top10_to_add.json` and keep only the repositories you want in the `selected` array.",
        "Anything removed from `selected` will be added to `data/rejected_projects.json` after merge.",
        "",
        "## Proposed additions",
        "",
    ]
    if not added_entries:
        lines.append("- No new high-quality repositories passed all filters this month.")
    else:
        for entry in added_entries:
            lines.append(f"- [{entry['name']}]({_entry_url(entry)}) — {entry['description']}")
    lines += [
        "",
        "## Notes",
        "",
        "- These additions are suggestions only and require manual inspection before merge.",
        "- Category and descriptions can be adjusted by maintainers during review.",
    ]
    return "\n".join(lines) + "\n"


def _entry_ref(item: dict[str, Any]) -> str:
    return normalize_repo_ref(str(item.get("html_url") or item.get("full_name") or ""))


def split_selected_and_rejected(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    proposed = payload.get("proposed") or payload.get("selected") or []
    selected = payload["selected"] if "selected" in payload else proposed
    selected_refs = {_entry_ref(item) for item in selected if _entry_ref(item)}

    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for item in proposed:
        ref = _entry_ref(item)
        if ref and ref in selected_refs:
            accepted.append(item)
        else:
            rejected.append(item)
    return accepted, rejected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Input top candidates JSON path")
    parser.add_argument("--readme", default=str(DEFAULT_README), help="README path")
    parser.add_argument("--pr-body-output", default=str(DEFAULT_PR_BODY), help="Generated PR body file path")
    parser.add_argument("--rejects", default=str(DEFAULT_REJECTS), help="Reject list JSON path")
    parser.add_argument("--review-only", action="store_true", help="Only generate the PR body without changing README")
    args = parser.parse_args()

    input_path = Path(args.input)
    readme_path = Path(args.readme)
    pr_body_path = Path(args.pr_body_output)
    pr_body_path.parent.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    if not readme_path.exists():
        raise FileNotFoundError(f"README not found: {readme_path}")

    payload = json.loads(input_path.read_text(encoding="utf-8"))
    selected = payload["selected"] if "selected" in payload else payload.get("proposed") or []

    lines = readme_path.read_text(encoding="utf-8").splitlines()
    existing_links = load_existing_links(lines)

    added_entries: list[dict[str, str]] = []
    if not args.review_only:
        accepted_entries, rejected_entries = split_selected_and_rejected(payload)
        for item in accepted_entries:
            url = normalize_repo_url(str(item.get("html_url") or ""))
            if not url or url.lower() in existing_links:
                continue
            name = str(item.get("name") or str(item.get("full_name", "")).split("/")[-1]).strip()
            description = str(item.get("description") or "").strip()
            section = normalize_section(str(item.get("category") or ""))
            entry = build_entry(name=name, url=url, description=description)
            lines, _ = insert_entry_in_section(lines, section, entry)
            existing_links.add(url.lower())
            match = ENTRY_RE.match(entry)
            added_entries.append(
                {
                    "name": name,
                    "url": url,
                    "description": match.group("desc").strip() if match else description,
                    "category": section,
                }
            )

        if added_entries:
            readme_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        update_rejected_projects(
            Path(args.rejects),
            add=[
                {
                    "full_name": item.get("full_name"),
                    "name": item.get("name"),
                    "html_url": item.get("html_url"),
                    "description": item.get("description"),
                    "source": item.get("source") or "monthly-discovery",
                    "reason": "Not selected in monthly discovery review.",
                }
                for item in rejected_entries
            ],
            default_source="monthly-discovery",
            default_reason="Not selected in monthly discovery review.",
        )

    month_tag = datetime.now(timezone.utc).strftime("%Y-%m")
    pr_body = build_pr_body(month_tag, payload.get("proposed") or selected)
    pr_body_path.write_text(pr_body, encoding="utf-8")

    if args.review_only:
        print(f"Prepared review bundle with {len(selected)} proposed candidates.")
    else:
        print(f"Applied {len(added_entries)} new candidate entries to README.")
    print(f"Generated PR body: {pr_body_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
