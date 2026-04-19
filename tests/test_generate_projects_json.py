"""Tests for scripts/generate_projects_json.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import generate_projects_json


_README = """\
# Awesome

## Web Applications

- [Alpha App](https://github.com/owner/alpha) - First app.
- [Beta App](https://github.com/owner/beta) - Second app.

## Mobile Apps

- [BD Mobile](https://github.com/owner/bd-mobile) - Mobile app.

## Developer Tools & Libraries

- [NLP Tool](https://github.com/owner/nlp-tool) - NLP library.

## Government & Utility Services

- [GovAPI](https://github.com/owner/govapi) - Government API.

## Fintech & Payments

- [PaySDK](https://github.com/owner/paysdk) - Payment SDK.

## Other FOSS Projects

- [Other](https://github.com/owner/other) - Other project.

## Awesome Lists & Resource Collections

- [Resources](https://github.com/owner/resources) - Resource collection.

## Non Project Section

- [Ignored](https://github.com/owner/ignored) - Should not appear in output.
"""


def test_generate_returns_expected_project_count(monkeypatch, tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(_README, encoding="utf-8")
    monkeypatch.setattr(generate_projects_json, "README_PATH", readme)

    result = generate_projects_json.generate_projects()
    # 2 Web Applications + 1 each for the remaining 6 recognised sections = 8 total.
    # "Non Project Section" is excluded.
    assert len(result["projects"]) == 8


def test_generate_output_has_required_fields(monkeypatch, tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(_README, encoding="utf-8")
    monkeypatch.setattr(generate_projects_json, "README_PATH", readme)

    projects = generate_projects_json.generate_projects()["projects"]
    for project in projects:
        assert "category" in project
        assert "name" in project
        assert "repository" in project
        assert "description" in project


def test_generate_excludes_non_project_sections(monkeypatch, tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(_README, encoding="utf-8")
    monkeypatch.setattr(generate_projects_json, "README_PATH", readme)

    projects = generate_projects_json.generate_projects()["projects"]
    repos = [p["repository"] for p in projects]
    assert "https://github.com/owner/ignored" not in repos


def test_generate_maps_category_correctly(monkeypatch, tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(_README, encoding="utf-8")
    monkeypatch.setattr(generate_projects_json, "README_PATH", readme)

    projects = generate_projects_json.generate_projects()["projects"]
    web_projects = [p for p in projects if p["category"] == "Web Applications"]
    assert len(web_projects) == 2
    names = {p["name"] for p in web_projects}
    assert names == {"Alpha App", "Beta App"}


def test_generate_empty_readme_returns_no_projects(monkeypatch, tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("# Just a title\n", encoding="utf-8")
    monkeypatch.setattr(generate_projects_json, "README_PATH", readme)

    result = generate_projects_json.generate_projects()
    assert result["projects"] == []


def test_main_writes_output_file(monkeypatch, tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(_README, encoding="utf-8")
    output = tmp_path / "data" / "projects.json"
    (tmp_path / "data").mkdir()
    monkeypatch.setattr(generate_projects_json, "README_PATH", readme)
    monkeypatch.setattr(generate_projects_json, "OUTPUT_PATH", output)
    monkeypatch.setattr(generate_projects_json, "REPO_ROOT", tmp_path)
    assert generate_projects_json.main() == 0
    assert output.exists()
    data = json.loads(output.read_text())
    assert "projects" in data
    assert len(data["projects"]) > 0


def test_main_raises_if_readme_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(generate_projects_json, "README_PATH", tmp_path / "NOFILE.md")
    monkeypatch.setattr(generate_projects_json, "OUTPUT_PATH", tmp_path / "out.json")
    with pytest.raises(FileNotFoundError):
        generate_projects_json.main()
