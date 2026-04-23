import json
import pytest
from pathlib import Path
from src import reject_list as rl
from src import removed_list as reml

def test_reject_list_missing_file(tmp_path):
    path = tmp_path / "non_existent.json"
    assert rl.load_rejected_repo_refs(path) == set()

def test_reject_list_invalid_json(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("not json", encoding="utf-8")
    assert rl.load_rejected_repo_refs(path) == set()

def test_reject_list_update(tmp_path):
    path = tmp_path / "rejected.json"
    # Use keyword argument 'add' as expected by update_rejected_projects
    rl.update_rejected_projects(path, add=[{"full_name": "owner/repo", "reason": "Test reason"}])
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["rejected"][0]["full_name"] == "owner/repo"
    assert data["rejected"][0]["reason"] == "Test reason"

def test_removed_list_missing_file(tmp_path):
    path = tmp_path / "non_existent.json"
    assert reml.load_removed_repo_refs(path) == set()

def test_removed_list_invalid_json(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("not json", encoding="utf-8")
    assert reml.load_removed_repo_refs(path) == set()

def test_removed_list_valid(tmp_path):
    path = tmp_path / "removed.json"
    path.write_text(json.dumps({"removed": [{"full_name": "old/repo", "html_url": "https://github.com/old/repo"}]}))
    refs = reml.load_removed_repo_refs(path)
    assert "https://github.com/old/repo" in refs
    assert "old/repo" in refs
