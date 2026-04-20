"""Tests for scripts/removed_list.py."""

from __future__ import annotations

import json

import removed_list as rl


def test_load_removed_repo_refs_empty_when_file_missing(tmp_path):
    refs = rl.load_removed_repo_refs(tmp_path / "missing.json")
    assert refs == set()


def test_load_removed_entries_non_list_returns_empty(tmp_path):
    path = tmp_path / "removed_projects.json"
    path.write_text(json.dumps({"removed": {}}), encoding="utf-8")
    assert rl.load_removed_entries(path) == []


def test_update_removed_projects_adds_entry(tmp_path):
    path = tmp_path / "removed_projects.json"
    payload = rl.update_removed_projects(
        path,
        add=[
            {
                "full_name": "owner/repo",
                "name": "repo",
                "html_url": "https://github.com/owner/repo",
                "description": "desc",
                "category": "Other FOSS Projects",
                "reason": "requested",
                "requested_by": "requester",
                "repo_owner": "owner",
                "owner_verified": True,
            }
        ],
    )
    assert payload["removed_count"] == 1
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["removed"][0]["full_name"] == "owner/repo"


def test_update_removed_projects_skips_duplicates(tmp_path):
    path = tmp_path / "removed_projects.json"
    rl.update_removed_projects(
        path,
        add=[
            {
                "full_name": "owner/repo",
                "name": "repo",
                "html_url": "https://github.com/owner/repo",
                "description": "desc",
                "category": "Other FOSS Projects",
            }
        ],
    )
    payload = rl.update_removed_projects(
        path,
        add=[
            {
                "full_name": "owner/repo",
                "name": "repo",
                "html_url": "https://github.com/owner/repo",
                "description": "desc",
                "category": "Other FOSS Projects",
            }
        ],
    )
    assert payload["removed_count"] == 1
