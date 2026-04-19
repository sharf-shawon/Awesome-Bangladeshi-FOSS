"""Tests for scripts/ai_utils.py."""

from __future__ import annotations

import json
import unittest.mock as mock

import ai_utils


# ---------------------------------------------------------------------------
# heuristic_category
# ---------------------------------------------------------------------------

def test_heuristic_category_fintech():
    assert ai_utils.heuristic_category({"name": "bkash-sdk", "description": "payment gateway", "topics": []}) == "Fintech & Payments"


def test_heuristic_category_mobile():
    assert ai_utils.heuristic_category({"name": "bd-app", "description": "android application", "topics": []}) == "Mobile Apps"


def test_heuristic_category_awesome_list():
    assert ai_utils.heuristic_category({"name": "bd-awesome", "description": "awesome list and resources", "topics": []}) == "Awesome Lists & Resource Collections"


def test_heuristic_category_gov_from_topic():
    repo = {"name": "bd-geo", "description": "district data", "topics": ["geo", "district"]}
    assert ai_utils.heuristic_category(repo) == "Government & Utility Services"


def test_heuristic_category_dev_tools():
    repo = {"name": "bangla-nlp", "description": "nlp toolkit library", "topics": []}
    assert ai_utils.heuristic_category(repo) == "Developer Tools & Libraries"


def test_heuristic_category_web_app():
    repo = {"name": "bd-dashboard", "description": "web platform", "topics": []}
    assert ai_utils.heuristic_category(repo) == "Web Applications"


def test_heuristic_category_other_foss():
    # No matching keywords → falls through to "Other FOSS Projects"
    repo = {"name": "my-project", "description": "a random build system", "topics": []}
    assert ai_utils.heuristic_category(repo) == "Other FOSS Projects"


# ---------------------------------------------------------------------------
# heuristic_scores
# ---------------------------------------------------------------------------

def test_heuristic_scores_bd_keyword_boosts_relevance():
    repo = {"name": "bangla-tool", "description": "bangla NLP", "topics": [], "stargazers_count": 0, "forks_count": 0}
    scores = ai_utils.heuristic_scores(repo)
    assert scores["relevance"] > 2.0


def test_heuristic_scores_no_bd_keyword_baseline_relevance():
    repo = {"name": "generic-tool", "description": "generic utility", "topics": [], "stargazers_count": 0, "forks_count": 0}
    scores = ai_utils.heuristic_scores(repo)
    assert scores["relevance"] == 2.0


def test_heuristic_scores_archived_lowers_maturity():
    repo = {"name": "old-tool", "description": "", "topics": [], "stargazers_count": 100, "forks_count": 80, "archived": True}
    scores = ai_utils.heuristic_scores(repo)
    assert scores["maturity"] == 1.0


def test_heuristic_scores_all_values_in_range():
    repo = {"name": "x", "description": "bangladesh", "topics": [], "stargazers_count": 9999, "forks_count": 9999}
    scores = ai_utils.heuristic_scores(repo)
    for key in ("relevance", "usefulness", "maturity"):
        assert 0.0 <= scores[key] <= 5.0, f"{key} out of range: {scores[key]}"


# ---------------------------------------------------------------------------
# call_openai_json – no API key
# ---------------------------------------------------------------------------

def test_call_openai_json_returns_none_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = ai_utils.call_openai_json({"name": "test"})
    assert result is None


def test_call_openai_json_returns_none_on_http_error(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    mock_response = mock.MagicMock()
    mock_response.status_code = 429
    with mock.patch("ai_utils.requests.post", return_value=mock_response):
        result = ai_utils.call_openai_json({"name": "test"})
    assert result is None


def test_call_openai_json_parses_valid_response(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    payload = {"category": "Mobile Apps", "scores": {"relevance": 4.0, "usefulness": 3.5, "maturity": 3.0}, "notes": "ok"}
    mock_response = mock.MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": json.dumps(payload)}}]
    }
    with mock.patch("ai_utils.requests.post", return_value=mock_response):
        result = ai_utils.call_openai_json({"name": "test"})
    assert result == payload


# ---------------------------------------------------------------------------
# classify_and_score
# ---------------------------------------------------------------------------

def test_classify_and_score_falls_back_to_heuristics_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    repo = {"name": "bangla-toolkit", "description": "NLP library", "topics": ["nlp"], "stargazers_count": 10, "forks_count": 2}
    result = ai_utils.classify_and_score(repo)
    assert result["category"] in ai_utils.ALLOWED_CATEGORIES
    assert "heuristic" in result["notes"]


def test_classify_and_score_uses_heuristic_category_as_fallback_for_invalid_llm_category(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    mock_response = mock.MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": json.dumps({"category": "INVALID CATEGORY", "scores": {"relevance": 5, "usefulness": 5, "maturity": 5}, "notes": "test"})}}]
    }
    with mock.patch("ai_utils.requests.post", return_value=mock_response):
        repo = {"name": "bd-tool", "description": "payment", "topics": []}
        result = ai_utils.classify_and_score(repo)
    # "INVALID CATEGORY" not in ALLOWED_CATEGORIES – heuristic category used instead
    assert result["category"] in ai_utils.ALLOWED_CATEGORIES
    assert result["category"] != "INVALID CATEGORY"


def test_call_openai_json_returns_none_for_empty_choices(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    mock_response = mock.MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"choices": []}
    with mock.patch("ai_utils.requests.post", return_value=mock_response):
        assert ai_utils.call_openai_json({"name": "x"}) is None


def test_call_openai_json_returns_none_for_empty_content(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    mock_response = mock.MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"choices": [{"message": {"content": ""}}]}
    with mock.patch("ai_utils.requests.post", return_value=mock_response):
        assert ai_utils.call_openai_json({"name": "x"}) is None


def test_call_openai_json_returns_none_for_invalid_json_content(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    mock_response = mock.MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"choices": [{"message": {"content": "not-json!!!"}}]}
    with mock.patch("ai_utils.requests.post", return_value=mock_response):
        assert ai_utils.call_openai_json({"name": "x"}) is None


def test_classify_and_score_clamps_scores_from_llm(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    mock_response = mock.MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": json.dumps({"category": "Mobile Apps", "scores": {"relevance": 99, "usefulness": -5, "maturity": 3}, "notes": ""})}}]
    }
    with mock.patch("ai_utils.requests.post", return_value=mock_response):
        result = ai_utils.classify_and_score({"name": "x", "description": "", "topics": []})
    assert result["scores"]["relevance"] == 5.0
    assert result["scores"]["usefulness"] == 0.0
