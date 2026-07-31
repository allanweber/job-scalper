"""Import a single job posting from an arbitrary URL (mobile "Apply by URL").

The scheduler fills the pool from a fixed catalog of boards; this lets a user pull
in one specific posting the scheduler hasn't collected. Fetching a user-supplied URL
server-side is an SSRF sink, so `default_url_fetch` validates the scheme, resolves
the host, and refuses any address that maps into a private/loopback/link-local/
reserved range before issuing the request. The fetcher is injectable so tests (and a
future headless-render path) can supply canned HTML without real egress.

Parsing arbitrary career pages perfectly is out of scope: we extract a best-effort
title/company/description/remote/salary from standard tags and pool the result. The
posting is scored per-user by the normal feed path once stored.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from typing import Any, Callable
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from scalper.models import JobPosting
from scalper.service.content_repos import PostingRepo

#: A callable that turns a URL into raw HTML (or raises UrlImportError).
UrlFetcher = Callable[[str], str]

_MAX_BYTES = 2_000_000
_TIMEOUT = 15.0
_UA = "JobScalperBot/1.0 (+https://jobscalper.allanweber.dev)"
_SALARY_RE = re.compile(
    r"(?P<cur>[$€£])\s?(?P<lo>\d{2,3}(?:[,.]\d{3})?)\s?(?:k)?\s?[–\-to]{1,3}\s?"
    r"(?P<hi>\d{2,3}(?:[,.]\d{3})?)\s?(?:k)?",
    re.IGNORECASE,
)
_CUR_SYMBOL = {"$": "USD", "€": "EUR", "£": "GBP"}


class UrlImportError(Exception):
    """The URL could not be safely fetched or parsed into a posting."""


def _guard_public_host(url: str) -> None:
    """Reject non-http(s) URLs and any host that resolves to a non-public IP."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UrlImportError("only http(s) URLs are supported")
    host = parsed.hostname
    if not host:
        raise UrlImportError("URL has no host")
    try:
        infos = socket.getaddrinfo(host, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise UrlImportError(f"could not resolve host: {host}") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise UrlImportError("URL resolves to a non-public address")


def default_url_fetch(url: str) -> str:
    """Fetch a public URL's HTML with SSRF guards, a size cap, and a timeout."""
    _guard_public_host(url)
    try:
        with httpx.Client(timeout=_TIMEOUT, follow_redirects=True,
                          headers={"User-Agent": _UA}) as client:
            resp = client.get(url)
            resp.raise_for_status()
            if len(resp.content) > _MAX_BYTES:
                raise UrlImportError("page too large to import")
            return resp.text
    except httpx.HTTPError as e:
        raise UrlImportError(f"could not fetch the page ({e.__class__.__name__})") from e


def _meta(soup: BeautifulSoup, *names: str) -> str | None:
    for name in names:
        tag = (soup.find("meta", property=name)
               or soup.find("meta", attrs={"name": name}))
        if tag and tag.get("content"):
            return tag["content"].strip()
    return None


def _parse_salary(text: str) -> tuple[float | None, float | None, str | None]:
    m = _SALARY_RE.search(text)
    if not m:
        return None, None, None

    def _num(raw: str) -> float:
        n = float(raw.replace(",", "").replace(".", ""))
        return n * 1000 if n < 1000 else n

    return _num(m["lo"]), _num(m["hi"]), _CUR_SYMBOL.get(m["cur"])


def parse_posting(url: str, html: str) -> JobPosting:
    """Best-effort extraction of a JobPosting from a career-page's HTML."""
    soup = BeautifulSoup(html, "html.parser")
    for junk in soup(["script", "style", "noscript"]):
        junk.decompose()

    title = (_meta(soup, "og:title", "twitter:title")
             or (soup.title.string.strip() if soup.title and soup.title.string else None))
    if not title:
        raise UrlImportError("could not read a job title from that page")
    title = re.sub(r"\s+", " ", title)[:200]

    company = (_meta(soup, "og:site_name")
               or (urlparse(url).hostname or "").replace("www.", "").split(".")[0].title()
               or "Unknown")

    body = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    description = _meta(soup, "og:description", "description") or body[:4000]
    if not description.strip():
        raise UrlImportError("could not read any job description from that page")

    haystack = f"{title} {body}".lower()
    remote = "remote" in haystack
    lo, hi, cur = _parse_salary(body)

    return JobPosting(
        source="url", source_id=url, url=url, company=company[:120],
        title=title, description=description[:8000], remote=remote,
        salary_min=lo, salary_max=hi, salary_currency=cur,
    )


def import_posting_from_url(conn: Any, url: str, *,
                            fetcher: UrlFetcher | None = None) -> str:
    """Fetch, parse, and pool a posting from `url`; return its pool posting id."""
    html = (fetcher or default_url_fetch)(url)
    posting = parse_posting(url, html)
    PostingRepo(conn).ingest([posting])
    return posting.dedup_key
