#!/usr/bin/env python3
"""Discover Bangladeshi FOSS candidate repositories from GitHub search.

Usage:
  python src/discover_candidates.py --output data/candidates.json

Environment:
  GITHUB_TOKEN (optional but recommended): GitHub API token.
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
DEFAULT_OUTPUT = REPO_ROOT / "data" / "candidates.json"
DEFAULT_CONFIG = REPO_ROOT / "data" / "discovery_config.json"
API_BASE = "https://api.github.com"
GITHUB_REPO_URL_RE = re.compile(r"^https://github\.com/[^/\s]+/[^/\s]+/?$")


def load_config(path: Path) -> dict[str, Any]:
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                logging.error("Failed to parse config file: %s", path)
                return {}
    return {}


def build_session() -> requests.Session:
    session = requests.Session()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "awesome-bd-foss-discovery",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    session.headers.update(headers)
    return session


def request_json(session: requests.Session, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    # Simple backoff for transient failures and GitHub API limits.
    for attempt in range(1, 6):
        response = session.get(url, params=params, timeout=30)
        if response.status_code == 403 and response.headers.get("X-RateLimit-Remaining") == "0":
            reset_epoch = int(response.headers.get("X-RateLimit-Reset", "0") or "0")
            sleep_for = max(reset_epoch - int(time.time()), 1)
            logging.warning("Rate limited by GitHub API; sleeping for %ss", sleep_for)
            time.sleep(min(sleep_for, 60))
            continue
        if response.status_code in {500, 502, 503, 504}:
            sleep_for = min(2**attempt, 30)
            logging.warning("GitHub API temporary error (%s); retrying in %ss", response.status_code, sleep_for)
            time.sleep(sleep_for)
            continue
        response.raise_for_status()
        return response.json()
    raise RuntimeError(f"Failed to fetch {url} after retries")


def normalize_repo_item(repo: dict[str, Any], source: str) -> dict[str, Any] | None:
    html_url = (repo.get("html_url") or "").strip()
    full_name = (repo.get("full_name") or "").strip()
    if not full_name or not GITHUB_REPO_URL_RE.match(html_url):
        return None

    topics = repo.get("topics") or []
    return {
        "full_name": full_name,
        "name": repo.get("name") or full_name.split("/")[-1],
        "html_url": html_url.rstrip("/"),
        "description": (repo.get("description") or "").strip(),
        "owner": {
            "login": (repo.get("owner") or {}).get("login"),
            "type": (repo.get("owner") or {}).get("type"),
        },
        "language": repo.get("language"),
        "topics": [str(topic).lower() for topic in topics if isinstance(topic, str)],
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


def discover_by_users(session: requests.Session, config: dict[str, Any]) -> list[dict[str, Any]]:
    query = config.get("user_search_query", "location:Bangladesh")
    max_users = config.get("max_users_to_fetch", 25)
    per_page = config.get("user_repos_per_page", 30)

    logging.info("Searching users with query: %s", query)
    users_payload = request_json(
        session,
        f"{API_BASE}/search/users",
        params={"q": query, "per_page": max_users, "page": 1},
    )
    users = users_payload.get("items") or []
    logging.info("Found %d users in location search", len(users))
    candidates: list[dict[str, Any]] = []

    for user in users[:max_users]:
        login = user.get("login")
        if not login:
            continue
        logging.info("Fetching repos for user: %s", login)
        repos = request_json(
            session,
            f"{API_BASE}/users/{login}/repos",
            params={"sort": "updated", "per_page": per_page, "type": "public"},
        )
        if not isinstance(repos, list):
            continue
        for repo in repos:
            normalized = normalize_repo_item(repo, source=f"github_user_location:{login}")
            if normalized:
                # Optional filtering by stars at discovery time
                if normalized["stargazers_count"] >= config.get("min_stars_for_candidate", 0):
                    candidates.append(normalized)
        time.sleep(0.2)
    return candidates


def discover_by_topics(session: requests.Session, config: dict[str, Any]) -> list[dict[str, Any]]:
    topic_queries = config.get("topic_queries", [
        "topic:bangladesh",
        "topic:bangla",
        "bangla in:name,description,readme",
        "bangladesh in:name,description,readme",
    ])
    per_page = config.get("repo_search_per_page", 50)
    min_stars = config.get("min_stars_for_candidate", 0)

    candidates: list[dict[str, Any]] = []
    for query in topic_queries:
        logging.info("Searching repositories with query: %s", query)
        payload = request_json(
            session,
            f"{API_BASE}/search/repositories",
            params={"q": query, "sort": "updated", "order": "desc", "per_page": per_page, "page": 1},
        )
        for item in payload.get("items") or []:
            normalized = normalize_repo_item(item, source=f"github_repo_search:{query}")
            if normalized and normalized["stargazers_count"] >= min_stars:
                candidates.append(normalized)
        time.sleep(0.3)
    return candidates


def dedupe_candidates(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_full_name: dict[str, dict[str, Any]] = {}
    for item in items:
        full_name = item["full_name"].lower()
        existing = by_full_name.get(full_name)
        if not existing:
            by_full_name[full_name] = item
            continue
        source_list = {existing.get("source", "")}
        source_list.add(item.get("source", ""))
        existing["source"] = ",".join(sorted(filter(None, source_list)))
        existing["stargazers_count"] = max(existing.get("stargazers_count", 0), item.get("stargazers_count", 0))
        existing["forks_count"] = max(existing.get("forks_count", 0), item.get("forks_count", 0))
    return sorted(by_full_name.values(), key=lambda r: (r.get("stargazers_count", 0), r["full_name"]), reverse=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output JSON file path")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Configuration JSON file path")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    config = load_config(Path(args.config))

    session = build_session()
    user_candidates = discover_by_users(session, config)
    topic_candidates = discover_by_topics(session, config)
    candidates = dedupe_candidates(user_candidates + topic_candidates)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": ["github_users_location_bangladesh", "github_repo_topic_search"],
        "candidate_count": len(candidates),
        "candidates": candidates,
    }
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    logging.info("Wrote %s with %d candidates", output_path, len(candidates))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
