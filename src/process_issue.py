import os
import sys
import json
import re
from pathlib import Path
import requests

REPO_ROOT = Path(__file__).parent.parent
PROJECTS_PATH = REPO_ROOT / "data" / "projects.json"
REMOVED_PATH = REPO_ROOT / "data" / "removed_projects.json"
REJECTED_PATH = REPO_ROOT / "data" / "rejected_projects.json"
CONFIG_PATH = REPO_ROOT / "data" / "discovery_config.json"

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "awesome-bd-foss-automation"
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

def parse_issue(body):
    fields = {}
    current_key = None
    # Match headers like "### Project name"
    header_re = re.compile(r"^###\s+(.+)$")
    
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        
        match = header_re.match(line)
        if match:
            current_key = match.group(1).strip().lower().replace(" ", "_")
            continue
            
        if current_key:
            # Handle checkboxes
            if line.startswith("- [") and "]" in line:
                is_checked = "[x]" in line.lower()
                # Store checkbox status if needed, but usually we just need the text
                continue
            
            if current_key not in fields:
                fields[current_key] = line
            else:
                fields[current_key] += " " + line
    
    # Normalize values
    for k in fields:
        fields[k] = fields[k].strip()
    return fields

def normalize_url(url):
    return url.rstrip("/").lower()

def get_repo_meta(repo_url):
    match = re.search(r"github\.com/([^/]+)/([^/]+)", repo_url)
    if not match:
        return None
    owner, repo = match.groups()
    try:
        resp = requests.get(f"https://api.github.com/repos/{owner}/{repo}", headers=HEADERS, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"Error fetching repo meta: {e}")
        return None

def process_submission(fields, issue_author):
    project_name = fields.get("project_name")
    repo_url = fields.get("repository_url")
    description = fields.get("short_description") or fields.get("description")
    category = fields.get("category")
    
    if not (project_name and repo_url and description and category):
        print(f"ERROR: Missing required fields. Found: {list(fields.keys())}")
        return False
    
    norm_url = normalize_url(repo_url)
    
    # Load existing data
    projects_data = load_json(PROJECTS_PATH, {"projects": []})
    removed_data = load_json(REMOVED_PATH, {"removed": []})
    rejected_data = load_json(REJECTED_PATH, {"rejected": []})
    config = load_json(CONFIG_PATH, {})
    
    min_stars = config.get("minimum_stars", 10)
    
    # Check for duplicates
    if any(normalize_url(p["repository"]) == norm_url for p in projects_data["projects"]):
        print(f"ERROR: Project already exists in the list: {repo_url}")
        return False
        
    # Check removed list
    if any(normalize_url(p.get("html_url") or p.get("repository") or "") == norm_url for p in removed_data.get("removed", [])):
        print(f"ERROR: Project was previously removed and cannot be re-added automatically: {repo_url}")
        return False
        
    # Check rejected list
    is_rejected = any(normalize_url(p.get("html_url") or p.get("repository") or "") == norm_url for p in rejected_data.get("rejected", []))
    reconsideration = fields.get("reconsideration_notes")
    if is_rejected and (not reconsideration or reconsideration.strip().lower() == "_no response_"):
        print(f"ERROR: Project is on the rejected list. Please provide reconsideration notes explaining what has changed.")
        return False
        
    # Fetch stars and validate
    meta = get_repo_meta(repo_url)
    if not meta:
        print(f"ERROR: Could not fetch repository metadata for {repo_url}. Ensure it exists and is public.")
        return False
        
    stars = meta.get("stargazers_count", 0)
    if stars < min_stars:
        print(f"ERROR: Project does not meet the minimum star requirement ({stars} < {min_stars}).")
        return False
    
    # Ensure description ends with a period
    if not description.endswith((".", "!", "?")):
        description += "."
        
    new_project = {
        "category": category,
        "name": project_name,
        "repository": repo_url.rstrip("/"),
        "description": description
    }
    
    # Add to list
    projects_data["projects"].append(new_project)
    # Sort by name within category (optional, but good for consistency)
    projects_data["projects"].sort(key=lambda p: (p["category"], p["name"].lower()))
    
    save_json(PROJECTS_PATH, projects_data)
    
    # If it was in rejected list, remove it
    if is_rejected:
        rejected_data["rejected"] = [
            p for p in rejected_data.get("rejected", []) 
            if normalize_url(p.get("html_url") or p.get("repository") or "") != norm_url
        ]
        rejected_data["rejected_count"] = len(rejected_data["rejected"])
        save_json(REJECTED_PATH, rejected_data)
        
    print(f"SUCCESS: Added '{project_name}' to '{category}'.")
    return True

def process_removal(fields, issue_author):
    repo_url = fields.get("repository_url")
    reason = fields.get("reason_for_removal") or fields.get("reason")
    
    if not (repo_url and reason):
        print(f"ERROR: Missing required fields for removal. Found: {list(fields.keys())}")
        return False
    
    norm_url = normalize_url(repo_url)
    projects_data = load_json(PROJECTS_PATH, {"projects": []})
    removed_data = load_json(REMOVED_PATH, {"removed": []})
    
    # Find project
    project = next((p for p in projects_data["projects"] if normalize_url(p["repository"]) == norm_url), None)
    if not project:
        print(f"ERROR: Project not found in the list: {repo_url}")
        return False
        
    # Verify ownership
    meta = get_repo_meta(repo_url)
    is_owner = False
    repo_owner_login = ""
    if meta:
        repo_owner_login = meta.get("owner", {}).get("login", "").lower()
        is_owner = repo_owner_login == issue_author.lower()
        
    # Remove from projects
    projects_data["projects"] = [p for p in projects_data["projects"] if normalize_url(p["repository"]) != norm_url]
    save_json(PROJECTS_PATH, projects_data)
    
    # Add to removed list
    removed_entry = {
        "name": project["name"],
        "html_url": project["repository"],
        "description": project["description"],
        "category": project["category"],
        "reason": reason,
        "requested_by": issue_author,
        "repo_owner": repo_owner_login,
        "owner_verified": is_owner
    }
    removed_data["removed"].append(removed_entry)
    removed_data["removed_count"] = len(removed_data["removed"])
    save_json(REMOVED_PATH, removed_data)
    
    status = "SUCCESS" if is_owner else "MANUAL_REVIEW"
    if is_owner:
        print(f"SUCCESS: Removed '{project['name']}' (Owner verified).")
    else:
        print(f"MANUAL_REVIEW: Removal requested by non-owner @{issue_author}. Owner is @{repo_owner_login}.")
    
    return True

def main():
    if len(sys.argv) < 5:
        print("Usage: python src/process_issue.py <number> <title> <body> <author>")
        return
        
    issue_number, title, body, author = sys.argv[1:5]
    title_lower = title.lower()
    
    fields = parse_issue(body)
    
    is_add = "submission" in title_lower or "[submission]" in title_lower
    is_remove = "removal" in title_lower or "[removal]" in title_lower
    
    changed = False
    if is_add:
        changed = process_submission(fields, author)
    elif is_remove:
        changed = process_removal(fields, author)
    else:
        print(f"ERROR: Issue title '{title}' must contain '[Submission]' or '[Removal]'.")
        
    if changed:
        print("DATA_UPDATED")

if __name__ == "__main__":
    main()
