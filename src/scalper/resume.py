"""Resume ingestion (Phase 0): groundwork shared by Phases 9 and 10.

The Resume is passed explicitly per-command (e.g. `profile from-resume --resume FILE`) —
there's no config-level default. The expected format is PDF (parsed via `pypdf`, a core
dependency); markdown/plain-text is also read as-is for convenience.
"""

from __future__ import annotations

from pathlib import Path


def load_resume(path: str | Path) -> str:
    """Return the Resume's text. Raises `FileNotFoundError` if `path` doesn't exist."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Resume not found at {p}.")

    if p.suffix.lower() == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(p))
        return "\n".join(page.extract_text() or "" for page in reader.pages).strip()

    return p.read_text(encoding="utf-8", errors="replace")
