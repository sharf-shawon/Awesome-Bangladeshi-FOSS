#!/usr/bin/env python3
"""Process project removal issues into README and removed-list updates."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any

import requests

from removed_list import update_removed_projects


REPO_ROOT = Path(__file__).resolve().parents[1]
README_PATH = REPO_ROOT / "README.md"
REMOVED_LIST_PATH = REPO_ROOT / "data" / "removed_projects.json"
API_BASE = "https://api.github.com"

GITHUB_REPO_RE = re.compile(r"^https://github\.com/[^/\s)]+/[^/\s)#]+/?$")
ENTRY_RE = re.compile(r"^- \[(?P<name>[^\]]+)\]\((?P<link>[^)]+)\) - (?P<desc>.+)$")
FIELD_RE = re.compile(r"^### (?P<label>.+)$", re.MULTILINE)


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def extract_field(issue_body: str, label: str) -> str:
    matches = list(FIELD_RE.finditer(issue_body))
    for idx, match in enumerate(matches):
        if match.group("label").strip() != label:
            continue
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(issue_body)
        value = issue_body[start:end].strip()
        value = re.sub(r"^\s*- \[x\]\s*", "", value, flags=re.IGNORECASE | re.MULTILINE)
        return normalize_whitespace(value)
    return ""


def parse_removal_request(issue_body: str) -> tuple[str, str]:
    repo_url = extract_field(issue_body, "Repository URL")
    reason = extract_field(issue_body, "Reason for removal")

    if not repo_url:
        raise ValueError("Missing required field: Repository URL")
    if not GITHUB_REPO_RE.match(repo_url):
        raise ValueError("Repository URL must be in the format https://github.com/owner/repo")
    if not reason:
        raise ValueError("Missing required field: Reason for removal")
    if len(reason) > 400:
        raise ValueError("Reason for removal must be concise (400 characters max)")
    return repo_url.rstrip("/"), reason


def extract_owner_repo(repo_url: str) -> str:
    parts = repo_url.rstrip("/").split("/")
    return "/".join(parts[-2:])


def build_session() -> requests.Session:
    session = requests.Session()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "awesome-bd-foss-removal",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    session.headers.update(headers)
    return session


def fetch_repo_metadata(session: requests.Session, owner_repo: str) -> dict[str, Any] | None:
    response = session.get(f"{API_BASE}/repos/{owner_repo}", timeout=30)
    if response.status_code >= 400:
        return None
    return response.json()


def remove_entry_from_readme(readme_text: str, repo_url: str) -> tuple[str, dict[str, str]]:
    target = repo_url.rstrip("/").lower()
    lines = readme_text.splitlines()
    current_section = ""

    for idx, raw_line in enumerate(lines):
        line = raw_line.strip()
        if line.startswith("## "):
            current_section = line[3:].strip()
            continue
        match = ENTRY_RE.match(line)
        if not match:
            continue
        link = match.group("link").strip().rstrip("/").lower()
        if link != target:
            continue

        removed_entry = {
            "name": match.group("name").strip(),
            "html_url": match.group("link").strip().rstrip("/"),
            "description": match.group("desc").strip(),
            "category": current_section,
        }
        del lines[idx]
        return "\n".join(lines) + "\n", removed_entry

    raise ValueError("Repository is not currently listed in README")


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
    issue_author = os.environ.get("ISSUE_AUTHOR", "").strip()

    if not issue_body.strip():
        print("ISSUE_BODY is empty")
        return 1
    if not issue_author:
        print("ISSUE_AUTHOR is empty")
        return 1

    try:
        repo_url, reason = parse_removal_request(issue_body)
    except ValueError as exc:
        print(f"Removal validation failed: {exc}")
        return 1

    owner_repo = extract_owner_repo(repo_url)
    session = build_session()
    metadata = fetch_repo_metadata(session, owner_repo)
    if metadata is None:
        print("Removal validation failed: could not verify repository metadata from GitHub")
        return 1

    repo_owner = str((metadata.get("owner") or {}).get("login") or "").strip()
    owner_verified = bool(repo_owner) and repo_owner.lower() == issue_author.lower()

    if not README_PATH.exists():
        print(f"README not found: {README_PATH}")
        return 1

    readme_text = README_PATH.read_text(encoding="utf-8")
    try:
        updated_readme, removed_entry = remove_entry_from_readme(readme_text, repo_url)
    except ValueError as exc:
        print(f"README update failed: {exc}")
        return 1

    README_PATH.write_text(updated_readme, encoding="utf-8")

    update_removed_projects(
        REMOVED_LIST_PATH,
        add=[
            {
                "full_name": owner_repo,
                "name": removed_entry["name"],
                "html_url": removed_entry["html_url"],
                "description": removed_entry["description"],
                "category": removed_entry["category"],
                "reason": reason,
                "requested_by": issue_author,
                "repo_owner": repo_owner,
                "owner_verified": owner_verified,
            }
        ],
    )

    branch_name = f"automation/project-removal-{issue_number or 'manual'}"
    pr_title = f"Remove {owner_repo} from awesome list{f' #{issue_number}' if issue_number else ''}"
    owner_line = "Repository owner verification: passed." if owner_verified else "Repository owner verification: not passed."
    pr_body = (
        "Automated PR generated from project removal issue"
        f" #{issue_number}.\n\n"
        f"Requested repository: {repo_url}\n"
        f"Reason: {reason}\n"
        f"Requested by: @{issue_author}\n"
        f"Repository owner: @{repo_owner or 'unknown'}\n"
        f"{owner_line}\n\n"
        f"Closes #{issue_number}."
        if issue_number
        else (
            "Automated PR generated from project removal issue.\n\n"
            f"Requested repository: {repo_url}\n"
            f"Reason: {reason}\n"
            f"Requested by: @{issue_author}\n"
            f"Repository owner: @{repo_owner or 'unknown'}\n"
            f"{owner_line}"
        )
    )

    write_output("branch_name", branch_name)
    write_output("pr_title", pr_title)
    write_output("pr_body", pr_body)
    write_output("owner_verified", "true" if owner_verified else "false")
    write_output("repo_url", repo_url)

    print(f"Prepared removal update for issue {issue_number or 'manual'}")
    print(f"Repository owner verified: {'yes' if owner_verified else 'no'}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
