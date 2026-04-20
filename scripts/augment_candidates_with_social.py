#!/usr/bin/env python3
"""Augment candidate repositories by scanning social/web sources for GitHub links.

Usage:
  python scripts/augment_candidates_with_social.py --input data/candidates.json --output data/candidates_augmented.json

Environment:
  GITHUB_TOKEN (optional but recommended): GitHub API token for repo metadata.
  REDDIT_TOKEN (optional): Reddit OAuth token for better search access.
  SEARCH_API_KEY (optional): Reserved for external search providers.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = REPO_ROOT / "data" / "candidates.json"
DEFAULT_OUTPUT = REPO_ROOT / "data" / "candidates_augmented.json"
GITHUB_REPO_LINK_RE = re.compile(r"https://github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)")
API_BASE = "https://api.github.com"


def build_session() -> requests.Session:
    session = requests.Session()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "awesome-bd-foss-augment"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    session.headers.update(headers)
    return session


def request_with_backoff(
    session: requests.Session,
    url: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    for attempt in range(1, 6):
        response = session.get(url, params=params, headers=headers, timeout=30)
        if response.status_code == 429:
            sleep_for = min(2**attempt, 45)
            logging.warning("Rate limited (%s); sleeping %ss", url, sleep_for)
            time.sleep(sleep_for)
            continue
        if response.status_code in {500, 502, 503, 504}:
            sleep_for = min(2**attempt, 30)
            logging.warning("Temporary error %s from %s; retrying in %ss", response.status_code, url, sleep_for)
            time.sleep(sleep_for)
            continue
        if response.status_code == 403 and response.headers.get("X-RateLimit-Remaining") == "0":
            reset_epoch = int(response.headers.get("X-RateLimit-Reset", "0") or "0")
            sleep_for = max(reset_epoch - int(time.time()), 1)
            logging.warning("Rate limited by GitHub API; sleeping %ss", sleep_for)
            time.sleep(min(sleep_for, 60))
            continue
        if response.status_code >= 400:
            logging.warning("Skipping failed request %s (%s)", url, response.status_code)
            return None
        content_type = response.headers.get("Content-Type", "")
        if "application/json" in content_type:
            return response.json()
        return response.text
    return None


def extract_repo_full_names(text: str) -> set[str]:
    matches = GITHUB_REPO_LINK_RE.findall(text or "")
    cleaned = {match.rstrip("/").rstrip(".") for match in matches if "/" in match}
    return {name for name in cleaned if len(name.split("/")) == 2}


def search_reddit(session: requests.Session, queries: list[str]) -> set[str]:
    results: set[str] = set()
    reddit_token = os.environ.get("REDDIT_TOKEN", "").strip()
    if reddit_token:
        # OAuth query; requires REDDIT_TOKEN provided in repository secrets.
        logging.info("Using Reddit OAuth API for discovery")
        headers = {"Authorization": f"Bearer {reddit_token}", "User-Agent": "awesome-bd-foss-augment"}
        for query in queries:
            payload = request_with_backoff(
                session,
                "https://oauth.reddit.com/search",
                params={"q": query, "limit": 25, "sort": "relevance"},
                headers=headers,
            )
            children = ((((payload or {}).get("data") or {}).get("children")) or [])
            for child in children:
                data = child.get("data") or {}
                text = " ".join(
                    [
                        data.get("url_overridden_by_dest", ""),
                        data.get("selftext", ""),
                        data.get("title", ""),
                    ]
                )
                results.update(extract_repo_full_names(text))
            time.sleep(1)
        return results

    # Public JSON search fallback; no auth required but modestly throttled.
    logging.info("Using public Reddit JSON search fallback")
    for query in queries:
        payload = request_with_backoff(
            session,
            "https://www.reddit.com/search.json",
            params={"q": query, "limit": 25, "sort": "relevance", "restrict_sr": "false"},
            headers={"User-Agent": "awesome-bd-foss-augment"},
        )
        children = ((((payload or {}).get("data") or {}).get("children")) or [])
        for child in children:
            data = child.get("data") or {}
            text = " ".join(
                [
                    data.get("url", ""),
                    data.get("selftext", ""),
                    data.get("title", ""),
                ]
            )
            results.update(extract_repo_full_names(text))
        time.sleep(1)
    return results


def search_web(session: requests.Session, queries: list[str]) -> set[str]:
    # Free fallback search source (DuckDuckGo HTML endpoint); SEARCH_API_KEY can be used by maintainers
    # for swapping to an external provider later without changing the rest of this script.
    if os.environ.get("SEARCH_API_KEY", "").strip():
        logging.info("SEARCH_API_KEY detected; using built-in web fallback anyway (provider can be swapped later).")

    results: set[str] = set()
    for query in queries:
        html = request_with_backoff(
            session,
            "https://duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": "awesome-bd-foss-augment"},
        )
        if isinstance(html, str):
            results.update(extract_repo_full_names(html))
        time.sleep(1)
    return results


def normalize_repo(repo: dict[str, Any], source: str) -> dict[str, Any]:
    return {
        "full_name": repo.get("full_name"),
        "name": repo.get("name"),
        "html_url": (repo.get("html_url") or "").rstrip("/"),
        "description": (repo.get("description") or "").strip(),
        "owner": {
            "login": (repo.get("owner") or {}).get("login"),
            "type": (repo.get("owner") or {}).get("type"),
        },
        "language": repo.get("language"),
        "topics": [str(topic).lower() for topic in (repo.get("topics") or []) if isinstance(topic, str)],
        "stargazers_count": int(repo.get("stargazers_count") or 0),
        "forks_count": int(repo.get("forks_count") or 0),
        "open_issues_count": int(repo.get("open_issues_count") or 0),
        "fork": bool(repo.get("fork")),
        "archived": bool(repo.get("archived")),
        "default_branch": repo.get("default_branch"),
        "updated_at": repo.get("updated_at"),
        "license": {
            "key": (repo.get("license") or {}).get("key"),
            "spdx_id": (repo.get("license") or {}).get("spdx_id"),
        },
        "source": source,
    }


def fetch_repo_details(session: requests.Session, full_name: str) -> dict[str, Any] | None:
    payload = request_with_backoff(session, f"{API_BASE}/repos/{full_name}")
    if not isinstance(payload, dict):
        return None
    if not payload.get("full_name"):
        return None
    if payload.get("fork") or payload.get("archived"):
        return None
    if not payload.get("description"):
        return None
    return payload


def merge_candidates(base: list[dict[str, Any]], extra: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_name: dict[str, dict[str, Any]] = {}
    for item in base + extra:
        full_name = (item.get("full_name") or "").lower()
        if not full_name:
            continue
        if full_name not in by_name:
            by_name[full_name] = item
            continue
        merged = by_name[full_name]
        merged_sources = set(str(merged.get("source") or "").split(",")) | set(str(item.get("source") or "").split(","))
        merged["source"] = ",".join(sorted(s for s in merged_sources if s))
        merged["stargazers_count"] = max(int(merged.get("stargazers_count") or 0), int(item.get("stargazers_count") or 0))
        merged["forks_count"] = max(int(merged.get("forks_count") or 0), int(item.get("forks_count") or 0))
        merged["open_issues_count"] = max(int(merged.get("open_issues_count") or 0), int(item.get("open_issues_count") or 0))
    return sorted(by_name.values(), key=lambda x: (int(x.get("stargazers_count") or 0), x.get("full_name") or ""), reverse=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Input candidates JSON path")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output augmented candidates JSON path")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    payload = json.loads(input_path.read_text(encoding="utf-8"))
    base_candidates = payload.get("candidates") or []

    session = build_session()
    queries = [
        "Bangladeshi open source GitHub",
        "Bangla NLP GitHub",
        "Bangladesh payment gateway GitHub",
        "বাংলা ওপেন সোর্স প্রজেক্ট GitHub",
        "r/BdProgrammers GitHub Bangladesh open source",
    ]

    repo_names = set()
    repo_names.update(search_reddit(session, queries))
    repo_names.update(search_web(session, queries))
    logging.info("Extracted %d candidate repository names from social/web sources", len(repo_names))

    augmented: list[dict[str, Any]] = []
    for full_name in sorted(repo_names):
        details = fetch_repo_details(session, full_name)
        if not details:
            continue
        augmented.append(normalize_repo(details, source="social_web_discovery"))
        time.sleep(0.3)

    merged_candidates = merge_candidates(base_candidates, augmented)
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_candidate_count": len(base_candidates),
        "social_extracted_repo_count": len(repo_names),
        "augmented_candidate_count": len(merged_candidates),
        "candidates": merged_candidates,
    }
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    logging.info("Wrote augmented candidates: %s (%d candidates)", output_path, len(merged_candidates))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
