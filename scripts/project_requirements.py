#!/usr/bin/env python3
"""Project acceptance requirements shared by automation scripts."""

from __future__ import annotations

import json
import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REQUIREMENTS_PATH = REPO_ROOT / "data" / "project_requirements.json"
DEFAULT_REQUIREMENTS = {
    "minimum_stars": 10,
}


def load_project_requirements(path: Path = DEFAULT_REQUIREMENTS_PATH) -> dict[str, int]:
    requirements = dict(DEFAULT_REQUIREMENTS)

    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        minimum_stars = payload.get("minimum_stars")
        if isinstance(minimum_stars, int) and minimum_stars >= 0:
            requirements["minimum_stars"] = minimum_stars

    env_override = os.environ.get("MIN_PROJECT_STARS", "").strip()
    if env_override:
        try:
            parsed = int(env_override)
        except ValueError:
            parsed = requirements["minimum_stars"]
        if parsed >= 0:
            requirements["minimum_stars"] = parsed

    return requirements
