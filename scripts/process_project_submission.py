#!/usr/bin/env python3
"""Process project submission issues into README entries."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
README_PATH = REPO_ROOT / "README.md"

GITHUB_REPO_RE = re.compile(r"^https://github\.com/[^/\s)]+/[^/\s)#]+/?$")
ENTRY_RE = re.compile(r"^- \[(?P<name>[^\]]+)\]\((?P<link>[^)]+)\) - (?P<desc>.+)$")
FIELD_RE = re.compile(r"^### (?P<label>.+)$", re.MULTILINE)

ALLOWED_SECTIONS = {
    "Web Applications",
    "Mobile Apps",
    "Developer Tools & Libraries",
    "Government & Utility Services",
    "Fintech & Payments",
    "Other FOSS Projects",
    "Awesome Lists & Resource Collections",
}


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def extract_field(issue_body: str, label: str) -> str:
    matches = list(FIELD_RE.finditer(issue_body))
    for idx, match in enumerate(matches):
        current_label = match.group("label").strip()
        if current_label != label:
            continue
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(issue_body)
        value = issue_body[start:end].strip()
        value = re.sub(r"^\s*- \[x\]\s*", "", value, flags=re.IGNORECASE | re.MULTILINE)
        return normalize_whitespace(value)
    return ""


def parse_submission(issue_body: str) -> tuple[str, str, str, str]:
    project_name = extract_field(issue_body, "Project name")
    repo_url = extract_field(issue_body, "Repository URL")
    description = extract_field(issue_body, "Short description")
    category = extract_field(issue_body, "Category")

    if not project_name:
        raise ValueError("Missing required field: Project name")
    if not repo_url:
        raise ValueError("Missing required field: Repository URL")
    if not description:
        raise ValueError("Missing required field: Short description")
    if not category:
        raise ValueError("Missing required field: Category")

    if not GITHUB_REPO_RE.match(repo_url):
        raise ValueError(
            "Repository URL must be in the format https://github.com/owner/repo"
        )

    if category not in ALLOWED_SECTIONS:
        raise ValueError(f"Unsupported category: {category}")

    if len(description) > 220:
        raise ValueError("Short description must be concise (220 characters max)")

    return project_name, repo_url.rstrip("/"), description, category


def build_entry_line(name: str, repo_url: str, description: str) -> str:
    if not description.endswith((".", "!", "?")):
        description = f"{description}."
    return f"- [{name}]({repo_url}) - {description}"


def insert_entry_in_section(readme_text: str, section: str, entry: str) -> str:
    lines = readme_text.splitlines()

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
        raise ValueError(f"Section not found in README: {section}")
    if section_end is None:
        section_end = len(lines)

    section_lines = lines[section_start + 1 : section_end]
    entries: list[tuple[int, str, str]] = []
    for offset, line in enumerate(section_lines):
        match = ENTRY_RE.match(line.strip())
        if not match:
            continue
        entries.append((section_start + 1 + offset, match.group("name").strip(), match.group("link").strip()))

    entry_match = ENTRY_RE.match(entry)
    assert entry_match is not None
    new_name = entry_match.group("name").strip()
    new_link = entry_match.group("link").strip()

    for _, _, existing_link in entries:
        if existing_link.rstrip("/") == new_link.rstrip("/"):
            raise ValueError(f"Duplicate repository URL already exists in README: {new_link}")

    insert_at = section_end
    for line_idx, existing_name, _ in entries:
        if existing_name.casefold() > new_name.casefold():
            insert_at = line_idx
            break

    lines.insert(insert_at, entry)
    return "\n".join(lines) + "\n"


def write_output(name: str, value: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with Path(output_path).open("a", encoding="utf-8") as file:
        if "\n" in value:
            file.write(f"{name}<<EOF\n{value}\nEOF\n")
        else:
            file.write(f"{name}={value}\n")


def main() -> int:
    issue_body = os.environ.get("ISSUE_BODY", "")
    issue_number = os.environ.get("ISSUE_NUMBER", "")

    if not issue_body.strip():
        print("ISSUE_BODY is empty")
        return 1

    try:
        project_name, repo_url, description, category = parse_submission(issue_body)
    except ValueError as exc:
        print(f"Submission validation failed: {exc}")
        return 1

    if not README_PATH.exists():
        print(f"README not found: {README_PATH}")
        return 1

    entry = build_entry_line(project_name, repo_url, description)

    readme_text = README_PATH.read_text(encoding="utf-8")
    try:
        updated = insert_entry_in_section(readme_text, category, entry)
    except ValueError as exc:
        print(f"README update failed: {exc}")
        return 1

    if updated == readme_text:
        print("No README changes detected")
        return 1

    README_PATH.write_text(updated, encoding="utf-8")

    issue_suffix = f" #{issue_number}" if issue_number else ""
    pr_title = f"Add {project_name} to {category}{issue_suffix}"
    pr_body = (
        "Automated PR generated from project submission issue"
        f" #{issue_number}.\n\n"
        f"Proposed entry:\n\n{entry}\n\n"
        f"Closes #{issue_number}."
        if issue_number
        else f"Automated PR generated from project submission issue.\n\nProposed entry:\n\n{entry}"
    )

    branch_name = f"automation/project-submission-{issue_number or 'manual'}"
    write_output("branch_name", branch_name)
    write_output("pr_title", pr_title)
    write_output("pr_body", pr_body)
    write_output("entry", entry)

    print(f"Prepared README update for issue {issue_number or 'manual'}")
    print(f"New entry: {entry}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
