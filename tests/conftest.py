"""Shared pytest configuration and fixtures for all script tests.

Adds the scripts/ directory to sys.path before any test is collected so that
modules like `ai_utils`, `discover_candidates`, etc. can be imported directly,
and cross-module imports (e.g. `from ai_utils import classify_and_score`) resolve
correctly without installing the scripts as a package.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# sys.path – must come before any test-module import collects script modules.
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


# ---------------------------------------------------------------------------
# Shared README content used across multiple test modules.
# ---------------------------------------------------------------------------
MINIMAL_README = """\
# Awesome Test

## Contents

- [About](#about)
- [Web Applications](#web-applications)
- [Mobile Apps](#mobile-apps)
- [Developer Tools & Libraries](#developer-tools--libraries)
- [Government & Utility Services](#government--utility-services)
- [Fintech & Payments](#fintech--payments)
- [Other FOSS Projects](#other-foss-projects)
- [Awesome Lists & Resource Collections](#awesome-lists--resource-collections)

## About

Test README.

## Web Applications

- [Alpha App](https://github.com/owner/alpha-app) - First alphabetical app.
- [Gamma App](https://github.com/owner/gamma-app) - Third alphabetical app.

## Mobile Apps

- [BD Mobile](https://github.com/owner/bd-mobile) - Mobile app for Bangladesh.

## Developer Tools & Libraries

- [NLP Tool](https://github.com/owner/nlp-tool) - Bangla NLP library.

## Government & Utility Services

- [GovData](https://github.com/owner/govdata) - Government data API for Bangladesh.

## Fintech & Payments

- [bKash SDK](https://github.com/owner/bkash-sdk) - bKash payment integration library.

## Other FOSS Projects

- [OSS Project](https://github.com/owner/oss-project) - Open source project.

## Awesome Lists & Resource Collections

- [BD Resources](https://github.com/owner/bd-resources) - Bangladesh FOSS resource collection.
"""


@pytest.fixture()
def sample_readme(tmp_path: Path) -> Path:
    """Write MINIMAL_README to a temp file and return its Path."""
    readme = tmp_path / "README.md"
    readme.write_text(MINIMAL_README, encoding="utf-8")
    return readme


@pytest.fixture()
def sample_projects_json(tmp_path: Path) -> Path:
    """Write a minimal projects.json to a temp file and return its Path."""
    data = {
        "projects": [
            {
                "category": "Web Applications",
                "name": "Existing App",
                "repository": "https://github.com/owner/existing-app",
                "description": "An already-listed application.",
            }
        ]
    }
    projects = tmp_path / "projects.json"
    projects.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return projects
