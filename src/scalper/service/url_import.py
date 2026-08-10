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
import json
import re
import socket
from html import unescape
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
#: A page whose readable description is thinner than this is almost certainly a
#: JavaScript app shell (the content loads client-side), not a real posting.
_MIN_DESC_WORDS = 20
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


def _clean(text: str | None) -> str | None:
    """Collapse whitespace; return None for empty/falsey input."""
    if not text:
        return None
    text = re.sub(r"\s+", " ", str(text)).strip()
    return text or None


def _iter_ld_nodes(data: Any):
    """Walk a parsed JSON-LD payload, yielding every object node (handling the
    top-level list and `@graph` container shapes JSON-LD comes in)."""
    if isinstance(data, list):
        for item in data:
            yield from _iter_ld_nodes(item)
    elif isinstance(data, dict):
        graph = data.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                yield from _iter_ld_nodes(item)
        yield data


def _json_ld_job(soup: BeautifulSoup) -> dict | None:
    """Return the first schema.org JobPosting node embedded as JSON-LD, if any.

    Career and ATS pages (Greenhouse, Lever, Workday, …) routinely ship the
    posting as `<script type="application/ld+json">` even when the visible body
    is rendered client-side, so this is often the only reliable content on a
    single-page-app posting.
    """
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = tag.string or tag.get_text()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            continue
        for node in _iter_ld_nodes(data):
            types = node.get("@type")
            types = types if isinstance(types, list) else [types]
            if "JobPosting" in types:
                return node
    return None


def _ld_org(node: dict) -> str | None:
    org = node.get("hiringOrganization")
    if isinstance(org, dict):
        return _clean(org.get("name"))
    return _clean(org) if isinstance(org, str) else None


def _ld_description(node: dict) -> str | None:
    """JSON-LD descriptions carry HTML markup; strip it down to plain text."""
    raw = node.get("description")
    if not raw:
        return None
    text = BeautifulSoup(unescape(str(raw)), "html.parser").get_text(" ", strip=True)
    return _clean(text)


def _ld_salary(node: dict) -> tuple[float | None, float | None, str | None]:
    base = node.get("baseSalary")
    if not isinstance(base, dict):
        return None, None, None
    cur = base.get("currency") or base.get("salaryCurrency")
    value = base.get("value")

    def _num(v: Any) -> float | None:
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    if isinstance(value, dict):
        lo = _num(value.get("minValue"))
        hi = _num(value.get("maxValue"))
        if lo is None and hi is None:
            lo = hi = _num(value.get("value"))
        return lo, hi, (str(cur) if cur else None)
    single = _num(value)
    return single, single, (str(cur) if cur else None)


def _parse_salary(text: str) -> tuple[float | None, float | None, str | None]:
    m = _SALARY_RE.search(text)
    if not m:
        return None, None, None

    def _num(raw: str) -> float:
        n = float(raw.replace(",", "").replace(".", ""))
        return n * 1000 if n < 1000 else n

    return _num(m["lo"]), _num(m["hi"]), _CUR_SYMBOL.get(m["cur"])


def parse_posting(url: str, html: str) -> JobPosting:
    """Best-effort extraction of a JobPosting from a career-page's HTML.

    Structured JSON-LD (when present) wins over page metadata and visible text,
    since it survives client-side rendering. A page that yields almost no
    readable content is treated as an unreadable app shell and rejected, so the
    caller gets a clear error instead of an empty posting.
    """
    soup = BeautifulSoup(html, "html.parser")
    # Read structured data before discarding <script> tags — that's where it lives.
    ld = _json_ld_job(soup) or {}
    for junk in soup(["script", "style", "noscript"]):
        junk.decompose()

    title = (_clean(ld.get("title"))
             or _meta(soup, "og:title", "twitter:title")
             or (soup.title.string.strip() if soup.title and soup.title.string else None))
    if not title:
        raise UrlImportError("could not read a job title from that page")
    title = re.sub(r"\s+", " ", title)[:200]

    company = (_ld_org(ld)
               or _meta(soup, "og:site_name")
               or (urlparse(url).hostname or "").replace("www.", "").split(".")[0].title()
               or "Unknown")

    body = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    og_desc = _meta(soup, "og:description", "description")
    # JSON-LD description first; then the visible body (the real posting text);
    # fall back to a meta-description teaser only when there's no body at all.
    description = _ld_description(ld) or _clean(body) or _clean(og_desc) or ""
    # A JS app shell leaves us with a title and little else — refuse rather than
    # pool a contentless posting that would score ~0.
    if len(description.split()) < _MIN_DESC_WORDS:
        raise UrlImportError(
            "couldn’t read the job details from that page — it may load its "
            "content with JavaScript. Try pasting the direct job-description URL "
            "(not an apply/login page).")

    haystack = f"{title} {body} {description}".lower()
    remote = ("remote" in haystack
              or str(ld.get("jobLocationType", "")).upper() == "TELECOMMUTE")
    lo, hi, cur = _parse_salary(f"{description} {body}")
    if lo is None:
        lo, hi, cur = _ld_salary(ld)

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
