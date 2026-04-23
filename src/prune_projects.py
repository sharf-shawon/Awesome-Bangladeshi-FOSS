#!/usr/bin/env python3
"""Prune projects that do not meet minimum stars or have broken links."""

import json
import os
import requests
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PROJECTS_PATH = REPO_ROOT / "data" / "projects.json"
REMOVED_PATH = REPO_ROOT / "data" / "removed_projects.json"
CONFIG_PATH = REPO_ROOT / "data" / "discovery_config.json"

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "awesome-bd-foss-pruner"
}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"

def load_json(path, default=None):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return default if default is not None else []
    return default if default is not None else []

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

def get_repo_meta(repo_url):
    import re
    match = re.search(r"github\.com/([^/]+)/([^/]+)", repo_url)
    if not match:
        return None
    owner, repo = match.groups()
    try:
        resp = requests.get(f"https://api.github.com/repos/{owner}/{repo}", headers=HEADERS, timeout=10)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None

def main():
    projects_data = load_json(PROJECTS_PATH, {"projects": []})
    removed_data = load_json(REMOVED_PATH, {"removed": []})
    config = load_json(CONFIG_PATH, {})
    min_stars = config.get("minimum_stars", 10)

    kept = []
    removed = []
    for p in projects_data["projects"]:
        repo_url = p["repository"]
        meta = get_repo_meta(repo_url)
        if not meta:
            p["removal_reason"] = "Repository not found or inaccessible."
            removed.append(p)
            print(f"REMOVED: {repo_url} (broken link)")
            continue
        stars = meta.get("stargazers_count", 0)
        if stars < min_stars:
            p["removal_reason"] = f"Stars below minimum ({stars} < {min_stars})"
            removed.append(p)
            print(f"REMOVED: {repo_url} (stars: {stars})")
            continue
        kept.append(p)

    if removed:
        for r in removed:
            removed_data["removed"].append({
                "name": r["name"],
                "html_url": r["repository"],
                "description": r["description"],
                "category": r["category"],
                "reason": r["removal_reason"],
                "requested_by": "automation",
                "repo_owner": "",
                "owner_verified": False
            })
        removed_data["removed_count"] = len(removed_data["removed"])
        save_json(REMOVED_PATH, removed_data)

    projects_data["projects"] = kept
    save_json(PROJECTS_PATH, projects_data)
    print(f"Pruned {len(removed)} projects. {len(kept)} remain.")

if __name__ == "__main__":
    main()
