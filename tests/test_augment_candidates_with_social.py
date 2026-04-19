"""Tests for scripts/augment_candidates_with_social.py.

Covers: extract_repo_full_names, normalize_repo, merge_candidates,
fetch_repo_details, build_session, request_with_backoff (all retry branches),
search_reddit (OAuth + public fallback), search_web (with/without key),
and main() integration – all with mocked network/sleep.
"""

from __future__ import annotations

import json
import sys
import unittest.mock as mock

import pytest

import augment_candidates_with_social as aug


# ---------------------------------------------------------------------------
# build_session
# ---------------------------------------------------------------------------

def test_build_session_with_token_sets_auth(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    session = aug.build_session()
    assert "Authorization" in session.headers


def test_build_session_without_token_no_auth(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    session = aug.build_session()
    assert "Authorization" not in session.headers


# ---------------------------------------------------------------------------
# request_with_backoff
# ---------------------------------------------------------------------------

def _resp(status, payload=None, text="", content_type="application/json", headers=None):
    r = mock.MagicMock()
    r.status_code = status
    r.headers = {"Content-Type": content_type, **(headers or {})}
    r.json.return_value = payload or {}
    r.text = text
    return r


def test_request_with_backoff_success_json(monkeypatch):
    monkeypatch.setattr(aug, "time", mock.MagicMock())
    session = mock.MagicMock()
    session.get.return_value = _resp(200, payload={"key": "val"})
    assert aug.request_with_backoff(session, "https://example.com") == {"key": "val"}


def test_request_with_backoff_success_text(monkeypatch):
    monkeypatch.setattr(aug, "time", mock.MagicMock())
    session = mock.MagicMock()
    session.get.return_value = _resp(200, content_type="text/html", text="<html>data</html>")
    result = aug.request_with_backoff(session, "https://example.com")
    assert result == "<html>data</html>"


def test_request_with_backoff_429_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr(aug, "time", mock.MagicMock())
    session = mock.MagicMock()
    session.get.side_effect = [_resp(429), _resp(200, payload={"ok": True})]
    assert aug.request_with_backoff(session, "https://example.com") == {"ok": True}


def test_request_with_backoff_503_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr(aug, "time", mock.MagicMock())
    session = mock.MagicMock()
    session.get.side_effect = [_resp(503), _resp(200, payload={"ok": True})]
    assert aug.request_with_backoff(session, "https://example.com") == {"ok": True}


def test_request_with_backoff_403_rate_limited_retries(monkeypatch):
    monkeypatch.setattr(aug, "time", mock.MagicMock())
    session = mock.MagicMock()
    rl = _resp(403, headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "0"})
    session.get.side_effect = [rl, _resp(200, payload={})]
    result = aug.request_with_backoff(session, "https://api.github.com/x")
    assert result == {}


def test_request_with_backoff_4xx_non_rate_limit_returns_none(monkeypatch):
    monkeypatch.setattr(aug, "time", mock.MagicMock())
    session = mock.MagicMock()
    session.get.return_value = _resp(404)
    assert aug.request_with_backoff(session, "https://example.com") is None


def test_request_with_backoff_403_without_rate_limit_header_returns_none(monkeypatch):
    monkeypatch.setattr(aug, "time", mock.MagicMock())
    session = mock.MagicMock()
    session.get.return_value = _resp(403, headers={"X-RateLimit-Remaining": "10"})
    assert aug.request_with_backoff(session, "https://example.com") is None


def test_request_with_backoff_all_retries_exhausted_returns_none(monkeypatch):
    monkeypatch.setattr(aug, "time", mock.MagicMock())
    session = mock.MagicMock()
    session.get.return_value = _resp(500)
    assert aug.request_with_backoff(session, "https://example.com") is None


# ---------------------------------------------------------------------------
# extract_repo_full_names
# ---------------------------------------------------------------------------

def test_extract_repo_full_names_from_plain_urls():
    assert "owner/repo" in aug.extract_repo_full_names("https://github.com/owner/repo for details")


def test_extract_repo_full_names_multiple_urls():
    text = "https://github.com/a/x and https://github.com/b/y"
    result = aug.extract_repo_full_names(text)
    assert "a/x" in result and "b/y" in result


def test_extract_repo_full_names_strips_trailing_dot():
    result = aug.extract_repo_full_names("visit https://github.com/owner/repo.")
    assert any(name == "owner/repo" for name in result)


def test_extract_repo_full_names_ignores_non_github():
    assert not aug.extract_repo_full_names("https://example.com/foo/bar")


def test_extract_repo_full_names_empty():
    assert aug.extract_repo_full_names("") == set()


def test_extract_repo_full_names_requires_slash():
    # github.com/owner (no repo slug) should not appear
    for name in aug.extract_repo_full_names("https://github.com/owner"):
        assert "/" in name


# ---------------------------------------------------------------------------
# normalize_repo
# ---------------------------------------------------------------------------

_RAW = {
    "full_name": "bd/project",
    "name": "project",
    "html_url": "https://github.com/bd/project",
    "description": "BD project",
    "owner": {"login": "bd", "type": "Organization"},
    "language": "Python",
    "topics": ["Bangladesh", "Open-Source"],
    "stargazers_count": 15,
    "forks_count": 3,
    "open_issues_count": 2,
    "fork": False,
    "archived": False,
    "default_branch": "main",
    "updated_at": "2024-06-01T00:00:00Z",
    "license": {"key": "mit", "spdx_id": "MIT"},
}


def test_normalize_repo_structure():
    result = aug.normalize_repo(_RAW, source="test")
    assert result["full_name"] == "bd/project"
    assert result["source"] == "test"
    assert result["topics"] == ["bangladesh", "open-source"]


def test_normalize_repo_strips_trailing_slash():
    raw = {**_RAW, "html_url": "https://github.com/bd/project/"}
    assert not aug.normalize_repo(raw, source="s")["html_url"].endswith("/")


# ---------------------------------------------------------------------------
# fetch_repo_details
# ---------------------------------------------------------------------------

def _mock_session(payload, status=200):
    session = mock.MagicMock()
    r = mock.MagicMock()
    r.status_code = status
    r.headers = {"Content-Type": "application/json"}
    r.json.return_value = payload
    r.text = ""
    session.get.return_value = r
    return session


def test_fetch_repo_details_skips_fork():
    assert aug.fetch_repo_details(_mock_session({"full_name": "a/b", "fork": True, "archived": False, "description": "x"}), "a/b") is None


def test_fetch_repo_details_skips_archived():
    assert aug.fetch_repo_details(_mock_session({"full_name": "a/b", "fork": False, "archived": True, "description": "x"}), "a/b") is None


def test_fetch_repo_details_skips_empty_description():
    assert aug.fetch_repo_details(_mock_session({"full_name": "a/b", "fork": False, "archived": False, "description": None}), "a/b") is None


def test_fetch_repo_details_returns_payload_when_valid():
    payload = {"full_name": "a/b", "fork": False, "archived": False, "description": "A project"}
    result = aug.fetch_repo_details(_mock_session(payload), "a/b")
    assert result is not None


def test_fetch_repo_details_returns_none_when_non_dict():
    session = mock.MagicMock()
    with mock.patch.object(aug, "request_with_backoff", return_value="not a dict"):
        assert aug.fetch_repo_details(session, "a/b") is None


def test_fetch_repo_details_returns_none_when_no_full_name():
    session = mock.MagicMock()
    with mock.patch.object(aug, "request_with_backoff", return_value={"full_name": "", "fork": False, "archived": False, "description": "x"}):
        assert aug.fetch_repo_details(session, "a/b") is None


# ---------------------------------------------------------------------------
# merge_candidates
# ---------------------------------------------------------------------------

def _cand(full_name, stars=0, forks=0, issues=0, source="s1"):
    return {"full_name": full_name, "stargazers_count": stars, "forks_count": forks,
            "open_issues_count": issues, "source": source}


def test_merge_candidates_base_only():
    result = aug.merge_candidates([_cand("a/r", stars=5)], [])
    assert len(result) == 1


def test_merge_candidates_extra_only():
    result = aug.merge_candidates([], [_cand("b/r", stars=10)])
    assert len(result) == 1


def test_merge_candidates_deduplicates_case_insensitive():
    result = aug.merge_candidates([_cand("Owner/Repo", stars=5)], [_cand("owner/repo", stars=8)])
    assert len(result) == 1


def test_merge_candidates_takes_max_stars():
    result = aug.merge_candidates([_cand("a/x", stars=10)], [_cand("a/x", stars=20)])
    assert result[0]["stargazers_count"] == 20


def test_merge_candidates_merges_sources():
    result = aug.merge_candidates([_cand("a/x", source="github")], [_cand("a/x", source="reddit")])
    assert "github" in result[0]["source"] and "reddit" in result[0]["source"]


def test_merge_candidates_skips_empty_full_name():
    result = aug.merge_candidates([_cand("", stars=5)], [])
    assert result == []


# ---------------------------------------------------------------------------
# search_reddit
# ---------------------------------------------------------------------------

def _reddit_payload(url="https://github.com/bd/tool", text="", title=""):
    return {"data": {"children": [{"data": {"url": url, "selftext": text, "title": title}}]}}


def test_search_reddit_public_fallback_extracts_repos(monkeypatch):
    monkeypatch.setattr(aug, "time", mock.MagicMock())
    monkeypatch.delenv("REDDIT_TOKEN", raising=False)
    with mock.patch.object(aug, "request_with_backoff", return_value=_reddit_payload()):
        result = aug.search_reddit(mock.MagicMock(), ["Bangladesh FOSS"])
    assert "bd/tool" in result


def test_search_reddit_public_fallback_none_payload(monkeypatch):
    monkeypatch.setattr(aug, "time", mock.MagicMock())
    monkeypatch.delenv("REDDIT_TOKEN", raising=False)
    with mock.patch.object(aug, "request_with_backoff", return_value=None):
        result = aug.search_reddit(mock.MagicMock(), ["q"])
    assert result == set()


def test_search_reddit_oauth_path_extracts_repos(monkeypatch):
    monkeypatch.setattr(aug, "time", mock.MagicMock())
    monkeypatch.setenv("REDDIT_TOKEN", "oauth_token_abc")
    # OAuth payload has url_overridden_by_dest key
    payload = {"data": {"children": [{"data": {
        "url_overridden_by_dest": "https://github.com/bd/oauthrepo",
        "selftext": "",
        "title": "",
    }}]}}
    with mock.patch.object(aug, "request_with_backoff", return_value=payload):
        result = aug.search_reddit(mock.MagicMock(), ["q"])
    assert "bd/oauthrepo" in result


def test_search_reddit_oauth_none_payload(monkeypatch):
    monkeypatch.setattr(aug, "time", mock.MagicMock())
    monkeypatch.setenv("REDDIT_TOKEN", "tok")
    with mock.patch.object(aug, "request_with_backoff", return_value=None):
        result = aug.search_reddit(mock.MagicMock(), ["q"])
    assert result == set()


# ---------------------------------------------------------------------------
# search_web
# ---------------------------------------------------------------------------

def test_search_web_extracts_repos_from_html(monkeypatch):
    monkeypatch.setattr(aug, "time", mock.MagicMock())
    html = '<a href="https://github.com/bd/webproject">BD Web Project</a>'
    with mock.patch.object(aug, "request_with_backoff", return_value=html):
        result = aug.search_web(mock.MagicMock(), ["query"])
    assert "bd/webproject" in result


def test_search_web_non_string_response_skipped(monkeypatch):
    monkeypatch.setattr(aug, "time", mock.MagicMock())
    with mock.patch.object(aug, "request_with_backoff", return_value=None):
        result = aug.search_web(mock.MagicMock(), ["q"])
    assert result == set()


def test_search_web_with_search_api_key_still_works(monkeypatch):
    monkeypatch.setattr(aug, "time", mock.MagicMock())
    monkeypatch.setenv("SEARCH_API_KEY", "some_key")
    html = "https://github.com/bd/apikeyrepo"
    with mock.patch.object(aug, "request_with_backoff", return_value=html):
        result = aug.search_web(mock.MagicMock(), ["q"])
    assert "bd/apikeyrepo" in result


# ---------------------------------------------------------------------------
# main() – integration
# ---------------------------------------------------------------------------

def test_main_merges_and_writes_output(monkeypatch, tmp_path):
    input_file = tmp_path / "candidates.json"
    input_file.write_text(json.dumps({"candidates": [
        {"full_name": "existing/repo", "stargazers_count": 5, "forks_count": 1,
         "open_issues_count": 0, "source": "github", "html_url": "https://github.com/existing/repo"}
    ]}), encoding="utf-8")
    output_file = tmp_path / "augmented.json"

    monkeypatch.setattr(aug, "search_reddit", lambda s, q: {"bd/social-find"})
    monkeypatch.setattr(aug, "search_web", lambda s, q: set())
    monkeypatch.setattr(aug, "fetch_repo_details", lambda s, n: {
        "full_name": n, "fork": False, "archived": False, "description": "Found via social",
    })
    monkeypatch.setattr(aug, "time", mock.MagicMock())

    monkeypatch.setattr(sys, "argv", [
        "augment_candidates_with_social.py",
        "--input", str(input_file),
        "--output", str(output_file),
    ])
    assert aug.main() == 0
    data = json.loads(output_file.read_text())
    assert "candidates" in data
    assert data["augmented_candidate_count"] >= 1


def test_main_input_missing_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "argv", [
        "augment_candidates_with_social.py",
        "--input", str(tmp_path / "missing.json"),
        "--output", str(tmp_path / "out.json"),
    ])
    with pytest.raises(FileNotFoundError):
        aug.main()


def test_main_skips_repos_whose_details_return_none(monkeypatch, tmp_path):
    # Covers the `if not details: continue` branch (line 250)
    input_file = tmp_path / "c.json"
    input_file.write_text(json.dumps({"candidates": []}), encoding="utf-8")
    output_file = tmp_path / "out.json"

    monkeypatch.setattr(aug, "search_reddit", lambda s, q: {"bd/valid", "bd/invalid"})
    monkeypatch.setattr(aug, "search_web", lambda s, q: set())
    # Return None for "bd/invalid" so that the `continue` branch is exercised
    monkeypatch.setattr(aug, "fetch_repo_details",
                        lambda s, n: {"full_name": n, "fork": False, "archived": False,
                                      "description": "Valid"} if n == "bd/valid" else None)
    monkeypatch.setattr(aug, "time", mock.MagicMock())

    monkeypatch.setattr(sys, "argv", [
        "augment_candidates_with_social.py",
        "--input", str(input_file),
        "--output", str(output_file),
    ])
    assert aug.main() == 0
    data = json.loads(output_file.read_text())
    # Only bd/valid should be included
    assert data["augmented_candidate_count"] == 1


def test_main_no_social_results_still_writes_base(monkeypatch, tmp_path):
    input_file = tmp_path / "c.json"
    input_file.write_text(json.dumps({"candidates": [
        {"full_name": "only/base", "stargazers_count": 3, "forks_count": 0,
         "open_issues_count": 0, "source": "github"}
    ]}), encoding="utf-8")
    output_file = tmp_path / "out.json"
    monkeypatch.setattr(aug, "search_reddit", lambda s, q: set())
    monkeypatch.setattr(aug, "search_web", lambda s, q: set())
    monkeypatch.setattr(aug, "time", mock.MagicMock())
    monkeypatch.setattr(sys, "argv", [
        "augment_candidates_with_social.py",
        "--input", str(input_file),
        "--output", str(output_file),
    ])
    assert aug.main() == 0
    data = json.loads(output_file.read_text())
    assert data["augmented_candidate_count"] == 1
