"""Regression tests for project submission workflow safeguards."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "project-submission.yaml"


def test_project_submission_workflow_installs_automation_dependencies():
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "name: install automation dependencies" in workflow
    assert "python -m pip install -r automation-requirements.txt" in workflow


def test_project_submission_workflow_installs_dependencies_before_prepare_step():
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    install_idx = workflow.find("python -m pip install -r automation-requirements.txt")
    prepare_idx = workflow.find("name: prepare README update from issue")
    assert install_idx != -1
    assert prepare_idx != -1
    assert install_idx < prepare_idx
