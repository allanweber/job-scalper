"""Fetch a single job posting from a URL and return a synthetic JobPosting.

No adapter machinery, no store — ephemeral use only (e.g. `draft --url`).
Extraction is heuristic: og:title / <title> for the job title, og:site_name or
the domain for company name, and all visible body text for description.
"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from scalper.models import JobPosting

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_SCRIPT_STYLE = {"script", "style", "noscript", "head", "meta", "link"}


def _slug(text: str, max_len: int = 40) -> str:
    return _SLUG_RE.sub("-", text.lower()).strip("-")[:max_len]


def _meta(soup: BeautifulSoup, *props: str) -> str:
    for prop in props:
        tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
        if tag and tag.get("content", "").strip():
            return tag["content"].strip()
    return ""


def _visible_text(soup: BeautifulSoup) -> str:
    for tag in soup.find_all(_SCRIPT_STYLE):
        tag.decompose()
    return " ".join(soup.get_text(" ", strip=True).split())


def fetch_posting(url: str, *, timeout: float = 15.0) -> JobPosting:
    """Fetch *url* and parse it into a synthetic, ephemeral JobPosting."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
    resp = httpx.get(url, headers=headers, follow_redirects=True, timeout=timeout)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    title = (
        _meta(soup, "og:title", "twitter:title")
        or (soup.find("title") or soup.new_tag("x")).get_text(strip=True)
        or "Untitled"
    )
    company = (
        _meta(soup, "og:site_name", "author")
        or urlparse(url).hostname.removeprefix("www.")
    )
    description = _visible_text(soup)

    url_hash = hashlib.sha1(url.encode()).hexdigest()[:8]
    source_id = f"{_slug(title)}-{url_hash}"

    return JobPosting(
        source="url",
        source_id=source_id,
        url=url,
        company=company,
        title=title,
        description=description,
        remote=True,
    )
