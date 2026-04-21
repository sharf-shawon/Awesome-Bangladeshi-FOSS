"""Regression tests for project submission workflow safeguards."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SUBMISSION_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "project-submission.yaml"
REMOVAL_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "project-removal.yaml"


def test_project_submission_workflow_installs_automation_dependencies():
    workflow = SUBMISSION_WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "name: install automation dependencies" in workflow
    assert "python -m pip install -r automation-requirements.txt" in workflow


def test_project_submission_workflow_installs_dependencies_before_prepare_step():
    workflow = SUBMISSION_WORKFLOW_PATH.read_text(encoding="utf-8")
    install_idx = workflow.find("python -m pip install -r automation-requirements.txt")
    prepare_idx = workflow.find("name: prepare README update from issue")
    assert install_idx != -1
    assert prepare_idx != -1
    assert install_idx < prepare_idx


def test_project_removal_workflow_installs_automation_dependencies():
    workflow = REMOVAL_WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "name: install automation dependencies" in workflow
    assert "python -m pip install -r automation-requirements.txt" in workflow


def test_project_removal_workflow_installs_dependencies_before_prepare_step():
    workflow = REMOVAL_WORKFLOW_PATH.read_text(encoding="utf-8")
    install_idx = workflow.find("python -m pip install -r automation-requirements.txt")
    prepare_idx = workflow.find("name: prepare removal update from issue")
    assert install_idx != -1
    assert prepare_idx != -1
    assert install_idx < prepare_idx
