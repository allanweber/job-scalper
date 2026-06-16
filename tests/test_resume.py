"""Tests for Resume ingestion (Phase 0): the shared groundwork for Phases 9 & 10.

Resume is always passed explicitly (no config-level default); `pypdf` is a core
dependency so PDF parsing always works.
"""

import pytest

from scalper.resume import load_resume


def test_missing_file_raises(tmp_path):
    missing = tmp_path / "nope.md"
    with pytest.raises(FileNotFoundError):
        load_resume(missing)


def test_loads_markdown_as_is(tmp_path):
    p = tmp_path / "resume.md"
    p.write_text("# Jane Doe\n\nBackend engineer, 5 years Python.")
    text = load_resume(p)
    assert "Jane Doe" in text
    assert "Python" in text


def test_loads_plain_text_as_is(tmp_path):
    p = tmp_path / "resume.txt"
    p.write_text("Jane Doe, Backend Engineer")
    assert load_resume(p) == "Jane Doe, Backend Engineer"


def test_pdf_path_is_parsed(tmp_path):
    from pypdf import PdfWriter

    p = tmp_path / "resume.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with open(p, "wb") as f:
        writer.write(f)

    text = load_resume(p)
    assert isinstance(text, str)  # blank page parses to empty/near-empty text, not a crash
