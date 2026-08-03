"""PDF render service: markdown -> HTML -> PDF via WeasyPrint.

Accepts POST /render with {markdown, document_type, template}.
Returns application/pdf bytes. Stateless — no DB, no auth (internal only).
"""
from __future__ import annotations

import pathlib

import mistune
import weasyprint
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel

app = FastAPI(title="pdf-service", docs_url=None, redoc_url=None)

_TEMPLATE_DIR = pathlib.Path(__file__).parent / "templates"


def _load_css(name: str) -> str:
    path = _TEMPLATE_DIR / f"{name}.css"
    if not path.exists():
        raise FileNotFoundError(name)
    return path.read_text()


_CSS_CACHE: dict[str, str] = {}


def _css(name: str) -> str:
    if name not in _CSS_CACHE:
        _CSS_CACHE[name] = _load_css(name)
    return _CSS_CACHE[name]


class RenderRequest(BaseModel):
    markdown: str
    document_type: str  # "resume" | "cover_letter"
    template: str = "default"


def _to_html(markdown: str, document_type: str, css: str) -> str:
    body = mistune.html(markdown)
    title = "Resume" if document_type == "resume" else "Cover Letter"
    return (
        f'<!DOCTYPE html><html><head><meta charset="utf-8">'
        f"<title>{title}</title>"
        f"<style>{css}</style>"
        f'</head><body class="{document_type}">'
        f"{body}</body></html>"
    )


@app.post("/render")
def render(body: RenderRequest) -> Response:
    if body.document_type not in {"resume", "cover_letter"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "document_type must be 'resume' or 'cover_letter'")
    try:
        css = _css(body.template)
    except FileNotFoundError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"unknown template '{body.template}'")
    if not body.markdown.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "markdown is empty")

    html = _to_html(body.markdown, body.document_type, css)
    pdf_bytes = weasyprint.HTML(string=html).write_pdf()
    return Response(content=pdf_bytes, media_type="application/pdf")


@app.get("/health")
def health() -> dict:
    return {"ok": True}
