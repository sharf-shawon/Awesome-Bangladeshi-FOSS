import json
import os
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from src.process_issue import parse_issue, process_submission, process_removal, main

@pytest.fixture
def mock_data_paths(tmp_path):
    projects_path = tmp_path / "projects.json"
    removed_path = tmp_path / "removed_projects.json"
    rejected_path = tmp_path / "rejected_projects.json"
    config_path = tmp_path / "discovery_config.json"
    
    with open(projects_path, "w") as f:
        json.dump({"projects": []}, f)
    with open(removed_path, "w") as f:
        json.dump({"removed": []}, f)
    with open(rejected_path, "w") as f:
        json.dump({"rejected": []}, f)
    with open(config_path, "w") as f:
        json.dump({"minimum_stars": 10}, f)
        
    return {
        "PROJECTS_PATH": projects_path,
        "REMOVED_PATH": removed_path,
        "REJECTED_PATH": rejected_path,
        "CONFIG_PATH": config_path
    }

def test_parse_issue_submission():
    body = """
### Project name
My Awesome Project

### Repository URL
https://github.com/user/repo

### Short description
A very cool project.

### Category
Web Applications
"""
    fields = parse_issue(body)
    assert fields["project_name"] == "My Awesome Project"
    assert fields["repository_url"] == "https://github.com/user/repo"
    assert fields["short_description"] == "A very cool project."
    assert fields["category"] == "Web Applications"

def test_parse_issue_removal():
    body = """
### Repository URL
https://github.com/user/repo

### Reason for removal
It is no longer maintained.
"""
    fields = parse_issue(body)
    assert fields["repository_url"] == "https://github.com/user/repo"
    assert fields["reason_for_removal"] == "It is no longer maintained."

@patch("src.process_issue.requests.get")
def test_process_submission_success(mock_get, mock_data_paths):
    mock_meta = MagicMock()
    mock_meta.status_code = 200
    mock_meta.json.return_value = {
        "stargazers_count": 25,
        "name": "New Project",
        "description": "A new project",
        "html_url": "https://github.com/user/new-repo",
        "full_name": "user/new-repo",
        "owner": {"login": "user"},
    }
    mock_get.return_value = mock_meta
    
    fields = {
        "repository_url": "https://github.com/user/new-repo",
        "category": "Web Applications"
    }
    
    with patch("src.process_issue.PROJECTS_PATH", mock_data_paths["PROJECTS_PATH"]), \
         patch("src.process_issue.REMOVED_PATH", mock_data_paths["REMOVED_PATH"]), \
         patch("src.process_issue.REJECTED_PATH", mock_data_paths["REJECTED_PATH"]), \
         patch("src.process_issue.CONFIG_PATH", mock_data_paths["CONFIG_PATH"]):
        
        result = process_submission(fields, "author-user")
        assert result is True
        
        with open(mock_data_paths["PROJECTS_PATH"], "r") as f:
            data = json.load(f)
            assert len(data["projects"]) == 1
            assert data["projects"][0]["name"] == "New Project"
            assert data["projects"][0]["description"] == "A new project."

@patch("src.process_issue.requests.get")
def test_process_submission_low_stars(mock_get, mock_data_paths):
    mock_meta = MagicMock()
    mock_meta.status_code = 200
    mock_meta.json.return_value = {
        "stargazers_count": 5,
        "name": "New Project",
        "description": "A new project",
        "html_url": "https://github.com/user/new-repo",
        "full_name": "user/new-repo",
        "owner": {"login": "user"},
    }
    mock_get.return_value = mock_meta
    
    fields = {
        "repository_url": "https://github.com/user/new-repo",
        "category": "Web Applications"
    }
    
    with patch("src.process_issue.PROJECTS_PATH", mock_data_paths["PROJECTS_PATH"]), \
         patch("src.process_issue.CONFIG_PATH", mock_data_paths["CONFIG_PATH"]):
        
        result = process_submission(fields, "author-user")
        assert result is False

@patch("src.process_issue.requests.get")
def test_process_removal_owner_verified(mock_get, mock_data_paths):
    # Setup existing project
    projects_data = {"projects": [{
        "category": "Web Applications",
        "name": "Target Project",
        "repository": "https://github.com/owner/target",
        "description": "To be removed."
    }]}
    with open(mock_data_paths["PROJECTS_PATH"], "w") as f:
        json.dump(projects_data, f)
        
    mock_meta = MagicMock()
    mock_meta.status_code = 200
    mock_meta.json.return_value = {"owner": {"login": "owner"}}
    mock_get.return_value = mock_meta
    
    fields = {
        "repository_url": "https://github.com/owner/target",
        "reason": "Test removal"
    }
    
    with patch("src.process_issue.PROJECTS_PATH", mock_data_paths["PROJECTS_PATH"]), \
         patch("src.process_issue.REMOVED_PATH", mock_data_paths["REMOVED_PATH"]):
        
        result = process_removal(fields, "owner", labels=[])
        assert result is True
        
        with open(mock_data_paths["PROJECTS_PATH"], "r") as f:
            data = json.load(f)
            assert len(data["projects"]) == 0
            
        with open(mock_data_paths["REMOVED_PATH"], "r") as f:
            data = json.load(f)
            assert len(data["removed"]) == 1
            assert data["removed"][0]["owner_verified"] is True

@patch("src.process_issue.requests.get")
def test_process_removal_not_owner(mock_get, mock_data_paths):
    # Setup existing project
    projects_data = {"projects": [{
        "category": "Web Applications",
        "name": "Target Project",
        "repository": "https://github.com/owner/target",
        "description": "To be removed."
    }]}
    with open(mock_data_paths["PROJECTS_PATH"], "w") as f:
        json.dump(projects_data, f)
        
    mock_meta = MagicMock()
    mock_meta.status_code = 200
    mock_meta.json.return_value = {"owner": {"login": "owner"}}
    mock_get.return_value = mock_meta
    
    fields = {
        "repository_url": "https://github.com/owner/target",
        "reason": "Test removal"
    }
    
    with patch("src.process_issue.PROJECTS_PATH", mock_data_paths["PROJECTS_PATH"]), \
         patch("src.process_issue.REMOVED_PATH", mock_data_paths["REMOVED_PATH"]):
        
        result = process_removal(fields, "other-user", labels=[])
        assert result is True # Returns True because it's still a "change" (moved to removed list)
        
        with open(mock_data_paths["REMOVED_PATH"], "r") as f:
            data = json.load(f)
            assert data["removed"][0]["owner_verified"] is False

@patch("src.process_issue.requests.get")
def test_process_removal_maintainer_authorized(mock_get, mock_data_paths):
    # Setup existing project
    projects_data = {"projects": [{
        "category": "Web Applications",
        "name": "Target Project",
        "repository": "https://github.com/owner/target",
        "description": "To be removed."
    }]}
    with open(mock_data_paths["PROJECTS_PATH"], "w") as f:
        json.dump(projects_data, f)
        
    mock_meta = MagicMock()
    mock_meta.status_code = 200
    mock_meta.json.return_value = {"owner": {"login": "owner"}}
    mock_get.return_value = mock_meta
    
    fields = {
        "repository_url": "https://github.com/owner/target",
        "reason": "Test removal"
    }
    
    with patch("src.process_issue.PROJECTS_PATH", mock_data_paths["PROJECTS_PATH"]), \
         patch("src.process_issue.REMOVED_PATH", mock_data_paths["REMOVED_PATH"]):
        
        # 'sharf-shawon' is in MAINTAINERS
        result = process_removal(fields, "sharf-shawon", labels=[])
        assert result is True
        
        with open(mock_data_paths["REMOVED_PATH"], "r") as f:
            data = json.load(f)
            assert data["removed"][0]["owner_verified"] is True

@patch("src.process_issue.requests.get")
def test_process_removal_label_confirmed(mock_get, mock_data_paths):
    # Setup existing project
    projects_data = {"projects": [{
        "category": "Web Applications",
        "name": "Target Project",
        "repository": "https://github.com/owner/target",
        "description": "To be removed."
    }]}
    with open(mock_data_paths["PROJECTS_PATH"], "w") as f:
        json.dump(projects_data, f)
        
    mock_meta = MagicMock()
    mock_meta.status_code = 200
    mock_meta.json.return_value = {"owner": {"login": "owner"}}
    mock_get.return_value = mock_meta
    
    fields = {
        "repository_url": "https://github.com/owner/target",
        "reason": "Test removal"
    }
    
    with patch("src.process_issue.PROJECTS_PATH", mock_data_paths["PROJECTS_PATH"]), \
         patch("src.process_issue.REMOVED_PATH", mock_data_paths["REMOVED_PATH"]):
        
        result = process_removal(fields, "random-user", labels=["confirm-delete"])
        assert result is True
        
        with open(mock_data_paths["REMOVED_PATH"], "r") as f:
            data = json.load(f)
            # owner_verified is True only if is_owner or is_maintainer
            # Label confirmed authorized the removal but doesn't necessarily mean owner_verified is True for the entry
            # Actually, looking at process_issue.py: "owner_verified": is_owner or is_maintainer
            assert data["removed"][0]["owner_verified"] is False

@patch("src.process_issue.requests.get")
def test_process_removal_404_maintainer(mock_get, mock_data_paths):
    # Setup existing project
    projects_data = {"projects": [{
        "category": "Web Applications",
        "name": "Target Project",
        "repository": "https://github.com/owner/target",
        "description": "To be removed."
    }]}
    with open(mock_data_paths["PROJECTS_PATH"], "w") as f:
        json.dump(projects_data, f)
        
    # Mock a 404 or failed API call
    mock_get.side_effect = Exception("404 Not Found")
    
    fields = {
        "repository_url": "https://github.com/owner/target",
        "reason": "Test removal"
    }
    
    with patch("src.process_issue.PROJECTS_PATH", mock_data_paths["PROJECTS_PATH"]), \
         patch("src.process_issue.REMOVED_PATH", mock_data_paths["REMOVED_PATH"]):
        
        result = process_removal(fields, "sharf-shawon", labels=[])
        assert result is True
        
        with open(mock_data_paths["REMOVED_PATH"], "r") as f:
            data = json.load(f)
            assert data["removed"][0]["owner_verified"] is True

@patch("src.process_issue.requests.get")
def test_process_removal_404_non_owner(mock_get, mock_data_paths, capsys):
    # Setup existing project
    projects_data = {"projects": [{
        "category": "Web Applications",
        "name": "Target Project",
        "repository": "https://github.com/owner/target",
        "description": "To be removed."
    }]}
    with open(mock_data_paths["PROJECTS_PATH"], "w") as f:
        json.dump(projects_data, f)
        
    # Mock a 404 or failed API call
    mock_get.side_effect = Exception("404 Not Found")
    
    fields = {
        "repository_url": "https://github.com/owner/target",
        "reason": "Test removal"
    }
    
    with patch("src.process_issue.PROJECTS_PATH", mock_data_paths["PROJECTS_PATH"]), \
         patch("src.process_issue.REMOVED_PATH", mock_data_paths["REMOVED_PATH"]):
        
        result = process_removal(fields, "random-user", labels=[])
        assert result is True
        
        captured = capsys.readouterr()
        assert "MANUAL_REVIEW" in captured.out

@patch("src.process_issue.requests.get")
def test_process_submission_duplicate(mock_get, mock_data_paths):
    # Setup existing project
    projects_data = {"projects": [{
        "category": "Web Applications",
        "name": "Existing",
        "repository": "https://github.com/user/existing",
        "description": "Existing."
    }]}
    with open(mock_data_paths["PROJECTS_PATH"], "w") as f:
        json.dump(projects_data, f)
        
    fields = {
        "project_name": "New Project",
        "repository_url": "https://github.com/user/existing",
        "description": "A new project",
        "category": "Web Applications"
    }
    
    with patch("src.process_issue.PROJECTS_PATH", mock_data_paths["PROJECTS_PATH"]):
        result = process_submission(fields, "author-user")
        assert result is False

def test_process_submission_missing_fields(mock_data_paths):
    fields = {"project_name": "Incomplete"}
    result = process_submission(fields, "author-user")
    assert result is False

@patch("src.process_issue.requests.get")
def test_process_submission_removed_list(mock_get, mock_data_paths):
    # Setup removed project
    removed_data = {"removed": [{
        "html_url": "https://github.com/user/removed"
    }]}
    with open(mock_data_paths["REMOVED_PATH"], "w") as f:
        json.dump(removed_data, f)
        
    fields = {
        "project_name": "New Project",
        "repository_url": "https://github.com/user/removed",
        "description": "A new project",
        "category": "Web Applications"
    }
    
    with patch("src.process_issue.REMOVED_PATH", mock_data_paths["REMOVED_PATH"]):
        result = process_submission(fields, "author-user")
        assert result is False

@patch("src.process_issue.requests.get")
def test_process_submission_rejected_no_notes(mock_get, mock_data_paths):
    mock_meta = MagicMock()
    mock_meta.status_code = 200
    mock_meta.json.return_value = {"stargazers_count": 25}
    mock_get.return_value = mock_meta
    
    # Setup rejected project
    rejected_data = {
        "rejected": [{
            "repository": "https://github.com/user/rejected"
        }],
        "rejected_count": 1
    }
    with open(mock_data_paths["REJECTED_PATH"], "w") as f:
        json.dump(rejected_data, f)
        
    fields = {
        "project_name": "New Project",
        "repository_url": "https://github.com/user/rejected",
        "description": "A new project",
        "category": "Web Applications"
    }
    
    with patch("src.process_issue.PROJECTS_PATH", mock_data_paths["PROJECTS_PATH"]), \
         patch("src.process_issue.REMOVED_PATH", mock_data_paths["REMOVED_PATH"]), \
         patch("src.process_issue.REJECTED_PATH", mock_data_paths["REJECTED_PATH"]), \
         patch("src.process_issue.CONFIG_PATH", mock_data_paths["CONFIG_PATH"]):
        result = process_submission(fields, "author-user")
        assert result is False

@patch("src.process_issue.requests.get")
def test_process_submission_rejected_with_notes(mock_get, mock_data_paths):
    mock_meta = MagicMock()
    mock_meta.status_code = 200
    mock_meta.json.return_value = {"stargazers_count": 25}
    mock_get.return_value = mock_meta
    
    # Setup rejected project
    rejected_data = {
        "rejected": [{
            "repository": "https://github.com/user/rejected"
        }],
        "rejected_count": 1
    }
    with open(mock_data_paths["REJECTED_PATH"], "w") as f:
        json.dump(rejected_data, f)
        
    fields = {
        "project_name": "New Project",
        "repository_url": "https://github.com/user/rejected",
        "description": "A new project",
        "category": "Web Applications",
        "reconsideration_notes": "I fixed the issues."
    }
    
    with patch("src.process_issue.PROJECTS_PATH", mock_data_paths["PROJECTS_PATH"]), \
         patch("src.process_issue.REMOVED_PATH", mock_data_paths["REMOVED_PATH"]), \
         patch("src.process_issue.REJECTED_PATH", mock_data_paths["REJECTED_PATH"]), \
         patch("src.process_issue.CONFIG_PATH", mock_data_paths["CONFIG_PATH"]):
        
        result = process_submission(fields, "author-user")
        assert result is True
        
        with open(mock_data_paths["REJECTED_PATH"], "r") as f:
            data = json.load(f)
            assert len(data["rejected"]) == 0
            assert data["rejected_count"] == 0

@patch("src.process_issue.requests.get")
def test_process_submission_api_failure(mock_get, mock_data_paths):
    mock_get.side_effect = Exception("API Down")
    
    fields = {
        "project_name": "New Project",
        "repository_url": "https://github.com/user/new-repo",
        "description": "A new project",
        "category": "Web Applications"
    }
    
    with patch("src.process_issue.PROJECTS_PATH", mock_data_paths["PROJECTS_PATH"]):
        result = process_submission(fields, "author-user")
        assert result is False

def test_process_removal_missing_fields():
    fields = {"repository_url": "https://github.com/user/repo"}
    result = process_removal(fields, "author")
    assert result is False

def test_process_removal_not_found(mock_data_paths):
    fields = {"repository_url": "https://github.com/not/found", "reason": "test"}
    with patch("src.process_issue.PROJECTS_PATH", mock_data_paths["PROJECTS_PATH"]):
        result = process_removal(fields, "author")
        assert result is False

def test_process_removal_already_removed_returns_false(mock_data_paths):
    removed_data = {"removed": [{"html_url": "https://github.com/user/removed"}]}
    with open(mock_data_paths["REMOVED_PATH"], "w") as f:
        json.dump(removed_data, f)

    fields = {"repository_url": "https://github.com/user/removed", "reason": "test"}
    with patch("src.process_issue.PROJECTS_PATH", mock_data_paths["PROJECTS_PATH"]), \
         patch("src.process_issue.REMOVED_PATH", mock_data_paths["REMOVED_PATH"]):
        result = process_removal(fields, "author")
        assert result is False

@patch("src.process_issue.requests.get")
def test_process_removal_matches_url_variants(mock_get, mock_data_paths):
    projects_data = {"projects": [{
        "category": "Web Applications",
        "name": "Target Project",
        "repository": "https://github.com/Owner/Target.git",
        "description": "To be removed."
    }]}
    with open(mock_data_paths["PROJECTS_PATH"], "w") as f:
        json.dump(projects_data, f)

    mock_meta = MagicMock()
    mock_meta.status_code = 200
    mock_meta.json.return_value = {
        "owner": {"login": "owner"},
        "full_name": "owner/target",
        "stargazers_count": 10,
    }
    mock_get.return_value = mock_meta

    fields = {"repository_url": "https://github.com/owner/target/", "reason": "test"}
    with patch("src.process_issue.PROJECTS_PATH", mock_data_paths["PROJECTS_PATH"]), \
         patch("src.process_issue.REMOVED_PATH", mock_data_paths["REMOVED_PATH"]):
        result = process_removal(fields, "owner")
        assert result is True

def test_main_submission(mock_data_paths):
    with patch("sys.argv", ["process_issue.py", "1", "[Submission]", "### Project name\nTest", "author"]), \
         patch("src.process_issue.process_submission") as mock_sub:
        mock_sub.return_value = True
        main()
        mock_sub.assert_called_once()

def test_main_removal(mock_data_paths):
    with patch("sys.argv", ["process_issue.py", "1", "[Removal]", "### Repository URL\nTest", "author"]), \
         patch("src.process_issue.process_removal") as mock_rem:
        mock_rem.return_value = True
        main()
        mock_rem.assert_called_once()

def test_main_invalid_title():
    with patch("sys.argv", ["process_issue.py", "1", "Invalid", "body", "author"]):
        main()
        # Should not raise SystemExit or call sys.exit

def test_load_json_invalid(tmp_path):
    invalid_file = tmp_path / "invalid.json"
    invalid_file.write_text("not json")
    from src.process_issue import load_json
    assert load_json(invalid_file, default={"test": 1}) == {"test": 1}
    assert load_json(invalid_file) == []

def test_parse_issue_extra_coverage():
    body = """
### Project name
Multi-line
project name

### Category
Web
- [x] This is a checkbox
- [ ] Another one
"""
    fields = parse_issue(body)
    assert fields["project_name"] == "Multi-line project name"
    assert fields["category"] == "Web"

def test_get_repo_meta_invalid_url():
    from src.process_issue import get_repo_meta
    assert get_repo_meta("https://example.com/user/repo") is None

def test_main_insufficient_args():
    with patch("sys.argv", ["process_issue.py"]), patch("sys.stdout", new=MagicMock()) as mock_stdout:
        main()
        # Should print usage and return
