"""Tests for scripts/augment_candidates_with_social.py."""

from __future__ import annotations

import unittest.mock as mock

import augment_candidates_with_social as aug


# ---------------------------------------------------------------------------
# extract_repo_full_names
# ---------------------------------------------------------------------------

def test_extract_repo_full_names_from_plain_urls():
    text = "check out https://github.com/owner/repo for details"
    result = aug.extract_repo_full_names(text)
    assert "owner/repo" in result


def test_extract_repo_full_names_multiple_urls():
    text = "https://github.com/a/x and https://github.com/b/y"
    result = aug.extract_repo_full_names(text)
    assert "a/x" in result
    assert "b/y" in result


def test_extract_repo_full_names_strips_trailing_dot():
    # Sentence ending: "...visit https://github.com/owner/repo."
    text = "visit https://github.com/owner/repo."
    result = aug.extract_repo_full_names(text)
    # The trailing period should be stripped from the repo name.
    assert any(name == "owner/repo" for name in result)


def test_extract_repo_full_names_ignores_non_github():
    text = "see https://example.com/foo/bar for more info"
    result = aug.extract_repo_full_names(text)
    assert not result


def test_extract_repo_full_names_empty_string():
    assert aug.extract_repo_full_names("") == set()


def test_extract_repo_full_names_ignores_single_segment():
    # github.com/owner (no repo) should not be returned
    text = "visit https://github.com/owner"
    result = aug.extract_repo_full_names(text)
    # owner without slash-segment pair: the regex requires owner/repo pattern
    for name in result:
        assert "/" in name


# ---------------------------------------------------------------------------
# normalize_repo
# ---------------------------------------------------------------------------

_RAW_REPO = {
    "full_name": "bd-org/project",
    "name": "project",
    "html_url": "https://github.com/bd-org/project",
    "description": "A Bangladesh project",
    "owner": {"login": "bd-org", "type": "Organization"},
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
    result = aug.normalize_repo(_RAW_REPO, source="test_source")
    assert result["full_name"] == "bd-org/project"
    assert result["source"] == "test_source"
    assert result["html_url"] == "https://github.com/bd-org/project"
    assert result["topics"] == ["bangladesh", "open-source"]  # lowercased


def test_normalize_repo_strips_trailing_slash_from_url():
    raw = {**_RAW_REPO, "html_url": "https://github.com/bd-org/project/"}
    result = aug.normalize_repo(raw, source="s")
    assert not result["html_url"].endswith("/")


# ---------------------------------------------------------------------------
# merge_candidates
# ---------------------------------------------------------------------------

def _cand(full_name: str, stars: int = 0, forks: int = 0, issues: int = 0, source: str = "s1") -> dict:
    return {"full_name": full_name, "stargazers_count": stars, "forks_count": forks,
            "open_issues_count": issues, "source": source}


def test_merge_candidates_base_only():
    base = [_cand("a/repo", stars=5)]
    result = aug.merge_candidates(base, [])
    assert len(result) == 1
    assert result[0]["full_name"] == "a/repo"


def test_merge_candidates_extra_only():
    result = aug.merge_candidates([], [_cand("b/repo", stars=10)])
    assert len(result) == 1


def test_merge_candidates_deduplicates_case_insensitive():
    base = [_cand("Owner/Repo", stars=5, source="github")]
    extra = [_cand("owner/repo", stars=8, source="social")]
    result = aug.merge_candidates(base, extra)
    assert len(result) == 1


def test_merge_candidates_takes_max_stars():
    base = [_cand("a/x", stars=10)]
    extra = [_cand("a/x", stars=20)]
    result = aug.merge_candidates(base, extra)
    assert result[0]["stargazers_count"] == 20


def test_merge_candidates_merges_sources():
    base = [_cand("a/x", source="github")]
    extra = [_cand("a/x", source="reddit")]
    result = aug.merge_candidates(base, extra)
    assert "github" in result[0]["source"]
    assert "reddit" in result[0]["source"]


# ---------------------------------------------------------------------------
# fetch_repo_details – mocked session
# ---------------------------------------------------------------------------

def _mock_session(payload, status_code=200):
    session = mock.MagicMock()
    response = mock.MagicMock()
    response.status_code = status_code
    response.headers = {"Content-Type": "application/json"}
    response.json.return_value = payload
    response.text = ""
    session.get.return_value = response
    return session


def test_fetch_repo_details_returns_none_for_fork():
    session = _mock_session({"full_name": "a/b", "fork": True, "archived": False, "description": "test"})
    assert aug.fetch_repo_details(session, "a/b") is None


def test_fetch_repo_details_returns_none_for_archived():
    session = _mock_session({"full_name": "a/b", "fork": False, "archived": True, "description": "test"})
    assert aug.fetch_repo_details(session, "a/b") is None


def test_fetch_repo_details_returns_none_without_description():
    session = _mock_session({"full_name": "a/b", "fork": False, "archived": False, "description": None})
    assert aug.fetch_repo_details(session, "a/b") is None


def test_fetch_repo_details_returns_payload_when_valid():
    payload = {"full_name": "a/b", "fork": False, "archived": False, "description": "A project"}
    session = _mock_session(payload)
    result = aug.fetch_repo_details(session, "a/b")
    assert result is not None
    assert result["full_name"] == "a/b"
