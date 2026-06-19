"""Pure tests for draft splitting and resume parsing (Phase 13).

`split_draft` has no dependencies. The PDF parsing helpers need the `markdown` lib
(the `[pdf]` extra), so those tests skip when it isn't installed; rendering itself
(headless Chromium) is not exercised here.
"""

import pytest

from scalper.app_draft import split_draft

_RESUME = (
    "<<<RESUME>>>\n"
    "# Jane Dev\n"
    "Staff Engineer\n"
    "Email: jane@example.com | Phone: +1 555\n\n"
    "## SUMMARY\n- Built things.\n\n"
    "## PROFESSIONAL EXPERIENCE\n"
    "### Engineer | Acme :: 2020 – Present\n"
    "Led the platform team.\n"
    "- **Scale**: 5M users.\n"
)
_COVER = "<<<COVER_LETTER>>>\n# Jane Dev\nEmail: jane@example.com\n\nDear team,\n"


def test_split_draft_separates_three_parts():
    parts = split_draft(_RESUME + _COVER + "<<<STRETCH_CLAIMS>>>\n- K8s from Docker.\n")
    assert parts.resume.startswith("# Jane Dev")
    assert "PROFESSIONAL EXPERIENCE" in parts.resume
    assert "<<<" not in parts.resume  # sentinels stripped
    assert parts.cover_letter.startswith("# Jane Dev")
    assert parts.stretch_claims.strip() == "- K8s from Docker."


def test_split_draft_stretch_claims_optional():
    parts = split_draft(_RESUME + _COVER)
    assert parts.stretch_claims is None


@pytest.mark.parametrize("text", ["", "just prose", _COVER, _RESUME])
def test_split_draft_requires_both_required_parts(text):
    with pytest.raises(ValueError):
        split_draft(text)


def test_parse_resume_structure():
    pytest.importorskip("markdown")
    from scalper.pdf import parse_resume

    ctx = parse_resume(split_draft(_RESUME + _COVER).resume)
    assert ctx["name"] == "Jane Dev"
    assert ctx["headline"] == "Staff Engineer"
    assert any("jane@example.com" in c for c in ctx["contact_lines"])

    titles = [s["title"] for s in ctx["sections"]]
    assert titles == ["SUMMARY", "PROFESSIONAL EXPERIENCE"]

    summary = ctx["sections"][0]
    assert summary["kind"] == "simple" and "<li>" in summary["html"]

    exp = ctx["sections"][1]
    assert exp["kind"] == "experience"
    entry = exp["entries"][0]
    assert entry["left"] == "Engineer | Acme"
    assert entry["date"] == "2020 – Present"
    assert "5M users" in entry["body_html"]


def test_parse_cover_letter_letterhead():
    pytest.importorskip("markdown")
    from scalper.pdf import parse_cover_letter

    ctx = parse_cover_letter(split_draft(_RESUME + _COVER).cover_letter)
    assert ctx["name"] == "Jane Dev"
    assert any("jane@example.com" in c for c in ctx["contact_lines"])
    assert "Dear team" in ctx["body_html"]
