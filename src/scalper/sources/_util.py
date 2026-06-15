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
