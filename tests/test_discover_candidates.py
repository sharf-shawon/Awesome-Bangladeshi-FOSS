"""Tests for scripts/discover_candidates.py.

Covers: normalize_repo_item, dedupe_candidates, build_session, request_json
(all retry/error branches), discover_by_users, discover_by_topics, and
main() integration – all with mocked network/sleep.
"""

from __future__ import annotations

import json
import sys
import unittest.mock as mock

import pytest

import discover_candidates as dc


# ---------------------------------------------------------------------------
# build_session
# ---------------------------------------------------------------------------

def test_build_session_sets_authorization_when_token_present(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test123")
    session = dc.build_session()
    assert "Authorization" in session.headers
    assert "ghp_test123" in session.headers["Authorization"]


def test_build_session_no_authorization_without_token(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    session = dc.build_session()
    assert "Authorization" not in session.headers


# ---------------------------------------------------------------------------
# request_json – mocked session responses
# ---------------------------------------------------------------------------

def _make_response(status, payload=None, headers=None):
    r = mock.MagicMock()
    r.status_code = status
    r.headers = headers or {}
    r.json.return_value = payload or {}
    r.raise_for_status = mock.MagicMock()
    if status >= 400:
        r.raise_for_status.side_effect = Exception(f"HTTP {status}")
    return r


def test_request_json_success_on_first_attempt():
    session = mock.MagicMock()
    session.get.return_value = _make_response(200, {"items": [1, 2, 3]})
    result = dc.request_json(session, "https://api.github.com/test")
    assert result == {"items": [1, 2, 3]}


def test_request_json_rate_limited_retries_and_succeeds(monkeypatch):
    monkeypatch.setattr(dc, "time", mock.MagicMock())
    session = mock.MagicMock()
    rl_resp = _make_response(403, headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "0"})
    ok_resp = _make_response(200, {"ok": True})
    session.get.side_effect = [rl_resp, ok_resp]
    result = dc.request_json(session, "https://api.github.com/test")
    assert result == {"ok": True}


def test_request_json_temp_error_retries_and_succeeds(monkeypatch):
    monkeypatch.setattr(dc, "time", mock.MagicMock())
    session = mock.MagicMock()
    session.get.side_effect = [_make_response(503), _make_response(200, {"data": "x"})]
    assert dc.request_json(session, "https://api.github.com/test") == {"data": "x"}


def test_request_json_502_retries(monkeypatch):
    monkeypatch.setattr(dc, "time", mock.MagicMock())
    session = mock.MagicMock()
    session.get.side_effect = [_make_response(502), _make_response(200, {})]
    dc.request_json(session, "https://api.github.com/test")  # should not raise


def test_request_json_all_retries_exhausted_raises(monkeypatch):
    monkeypatch.setattr(dc, "time", mock.MagicMock())
    session = mock.MagicMock()
    session.get.return_value = _make_response(500)
    with pytest.raises(RuntimeError, match="after retries"):
        dc.request_json(session, "https://api.github.com/test")


def test_request_json_non_rate_limit_403_raises():
    session = mock.MagicMock()
    session.get.return_value = _make_response(403, headers={"X-RateLimit-Remaining": "5"})
    with pytest.raises(Exception):
        dc.request_json(session, "https://api.github.com/test")


def test_request_json_404_raises():
    session = mock.MagicMock()
    session.get.return_value = _make_response(404)
    with pytest.raises(Exception):
        dc.request_json(session, "https://api.github.com/test")


# ---------------------------------------------------------------------------
# normalize_repo_item
# ---------------------------------------------------------------------------

_VALID_RAW = {
    "full_name": "owner/my-repo",
    "name": "my-repo",
    "html_url": "https://github.com/owner/my-repo",
    "description": "A Bangladesh project.",
    "owner": {"login": "owner", "type": "User"},
    "language": "Python",
    "topics": ["Bangladesh", "nlp"],
    "stargazers_count": 42,
    "forks_count": 5,
    "open_issues_count": 3,
    "fork": False,
    "archived": False,
    "default_branch": "main",
    "updated_at": "2024-01-01T00:00:00Z",
    "license": {"key": "mit", "spdx_id": "MIT"},
}


def test_normalize_repo_item_valid():
    result = dc.normalize_repo_item(_VALID_RAW, source="test")
    assert result is not None
    assert result["full_name"] == "owner/my-repo"
    assert result["source"] == "test"
    assert result["topics"] == ["bangladesh", "nlp"]  # lowercased


def test_normalize_repo_item_strips_trailing_slash():
    raw = {**_VALID_RAW, "html_url": "https://github.com/owner/my-repo/"}
    result = dc.normalize_repo_item(raw, source="test")
    assert result is not None
    assert not result["html_url"].endswith("/")


def test_normalize_repo_item_missing_full_name_returns_none():
    assert dc.normalize_repo_item({**_VALID_RAW, "full_name": ""}, source="t") is None


def test_normalize_repo_item_invalid_url_returns_none():
    raw = {**_VALID_RAW, "html_url": "https://example.com/owner/repo"}
    assert dc.normalize_repo_item(raw, source="t") is None


def test_normalize_repo_item_no_license_uses_none():
    result = dc.normalize_repo_item({**_VALID_RAW, "license": None}, source="t")
    assert result is not None
    assert result["license"]["key"] is None


# ---------------------------------------------------------------------------
# dedupe_candidates
# ---------------------------------------------------------------------------

def _item(full_name, stars=0, forks=0, source="s1"):
    return {"full_name": full_name, "stargazers_count": stars, "forks_count": forks, "source": source}


def test_dedupe_single_item():
    result = dc.dedupe_candidates([_item("a/b", stars=5)])
    assert len(result) == 1


def test_dedupe_same_full_name_case_insensitive():
    result = dc.dedupe_candidates([_item("A/Repo"), _item("a/repo")])
    assert len(result) == 1


def test_dedupe_keeps_max_stars():
    result = dc.dedupe_candidates([_item("a/r", stars=10), _item("a/r", stars=25)])
    assert result[0]["stargazers_count"] == 25


def test_dedupe_merges_sources():
    result = dc.dedupe_candidates([_item("a/r", source="s1"), _item("a/r", source="s2")])
    assert "s1" in result[0]["source"] and "s2" in result[0]["source"]


def test_dedupe_sorted_by_stars_descending():
    items = [_item("low/r", stars=1), _item("high/r", stars=100), _item("mid/r", stars=50)]
    result = dc.dedupe_candidates(items)
    stars = [r["stargazers_count"] for r in result]
    assert stars == sorted(stars, reverse=True)


# ---------------------------------------------------------------------------
# discover_by_users – mocked request_json
# ---------------------------------------------------------------------------

_SAMPLE_REPO = {
    "full_name": "bd-user/tool",
    "name": "tool",
    "html_url": "https://github.com/bd-user/tool",
    "description": "A BD tool.",
    "owner": {"login": "bd-user", "type": "User"},
    "language": "Python",
    "topics": [],
    "stargazers_count": 10,
    "forks_count": 2,
    "open_issues_count": 1,
    "fork": False,
    "archived": False,
    "default_branch": "main",
    "updated_at": "2024-01-01T00:00:00Z",
    "license": {"key": "mit", "spdx_id": "MIT"},
}


def test_discover_by_users_returns_candidates(monkeypatch):
    monkeypatch.setattr(dc, "time", mock.MagicMock())

    def _mock_request(session, url, params=None):
        if "search/users" in url:
            return {"items": [{"login": "bd-user"}]}
        if "users/bd-user/repos" in url:
            return [_SAMPLE_REPO]
        return {}

    with mock.patch.object(dc, "request_json", side_effect=_mock_request):
        result = dc.discover_by_users(mock.MagicMock())
    assert any(r["full_name"] == "bd-user/tool" for r in result)


def test_discover_by_users_skips_user_without_login(monkeypatch):
    monkeypatch.setattr(dc, "time", mock.MagicMock())

    def _mock_request(session, url, params=None):
        if "search/users" in url:
            return {"items": [{"login": None}]}
        return []

    with mock.patch.object(dc, "request_json", side_effect=_mock_request):
        result = dc.discover_by_users(mock.MagicMock())
    assert result == []


def test_discover_by_users_skips_non_list_repos(monkeypatch):
    monkeypatch.setattr(dc, "time", mock.MagicMock())

    def _mock_request(session, url, params=None):
        if "search/users" in url:
            return {"items": [{"login": "user1"}]}
        # non-list response for repos
        return {"message": "Not Found"}

    with mock.patch.object(dc, "request_json", side_effect=_mock_request):
        result = dc.discover_by_users(mock.MagicMock())
    assert result == []


# ---------------------------------------------------------------------------
# discover_by_topics – mocked request_json
# ---------------------------------------------------------------------------

def test_discover_by_topics_returns_candidates(monkeypatch):
    monkeypatch.setattr(dc, "time", mock.MagicMock())

    with mock.patch.object(dc, "request_json", return_value={"items": [_SAMPLE_REPO]}):
        result = dc.discover_by_topics(mock.MagicMock())
    assert len(result) > 0


def test_discover_by_topics_empty_items(monkeypatch):
    monkeypatch.setattr(dc, "time", mock.MagicMock())

    with mock.patch.object(dc, "request_json", return_value={"items": []}):
        result = dc.discover_by_topics(mock.MagicMock())
    assert result == []


# ---------------------------------------------------------------------------
# main() – integration
# ---------------------------------------------------------------------------

def test_main_writes_candidates_file(monkeypatch, tmp_path):
    monkeypatch.setattr(dc, "discover_by_users", lambda s: [
        dc.normalize_repo_item(_SAMPLE_REPO, "github_user_location:bd-user")
    ])
    monkeypatch.setattr(dc, "discover_by_topics", lambda s: [])

    output_file = tmp_path / "candidates.json"
    monkeypatch.setattr(sys, "argv", ["discover_candidates.py", "--output", str(output_file)])
    result = dc.main()
    assert result == 0
    data = json.loads(output_file.read_text())
    assert "candidates" in data
    assert data["candidate_count"] == 1


def test_main_deduplicates_across_sources(monkeypatch, tmp_path):
    repo = dc.normalize_repo_item(_SAMPLE_REPO, "user_search")
    repo2 = dc.normalize_repo_item(_SAMPLE_REPO, "topic_search")  # same repo, different source

    monkeypatch.setattr(dc, "discover_by_users", lambda s: [repo])
    monkeypatch.setattr(dc, "discover_by_topics", lambda s: [repo2])

    output_file = tmp_path / "candidates.json"
    monkeypatch.setattr(sys, "argv", ["discover_candidates.py", "--output", str(output_file)])
    dc.main()
    data = json.loads(output_file.read_text())
    # Should be deduplicated to 1 candidate even though both sources found it
    assert data["candidate_count"] == 1
