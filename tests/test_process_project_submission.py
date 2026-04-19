"""Tests for scripts/process_project_submission.py."""

from __future__ import annotations

import os
from pathlib import Path
from textwrap import dedent

import pytest

import process_project_submission as pps

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SECTION_README = dedent("""\
    ## Web Applications

    - [Alpha App](https://github.com/owner/alpha) - First app.
    - [Gamma App](https://github.com/owner/gamma) - Third app.

    ## Mobile Apps

    - [BD Mobile](https://github.com/owner/bd-mobile) - Mobile app.
""")


def _issue_body(name="My Tool", url="https://github.com/owner/my-tool",
                desc="A useful tool.", category="Web Applications"):
    return dedent(f"""\
        ### Project name
        {name}
        ### Repository URL
        {url}
        ### Short description
        {desc}
        ### Category
        {category}
    """)


# ---------------------------------------------------------------------------
# normalize_whitespace
# ---------------------------------------------------------------------------

def test_normalize_whitespace_collapses_spaces():
    assert pps.normalize_whitespace("  hello   world  ") == "hello world"


def test_normalize_whitespace_collapses_tabs_and_newlines():
    assert pps.normalize_whitespace("hello\t\nworld") == "hello world"


def test_normalize_whitespace_empty():
    assert pps.normalize_whitespace("   ") == ""


# ---------------------------------------------------------------------------
# extract_field
# ---------------------------------------------------------------------------

def test_extract_field_returns_value():
    body = "### Project name\nMy Project\n### Repository URL\nhttps://github.com/a/b\n"
    assert pps.extract_field(body, "Project name") == "My Project"


def test_extract_field_missing_label_returns_empty():
    body = "### Something\nValue\n"
    assert pps.extract_field(body, "Missing Label") == ""


def test_extract_field_strips_checkbox_markup():
    body = "### Category\n- [x] Web Applications\n"
    assert pps.extract_field(body, "Category") == "Web Applications"


# ---------------------------------------------------------------------------
# parse_submission – valid cases
# ---------------------------------------------------------------------------

def test_parse_submission_valid():
    name, url, desc, cat = pps.parse_submission(_issue_body())
    assert name == "My Tool"
    assert url == "https://github.com/owner/my-tool"
    assert desc == "A useful tool."
    assert cat == "Web Applications"


def test_parse_submission_strips_trailing_slash_from_url():
    body = _issue_body(url="https://github.com/owner/tool/")
    _, url, _, _ = pps.parse_submission(body)
    assert not url.endswith("/")


# ---------------------------------------------------------------------------
# parse_submission – validation failures
# ---------------------------------------------------------------------------

def test_parse_submission_missing_name_raises():
    with pytest.raises(ValueError, match="Project name"):
        pps.parse_submission(_issue_body(name=""))


def test_parse_submission_missing_url_raises():
    with pytest.raises(ValueError, match="Repository URL"):
        pps.parse_submission(_issue_body(url=""))


def test_parse_submission_missing_description_raises():
    with pytest.raises(ValueError, match="Short description"):
        pps.parse_submission(_issue_body(desc=""))


def test_parse_submission_bad_url_raises():
    with pytest.raises(ValueError, match="format"):
        pps.parse_submission(_issue_body(url="https://example.com/owner/repo"))


def test_parse_submission_missing_category_raises():
    with pytest.raises(ValueError, match="Category"):
        pps.parse_submission(_issue_body(category=""))


def test_parse_submission_unknown_category_raises():
    with pytest.raises(ValueError, match="Unsupported category"):
        pps.parse_submission(_issue_body(category="Unknown Section"))


def test_parse_submission_description_too_long_raises():
    with pytest.raises(ValueError, match="220 characters"):
        pps.parse_submission(_issue_body(desc="x" * 221))


# ---------------------------------------------------------------------------
# build_entry_line
# ---------------------------------------------------------------------------

def test_build_entry_line_adds_period_when_missing():
    entry = pps.build_entry_line("Tool", "https://github.com/a/b", "A description")
    assert entry.endswith(".")


def test_build_entry_line_keeps_existing_period():
    # When the description already ends with a period, build_entry_line must not add another.
    entry = pps.build_entry_line("Tool", "https://github.com/a/b", "A description.")
    assert entry.endswith(" - A description.")
    assert not entry.endswith("..")


def test_build_entry_line_format():
    entry = pps.build_entry_line("My Tool", "https://github.com/owner/tool", "Does things.")
    assert entry == "- [My Tool](https://github.com/owner/tool) - Does things."


# ---------------------------------------------------------------------------
# insert_entry_in_section
# ---------------------------------------------------------------------------

def test_insert_entry_alphabetical_middle():
    entry = "- [Beta App](https://github.com/owner/beta) - Second app."
    result = pps.insert_entry_in_section(_SECTION_README, "Web Applications", entry)
    lines = result.splitlines()
    names = [l for l in lines if l.strip().startswith("- [")]
    assert names.index("- [Beta App](https://github.com/owner/beta) - Second app.") == 1


def test_insert_entry_alphabetical_first():
    entry = "- [AAA App](https://github.com/owner/aaa) - Very first."
    result = pps.insert_entry_in_section(_SECTION_README, "Web Applications", entry)
    web_entries = [l for l in result.splitlines() if l.strip().startswith("- [") and "github.com/owner" in l]
    first_entry = next(e for e in web_entries if "owner/aaa" in e or "owner/alpha" in e or "owner/gamma" in e)
    assert "aaa" in first_entry


def test_insert_entry_alphabetical_last():
    entry = "- [ZZZ App](https://github.com/owner/zzz) - Very last."
    result = pps.insert_entry_in_section(_SECTION_README, "Web Applications", entry)
    web_entries = [l for l in result.splitlines()
                   if l.strip().startswith("- [") and "github.com/owner/" in l
                   and any(k in l for k in ("alpha", "gamma", "zzz"))]
    assert "zzz" in web_entries[-1]


def test_insert_entry_duplicate_url_raises():
    entry = "- [Dupe](https://github.com/owner/alpha) - Duplicate."
    with pytest.raises(ValueError, match="Duplicate"):
        pps.insert_entry_in_section(_SECTION_README, "Web Applications", entry)


def test_insert_entry_missing_section_raises():
    entry = "- [Foo](https://github.com/owner/foo) - A tool."
    with pytest.raises(ValueError, match="Section not found"):
        pps.insert_entry_in_section(_SECTION_README, "Nonexistent Section", entry)


def test_insert_entry_last_section_has_no_next_header():
    # When the target section is the last section in the file, section_end = len(lines).
    readme = dedent("""\
        ## Web Applications

        - [Alpha App](https://github.com/owner/alpha) - First app.
    """)
    entry = "- [Zebra App](https://github.com/owner/zebra) - Last app."
    result = pps.insert_entry_in_section(readme, "Web Applications", entry)
    assert "https://github.com/owner/zebra" in result


# ---------------------------------------------------------------------------
# write_output
# ---------------------------------------------------------------------------

def test_write_output_single_line(monkeypatch, tmp_path):
    output_file = tmp_path / "github_output"
    output_file.write_text("")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    pps.write_output("branch_name", "automation/test-branch")
    content = output_file.read_text()
    assert "branch_name=automation/test-branch" in content


def test_write_output_multiline_uses_heredoc(monkeypatch, tmp_path):
    output_file = tmp_path / "github_output"
    output_file.write_text("")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    pps.write_output("pr_body", "line1\nline2")
    content = output_file.read_text()
    assert "<<EOF" in content
    assert "line1" in content
    assert "line2" in content


def test_write_output_no_github_output_is_noop(monkeypatch):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    # Should not raise even when env var is absent.
    pps.write_output("key", "value")


# ---------------------------------------------------------------------------
# main() – integration
# ---------------------------------------------------------------------------

def test_main_inserts_entry_into_readme(monkeypatch, tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(_SECTION_README, encoding="utf-8")
    monkeypatch.setattr(pps, "README_PATH", readme)
    monkeypatch.setenv("ISSUE_BODY", _issue_body(
        name="Beta App",
        url="https://github.com/owner/beta-app",
        desc="A beta application.",
        category="Web Applications",
    ))
    monkeypatch.setenv("ISSUE_NUMBER", "42")
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)

    result = pps.main()
    assert result == 0
    updated = readme.read_text(encoding="utf-8")
    assert "https://github.com/owner/beta-app" in updated


def test_main_empty_issue_body_returns_error(monkeypatch, tmp_path):
    monkeypatch.setenv("ISSUE_BODY", "")
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    assert pps.main() == 1


def test_main_invalid_submission_returns_error(monkeypatch, tmp_path):
    # parse_submission raises ValueError (bad URL) → main returns 1
    readme = tmp_path / "README.md"
    readme.write_text(_SECTION_README, encoding="utf-8")
    monkeypatch.setattr(pps, "README_PATH", readme)
    monkeypatch.setenv("ISSUE_BODY", _issue_body(url="https://example.com/not/github"))
    monkeypatch.setenv("ISSUE_NUMBER", "1")
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    assert pps.main() == 1


def test_main_missing_readme_returns_error(monkeypatch, tmp_path):
    monkeypatch.setattr(pps, "README_PATH", tmp_path / "NOFILE.md")
    monkeypatch.setenv("ISSUE_BODY", _issue_body())
    monkeypatch.setenv("ISSUE_NUMBER", "2")
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    assert pps.main() == 1


def test_main_duplicate_url_returns_error(monkeypatch, tmp_path):
    # The URL from _issue_body is already in _SECTION_README → insert raises ValueError
    readme = tmp_path / "README.md"
    readme.write_text(_SECTION_README, encoding="utf-8")
    monkeypatch.setattr(pps, "README_PATH", readme)
    # Use a URL that already exists in _SECTION_README
    body = _issue_body(
        name="Alpha Duplicate",
        url="https://github.com/owner/alpha",
        desc="Duplicate of existing entry.",
    )
    monkeypatch.setenv("ISSUE_BODY", body)
    monkeypatch.setenv("ISSUE_NUMBER", "3")
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    assert pps.main() == 1
