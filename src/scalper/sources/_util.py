"""Shared parsing helpers for structured source adapters."""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
REMOTE_HINT = re.compile(r"\bremote\b", re.IGNORECASE)


def strip_html(raw: str) -> str:
    """Unescape HTML entities then strip tags, collapsing whitespace."""
    text = html.unescape(raw or "")
    text = _TAG.sub(" ", text)
    text = html.unescape(text)  # entities sometimes survive a layer
    return _WS.sub(" ", text).strip()


def parse_iso_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def parse_epoch_ms(value: object) -> datetime | None:
    """Parse a millisecond epoch."""
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def parse_epoch_s(value: object) -> datetime | None:
    """Parse a second-granularity epoch (RemoteOK uses these for `epoch`)."""
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def parse_rss_dt(value: str | None) -> datetime | None:
    """Parse an RFC-822 RSS pubDate (e.g. 'Thu, 21 May 2026 20:03:04 +0000')."""
    if not value:
        return None
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None


def rss_items(xml_text: str) -> list[dict[str, str]]:
    """Parse an RSS document into a list of item dicts (local tag -> text).

    Namespaces are stripped from tags so callers index by the bare element name
    (e.g. 'title', 'link', 'pubDate'). Returns [] if the document doesn't parse.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    items: list[dict[str, str]] = []
    for item in root.findall(".//item"):
        fields: dict[str, str] = {}
        for child in item:
            tag = child.tag.split("}")[-1]
            fields[tag] = (child.text or "").strip()
        items.append(fields)
    return items


def atom_entries(xml_text: str) -> list[dict[str, str]]:
    """Parse an Atom feed into a list of entry dicts (Reddit serves Atom).

    Each dict carries the bare-name text fields (title, content, id, published,
    updated) plus a `link` taken from the entry's <link href="...">. Returns []
    if the document is empty or doesn't parse (Reddit rate-limits with a blank
    body, which must not crash the caller).
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    entries: list[dict[str, str]] = []
    for entry in root.iter():
        if entry.tag.split("}")[-1] != "entry":
            continue
        fields: dict[str, str] = {}
        for child in entry:
            tag = child.tag.split("}")[-1]
            if tag == "link":
                fields.setdefault("link", child.get("href", ""))
            elif tag == "author":
                name = child.find("{http://www.w3.org/2005/Atom}name")
                fields["author"] = (name.text or "").strip() if name is not None else ""
            else:
                fields[tag] = (child.text or "").strip()
        entries.append(fields)
    return entries


def looks_remote(*texts: str | None) -> bool:
    return any(t and REMOTE_HINT.search(t) for t in texts)


# --- structured-compensation parsing (Phase 5) ----------------------------

_CURRENCY_SYMBOL = {"$": "USD", "€": "EUR", "£": "GBP"}
_CURRENCY_CODE = re.compile(r"\b(USD|EUR|GBP|CAD|AUD|CHF|SGD|INR|NZD)\b", re.IGNORECASE)
# A money amount, optionally with thousands separators and a `k`/`m` magnitude.
_AMOUNT = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*([kKmM])?")
# Annual-salary sanity window: drop stray small numbers (hourly rates, "401(k)")
# and absurd outliers, so a free-text field yields a sensible range or nothing.
_SALARY_MIN, _SALARY_MAX = 1_000.0, 10_000_000.0


def parse_salary(text: str | None) -> tuple[float | None, float | None, str | None]:
    """Best-effort parse of a free-text compensation string into (min, max, currency).

    Handles the shapes sources like Remotive emit: ``"$90,000 - $120,000"``,
    ``"€80k–€100k"``, ``"USD 120000"``, ``"Up to $150k"``, ``"$110,000"``. Returns
    ``(None, None, None)`` when nothing salary-shaped is found. Amounts outside a
    plausible annual window are ignored, so hourly rates and noise like ``401(k)``
    don't masquerade as a salary. A single amount becomes the min (max stays
    ``None``) unless the text says "up to"/"max", which makes it the ceiling.
    """
    if not text:
        return None, None, None

    currency = None
    for sym, code in _CURRENCY_SYMBOL.items():
        if sym in text:
            currency = code
            break
    if currency is None:
        m = _CURRENCY_CODE.search(text)
        if m:
            currency = m.group(1).upper()

    amounts: list[float] = []
    for num, mag in _AMOUNT.findall(text):
        val = float(num.replace(",", ""))
        if mag in ("k", "K"):
            val *= 1_000
        elif mag in ("m", "M"):
            val *= 1_000_000
        if _SALARY_MIN <= val <= _SALARY_MAX:
            amounts.append(val)

    if not amounts:
        return None, None, currency
    if len(amounts) == 1:
        amt = amounts[0]
        if re.search(r"\b(up to|max(?:imum)?|under|below)\b", text, re.IGNORECASE):
            return None, amt, currency
        return amt, None, currency
    return min(amounts), max(amounts), currency


# --- timezone extraction from location strings (Phase 5) -------------------

# Explicit UTC/GMT offset, e.g. "UTC+2", "GMT -5", "UTC+05:30" -> normalized "UTC+2".
_TZ_OFFSET = re.compile(r"\b(?:UTC|GMT)\s*([+-])\s*(\d{1,2})(?::?(\d{2}))?\b", re.IGNORECASE)
# Named timezone abbreviations commonly seen in remote-job location fields.
_TZ_ABBR = re.compile(
    r"\b(EST|EDT|PST|PDT|CST|CDT|MST|MDT|CET|CEST|EET|EEST|WET|BST|IST|JST|AEST|UTC|GMT)\b"
)
# Coarse multi-timezone region buckets — honest when a posting names a region or
# country rather than a single zone (a US-remote role spans several zones).
_TZ_REGIONS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bEMEA\b", re.IGNORECASE), "EMEA"),
    (re.compile(r"\bAPAC\b", re.IGNORECASE), "APAC"),
    (re.compile(r"\bLATAM\b", re.IGNORECASE), "LATAM"),
    (re.compile(r"\b(?:Americas|North America|U\.?S\.?A?\.?|United States|Canada)\b", re.IGNORECASE), "Americas"),
    (re.compile(r"\b(?:Europe|European|EU)\b", re.IGNORECASE), "Europe"),
    (re.compile(r"\b(?:Asia|Asian|Asia[- ]Pacific)\b", re.IGNORECASE), "Asia"),
]


def extract_timezone(location: str | None) -> str | None:
    """Pull a timezone hint out of a free-text location, or ``None``.

    Prefers the most precise signal: an explicit ``UTC±N`` offset, then a named
    abbreviation (``CET``, ``EST``…), then a coarse region bucket (``Europe``,
    ``Americas``…) for postings that name a region or country instead of a zone.
    """
    if not location:
        return None
    m = _TZ_OFFSET.search(location)
    if m:
        sign, hours = m.group(1), int(m.group(2))
        mins = m.group(3)
        suffix = f":{mins}" if mins and mins != "00" else ""
        return f"UTC{sign}{hours}{suffix}"
    m = _TZ_ABBR.search(location)
    if m:
        return m.group(1).upper()
    for pattern, label in _TZ_REGIONS:
        if pattern.search(location):
            return label
    return None


def matches_any_term(text: str, terms: list[str]) -> bool:
    """True if `text` matches any of `terms` (case-insensitive).

    A multi-word term matches when *all* its words appear somewhere in `text`
    (AND within a term), and the result is OR across terms — so "python backend"
    matches a posting mentioning both "Python" and "Backend" anywhere, not only
    the literal phrase. Used by broad-feed sources that can't search server-side.
    Empty `terms` matches everything (the source's whole feed is in scope).
    """
    if not terms:
        return True
    low = text.lower()
    for term in terms:
        words = [w for w in term.lower().split() if w]
        if words and all(w in low for w in words):
            return True
    return False
