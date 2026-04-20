"""Tests for scripts/process_project_removal.py."""

from __future__ import annotations

import json
from textwrap import dedent

import pytest

import process_project_removal as ppr


README_TEXT = dedent(
    """\
    ## Other FOSS Projects

    - [Demo Project](https://github.com/owner/demo-project) - Demo description.
    """
)


def _issue_body(url="https://github.com/owner/demo-project", reason="Project owner requested removal"):
    return dedent(
        f"""\
        ### Repository URL
        {url}
        ### Reason for removal
        {reason}
        """
    )


def test_parse_removal_request_valid():
    repo_url, reason = ppr.parse_removal_request(_issue_body())
    assert repo_url == "https://github.com/owner/demo-project"
    assert "requested" in reason


def test_parse_removal_request_missing_reason_raises():
    with pytest.raises(ValueError, match="Reason for removal"):
        ppr.parse_removal_request(_issue_body(reason=""))


def test_parse_removal_request_missing_repo_url_raises():
    with pytest.raises(ValueError, match="Repository URL"):
        ppr.parse_removal_request(_issue_body(url=""))


def test_parse_removal_request_invalid_repo_url_raises():
    with pytest.raises(ValueError, match="format"):
        ppr.parse_removal_request(_issue_body(url="https://example.com/owner/repo"))


def test_parse_removal_request_long_reason_raises():
    with pytest.raises(ValueError, match="400 characters"):
        ppr.parse_removal_request(_issue_body(reason="x" * 401))


def test_remove_entry_from_readme_success():
    updated, removed = ppr.remove_entry_from_readme(README_TEXT, "https://github.com/owner/demo-project")
    assert "demo-project" not in updated
    assert removed["name"] == "Demo Project"


def test_remove_entry_from_readme_not_found_raises():
    with pytest.raises(ValueError, match="not currently listed"):
        ppr.remove_entry_from_readme(README_TEXT, "https://github.com/owner/missing")


def test_extract_field_with_checkbox_prefix():
    body = "### Reason for removal\n- [x] Project owner requested\n"
    assert ppr.extract_field(body, "Reason for removal") == "Project owner requested"


def test_build_session_adds_auth_header(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "token123")
    session = ppr.build_session()
    assert "Authorization" in session.headers


def test_build_session_without_token(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    session = ppr.build_session()
    assert "Authorization" not in session.headers


def test_fetch_repo_metadata_returns_none_on_error():
    class _Resp:
        status_code = 404

        @staticmethod
        def json():
            return {}

    class _Session:
        @staticmethod
        def get(url, timeout):
            return _Resp()

    assert ppr.fetch_repo_metadata(_Session(), "owner/repo") is None


def test_write_output_no_env_is_noop(monkeypatch):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    ppr.write_output("key", "value")


def test_main_owner_verified_updates_readme_and_removed_list(monkeypatch, tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(README_TEXT, encoding="utf-8")
    removed = tmp_path / "removed_projects.json"
    removed.write_text(json.dumps({"removed": []}), encoding="utf-8")

    monkeypatch.setattr(ppr, "README_PATH", readme)
    monkeypatch.setattr(ppr, "REMOVED_LIST_PATH", removed)
    monkeypatch.setattr(
        ppr,
        "fetch_repo_metadata",
        lambda session, owner_repo: {"owner": {"login": "owner"}},
    )
    monkeypatch.setenv("ISSUE_BODY", _issue_body())
    monkeypatch.setenv("ISSUE_NUMBER", "101")
    monkeypatch.setenv("ISSUE_AUTHOR", "owner")

    assert ppr.main() == 0
    assert "demo-project" not in readme.read_text(encoding="utf-8")
    payload = json.loads(removed.read_text(encoding="utf-8"))
    assert payload["removed_count"] == 1
    assert payload["removed"][0]["owner_verified"] is True


def test_main_non_owner_still_processes(monkeypatch, tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(README_TEXT, encoding="utf-8")
    removed = tmp_path / "removed_projects.json"
    removed.write_text(json.dumps({"removed": []}), encoding="utf-8")
    output_file = tmp_path / "github_output"
    output_file.write_text("", encoding="utf-8")

    monkeypatch.setattr(ppr, "README_PATH", readme)
    monkeypatch.setattr(ppr, "REMOVED_LIST_PATH", removed)
    monkeypatch.setattr(
        ppr,
        "fetch_repo_metadata",
        lambda session, owner_repo: {"owner": {"login": "owner"}},
    )
    monkeypatch.setenv("ISSUE_BODY", _issue_body())
    monkeypatch.setenv("ISSUE_NUMBER", "102")
    monkeypatch.setenv("ISSUE_AUTHOR", "someoneelse")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))

    assert ppr.main() == 0
    content = output_file.read_text(encoding="utf-8")
    assert "owner_verified=false" in content


def test_main_fails_with_empty_issue_body(monkeypatch):
    monkeypatch.setenv("ISSUE_BODY", "")
    monkeypatch.setenv("ISSUE_AUTHOR", "owner")
    assert ppr.main() == 1


def test_main_fails_with_empty_issue_author(monkeypatch):
    monkeypatch.setenv("ISSUE_BODY", _issue_body())
    monkeypatch.delenv("ISSUE_AUTHOR", raising=False)
    assert ppr.main() == 1


def test_main_fails_when_metadata_unavailable(monkeypatch, tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(README_TEXT, encoding="utf-8")
    removed = tmp_path / "removed_projects.json"
    removed.write_text(json.dumps({"removed": []}), encoding="utf-8")

    monkeypatch.setattr(ppr, "README_PATH", readme)
    monkeypatch.setattr(ppr, "REMOVED_LIST_PATH", removed)
    monkeypatch.setattr(ppr, "fetch_repo_metadata", lambda session, owner_repo: None)
    monkeypatch.setenv("ISSUE_BODY", _issue_body())
    monkeypatch.setenv("ISSUE_AUTHOR", "owner")
    assert ppr.main() == 1


def test_main_fails_when_readme_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(ppr, "README_PATH", tmp_path / "README.md")
    monkeypatch.setattr(ppr, "REMOVED_LIST_PATH", tmp_path / "removed_projects.json")
    monkeypatch.setattr(
        ppr,
        "fetch_repo_metadata",
        lambda session, owner_repo: {"owner": {"login": "owner"}},
    )
    monkeypatch.setenv("ISSUE_BODY", _issue_body())
    monkeypatch.setenv("ISSUE_AUTHOR", "owner")
    assert ppr.main() == 1


def test_main_fails_when_repo_not_in_readme(monkeypatch, tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(README_TEXT, encoding="utf-8")
    removed = tmp_path / "removed_projects.json"
    removed.write_text(json.dumps({"removed": []}), encoding="utf-8")

    monkeypatch.setattr(ppr, "README_PATH", readme)
    monkeypatch.setattr(ppr, "REMOVED_LIST_PATH", removed)
    monkeypatch.setattr(
        ppr,
        "fetch_repo_metadata",
        lambda session, owner_repo: {"owner": {"login": "owner"}},
    )
    monkeypatch.setenv("ISSUE_BODY", _issue_body(url="https://github.com/owner/not-listed"))
    monkeypatch.setenv("ISSUE_AUTHOR", "owner")
    assert ppr.main() == 1
