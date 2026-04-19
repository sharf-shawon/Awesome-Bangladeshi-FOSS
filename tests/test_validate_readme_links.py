"""Tests for scripts/validate_readme_links.py."""

from __future__ import annotations

from pathlib import Path

import validate_readme_links


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_VALID = """\
# Awesome

## Web Applications

- [Bangla App](https://github.com/owner/bangla-app) - A useful Bangla application.
- [Dhaka Tool](https://github.com/owner/dhaka-tool) - A tool for Dhaka users.
"""

_DUPLICATE_LINK = """\
## Web Applications

- [Bangla App](https://github.com/owner/bangla-app) - First entry.
- [Duplicate](https://github.com/owner/bangla-app) - Same URL as above.
"""

_NON_GITHUB_URL = """\
## Web Applications

- [Bad Link](https://example.com/owner/repo) - Non-GitHub URL.
"""

_GITHUB_URL_WITH_EXTRA_PATH = """\
## Web Applications

- [Deep Link](https://github.com/owner/repo/tree/main) - URL with extra path segments.
"""


def _write(tmp_path: Path, content: str) -> Path:
    readme = tmp_path / "README.md"
    readme.write_text(content, encoding="utf-8")
    return readme


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_valid_readme_passes(monkeypatch, tmp_path):
    readme = _write(tmp_path, _VALID)
    monkeypatch.setattr(validate_readme_links, "README_PATH", readme)
    assert validate_readme_links.main() == 0


def test_duplicate_link_fails(monkeypatch, tmp_path):
    readme = _write(tmp_path, _DUPLICATE_LINK)
    monkeypatch.setattr(validate_readme_links, "README_PATH", readme)
    assert validate_readme_links.main() == 1


def test_non_github_url_fails(monkeypatch, tmp_path):
    readme = _write(tmp_path, _NON_GITHUB_URL)
    monkeypatch.setattr(validate_readme_links, "README_PATH", readme)
    assert validate_readme_links.main() == 1


def test_github_url_with_extra_path_fails(monkeypatch, tmp_path):
    readme = _write(tmp_path, _GITHUB_URL_WITH_EXTRA_PATH)
    monkeypatch.setattr(validate_readme_links, "README_PATH", readme)
    assert validate_readme_links.main() == 1


def test_missing_readme_returns_error(monkeypatch, tmp_path):
    monkeypatch.setattr(validate_readme_links, "README_PATH", tmp_path / "NOFILE.md")
    assert validate_readme_links.main() == 1


def test_empty_readme_passes(monkeypatch, tmp_path):
    # An empty README has no entries to validate – should pass.
    readme = _write(tmp_path, "")
    monkeypatch.setattr(validate_readme_links, "README_PATH", readme)
    assert validate_readme_links.main() == 0
