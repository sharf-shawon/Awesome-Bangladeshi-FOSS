"""Tests for scripts/lint_repo.py."""

from __future__ import annotations

import subprocess

import lint_repo


def test_main_runs_checks_in_order(monkeypatch):
    commands = []

    def fake_run(command, cwd=None):
        commands.append((command, cwd))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(lint_repo.subprocess, "run", fake_run)

    assert lint_repo.main() == 0
    assert len(commands) == 2
    assert commands[0][0][:2] == ["npx", "-y"]
    assert commands[1][0][-1].endswith("validate_readme_links.py")


def test_main_stops_on_first_failure(monkeypatch):
    commands = []

    def fake_run(command, cwd=None):
        commands.append(command)
        return subprocess.CompletedProcess(command, 1)

    monkeypatch.setattr(lint_repo.subprocess, "run", fake_run)

    assert lint_repo.main() == 1
    assert len(commands) == 1