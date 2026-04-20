"""Tests for scripts/project_requirements.py."""

from __future__ import annotations

import json

import project_requirements as pr


def test_load_project_requirements_defaults_when_file_missing(tmp_path, monkeypatch):
    missing = tmp_path / "missing.json"
    monkeypatch.delenv("MIN_PROJECT_STARS", raising=False)
    result = pr.load_project_requirements(missing)
    assert result["minimum_stars"] == 10


def test_load_project_requirements_from_file(tmp_path, monkeypatch):
    path = tmp_path / "project_requirements.json"
    path.write_text(json.dumps({"minimum_stars": 25}), encoding="utf-8")
    monkeypatch.delenv("MIN_PROJECT_STARS", raising=False)
    result = pr.load_project_requirements(path)
    assert result["minimum_stars"] == 25


def test_load_project_requirements_env_override(tmp_path, monkeypatch):
    path = tmp_path / "project_requirements.json"
    path.write_text(json.dumps({"minimum_stars": 25}), encoding="utf-8")
    monkeypatch.setenv("MIN_PROJECT_STARS", "12")
    result = pr.load_project_requirements(path)
    assert result["minimum_stars"] == 12


def test_load_project_requirements_invalid_env_override_ignored(tmp_path, monkeypatch):
    path = tmp_path / "project_requirements.json"
    path.write_text(json.dumps({"minimum_stars": 25}), encoding="utf-8")
    monkeypatch.setenv("MIN_PROJECT_STARS", "abc")
    result = pr.load_project_requirements(path)
    assert result["minimum_stars"] == 25