#!/usr/bin/env python3
"""Small AI helper for category classification and scoring.

Usage:
  Imported by scripts/filter_and_rank_candidates.py.

Environment:
  OPENAI_API_KEY (optional): Enables model-assisted scoring.
  OPENAI_MODEL (optional): Defaults to gpt-4o-mini.

Notes:
  - If no API key is set, this module falls back to deterministic heuristics.
  - Provider can be swapped by replacing `call_openai_json` implementation.
"""

from __future__ import annotations

import json
import os
from typing import Any

import requests


ALLOWED_CATEGORIES = [
    "Web Applications",
    "Mobile Apps",
    "Developer Tools & Libraries",
    "Government & Utility Services",
    "Fintech & Payments",
    "Other FOSS Projects",
    "Awesome Lists & Resource Collections",
]


def heuristic_category(repo: dict[str, Any]) -> str:
    text = " ".join(
        [
            repo.get("name") or "",
            repo.get("description") or "",
            " ".join(repo.get("topics") or []),
        ]
    ).lower()
    if any(k in text for k in ["bkash", "nagad", "payment", "sslcommerz", "gateway", "wallet", "fintech"]):
        return "Fintech & Payments"
    if any(k in text for k in ["android", "ios", "flutter", "react native", "mobile", "apk"]):
        return "Mobile Apps"
    if any(k in text for k in ["dataset", "awesome", "resources", "collection", "list"]):
        return "Awesome Lists & Resource Collections"
    if any(k in text for k in ["geo", "civic", "gov", "utility", "district", "upazila", "public api"]):
        return "Government & Utility Services"
    if any(k in text for k in ["library", "sdk", "toolkit", "cli", "package", "api", "plugin", "nlp"]):
        return "Developer Tools & Libraries"
    if any(k in text for k in ["web", "dashboard", "platform", "portal", "site", "saas"]):
        return "Web Applications"
    return "Other FOSS Projects"


def heuristic_scores(repo: dict[str, Any]) -> dict[str, float]:
    text = " ".join(
        [
            repo.get("name") or "",
            repo.get("description") or "",
            " ".join(repo.get("topics") or []),
            repo.get("readme_snippet") or "",
        ]
    ).lower()

    relevance = 2.0
    if any(k in text for k in ["bangla", "বাংলা", "bangladesh", "bd", "dhaka", "bkash", "nagad"]):
        relevance = 4.5
    usefulness = 2.5 + min(float(repo.get("stargazers_count") or 0) / 150.0, 2.0)
    maturity = 2.0 + min(float(repo.get("forks_count") or 0) / 120.0, 1.5)
    if repo.get("archived"):
        maturity = 1.0

    return {
        "relevance": round(min(relevance, 5.0), 2),
        "usefulness": round(min(usefulness, 5.0), 2),
        "maturity": round(min(maturity, 5.0), 2),
    }


def call_openai_json(repo: dict[str, Any]) -> dict[str, Any] | None:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None

    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    prompt = {
        "task": "Classify and score repository for Awesome Bangladeshi FOSS curation",
        "allowed_categories": ALLOWED_CATEGORIES,
        "repo": {
            "full_name": repo.get("full_name"),
            "name": repo.get("name"),
            "description": repo.get("description"),
            "topics": repo.get("topics"),
            "license_spdx": ((repo.get("license") or {}).get("spdx_id")),
            "stars": repo.get("stargazers_count"),
            "forks": repo.get("forks_count"),
            "updated_at": repo.get("updated_at"),
            "readme_snippet": repo.get("readme_snippet"),
        },
        "output_schema": {
            "category": "one of allowed_categories",
            "scores": {"relevance": "0-5", "usefulness": "0-5", "maturity": "0-5"},
            "notes": "short reason",
        },
    }
    payload = {
        "model": model,
        "input": [
            {"role": "system", "content": "Return strict JSON only."},
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
        "text": {"format": {"type": "json_object"}},
    }
    response = requests.post(
        "https://api.openai.com/v1/responses",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=45,
    )
    if response.status_code >= 400:
        return None
    body = response.json()
    text = (body.get("output_text") or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def classify_and_score(repo: dict[str, Any]) -> dict[str, Any]:
    llm = call_openai_json(repo)
    default_category = heuristic_category(repo)
    default_scores = heuristic_scores(repo)
    if not llm:
        return {"category": default_category, "scores": default_scores, "notes": "heuristic fallback"}

    raw_category = str(llm.get("category") or "").strip()
    category = raw_category if raw_category in ALLOWED_CATEGORIES else default_category
    raw_scores = llm.get("scores") or {}
    scores = {
        "relevance": float(raw_scores.get("relevance", default_scores["relevance"])),
        "usefulness": float(raw_scores.get("usefulness", default_scores["usefulness"])),
        "maturity": float(raw_scores.get("maturity", default_scores["maturity"])),
    }
    for key in ("relevance", "usefulness", "maturity"):
        scores[key] = round(max(0.0, min(5.0, scores[key])), 2)

    return {
        "category": category,
        "scores": scores,
        "notes": str(llm.get("notes") or "model"),
    }
