"""Tests for scripts/reject_list.py."""

from __future__ import annotations

import json

import reject_list as rl


def test_load_rejected_entries_missing_file_returns_empty(tmp_path):
    assert rl.load_rejected_entries(tmp_path / "missing.json") == []


def test_load_rejected_entries_non_list_returns_empty(tmp_path):
    path = tmp_path / "rejected.json"
    path.write_text(json.dumps({"rejected": {}}), encoding="utf-8")
    assert rl.load_rejected_entries(path) == []


def test_update_rejected_projects_remove_entry(tmp_path):
    path = tmp_path / "rejected.json"
    rl.update_rejected_projects(
        path,
        add=[
            {
                "full_name": "owner/repo",
                "html_url": "https://github.com/owner/repo",
            }
        ],
    )
    payload = rl.update_rejected_projects(path, remove=["https://github.com/owner/repo"])
    assert payload["rejected_count"] == 0


def test_update_rejected_projects_skips_duplicates(tmp_path):
    path = tmp_path / "rejected.json"
    rl.update_rejected_projects(
        path,
        add=[
            {
                "full_name": "owner/repo",
                "html_url": "https://github.com/owner/repo",
            }
        ],
    )
    payload = rl.update_rejected_projects(
        path,
        add=[
            {
                "full_name": "owner/repo",
                "html_url": "https://github.com/owner/repo",
            }
        ],
    )
    assert payload["rejected_count"] == 1
