"""SQLite-backed persistence for collected postings (the collect/report split, ADR 0002)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from scalper.models import JobPosting

_SCHEMA = """
CREATE TABLE IF NOT EXISTS postings (
    uid           TEXT PRIMARY KEY,
    source        TEXT NOT NULL,
    source_id     TEXT NOT NULL,
    url           TEXT NOT NULL,
    company       TEXT NOT NULL,
    title         TEXT NOT NULL,
    description   TEXT NOT NULL DEFAULT '',
    location      TEXT,
    remote        INTEGER NOT NULL DEFAULT 0,
    timezone      TEXT,
    salary_min    REAL,
    salary_max    REAL,
    salary_currency TEXT,
    published_at  TEXT,
    collected_at  TEXT NOT NULL,
    dedup_key     TEXT NOT NULL,
    raw           TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_postings_dedup ON postings(dedup_key);
CREATE INDEX IF NOT EXISTS idx_postings_published ON postings(published_at);
"""


def _to_iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _from_iso(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


class JobStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "JobStore":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def upsert_many(self, postings: list[JobPosting]) -> tuple[int, int]:
        """Insert/replace postings. Returns (new, updated) counts."""
        new = updated = 0
        now = datetime.now(timezone.utc)
        cur = self._conn.cursor()
        for p in postings:
            p.collected_at = p.collected_at or now
            exists = cur.execute(
                "SELECT 1 FROM postings WHERE uid = ?", (p.uid,)
            ).fetchone()
            cur.execute(
                """
                INSERT INTO postings (
                    uid, source, source_id, url, company, title, description,
                    location, remote, timezone, salary_min, salary_max,
                    salary_currency, published_at, collected_at, dedup_key, raw
                ) VALUES (
                    :uid, :source, :source_id, :url, :company, :title, :description,
                    :location, :remote, :timezone, :salary_min, :salary_max,
                    :salary_currency, :published_at, :collected_at, :dedup_key, :raw
                )
                ON CONFLICT(uid) DO UPDATE SET
                    url=excluded.url, company=excluded.company, title=excluded.title,
                    description=excluded.description, location=excluded.location,
                    remote=excluded.remote, timezone=excluded.timezone,
                    salary_min=excluded.salary_min, salary_max=excluded.salary_max,
                    salary_currency=excluded.salary_currency,
                    published_at=excluded.published_at, dedup_key=excluded.dedup_key,
                    raw=excluded.raw
                """,
                {
                    "uid": p.uid,
                    "source": p.source,
                    "source_id": p.source_id,
                    "url": p.url,
                    "company": p.company,
                    "title": p.title,
                    "description": p.description,
                    "location": p.location,
                    "remote": int(p.remote),
                    "timezone": p.timezone,
                    "salary_min": p.salary_min,
                    "salary_max": p.salary_max,
                    "salary_currency": p.salary_currency,
                    "published_at": _to_iso(p.published_at),
                    "collected_at": _to_iso(p.collected_at),
                    "dedup_key": p.dedup_key,
                    "raw": json.dumps(p.raw, default=str),
                },
            )
            if exists:
                updated += 1
            else:
                new += 1
        self._conn.commit()
        return new, updated

    def iter_postings(self) -> Iterator[JobPosting]:
        for row in self._conn.execute("SELECT * FROM postings"):
            yield self._row_to_posting(row)

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM postings").fetchone()[0]

    @staticmethod
    def _row_to_posting(row: sqlite3.Row) -> JobPosting:
        return JobPosting(
            source=row["source"],
            source_id=row["source_id"],
            url=row["url"],
            company=row["company"],
            title=row["title"],
            description=row["description"],
            location=row["location"],
            remote=bool(row["remote"]),
            timezone=row["timezone"],
            salary_min=row["salary_min"],
            salary_max=row["salary_max"],
            salary_currency=row["salary_currency"],
            published_at=_from_iso(row["published_at"]),
            collected_at=_from_iso(row["collected_at"]),
            raw=json.loads(row["raw"]),
        )
