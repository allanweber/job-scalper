"""`render` command core: (re)render Application Draft PDFs from markdown (Phase 13).

No LLM, no store — a pure markdown -> PDF transform (see `scalper.pdf` / ADR 0007). The
workflow it serves: edit `resume.md` / `cover_letter.md` by hand, then re-render to a
fresh PDF. Accepts draft folders (renders every renderable markdown inside) and individual
`resume.md` / `cover_letter.md` files. `stretch_claims.md` is never rendered.

Purity contract: raises `CommandError` instead of printing/exiting. Unlike `draft`, the
PDF engine is required here (it's the whole point), so a missing `[pdf]` extra is a hard
error rather than a soft skip.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from scalper.commands import CommandError
from scalper.pdf import (
    install_hint,
    pdf_available,
    render_draft_folder,
    render_markdown_file,
)


class PDFUnavailableError(CommandError):
    """The `[pdf]` extra (Playwright + markdown) isn't installed."""


class NothingToRenderError(CommandError):
    """None of the given paths exist."""


def _noop(_msg: str) -> None:
    pass


@dataclass
class RenderResult:
    rendered: list[Path] = field(default_factory=list)
    #: (path, reason) for inputs that were not rendered (missing, wrong type, failed).
    skipped: list[tuple[Path, str]] = field(default_factory=list)


def run_render(
    config: object,  # unused; kept for a uniform command signature
    paths: list[str | Path],
    *,
    on_warning: Callable[[str], None] = _noop,
) -> RenderResult:
    """Render each path's draft markdown to PDF.

    A directory renders every renderable markdown it contains; a `resume.md` /
    `cover_letter.md` file renders just that one. Paths that don't exist, aren't a
    renderable draft file, or fail to render are collected in `RenderResult.skipped`
    (fail-soft per path) rather than aborting the whole run.
    """
    if not pdf_available():
        raise PDFUnavailableError(f"PDF rendering needs the [pdf] extra — {install_hint()}")

    if not any(Path(p).exists() for p in paths):
        raise NothingToRenderError(
            "no existing path to render (give a draft folder or a resume.md/cover_letter.md)"
        )

    result = RenderResult()
    for raw in paths:
        path = Path(raw)
        if not path.exists():
            result.skipped.append((path, "does not exist"))
            on_warning(f"{path}: does not exist")
            continue
        try:
            if path.is_dir():
                rendered = render_draft_folder(path)
                if not rendered:
                    result.skipped.append((path, "no resume.md/cover_letter.md inside"))
                    on_warning(f"{path}: no renderable markdown inside")
                result.rendered.extend(rendered)
            else:
                result.rendered.append(render_markdown_file(path))
        except ValueError as e:
            result.skipped.append((path, str(e)))
            on_warning(f"{path}: {e}")
        except Exception as e:  # noqa: BLE001 — one bad file shouldn't abort the batch
            result.skipped.append((path, str(e)))
            on_warning(f"{path}: rendering failed ({e})")

    return result
