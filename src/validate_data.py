import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PROJECTS_PATH = REPO_ROOT / "data" / "projects.json"

def validate():
    if not PROJECTS_PATH.exists():
        print(f"ERROR: {PROJECTS_PATH} does not exist.")
        return False
        
    try:
        with open(PROJECTS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"ERROR: Failed to parse JSON: {e}")
        return False
        
    if "projects" not in data or not isinstance(data["projects"], list):
        print("ERROR: JSON must contain a 'projects' list.")
        return False
        
    required_fields = ["category", "name", "repository", "description"]
    allowed_categories = {
        "Web Applications",
        "Mobile Apps",
        "Developer Tools & Libraries",
        "Government & Utility Services",
        "Fintech & Payments",
        "Other FOSS Projects",
        "Awesome Lists & Resource Collections"
    }
    
    for idx, p in enumerate(data["projects"]):
        for field in required_fields:
            if field not in p:
                print(f"ERROR: Project at index {idx} is missing field '{field}'.")
                return False
        
        if p["category"] not in allowed_categories:
            print(f"ERROR: Project at index {idx} has invalid category '{p['category']}'.")
            return False
            
    print("Data validation successful.")
    return True

if __name__ == "__main__":
    if not validate():
        sys.exit(1)
