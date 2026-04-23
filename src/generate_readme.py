import json
import os
import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PROJECTS_PATH = REPO_ROOT / "data" / "projects.json"
README_PATH = REPO_ROOT / "README.md"

def load_projects():
    if PROJECTS_PATH.exists():
        with open(PROJECTS_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("projects", [])
    return []

def clean_description(desc):
    if not desc:
        return ""
    desc = desc.strip()
    # Remove prohibited words (case-insensitive)
    prohibited = ["awesome", "best", "great", "excellent", "amazing", "wonderful", "cool"]
    for word in prohibited:
        # Match word with boundaries to avoid partial matches (e.g., "awesome" vs "awesomeness")
        pattern = re.compile(r'\b' + re.escape(word) + r'\b', re.IGNORECASE)
        desc = pattern.sub("", desc).strip()
    
    # Clean up double spaces
    desc = re.sub(r'\s+', ' ', desc)
    
    # Ensure starts with uppercase
    if desc:
        desc = desc[0].upper() + desc[1:]
    
    # Ensure ends with period
    if desc and not desc.endswith((".", "!", "?")):
        desc += "."
    return desc

def generate_toc(categories):
    toc = [
        "## Contents",
        "",
        "<!--lint disable awesome-toc-->",
        "- [Awesome Bangladeshi FOSS](#awesome-bangladeshi-foss)",
        "  - [Contents](#contents)",
        "  - [About](#about)",
        "    - [How to contribute](#-how-to-contribute)"
    ]
    for cat in categories:
        anchor = cat.lower().replace(" ", "-").replace("&", "\\&")
        toc.append(f"  - [{cat}](#{anchor})")
    
    toc += [
        "  - [Contributing](#contributing)",
        "  - [Automation](#automation)",
        "  - [License](#license)",
        "<!--lint enable awesome-toc-->"
    ]
    return "\n".join(toc)

def main():
    projects = load_projects()
    
    # Define categories in order
    categories = [
        "Web Applications",
        "Mobile Apps",
        "Developer Tools & Libraries",
        "Government & Utility Services",
        "Fintech & Payments",
        "Other FOSS Projects",
        "Awesome Lists & Resource Collections"
    ]
    
    # Header
    lines = [
        "<!--lint disable awesome-github-->",
        "# Awesome Bangladeshi FOSS ",
        "",
        "[![Awesome](https://awesome.re/badge.svg)](https://awesome.re) "
        "[![CI/CD Pipeline](https://github.com/sharf-shawon/Awesome-Bangladeshi-FOSS/actions/workflows/pipeline.yml/badge.svg)](https://github.com/sharf-shawon/Awesome-Bangladeshi-FOSS/actions/workflows/pipeline.yml) "
        "![Visitors](https://api.visitorbadge.io/api/combined?path=https%3A%2F%2Fgithub.com%2Fsharf-shawon%2FAwesome-Bangladeshi-FOSS&labelColor=%233f4850&countColor=%2330c855&style=flat)",
        "",
        "A curated list of high-quality free and open source software created in or actively maintained from Bangladesh.",
        "",
        "For Better Experience use the web version: [sharf-shawon.github.io/Awesome-Bangladeshi-FOSS](https://sharf-shawon.github.io/Awesome-Bangladeshi-FOSS/)",
        "",
        generate_toc(categories),
        "",
        "## About",
        "",
        "This list curates high-quality FOSS built in or actively maintained from Bangladesh. It highlights useful projects for real-world use, but it is not an exhaustive directory.",
        "",
        "### 🚀 How to contribute",
        "",
        "To add a project to this list, please **[Submit a New Project here](https://github.com/sharf-shawon/Awesome-Bangladeshi-FOSS/issues/new?template=project-submission.yml)**.",
        "",
        "#### Requirements",
        "",
        "- **Genuine FOSS:** Must have an open source license.",
        "- **Popularity:** At least 10 Repo Stars.",
        "- **Quality:** Clear documentation and real-world usefulness.",
        "- **Maintenance:** Active maintenance when possible.",
        ""
    ]
    
    # Project Sections
    projects_by_cat = {}
    for p in projects:
        cat = p["category"]
        if cat not in projects_by_cat:
            projects_by_cat[cat] = []
        projects_by_cat[cat].append(p)
        
    for cat in categories:
        lines.append(f"## {cat}")
        lines.append("")
        cat_projects = projects_by_cat.get(cat, [])
        # Sort alphabetically by name
        cat_projects.sort(key=lambda x: x["name"].lower())
        
        for p in cat_projects:
            desc = clean_description(p["description"])
            lines.append(f"- [{p['name']}]({p['repository']}) - {desc}")
        lines.append("")
        
    # Footer
    lines += [
        "## Contributing",
        "",
        "[Contributions of any kind welcome, just follow the guidelines](contributing.md)!",
        "",
        "## Automation",
        "",
        "This list is partially maintained using automated scripts. Submissions and removals are processed via GitHub Issues.",
        "",
        "## License",
        "",
        "[![CC0](https://mirrors.creativecommons.org/presskit/buttons/88x31/svg/cc-zero.svg)](https://creativecommons.org/publicdomain/zero/1.0/)",
        "",
        "To the extent possible under law, all contributors have waived all copyright and related or neighboring rights to this work."
    ]
    
    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("README.md updated successfully.")

if __name__ == "__main__":
    main()
