#!/usr/bin/env python3
"""Helpers for loading and updating the repository reject list."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = REPO_ROOT / "data" / "rejected_projects.json"


def normalize_repo_ref(value: str) -> str:
    text = (value or "").strip().rstrip("/")
    return text.lower()


def _entry_refs(entry: dict[str, Any]) -> set[str]:
    refs: set[str] = set()
    full_name = normalize_repo_ref(str(entry.get("full_name") or ""))
    html_url = normalize_repo_ref(str(entry.get("html_url") or ""))
    if full_name:
        refs.add(full_name)
    if html_url:
        refs.add(html_url)
    return refs


def load_rejected_entries(path: Path = DEFAULT_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get("rejected") or []
    if not isinstance(entries, list):
        return []
    result: list[dict[str, Any]] = []
    for item in entries:
        if isinstance(item, dict):
            result.append(item)
    return result


def load_rejected_repo_refs(path: Path = DEFAULT_PATH) -> set[str]:
    refs: set[str] = set()
    for entry in load_rejected_entries(path):
        refs.update(_entry_refs(entry))
    return refs


def update_rejected_projects(
    path: Path = DEFAULT_PATH,
    *,
    add: list[dict[str, Any]] | None = None,
    remove: list[str] | None = None,
    default_source: str = "",
    default_reason: str = "",
) -> dict[str, Any]:
    existing_entries = load_rejected_entries(path)
    remove_refs = {normalize_repo_ref(value) for value in (remove or []) if normalize_repo_ref(value)}

    updated_entries: list[dict[str, Any]] = []
    for entry in existing_entries:
        if _entry_refs(entry) & remove_refs:
            continue
        updated_entries.append(entry)

    existing_refs = set().union(*(_entry_refs(entry) for entry in updated_entries)) if updated_entries else set()
    for candidate in add or []:
        full_name = normalize_repo_ref(str(candidate.get("full_name") or ""))
        html_url = normalize_repo_ref(str(candidate.get("html_url") or ""))
        refs = {ref for ref in (full_name, html_url) if ref}
        if not refs or refs & existing_refs:
            continue

        updated_entries.append(
            {
                "full_name": str(candidate.get("full_name") or "").strip(),
                "name": str(candidate.get("name") or str(candidate.get("full_name") or "").split("/")[-1]).strip(),
                "html_url": str(candidate.get("html_url") or "").strip().rstrip("/"),
                "description": str(candidate.get("description") or "").strip(),
                "source": str(candidate.get("source") or default_source).strip(),
                "reason": str(candidate.get("reason") or default_reason).strip(),
                "rejected_at": str(candidate.get("rejected_at") or datetime.now(timezone.utc).isoformat()),
            }
        )
        existing_refs.update(refs)

    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rejected_count": len(updated_entries),
        "rejected": updated_entries,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return data
