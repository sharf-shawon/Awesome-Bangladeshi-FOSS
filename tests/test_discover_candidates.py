"""Tests for scripts/discover_candidates.py.

Network-bound functions (discover_by_users, discover_by_topics) are covered
only for their pure helper logic; live HTTP calls are not made in tests.
"""

from __future__ import annotations

import discover_candidates as dc


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
    assert result["html_url"] == "https://github.com/owner/my-repo"
    assert result["source"] == "test"
    assert result["stargazers_count"] == 42
    assert result["topics"] == ["bangladesh", "nlp"]  # lowercased


def test_normalize_repo_item_strips_trailing_slash_from_url():
    raw = {**_VALID_RAW, "html_url": "https://github.com/owner/my-repo/"}
    result = dc.normalize_repo_item(raw, source="test")
    assert result is not None
    assert not result["html_url"].endswith("/")


def test_normalize_repo_item_missing_full_name_returns_none():
    raw = {**_VALID_RAW, "full_name": ""}
    assert dc.normalize_repo_item(raw, source="test") is None


def test_normalize_repo_item_invalid_url_returns_none():
    raw = {**_VALID_RAW, "html_url": "https://example.com/owner/repo"}
    assert dc.normalize_repo_item(raw, source="test") is None


def test_normalize_repo_item_no_license_uses_none():
    raw = {**_VALID_RAW, "license": None}
    result = dc.normalize_repo_item(raw, source="test")
    assert result is not None
    assert result["license"]["key"] is None
    assert result["license"]["spdx_id"] is None


# ---------------------------------------------------------------------------
# dedupe_candidates
# ---------------------------------------------------------------------------

def _make(full_name: str, stars: int = 0, forks: int = 0, source: str = "s1") -> dict:
    return {
        "full_name": full_name,
        "stargazers_count": stars,
        "forks_count": forks,
        "source": source,
    }


def test_dedupe_candidates_single_item():
    result = dc.dedupe_candidates([_make("a/b", stars=5)])
    assert len(result) == 1
    assert result[0]["full_name"] == "a/b"


def test_dedupe_candidates_deduplicates_same_full_name():
    items = [_make("A/Repo", stars=10, source="s1"), _make("a/repo", stars=20, source="s2")]
    result = dc.dedupe_candidates(items)
    assert len(result) == 1


def test_dedupe_candidates_keeps_max_stars():
    items = [_make("a/repo", stars=10), _make("a/repo", stars=25)]
    result = dc.dedupe_candidates(items)
    assert result[0]["stargazers_count"] == 25


def test_dedupe_candidates_merges_sources():
    items = [_make("a/repo", source="github_search"), _make("a/repo", source="social")]
    result = dc.dedupe_candidates(items)
    sources = result[0]["source"]
    assert "github_search" in sources
    assert "social" in sources


def test_dedupe_candidates_sorted_by_stars_descending():
    items = [_make("low/stars", stars=1), _make("high/stars", stars=100), _make("mid/stars", stars=50)]
    result = dc.dedupe_candidates(items)
    star_values = [r["stargazers_count"] for r in result]
    assert star_values == sorted(star_values, reverse=True)
