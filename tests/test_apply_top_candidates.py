"""Tests for scripts/apply_top_candidates.py.

Covers: all pure helper functions, insert_entry_in_section across every
alphabetical code-path, build_pr_body, and full main() integration including
idempotency, missing-file errors, section mapping, and empty-selected handling.
"""

from __future__ import annotations

import json
import sys

import pytest

import apply_top_candidates as atc


# ---------------------------------------------------------------------------
# normalize_section
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("section,expected", [
    ("Web Applications", "Web Applications"),
    ("Mobile Apps", "Mobile Apps"),
    ("Developer Tools & Libraries", "Developer Tools & Libraries"),
    ("Government & Utility Services", "Government & Utility Services"),
    ("Fintech & Payments", "Fintech & Payments"),
    ("Other FOSS Projects", "Other FOSS Projects"),
    ("Awesome Lists & Resource Collections", "Awesome Lists & Resource Collections"),
    # Mapped alias
    ("Datasets & Resources", "Awesome Lists & Resource Collections"),
    # Unknown → fallback
    ("Random Category", "Other FOSS Projects"),
    ("", "Other FOSS Projects"),
])
def test_normalize_section(section, expected):
    assert atc.normalize_section(section) == expected


# ---------------------------------------------------------------------------
# normalize_repo_url
# ---------------------------------------------------------------------------

def test_normalize_repo_url_strips_trailing_slash():
    assert atc.normalize_repo_url("https://github.com/owner/repo/") == "https://github.com/owner/repo"


def test_normalize_repo_url_no_change_needed():
    assert atc.normalize_repo_url("https://github.com/owner/repo") == "https://github.com/owner/repo"


def test_normalize_repo_url_strips_whitespace():
    assert atc.normalize_repo_url("  https://github.com/owner/repo  ") == "https://github.com/owner/repo"


def test_normalize_repo_url_empty():
    assert atc.normalize_repo_url("") == ""


# ---------------------------------------------------------------------------
# shorten_description
# ---------------------------------------------------------------------------

def test_shorten_description_empty_returns_fallback():
    result = atc.shorten_description("")
    assert result.endswith(".")
    assert len(result) > 5


def test_shorten_description_short_no_period_adds_period():
    assert atc.shorten_description("A useful tool") == "A useful tool."


def test_shorten_description_short_with_period_unchanged():
    assert atc.shorten_description("A useful tool.") == "A useful tool."


def test_shorten_description_short_with_question_mark_unchanged():
    assert atc.shorten_description("Is it useful?") == "Is it useful?"


def test_shorten_description_short_with_exclamation_unchanged():
    assert atc.shorten_description("Great tool!") == "Great tool!"


def test_shorten_description_long_cuts_at_word_boundary():
    # 30-char limit; "word " repeated enough to exceed it
    text = "hello " * 30
    result = atc.shorten_description(text, max_chars=30)
    assert len(result) <= 31  # cut + period
    assert result.endswith(".")
    # Should not end with a space before the period
    assert not result.endswith(" .")


def test_shorten_description_collapses_whitespace():
    result = atc.shorten_description("hello   world", max_chars=120)
    assert "  " not in result


def test_shorten_description_no_space_to_split_on():
    # Single long word – rstrip punctuation then add period
    result = atc.shorten_description("A" * 130, max_chars=120)
    assert result.endswith(".")
    assert len(result) <= 121


def test_shorten_description_exactly_at_limit_gets_period():
    text = "A" * 120  # exactly max_chars
    result = atc.shorten_description(text, max_chars=120)
    assert result.endswith(".")


# ---------------------------------------------------------------------------
# build_entry
# ---------------------------------------------------------------------------

def test_build_entry_valid_url():
    entry = atc.build_entry("My Tool", "https://github.com/owner/tool", "A useful tool.")
    assert entry == "- [My Tool](https://github.com/owner/tool) - A useful tool."


def test_build_entry_strips_trailing_slash_from_url():
    entry = atc.build_entry("Tool", "https://github.com/owner/tool/", "Desc.")
    assert "tool/" not in entry


def test_build_entry_adds_period_to_description():
    entry = atc.build_entry("Tool", "https://github.com/a/b", "No period")
    assert entry.endswith("No period.")


def test_build_entry_invalid_url_raises():
    with pytest.raises(ValueError, match="Invalid GitHub"):
        atc.build_entry("Bad", "https://example.com/owner/repo", "Desc.")


# ---------------------------------------------------------------------------
# load_existing_links
# ---------------------------------------------------------------------------

_LINK_LINES = [
    "- [App A](https://github.com/owner/app-a) - First.",
    "- [App B](https://github.com/owner/app-b) - Second.",
    "## Some Section",
    "Plain text line",
]


def test_load_existing_links_finds_entries():
    result = atc.load_existing_links(_LINK_LINES)
    assert "https://github.com/owner/app-a" in result
    assert "https://github.com/owner/app-b" in result


def test_load_existing_links_ignores_non_entry_lines():
    result = atc.load_existing_links(["## Section", "Plain text"])
    assert len(result) == 0


def test_load_existing_links_returns_lowercase():
    result = atc.load_existing_links(["- [X](https://github.com/Owner/Repo) - desc."])
    assert "https://github.com/owner/repo" in result


def test_load_existing_links_empty_list():
    assert atc.load_existing_links([]) == set()


def test_load_existing_links_strips_trailing_slash():
    result = atc.load_existing_links(["- [X](https://github.com/owner/repo/) - desc."])
    assert "https://github.com/owner/repo" in result


# ---------------------------------------------------------------------------
# insert_entry_in_section
# ---------------------------------------------------------------------------

_README_LINES = [
    "# Awesome Test",
    "",
    "## Web Applications",
    "",
    "- [Alpha App](https://github.com/owner/alpha) - First alphabetical app.",
    "- [Gamma App](https://github.com/owner/gamma) - Third alphabetical app.",
    "",
    "## Mobile Apps",
    "",
    "- [BD Mobile](https://github.com/owner/bd-mobile) - Mobile app.",
]


def test_insert_entry_middle_alphabetical():
    entry = "- [Beta App](https://github.com/owner/beta) - Second app."
    result, ok = atc.insert_entry_in_section(_README_LINES, "Web Applications", entry)
    assert ok is True
    web_entries = [l for l in result if l.strip().startswith("- [") and "owner/" in l
                   and any(k in l for k in ("alpha", "beta", "gamma"))]
    assert len(web_entries) == 3
    assert "alpha" in web_entries[0]
    assert "beta" in web_entries[1]
    assert "gamma" in web_entries[2]


def test_insert_entry_alphabetical_first():
    entry = "- [AAA App](https://github.com/owner/aaa) - Very first."
    result, _ = atc.insert_entry_in_section(_README_LINES, "Web Applications", entry)
    web_entries = [l for l in result if l.strip().startswith("- [") and "owner/" in l
                   and any(k in l for k in ("aaa", "alpha", "gamma"))]
    assert "aaa" in web_entries[0]


def test_insert_entry_alphabetical_last():
    entry = "- [ZZZ App](https://github.com/owner/zzz) - Very last."
    result, _ = atc.insert_entry_in_section(_README_LINES, "Web Applications", entry)
    web_entries = [l for l in result if l.strip().startswith("- [") and "owner/" in l
                   and any(k in l for k in ("alpha", "gamma", "zzz"))]
    assert "zzz" in web_entries[-1]


def test_insert_entry_section_not_found_raises():
    with pytest.raises(ValueError, match="Section not found"):
        atc.insert_entry_in_section(_README_LINES, "Nonexistent Section",
                                    "- [X](https://github.com/a/b) - x.")


def test_insert_entry_invalid_entry_format_raises():
    with pytest.raises(ValueError, match="Invalid entry format"):
        atc.insert_entry_in_section(_README_LINES, "Web Applications", "not an entry format")


def test_insert_entry_last_section_no_next_header():
    # When the target section is the final one in the file, section_end = len(lines).
    lines = [
        "## Mobile Apps",
        "- [Alpha](https://github.com/owner/alpha) - First.",
    ]
    entry = "- [Zebra](https://github.com/owner/zebra) - Last."
    result, ok = atc.insert_entry_in_section(lines, "Mobile Apps", entry)
    assert ok is True
    assert any("zebra" in l for l in result)


def test_insert_entry_empty_section_inserts_before_next_header():
    lines = [
        "## Web Applications",
        "",
        "## Mobile Apps",
        "- [BD App](https://github.com/owner/bd-app) - Mobile.",
    ]
    entry = "- [New App](https://github.com/owner/new) - New."
    result, ok = atc.insert_entry_in_section(lines, "Web Applications", entry)
    assert ok is True
    assert any("new" in l for l in result)


# ---------------------------------------------------------------------------
# build_pr_body
# ---------------------------------------------------------------------------

def test_build_pr_body_empty_entries():
    body = atc.build_pr_body("2024-01", [])
    assert "No new high-quality" in body
    assert "2024-01" in body


def test_build_pr_body_with_entries():
    entries = [{"name": "My Tool", "url": "https://github.com/a/b", "description": "Desc."}]
    body = atc.build_pr_body("2024-01", entries)
    assert "My Tool" in body
    assert "https://github.com/a/b" in body
    assert "manual inspection" in body


def test_build_pr_body_ends_with_newline():
    assert atc.build_pr_body("2024-01", []).endswith("\n")


# ---------------------------------------------------------------------------
# main() – integration
# ---------------------------------------------------------------------------

_README_CONTENT = """\
# Awesome

## Developer Tools & Libraries

- [Old Tool](https://github.com/owner/old-tool) - An existing tool.

## Other FOSS Projects

- [Existing](https://github.com/owner/existing) - Existing project.

## Awesome Lists & Resource Collections

- [Existing Resource](https://github.com/owner/existing-resource) - Resource.
"""

_SINGLE_SELECTED = {
    "selected": [
        {
            "full_name": "bd-org/new-tool",
            "name": "New Tool",
            "html_url": "https://github.com/bd-org/new-tool",
            "description": "A new Bangladesh developer tool.",
            "category": "Developer Tools & Libraries",
        }
    ]
}


def _setup(tmp_path, top10=None, readme=None):
    input_file = tmp_path / "top10.json"
    input_file.write_text(json.dumps(top10 or _SINGLE_SELECTED), encoding="utf-8")
    readme_file = tmp_path / "README.md"
    readme_file.write_text(readme or _README_CONTENT, encoding="utf-8")
    pr_body_file = tmp_path / "pr_body.md"
    return input_file, readme_file, pr_body_file


def test_main_inserts_entry_and_creates_pr_body(monkeypatch, tmp_path):
    inp, readme, pr = _setup(tmp_path)
    monkeypatch.setattr(sys, "argv", [
        "apply_top_candidates.py",
        "--input", str(inp),
        "--readme", str(readme),
        "--pr-body-output", str(pr),
    ])
    assert atc.main() == 0
    assert "https://github.com/bd-org/new-tool" in readme.read_text()
    assert pr.exists()
    assert "New Tool" in pr.read_text()


def test_main_skips_duplicate_url(monkeypatch, tmp_path):
    # Use an entry that already exists in _README_CONTENT.
    top10 = {"selected": [{"full_name": "owner/old-tool", "name": "Old Tool",
                            "html_url": "https://github.com/owner/old-tool",
                            "description": "Already here.", "category": "Developer Tools & Libraries"}]}
    inp, readme, pr = _setup(tmp_path, top10=top10)
    original = readme.read_text()
    monkeypatch.setattr(sys, "argv", [
        "apply_top_candidates.py",
        "--input", str(inp),
        "--readme", str(readme),
        "--pr-body-output", str(pr),
    ])
    atc.main()
    # URL should appear exactly once (not duplicated)
    assert readme.read_text().count("https://github.com/owner/old-tool") == 1


def test_main_empty_selected_is_noop(monkeypatch, tmp_path):
    inp, readme, pr = _setup(tmp_path, top10={"selected": []})
    original = readme.read_text()
    monkeypatch.setattr(sys, "argv", [
        "apply_top_candidates.py",
        "--input", str(inp),
        "--readme", str(readme),
        "--pr-body-output", str(pr),
    ])
    assert atc.main() == 0
    assert "No new high-quality" in pr.read_text()


def test_main_maps_datasets_category(monkeypatch, tmp_path):
    top10 = {"selected": [{"full_name": "owner/ds", "name": "Dataset",
                            "html_url": "https://github.com/owner/ds",
                            "description": "A Bangladesh dataset.",
                            "category": "Datasets & Resources"}]}
    inp, readme, pr = _setup(tmp_path, top10=top10)
    monkeypatch.setattr(sys, "argv", [
        "apply_top_candidates.py",
        "--input", str(inp),
        "--readme", str(readme),
        "--pr-body-output", str(pr),
    ])
    assert atc.main() == 0
    assert "https://github.com/owner/ds" in readme.read_text()


def test_main_missing_input_raises(monkeypatch, tmp_path):
    _, readme, pr = _setup(tmp_path)
    monkeypatch.setattr(sys, "argv", [
        "apply_top_candidates.py",
        "--input", str(tmp_path / "missing.json"),
        "--readme", str(readme),
        "--pr-body-output", str(pr),
    ])
    with pytest.raises(FileNotFoundError):
        atc.main()


def test_main_missing_readme_raises(monkeypatch, tmp_path):
    inp, _, pr = _setup(tmp_path)
    monkeypatch.setattr(sys, "argv", [
        "apply_top_candidates.py",
        "--input", str(inp),
        "--readme", str(tmp_path / "NOFILE.md"),
        "--pr-body-output", str(pr),
    ])
    with pytest.raises(FileNotFoundError):
        atc.main()


def test_main_entry_inserted_in_alphabetical_order(monkeypatch, tmp_path):
    # AAA should land before Old Tool in Developer Tools & Libraries.
    top10 = {"selected": [{"full_name": "bd/aaa", "name": "AAA Tool",
                            "html_url": "https://github.com/bd/aaa",
                            "description": "Alphabetically first tool.",
                            "category": "Developer Tools & Libraries"}]}
    inp, readme, pr = _setup(tmp_path, top10=top10)
    monkeypatch.setattr(sys, "argv", [
        "apply_top_candidates.py",
        "--input", str(inp),
        "--readme", str(readme),
        "--pr-body-output", str(pr),
    ])
    atc.main()
    lines = readme.read_text().splitlines()
    dev_entries = [l for l in lines if l.strip().startswith("- [")
                   and any(k in l for k in ("aaa", "old-tool"))]
    assert "aaa" in dev_entries[0].lower()
