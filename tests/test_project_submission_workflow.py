"""Regression tests for project submission workflow safeguards."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SUBMISSION_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "project-submission.yaml"
REMOVAL_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "project-removal.yaml"


def _find_step_index(lines: list[str], step_name: str) -> int:
    for idx, line in enumerate(lines):
        if line.strip() == f"- name: {step_name}":
            return idx
    return -1


def _assert_dependency_install_step(workflow_path: Path, prepare_step_name: str) -> None:
    lines = workflow_path.read_text(encoding="utf-8").splitlines()

    install_step_idx = _find_step_index(lines, "install automation dependencies")
    prepare_step_idx = _find_step_index(lines, prepare_step_name)
    assert install_step_idx != -1
    assert prepare_step_idx != -1
    assert install_step_idx < prepare_step_idx

    next_step_idx = len(lines)
    for idx in range(install_step_idx + 1, len(lines)):
        if lines[idx].strip().startswith("- name: "):
            next_step_idx = idx
            break

    install_step_block = "\n".join(lines[install_step_idx:next_step_idx])
    assert "run: python -m pip install -r automation-requirements.txt" in install_step_block


def test_project_submission_workflow_installs_dependencies_before_prepare_step():
    _assert_dependency_install_step(
        SUBMISSION_WORKFLOW_PATH,
        "prepare README update from issue",
    )


def test_project_removal_workflow_installs_dependencies_before_prepare_step():
    _assert_dependency_install_step(
        REMOVAL_WORKFLOW_PATH,
        "prepare removal update from issue",
    )
