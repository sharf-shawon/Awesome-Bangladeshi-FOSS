import json
import pytest
from pathlib import Path
from src.validate_data import validate

def test_validate_data_success(tmp_path):
    projects_path = tmp_path / "projects.json"
    data = {
        "projects": [
            {
                "category": "Web Applications",
                "name": "Valid App",
                "repository": "https://github.com/user/repo",
                "description": "Valid description."
            }
        ]
    }
    with open(projects_path, "w") as f:
        json.dump(data, f)
        
    from unittest.mock import patch
    with patch("src.validate_data.PROJECTS_PATH", projects_path):
        assert validate() is True

def test_validate_data_missing_field(tmp_path):
    projects_path = tmp_path / "projects.json"
    data = {
        "projects": [
            {
                "category": "Web Applications",
                "name": "Invalid App"
                # missing repository and description
            }
        ]
    }
    with open(projects_path, "w") as f:
        json.dump(data, f)
        
    from unittest.mock import patch
    with patch("src.validate_data.PROJECTS_PATH", projects_path):
        assert validate() is False

def test_validate_data_invalid_category(tmp_path):
    projects_path = tmp_path / "invalid_cat.json"
    data = {
        "projects": [
            {
                "category": "Invalid Category",
                "name": "App",
                "repository": "https://github.com/user/repo",
                "description": "Desc"
            }
        ]
    }
    with open(projects_path, "w") as f:
        json.dump(data, f)
        
    from unittest.mock import patch
    with patch("src.validate_data.PROJECTS_PATH", projects_path):
        assert validate() is False

def test_validate_data_not_exists(tmp_path):
    projects_path = tmp_path / "non_existent.json"
    from unittest.mock import patch
    with patch("src.validate_data.PROJECTS_PATH", projects_path):
        assert validate() is False

def test_validate_data_invalid_json(tmp_path):
    projects_path = tmp_path / "invalid.json"
    with open(projects_path, "w") as f:
        f.write("{invalid: json}")
    from unittest.mock import patch
    with patch("src.validate_data.PROJECTS_PATH", projects_path):
        assert validate() is False

def test_validate_data_no_projects_key(tmp_path):
    projects_path = tmp_path / "no_projects.json"
    with open(projects_path, "w") as f:
        json.dump({"data": []}, f)
    from unittest.mock import patch
    with patch("src.validate_data.PROJECTS_PATH", projects_path):
        assert validate() is False

