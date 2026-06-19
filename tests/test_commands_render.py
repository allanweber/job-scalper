"""Tests for the `render` command layer (Phase 13).

The actual HTML->PDF transform (headless Chromium) is monkeypatched out, so these
exercise the dispatch logic — folder vs file, skipping non-renderable files, and the
hard error when the `[pdf]` extra is absent — without Playwright or markdown.
"""

import pytest

from scalper.commands import render as render_cmd
from scalper.commands.render import NothingToRenderError, PDFUnavailableError, run_render


@pytest.fixture
def fake_pdf(monkeypatch):
    """Make the pdf engine 'available' and turn rendering into a touch-the-pdf stub."""
    monkeypatch.setattr(render_cmd, "pdf_available", lambda: True)

    def fake_render_file(path):
        out = path.with_suffix(".pdf")
        if path.name not in ("resume.md", "cover_letter.md"):
            raise ValueError(f"{path.name} is not a renderable draft file")
        out.write_text("%PDF stub")
        return out

    def fake_render_folder(folder):
        rendered = []
        for name in ("resume.md", "cover_letter.md"):
            md = folder / name
            if md.exists():
                rendered.append(fake_render_file(md))
        return rendered

    monkeypatch.setattr(render_cmd, "render_markdown_file", fake_render_file)
    monkeypatch.setattr(render_cmd, "render_draft_folder", fake_render_folder)


def test_pdf_unavailable_is_a_hard_error(monkeypatch, tmp_path):
    monkeypatch.setattr(render_cmd, "pdf_available", lambda: False)
    (tmp_path / "resume.md").write_text("# x")
    with pytest.raises(PDFUnavailableError):
        run_render(None, [tmp_path / "resume.md"])


def test_no_existing_path_raises(fake_pdf, tmp_path):
    with pytest.raises(NothingToRenderError):
        run_render(None, [tmp_path / "nope"])


def test_renders_a_folder(fake_pdf, tmp_path):
    (tmp_path / "resume.md").write_text("# r")
    (tmp_path / "cover_letter.md").write_text("# c")
    (tmp_path / "stretch_claims.md").write_text("- s")  # must be ignored

    result = run_render(None, [tmp_path])

    names = sorted(p.name for p in result.rendered)
    assert names == ["cover_letter.pdf", "resume.pdf"]


def test_renders_a_single_file(fake_pdf, tmp_path):
    md = tmp_path / "resume.md"
    md.write_text("# r")

    result = run_render(None, [md])

    assert [p.name for p in result.rendered] == ["resume.pdf"]


def test_non_renderable_file_is_skipped(fake_pdf, tmp_path):
    md = tmp_path / "stretch_claims.md"
    md.write_text("- s")

    result = run_render(None, [md])

    assert result.rendered == []
    assert result.skipped and result.skipped[0][0] == md
