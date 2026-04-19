"""Tests for scripts/filter_and_rank_candidates.py.

Covers: license filtering, BD-signal detection, documentation/activity thresholds,
scoring helpers, session/request utilities (mocked), and full main() integration
across all filter code-paths.
"""

from __future__ import annotations

import base64
import json
import sys
import unittest.mock as mock
from datetime import datetime, timezone
from pathlib import Path

import pytest

import filter_and_rank_candidates as far


# ---------------------------------------------------------------------------
# license_is_allowed
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("spdx,expected", [
    ("MIT", True),
    ("Apache-2.0", True),
    ("GPL-3.0", True),
    ("AGPL-3.0-only", True),
    ("LGPL-2.1", True),
    ("BSD-3-Clause", True),
    ("MPL-2.0", True),
    ("ISC", True),
    ("EPL-2.0", True),
    ("CC0-1.0", True),
    ("NOASSERTION", False),
    ("", False),
    ("WTFPL", False),
    ("Proprietary", False),
])
def test_license_is_allowed(spdx, expected):
    assert far.license_is_allowed(spdx) is expected


# ---------------------------------------------------------------------------
# normalize_license_spdx
# ---------------------------------------------------------------------------

def test_normalize_license_spdx_returns_id():
    assert far.normalize_license_spdx({"license": {"spdx_id": "MIT"}}) == "MIT"


def test_normalize_license_spdx_strips_whitespace():
    assert far.normalize_license_spdx({"license": {"spdx_id": "  MIT  "}}) == "MIT"


def test_normalize_license_spdx_no_license_key():
    assert far.normalize_license_spdx({}) == ""


def test_normalize_license_spdx_none_license():
    assert far.normalize_license_spdx({"license": None}) == ""


def test_normalize_license_spdx_none_spdx_id():
    assert far.normalize_license_spdx({"license": {"spdx_id": None}}) == ""


# ---------------------------------------------------------------------------
# load_existing_repo_names
# ---------------------------------------------------------------------------

def test_load_existing_repo_names_from_valid_file(sample_projects_json):
    result = far.load_existing_repo_names(sample_projects_json)
    assert "owner/existing-app" in result


def test_load_existing_repo_names_all_lowercase(tmp_path):
    data = {"projects": [{"repository": "https://github.com/Owner/Repo"}]}
    f = tmp_path / "projects.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    assert "owner/repo" in far.load_existing_repo_names(f)


def test_load_existing_repo_names_missing_file(tmp_path):
    assert far.load_existing_repo_names(tmp_path / "nope.json") == set()


def test_load_existing_repo_names_skips_invalid_urls(tmp_path):
    data = {"projects": [{"repository": "not-a-url"}]}
    f = tmp_path / "p.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    assert len(far.load_existing_repo_names(f)) == 0


def test_load_existing_repo_names_trailing_slash_stripped(tmp_path):
    data = {"projects": [{"repository": "https://github.com/owner/repo/"}]}
    f = tmp_path / "p.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    assert "owner/repo" in far.load_existing_repo_names(f)


# ---------------------------------------------------------------------------
# has_bangladeshi_signal
# ---------------------------------------------------------------------------

def _blank_cand(**kw):
    defaults = {"full_name": "a/b", "description": "", "topics": []}
    defaults.update(kw)
    return defaults


def test_has_bd_signal_location_bangladesh():
    assert far.has_bangladeshi_signal(_blank_cand(), "Dhaka, Bangladesh", "") is True


def test_has_bd_signal_location_bd_exact():
    assert far.has_bangladeshi_signal(_blank_cand(), "BD", "") is True


def test_has_bd_signal_location_bd_lowercase():
    assert far.has_bangladeshi_signal(_blank_cand(), "bd", "") is True


def test_has_bd_signal_bangla_in_description():
    assert far.has_bangladeshi_signal(_blank_cand(description="bangla NLP"), "", "") is True


def test_has_bd_signal_bkash_in_topics():
    assert far.has_bangladeshi_signal(_blank_cand(topics=["bkash"]), "", "") is True


def test_has_bd_signal_keyword_in_readme():
    assert far.has_bangladeshi_signal(_blank_cand(), "Germany", "A Dhaka-based project") is True


def test_has_bd_signal_bengali_keyword():
    assert far.has_bangladeshi_signal(_blank_cand(description="bengali text"), "", "") is True


def test_has_bd_signal_no_signal_returns_false():
    cand = _blank_cand(full_name="user/generic", description="generic tool", topics=["python"])
    assert far.has_bangladeshi_signal(cand, "Germany", "Generic readme text.") is False


# ---------------------------------------------------------------------------
# has_non_trivial_docs
# ---------------------------------------------------------------------------

def test_has_non_trivial_docs_long_description():
    assert far.has_non_trivial_docs({"description": "A" * 25}, "") is True


def test_has_non_trivial_docs_short_desc_long_readme():
    assert far.has_non_trivial_docs({"description": "short"}, "R" * 180) is True


def test_has_non_trivial_docs_short_desc_short_readme():
    assert far.has_non_trivial_docs({"description": "short"}, "R" * 100) is False


def test_has_non_trivial_docs_empty():
    assert far.has_non_trivial_docs({"description": ""}, "") is False


def test_has_non_trivial_docs_exactly_25_chars():
    assert far.has_non_trivial_docs({"description": "A" * 24}, "") is False
    assert far.has_non_trivial_docs({"description": "A" * 25}, "") is True


# ---------------------------------------------------------------------------
# has_min_signal
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("stars,forks,issues,expected", [
    (3, 0, 0, True),
    (0, 2, 0, True),
    (0, 0, 3, True),
    (2, 1, 2, False),
    (0, 0, 0, False),
])
def test_has_min_signal(stars, forks, issues, expected):
    cand = {"stargazers_count": stars, "forks_count": forks, "open_issues_count": issues}
    assert far.has_min_signal(cand) is expected


# ---------------------------------------------------------------------------
# activity_score
# ---------------------------------------------------------------------------

def test_activity_score_recent_repo_in_range():
    cand = {"stargazers_count": 200, "forks_count": 80,
            "updated_at": datetime.now(timezone.utc).isoformat()}
    score = far.activity_score(cand)
    assert 0.0 <= score <= 5.0
    assert score > 0.0


def test_activity_score_old_repo_low():
    cand = {"stargazers_count": 0, "forks_count": 0, "updated_at": "2000-01-01T00:00:00Z"}
    assert far.activity_score(cand) < 2.0


def test_activity_score_invalid_date_uses_fallback():
    cand = {"stargazers_count": 0, "forks_count": 0, "updated_at": "not-a-date"}
    score = far.activity_score(cand)
    assert 0.0 <= score <= 5.0


def test_activity_score_capped_at_five():
    cand = {"stargazers_count": 999999, "forks_count": 999999,
            "updated_at": datetime.now(timezone.utc).isoformat()}
    assert far.activity_score(cand) <= 5.0


# ---------------------------------------------------------------------------
# final_rank_score
# ---------------------------------------------------------------------------

def test_final_rank_score_positive_for_good_candidate():
    ai_scores = {"relevance": 5.0, "usefulness": 5.0, "maturity": 5.0}
    cand = {"stargazers_count": 200, "forks_count": 80,
            "updated_at": datetime.now(timezone.utc).isoformat()}
    assert far.final_rank_score(ai_scores, cand) > 0.0


def test_final_rank_score_zero_for_zero_scores():
    ai_scores = {"relevance": 0.0, "usefulness": 0.0, "maturity": 0.0}
    cand = {"stargazers_count": 0, "forks_count": 0, "updated_at": "2000-01-01T00:00:00Z"}
    assert far.final_rank_score(ai_scores, cand) >= 0.0


def test_final_rank_score_higher_relevance_beats_lower():
    cand = {"stargazers_count": 10, "forks_count": 2,
            "updated_at": datetime.now(timezone.utc).isoformat()}
    high = far.final_rank_score({"relevance": 5.0, "usefulness": 3.0, "maturity": 3.0}, cand)
    low = far.final_rank_score({"relevance": 1.0, "usefulness": 3.0, "maturity": 3.0}, cand)
    assert high > low


# ---------------------------------------------------------------------------
# sort_key
# ---------------------------------------------------------------------------

def test_sort_key_returns_correct_tuple():
    assert far.sort_key({"rank_score": 3.5, "stargazers_count": 42}) == (3.5, 42)


def test_sort_key_missing_fields_defaults_to_zero():
    assert far.sort_key({}) == (0.0, 0)


# ---------------------------------------------------------------------------
# build_session
# ---------------------------------------------------------------------------

def test_build_session_with_token(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "tok123")
    session = far.build_session()
    assert "Authorization" in session.headers


def test_build_session_without_token(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    session = far.build_session()
    assert "Authorization" not in session.headers


# ---------------------------------------------------------------------------
# request_json (mocked)
# ---------------------------------------------------------------------------

def _resp(status, payload=None, headers=None):
    r = mock.MagicMock()
    r.status_code = status
    r.headers = headers or {}
    r.json.return_value = payload or {}
    r.raise_for_status = mock.MagicMock()
    if status >= 400:
        r.raise_for_status.side_effect = Exception(f"HTTP {status}")
    return r


def test_request_json_success():
    session = mock.MagicMock()
    session.get.return_value = _resp(200, {"key": "value"})
    assert far.request_json(session, "https://api.github.com/x") == {"key": "value"}


def test_request_json_rate_limited_retries(monkeypatch):
    monkeypatch.setattr(far, "time", mock.MagicMock())
    session = mock.MagicMock()
    rl = _resp(403, headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "0"})
    ok = _resp(200, {"ok": True})
    session.get.side_effect = [rl, ok]
    assert far.request_json(session, "https://api.github.com/x") == {"ok": True}


def test_request_json_temp_error_retries(monkeypatch):
    monkeypatch.setattr(far, "time", mock.MagicMock())
    session = mock.MagicMock()
    session.get.side_effect = [_resp(503), _resp(200, {"data": 1})]
    assert far.request_json(session, "https://api.github.com/x") == {"data": 1}


def test_request_json_all_retries_exhausted_returns_none(monkeypatch):
    monkeypatch.setattr(far, "time", mock.MagicMock())
    session = mock.MagicMock()
    session.get.return_value = _resp(500)
    # far.request_json returns None after exhausting retries (doesn't raise)
    assert far.request_json(session, "https://api.github.com/x") is None


def test_request_json_non_rate_limit_4xx_returns_none():
    session = mock.MagicMock()
    session.get.return_value = _resp(403, headers={"X-RateLimit-Remaining": "10"})
    # 4xx that isn't a rate limit → logged warning, returns None
    assert far.request_json(session, "https://api.github.com/x") is None


def test_request_json_404_returns_none():
    session = mock.MagicMock()
    session.get.return_value = _resp(404)
    assert far.request_json(session, "https://api.github.com/x") is None


# ---------------------------------------------------------------------------
# fetch_owner_location
# ---------------------------------------------------------------------------

def test_fetch_owner_location_empty_login():
    assert far.fetch_owner_location(mock.MagicMock(), "") == ""


def test_fetch_owner_location_success():
    with mock.patch.object(far, "request_json", return_value={"location": "Dhaka, Bangladesh"}):
        assert far.fetch_owner_location(mock.MagicMock(), "user") == "Dhaka, Bangladesh"


def test_fetch_owner_location_no_payload():
    with mock.patch.object(far, "request_json", return_value=None):
        assert far.fetch_owner_location(mock.MagicMock(), "user") == ""


def test_fetch_owner_location_no_location_field():
    with mock.patch.object(far, "request_json", return_value={"login": "user"}):
        assert far.fetch_owner_location(mock.MagicMock(), "user") == ""


# ---------------------------------------------------------------------------
# fetch_readme_snippet
# ---------------------------------------------------------------------------

def test_fetch_readme_snippet_no_payload():
    with mock.patch.object(far, "request_json", return_value=None):
        assert far.fetch_readme_snippet(mock.MagicMock(), "o/r") == ""


def test_fetch_readme_snippet_no_content_field():
    with mock.patch.object(far, "request_json", return_value={"name": "README.md"}):
        assert far.fetch_readme_snippet(mock.MagicMock(), "o/r") == ""


def test_fetch_readme_snippet_valid_content():
    text = "This is a Bangladesh project."
    encoded = base64.b64encode(text.encode()).decode()
    with mock.patch.object(far, "request_json", return_value={"content": encoded}):
        assert far.fetch_readme_snippet(mock.MagicMock(), "o/r") == text


def test_fetch_readme_snippet_truncates_long_content():
    text = "A" * 1000
    encoded = base64.b64encode(text.encode()).decode()
    with mock.patch.object(far, "request_json", return_value={"content": encoded}):
        result = far.fetch_readme_snippet(mock.MagicMock(), "o/r")
    assert len(result) <= 600


def test_fetch_readme_snippet_invalid_content_type_returns_empty():
    # Passing an integer causes TypeError in base64.b64decode → except block returns ""
    with mock.patch.object(far, "request_json", return_value={"content": 12345}):
        assert far.fetch_readme_snippet(mock.MagicMock(), "o/r") == ""


# ---------------------------------------------------------------------------
# main() – integration helpers
# ---------------------------------------------------------------------------

def _make_cand(**kw):
    base = {
        "full_name": "bd-org/cool-tool",
        "name": "cool-tool",
        "html_url": "https://github.com/bd-org/cool-tool",
        "description": "A useful Bangladesh developer tool for engineers.",
        "owner": {"login": "bd-org", "type": "Organization"},
        "fork": False,
        "archived": False,
        "license": {"key": "mit", "spdx_id": "MIT"},
        "stargazers_count": 50,
        "forks_count": 10,
        "open_issues_count": 5,
        "topics": ["bangladesh", "tools"],
        "updated_at": "2024-06-01T00:00:00Z",
        "source": "github_search",
    }
    base.update(kw)
    return base


def _run_main(monkeypatch, tmp_path, candidates, projects_data=None, limit=10):
    """Set up temp files, mock all I/O, and invoke far.main()."""
    input_file = tmp_path / "aug.json"
    input_file.write_text(json.dumps({"candidates": candidates}), encoding="utf-8")
    output_file = tmp_path / "top10.json"
    projects_file = tmp_path / "projects.json"
    if projects_data is not None:
        projects_file.write_text(json.dumps(projects_data), encoding="utf-8")

    monkeypatch.setattr(far, "fetch_owner_location", lambda s, login: "Dhaka, Bangladesh")
    monkeypatch.setattr(far, "fetch_readme_snippet",
                        lambda s, name: "A Bangladesh open source project for developers and programmers.")
    monkeypatch.setattr(far, "classify_and_score", lambda repo: {
        "category": "Developer Tools & Libraries",
        "scores": {"relevance": 4.5, "usefulness": 4.0, "maturity": 3.5},
        "notes": "test",
    })
    monkeypatch.setattr(far, "time", mock.MagicMock())
    monkeypatch.setattr(sys, "argv", [
        "filter_and_rank_candidates.py",
        "--input", str(input_file),
        "--projects", str(projects_file),
        "--output", str(output_file),
        "--limit", str(limit),
    ])
    return far.main(), output_file


# ---------------------------------------------------------------------------
# main() – filter code paths
# ---------------------------------------------------------------------------

def test_main_selects_qualifying_candidate(monkeypatch, tmp_path):
    rc, out = _run_main(monkeypatch, tmp_path, [_make_cand()])
    assert rc == 0
    data = json.loads(out.read_text())
    assert data["selected_count"] == 1
    assert data["selected"][0]["full_name"] == "bd-org/cool-tool"


def test_main_output_has_required_fields(monkeypatch, tmp_path):
    rc, out = _run_main(monkeypatch, tmp_path, [_make_cand()])
    assert rc == 0
    entry = json.loads(out.read_text())["selected"][0]
    for field in ("full_name", "html_url", "category", "stars", "forks", "ai_scores", "rank_score"):
        assert field in entry


def test_main_skips_empty_full_name(monkeypatch, tmp_path):
    _, out = _run_main(monkeypatch, tmp_path, [_make_cand(full_name="")])
    assert json.loads(out.read_text())["selected_count"] == 0


def test_main_skips_already_existing(monkeypatch, tmp_path):
    projects = {"projects": [
        {"repository": "https://github.com/bd-org/cool-tool",
         "name": "Cool Tool", "category": "Web Applications", "description": "x"}
    ]}
    _, out = _run_main(monkeypatch, tmp_path, [_make_cand()], projects_data=projects)
    assert json.loads(out.read_text())["selected_count"] == 0


def test_main_skips_fork(monkeypatch, tmp_path):
    _, out = _run_main(monkeypatch, tmp_path, [_make_cand(fork=True)])
    assert json.loads(out.read_text())["selected_count"] == 0


def test_main_skips_archived(monkeypatch, tmp_path):
    _, out = _run_main(monkeypatch, tmp_path, [_make_cand(archived=True)])
    assert json.loads(out.read_text())["selected_count"] == 0


def test_main_skips_bad_license(monkeypatch, tmp_path):
    _, out = _run_main(monkeypatch, tmp_path,
                       [_make_cand(license={"key": "x", "spdx_id": "NOASSERTION"})])
    assert json.loads(out.read_text())["selected_count"] == 0


def test_main_skips_trivial_docs(monkeypatch, tmp_path):
    # Short description AND short readme → has_non_trivial_docs = False.
    monkeypatch.setattr(far, "fetch_owner_location", lambda s, l: "Bangladesh")
    monkeypatch.setattr(far, "fetch_readme_snippet", lambda s, n: "Short.")
    monkeypatch.setattr(far, "classify_and_score", lambda r: {
        "category": "Other FOSS Projects", "scores": {"relevance": 2, "usefulness": 2, "maturity": 2}, "notes": ""
    })
    monkeypatch.setattr(far, "time", mock.MagicMock())

    input_file = tmp_path / "a.json"
    input_file.write_text(json.dumps({"candidates": [_make_cand(description="Tiny")]}),
                          encoding="utf-8")
    out = tmp_path / "out.json"
    monkeypatch.setattr(sys, "argv", [
        "filter_and_rank_candidates.py",
        "--input", str(input_file),
        "--projects", str(tmp_path / "p.json"),
        "--output", str(out),
    ])
    assert far.main() == 0
    assert json.loads(out.read_text())["selected_count"] == 0


def test_main_skips_low_signal(monkeypatch, tmp_path):
    _, out = _run_main(monkeypatch, tmp_path,
                       [_make_cand(stargazers_count=0, forks_count=0, open_issues_count=0)])
    assert json.loads(out.read_text())["selected_count"] == 0


def test_main_skips_no_bd_signal(monkeypatch, tmp_path):
    monkeypatch.setattr(far, "fetch_owner_location", lambda s, l: "Germany")
    monkeypatch.setattr(far, "fetch_readme_snippet",
                        lambda s, n: "A generic programming tool for software engineers everywhere.")
    monkeypatch.setattr(far, "classify_and_score", lambda r: {
        "category": "Other FOSS Projects", "scores": {"relevance": 2, "usefulness": 2, "maturity": 2}, "notes": ""
    })
    monkeypatch.setattr(far, "time", mock.MagicMock())

    input_file = tmp_path / "a.json"
    input_file.write_text(json.dumps({"candidates": [
        _make_cand(
            full_name="gen/tool",
            html_url="https://github.com/gen/tool",
            description="Generic cross-platform developer toolchain for modern software engineers.",
            topics=[],
        )
    ]}), encoding="utf-8")
    out = tmp_path / "out.json"
    monkeypatch.setattr(sys, "argv", [
        "filter_and_rank_candidates.py",
        "--input", str(input_file),
        "--projects", str(tmp_path / "p.json"),
        "--output", str(out),
    ])
    assert far.main() == 0
    assert json.loads(out.read_text())["selected_count"] == 0


def test_main_respects_limit(monkeypatch, tmp_path):
    candidates = [
        _make_cand(full_name=f"org/repo{i}", html_url=f"https://github.com/org/repo{i}")
        for i in range(5)
    ]
    _, out = _run_main(monkeypatch, tmp_path, candidates, limit=2)
    assert json.loads(out.read_text())["selected_count"] == 2


def test_main_input_not_found_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "argv", [
        "filter_and_rank_candidates.py",
        "--input", str(tmp_path / "missing.json"),
        "--projects", str(tmp_path / "p.json"),
        "--output", str(tmp_path / "out.json"),
    ])
    with pytest.raises(FileNotFoundError):
        far.main()


def test_main_sorted_by_rank_desc(monkeypatch, tmp_path):
    """Higher-scored candidates should appear earlier in the output."""
    call_count = [0]

    def _classify(repo):
        call_count[0] += 1
        # Alternate between high/low relevance
        rel = 5.0 if call_count[0] % 2 == 0 else 1.0
        return {"category": "Other FOSS Projects",
                "scores": {"relevance": rel, "usefulness": 3.0, "maturity": 3.0},
                "notes": ""}

    candidates = [
        _make_cand(full_name=f"org/r{i}", html_url=f"https://github.com/org/r{i}")
        for i in range(4)
    ]
    monkeypatch.setattr(far, "fetch_owner_location", lambda s, l: "Dhaka, Bangladesh")
    monkeypatch.setattr(far, "fetch_readme_snippet",
                        lambda s, n: "Bangladesh open source project for developers worldwide.")
    monkeypatch.setattr(far, "classify_and_score", _classify)
    monkeypatch.setattr(far, "time", mock.MagicMock())

    input_file = tmp_path / "a.json"
    input_file.write_text(json.dumps({"candidates": candidates}), encoding="utf-8")
    out = tmp_path / "out.json"
    monkeypatch.setattr(sys, "argv", [
        "filter_and_rank_candidates.py",
        "--input", str(input_file),
        "--projects", str(tmp_path / "p.json"),
        "--output", str(out),
        "--limit", "10",
    ])
    assert far.main() == 0
    selected = json.loads(out.read_text())["selected"]
    scores = [s["rank_score"] for s in selected]
    assert scores == sorted(scores, reverse=True)
