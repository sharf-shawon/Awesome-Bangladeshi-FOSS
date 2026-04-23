import json
import pytest
from pathlib import Path
from src.generate_readme import main, clean_description

def test_generate_readme_no_file(tmp_path):
    readme_path = tmp_path / "README.md"
    from unittest.mock import patch
    # Patch Path.exists to return False for the specific projects path
    with patch("src.generate_readme.PROJECTS_PATH", tmp_path / "non_existent.json"), \
         patch("src.generate_readme.README_PATH", readme_path):
        main()
        assert readme_path.exists()
        assert "## Web Applications\n\n\n" in readme_path.read_text()

def test_clean_description():
    assert clean_description("awesome app") == "App."
    assert clean_description("the best tool ever") == "The tool ever."
    assert clean_description("Cool project!") == "Project!"
    assert clean_description("already clean.") == "Already clean."
    assert clean_description("   multiple   spaces   ") == "Multiple spaces."

def test_generate_readme(tmp_path):
    projects_path = tmp_path / "projects.json"
    readme_path = tmp_path / "README.md"
    
    data = {
        "projects": [
            {
                "category": "Web Applications",
                "name": "App A",
                "repository": "https://github.com/user/app-a",
                "description": "Desc A"
            },
            {
                "category": "Mobile Apps",
                "name": "App B",
                "repository": "https://github.com/user/app-b",
                "description": "Desc B"
            }
        ]
    }
    
    with open(projects_path, "w") as f:
        json.dump(data, f)
        
    from unittest.mock import patch
    with patch("src.generate_readme.PROJECTS_PATH", projects_path), \
         patch("src.generate_readme.README_PATH", readme_path):
        
        main()
        
        assert readme_path.exists()
        content = readme_path.read_text()
        assert "App A" in content
        assert "App B" in content
        assert "## Web Applications" in content
        assert "## Mobile Apps" in content
        assert "### 🚀 How to contribute" in content

