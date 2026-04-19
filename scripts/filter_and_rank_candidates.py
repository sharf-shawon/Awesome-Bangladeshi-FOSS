#!/usr/bin/env python3
"""Filter, classify, and rank discovered candidate repositories.

Usage:
  python scripts/filter_and_rank_candidates.py --input data/candidates_augmented.json --projects data/projects.json --output data/top10_to_add.json

Environment:
  GITHUB_TOKEN (optional but recommended): GitHub API token for README snippets and owner metadata.
  OPENAI_API_KEY (optional): Enables AI-assisted scoring via scripts/ai_utils.py.
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from ai_utils import classify_and_score


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = REPO_ROOT / "data" / "candidates_augmented.json"
DEFAULT_PROJECTS = REPO_ROOT / "data" / "projects.json"
DEFAULT_OUTPUT = REPO_ROOT / "data" / "top10_to_add.json"
API_BASE = "https://api.github.com"

ALLOWED_LICENSE_PREFIXES = ("MIT", "Apache", "GPL", "AGPL", "LGPL", "BSD", "MPL", "ISC", "EPL", "CC0")
BD_KEYWORDS = {
    "bangla",
    "বাংলা",
    "bangladesh",
    "dhaka",
    "chattogram",
    "bkash",
    "nagad",
    "bd",
    "upazila",
    "district",
    "bengali",
}
README_ENTRY_REPO_RE = re.compile(r"^https://github\.com/([^/\s]+/[^/\s]+)/*$")


def build_session() -> requests.Session:
    session = requests.Session()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "awesome-bd-foss-ranker"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    session.headers.update(headers)
    return session


def request_json(session: requests.Session, url: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    # Minimal retry/backoff around transient errors and rate limits.
    for attempt in range(1, 6):
        response = session.get(url, params=params, timeout=30)
        if response.status_code == 403 and response.headers.get("X-RateLimit-Remaining") == "0":
            reset_epoch = int(response.headers.get("X-RateLimit-Reset", "0") or "0")
            wait_for = max(reset_epoch - int(time.time()), 1)
            logging.warning("GitHub rate limited; waiting %ss", wait_for)
            time.sleep(min(wait_for, 60))
            continue
        if response.status_code in {500, 502, 503, 504}:
            wait_for = min(2**attempt, 30)
            logging.warning("Temporary API error %s; waiting %ss", response.status_code, wait_for)
            time.sleep(wait_for)
            continue
        if response.status_code >= 400:
            logging.warning("Failed request %s (%s)", url, response.status_code)
            return None
        return response.json()
    return None


def load_existing_repo_names(projects_path: Path) -> set[str]:
    if not projects_path.exists():
        return set()
    payload = json.loads(projects_path.read_text(encoding="utf-8"))
    existing: set[str] = set()
    for item in payload.get("projects") or []:
        repository = str(item.get("repository") or "").strip()
        match = README_ENTRY_REPO_RE.match(repository)
        if match:
            existing.add(match.group(1).lower())
    return existing


def normalize_license_spdx(candidate: dict[str, Any]) -> str:
    license_data = candidate.get("license") or {}
    spdx = (license_data.get("spdx_id") or "").strip()
    return spdx


def license_is_allowed(spdx: str) -> bool:
    if not spdx or spdx.upper() == "NOASSERTION":
        return False
    return any(spdx.startswith(prefix) for prefix in ALLOWED_LICENSE_PREFIXES)


def fetch_owner_location(session: requests.Session, owner_login: str) -> str:
    if not owner_login:
        return ""
    payload = request_json(session, f"{API_BASE}/users/{owner_login}")
    if not payload:
        return ""
    return str(payload.get("location") or "").strip()


def fetch_readme_snippet(session: requests.Session, full_name: str) -> str:
    payload = request_json(session, f"{API_BASE}/repos/{full_name}/readme")
    if not payload:
        return ""
    content_b64 = payload.get("content")
    if not content_b64:
        return ""
    try:
        decoded = base64.b64decode(content_b64).decode("utf-8", errors="ignore")
    except Exception:
        return ""
    text = re.sub(r"\s+", " ", decoded).strip()
    return text[:600]


def has_bangladeshi_signal(candidate: dict[str, Any], owner_location: str, readme_snippet: str) -> bool:
    blob = " ".join(
        [
            candidate.get("full_name") or "",
            candidate.get("description") or "",
            " ".join(candidate.get("topics") or []),
            owner_location,
            readme_snippet,
        ]
    ).lower()
    if "bangladesh" in owner_location.lower():
        return True
    if "bd" == owner_location.lower().strip():
        return True
    return any(keyword in blob for keyword in BD_KEYWORDS)


def has_non_trivial_docs(candidate: dict[str, Any], readme_snippet: str) -> bool:
    description = (candidate.get("description") or "").strip()
    if len(description) >= 25:
        return True
    return len(readme_snippet) >= 180


def has_min_signal(candidate: dict[str, Any]) -> bool:
    stars = int(candidate.get("stargazers_count") or 0)
    forks = int(candidate.get("forks_count") or 0)
    issues = int(candidate.get("open_issues_count") or 0)
    return stars >= 3 or forks >= 2 or issues >= 3


def activity_score(candidate: dict[str, Any]) -> float:
    stars = int(candidate.get("stargazers_count") or 0)
    forks = int(candidate.get("forks_count") or 0)
    updated_at = str(candidate.get("updated_at") or "")
    freshness = 0.0
    try:
        dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        age_days = max((datetime.now(timezone.utc) - dt).days, 0)
        freshness = max(0.0, 1.0 - min(age_days, 3650) / 3650)
    except Exception:
        freshness = 0.2
    score = min(stars / 200, 1.0) * 0.6 + min(forks / 80, 1.0) * 0.2 + freshness * 0.2
    return round(score * 5, 2)


def final_rank_score(ai_scores: dict[str, float], candidate: dict[str, Any]) -> float:
    activity = activity_score(candidate)
    score = (
        float(ai_scores.get("relevance", 0)) * 0.45
        + float(ai_scores.get("usefulness", 0)) * 0.25
        + float(ai_scores.get("maturity", 0)) * 0.20
        + activity * 0.10
    )
    return round(score, 4)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Augmented candidates JSON path")
    parser.add_argument("--projects", default=str(DEFAULT_PROJECTS), help="Existing projects JSON path")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output top candidates JSON path")
    parser.add_argument("--limit", type=int, default=10, help="Max number of candidates to select")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    input_path = Path(args.input)
    projects_path = Path(args.projects)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    payload = json.loads(input_path.read_text(encoding="utf-8"))
    candidates = payload.get("candidates") or []
    existing_repo_names = load_existing_repo_names(projects_path)
    session = build_session()

    selected: list[dict[str, Any]] = []
    skipped = 0
    for candidate in candidates:
        full_name = str(candidate.get("full_name") or "").strip()
        if not full_name:
            skipped += 1
            continue
        if full_name.lower() in existing_repo_names:
            skipped += 1
            continue
        if candidate.get("fork") or candidate.get("archived"):
            skipped += 1
            continue

        spdx = normalize_license_spdx(candidate)
        if not license_is_allowed(spdx):
            skipped += 1
            continue

        owner_login = str((candidate.get("owner") or {}).get("login") or "")
        owner_location = fetch_owner_location(session, owner_login)
        readme_snippet = fetch_readme_snippet(session, full_name)
        candidate["owner_location"] = owner_location
        candidate["readme_snippet"] = readme_snippet

        if not has_non_trivial_docs(candidate, readme_snippet):
            skipped += 1
            continue
        if not has_min_signal(candidate):
            skipped += 1
            continue
        if not has_bangladeshi_signal(candidate, owner_location, readme_snippet):
            skipped += 1
            continue

        ai_result = classify_and_score(candidate)
        candidate["category"] = ai_result["category"]
        candidate["ai_scores"] = ai_result["scores"]
        candidate["ai_notes"] = ai_result.get("notes", "")
        candidate["rank_score"] = final_rank_score(candidate["ai_scores"], candidate)
        selected.append(candidate)
        time.sleep(0.2)

    selected.sort(key=lambda c: (float(c.get("rank_score") or 0), int(c.get("stargazers_count") or 0)), reverse=True)
    top_selected = selected[: max(0, args.limit)]

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_candidate_count": len(candidates),
        "skipped_count": skipped,
        "selected_count": len(top_selected),
        "selected": [
            {
                "full_name": c.get("full_name"),
                "name": c.get("name") or str(c.get("full_name", "")).split("/")[-1],
                "html_url": c.get("html_url"),
                "description": c.get("description"),
                "category": c.get("category"),
                "license": c.get("license"),
                "stars": int(c.get("stargazers_count") or 0),
                "forks": int(c.get("forks_count") or 0),
                "updated_at": c.get("updated_at"),
                "source": c.get("source"),
                "owner_location": c.get("owner_location"),
                "ai_scores": c.get("ai_scores"),
                "ai_notes": c.get("ai_notes"),
                "rank_score": c.get("rank_score"),
            }
            for c in top_selected
        ],
    }
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    logging.info("Selected %d candidates (from %d) and wrote %s", len(top_selected), len(candidates), output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
