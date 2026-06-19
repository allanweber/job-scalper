"""Render (Phase 13): turn an Application Draft's markdown into PDF renditions.

No LLM is involved — this is a pure markdown -> HTML -> PDF transform. The markdown is the
source of truth; PDFs are always re-derivable, so the user can hand-edit `resume.md` /
`cover_letter.md` and re-render with `scalper render` (see ADR 0007).

The resume is parsed into a known structure (header + CAPS sections + `### Role :: dates`
experience entries) and rendered through a Jinja+CSS template that reproduces the layout
of a classic single-column Word resume (centred header, right-aligned dates, justified
body). HTML is printed to PDF by headless Chromium, reusing the Playwright dependency the
scrape sources already use. Both the engine and the `markdown` helper live behind the
optional `[pdf]` extra and degrade soft when absent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, PackageLoader

# Trusted content (our own markdown -> HTML), so no autoescape.
_env = Environment(loader=PackageLoader("scalper", "templates"), autoescape=False)

#: Markdown filenames an Application Draft folder may contain, and whether each renders.
RESUME_MD = "resume.md"
COVER_LETTER_MD = "cover_letter.md"
#: stretch_claims.md is intentionally never rendered — it stays a private ledger.

_EXP_HEAD_RE = re.compile(r"^###\s+(.*)$")
_DATE_SEP = " :: "

_INSTALL_HINT = (
    "PDF rendering needs the [pdf] extra: pip install -e '.[pdf]' && "
    "playwright install chromium"
)


def pdf_available() -> bool:
    """True if the `[pdf]` extra (Playwright + markdown) is importable."""
    try:
        import markdown  # noqa: F401
        import playwright.sync_api  # noqa: F401
    except Exception:  # noqa: BLE001 — any import error means the extra is unusable
        return False
    return True


def install_hint() -> str:
    return _INSTALL_HINT


_BULLET_RE = re.compile(r"^\s*[-*+]\s+")


def _normalize_lists(text: str) -> str:
    """Insert a blank line before a bullet block that directly follows a paragraph.

    Markdown needs a blank line between a paragraph and a list; the model doesn't always
    emit one (e.g. a one-line role description immediately followed by `- ` bullets), so
    without this the bullets get absorbed into the paragraph as literal "- " text.
    """
    out: list[str] = []
    for line in text.splitlines():
        if _BULLET_RE.match(line) and out and out[-1].strip() and not _BULLET_RE.match(out[-1]):
            out.append("")
        out.append(line)
    return "\n".join(out)


def _md_to_html(text: str) -> str:
    import markdown

    return markdown.markdown(_normalize_lists(text.strip()), extensions=["sane_lists"])


def _split_header(lines: list[str]) -> tuple[str, list[str], int]:
    """Read the leading `# Name` + contiguous header lines (headline, contact).

    The header ends at the first blank line or `## ` section — whichever comes first —
    so it works for both the resume (header, blank, `## SUMMARY`, …) and the cover letter
    (letterhead, blank, body paragraphs). Returns (name, header_lines, index_of_rest).
    """
    name = ""
    header: list[str] = []
    i = 0
    n = len(lines)
    # Skip leading blanks, take the first `# ` line as the name.
    while i < n and not lines[i].strip():
        i += 1
    if i < n and lines[i].lstrip().startswith("# ") and not lines[i].lstrip().startswith("## "):
        name = lines[i].lstrip()[2:].strip()
        i += 1
    while i < n and lines[i].strip() and not lines[i].lstrip().startswith("## "):
        header.append(lines[i].strip())
        i += 1
    return name, header, i


@dataclass
class _Experience:
    left: str
    date: str
    body_html: str


def _parse_experience(body: str) -> list[dict]:
    """Split an experience section body into `### Role :: dates` entries."""
    lines = body.splitlines()
    entries: list[_Experience] = []
    cur_head: str | None = None
    cur_body: list[str] = []

    def flush() -> None:
        if cur_head is None:
            return
        left, _, date = cur_head.partition(_DATE_SEP)
        entries.append(
            _Experience(
                left=left.strip(),
                date=date.strip(),
                body_html=_md_to_html("\n".join(cur_body)) if any(cur_body) else "",
            )
        )

    for line in lines:
        m = _EXP_HEAD_RE.match(line.strip())
        if m:
            flush()
            cur_head = m.group(1).strip()
            cur_body = []
        elif cur_head is not None:
            cur_body.append(line)
    flush()
    return [e.__dict__ for e in entries]


def parse_resume(md_text: str) -> dict:
    """Parse resume markdown into the template context (header + sections)."""
    lines = md_text.splitlines()
    name, header, start = _split_header(lines)

    headline = ""
    contact_lines = list(header)
    # Heuristic: a header line that looks like contact info (has a digit, '@', or a
    # 'Label:' prefix) is contact; the first plain line is the headline.
    if contact_lines and not re.search(r"[@:0-9]", contact_lines[0]):
        headline = contact_lines.pop(0)

    sections: list[dict] = []
    cur_title: str | None = None
    cur_body: list[str] = []

    def flush() -> None:
        if cur_title is None:
            return
        body = "\n".join(cur_body).strip()
        if _EXP_HEAD_RE.search("\n".join(cur_body)) or "\n### " in "\n" + body:
            sections.append(
                {"title": cur_title, "kind": "experience", "entries": _parse_experience(body)}
            )
        else:
            sections.append({"title": cur_title, "kind": "simple", "html": _md_to_html(body)})

    for line in lines[start:]:
        if line.lstrip().startswith("## "):
            flush()
            cur_title = line.lstrip()[3:].strip()
            cur_body = []
        elif cur_title is not None:
            cur_body.append(line)
    flush()

    return {
        "name": name,
        "headline": headline,
        "contact_lines": contact_lines,
        "sections": sections,
    }


def parse_cover_letter(md_text: str) -> dict:
    """Parse cover-letter markdown into (letterhead name + contact, body HTML)."""
    lines = md_text.splitlines()
    name, header, start = _split_header(lines)
    body = "\n".join(lines[start:]).strip()
    return {
        "name": name,
        "contact_lines": header,
        "body_html": _md_to_html(body),
    }


def _html_to_pdf(html: str, out_path: Path) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(html, wait_until="load")
            page.pdf(
                path=str(out_path),
                format="Letter",
                print_background=True,
                margin={"top": "0.5in", "bottom": "0.5in", "left": "0.6in", "right": "0.6in"},
            )
        finally:
            browser.close()


def render_resume_pdf(md_text: str, out_path: Path) -> Path:
    html = _env.get_template("resume_pdf.html").render(**parse_resume(md_text))
    _html_to_pdf(html, out_path)
    return out_path


def render_cover_letter_pdf(md_text: str, out_path: Path) -> Path:
    html = _env.get_template("cover_letter_pdf.html").render(**parse_cover_letter(md_text))
    _html_to_pdf(html, out_path)
    return out_path


#: Map a draft markdown filename to its renderer; only these markdown files render.
_RENDERERS = {RESUME_MD: render_resume_pdf, COVER_LETTER_MD: render_cover_letter_pdf}


def render_markdown_file(path: Path) -> Path:
    """Render a single `resume.md` / `cover_letter.md` to a sibling `.pdf`.

    Raises `ValueError` for any other filename (e.g. `stretch_claims.md`, never rendered).
    """
    renderer = _RENDERERS.get(path.name)
    if renderer is None:
        raise ValueError(f"{path.name} is not a renderable draft file")
    return renderer(path.read_text(), path.with_suffix(".pdf"))


def render_draft_folder(folder: Path) -> list[Path]:
    """Render every renderable markdown file present in a draft folder."""
    rendered: list[Path] = []
    for name in _RENDERERS:
        md = folder / name
        if md.exists():
            rendered.append(render_markdown_file(md))
    return rendered
