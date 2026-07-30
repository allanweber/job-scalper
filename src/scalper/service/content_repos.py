"""Data-access repositories for content: postings pool, per-user config,
resumes, overlays, drafts, async jobs, shared enrichment cache, LLM ledger.

Companion to `repositories.py` (identity/auth/quota). Same conventions: raw SQL
over the DB-API conn, positional row reads, ISO-8601 UTC timestamps. Postings are
a SHARED pool deduped at storage time (one row per `dedup_key`); everything a user
owns is scoped by `user_id`. See docs/DESIGN.md and ADRs 0008/0009/0011.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from scalper.config import Profile, Weights
from scalper.models import JobPosting
from scalper.service.models import now_iso


def _new_id() -> str:
    return uuid.uuid4().hex


def _dumps(value: Any) -> str:
    return json.dumps(value, default=str)


# --------------------------------------------------------------------------- postings


@dataclass
class PoolPosting:
    """A row from the shared postings pool plus its provenance source list."""

    id: str
    company: str
    title: str
    description: str
    location: str | None
    remote: bool
    url: str
    salary_min: float | None
    salary_max: float | None
    salary_currency: str | None
    published_at: str | None
    first_seen_at: str
    last_seen_at: str
    sources: list[str] = field(default_factory=list)

    def to_job_posting(self) -> JobPosting:
        """Reconstruct a `JobPosting` (source='pool') for scoring/drafting."""
        return JobPosting(
            source="pool",
            source_id=self.id,
            url=self.url,
            company=self.company,
            title=self.title,
            description=self.description,
            location=self.location,
            remote=self.remote,
            salary_min=self.salary_min,
            salary_max=self.salary_max,
            salary_currency=self.salary_currency,
            published_at=_parse_dt(self.published_at),
        )


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


_POSTING_COLS = (
    "id, company, title, description, location, remote, url, salary_min, "
    "salary_max, salary_currency, published_at, first_seen_at, last_seen_at"
)


def _to_pool_posting(row: Any) -> PoolPosting:
    return PoolPosting(
        id=row[0], company=row[1], title=row[2], description=row[3] or "",
        location=row[4], remote=bool(row[5]), url=row[6], salary_min=row[7],
        salary_max=row[8], salary_currency=row[9], published_at=row[10],
        first_seen_at=row[11], last_seen_at=row[12],
    )


class PostingRepo:
    """The shared pool. `ingest` collapses postings by `dedup_key` at write time."""

    def __init__(self, conn: Any):
        self._c = conn

    def ingest(self, postings: list[JobPosting]) -> dict[str, int]:
        """Upsert postings into the pool, deduping by `dedup_key`.

        One physical row per `dedup_key` (its value is also the row id); each
        source a posting was seen on is recorded in `posting_sources` so
        provenance survives the dedup. Returns {new, updated, sources} counts.
        """
        new = updated = source_rows = 0
        for p in postings:
            pid = p.dedup_key
            ts = p.collected_at.isoformat() if p.collected_at else now_iso()
            published = p.published_at.isoformat() if p.published_at else None
            existing = self._c.execute(
                "SELECT 1 FROM postings WHERE id=?", (pid,)
            ).fetchone()
            if existing is None:
                self._c.execute(
                    "INSERT INTO postings (id, dedup_key, company, title, description, "
                    "location, remote, timezone, salary_min, salary_max, salary_currency, "
                    "url, published_at, first_seen_at, last_seen_at, raw) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (pid, p.dedup_key, p.company, p.title, p.description,
                     p.location, 1 if p.remote else 0, p.timezone, p.salary_min,
                     p.salary_max, p.salary_currency, p.url, published, ts, ts,
                     _dumps(p.raw)),
                )
                new += 1
            else:
                self._c.execute(
                    "UPDATE postings SET last_seen_at=? WHERE id=?", (ts, pid)
                )
                updated += 1
            self._c.execute(
                "INSERT INTO posting_sources (source, source_id, posting_id, url, seen_at) "
                "VALUES (?,?,?,?,?) ON CONFLICT(source, source_id) DO UPDATE SET "
                "url=excluded.url, seen_at=excluded.seen_at",
                (p.source, p.source_id, pid, p.url, ts),
            )
            source_rows += 1
        self._c.commit()
        return {"new": new, "updated": updated, "sources": source_rows}

    def get(self, posting_id: str) -> PoolPosting | None:
        row = self._c.execute(
            f"SELECT {_POSTING_COLS} FROM postings WHERE id=?", (posting_id,)
        ).fetchone()
        if row is None:
            return None
        post = _to_pool_posting(row)
        post.sources = self._sources_for([post.id]).get(post.id, [])
        return post

    def _sources_for(self, posting_ids: list[str]) -> dict[str, list[str]]:
        if not posting_ids:
            return {}
        placeholders = ",".join("?" for _ in posting_ids)
        rows = self._c.execute(
            f"SELECT posting_id, source FROM posting_sources "
            f"WHERE posting_id IN ({placeholders})",
            tuple(posting_ids),
        ).fetchall()
        out: dict[str, list[str]] = {}
        for pid, source in rows:
            out.setdefault(pid, [])
            if source not in out[pid]:
                out[pid].append(source)
        return out

    def candidates_for_sources(
        self, sources: list[str], *, limit: int = 500
    ) -> list[PoolPosting]:
        """Recent pool postings seen on any of `sources` (feed candidate set)."""
        if not sources:
            return []
        placeholders = ",".join("?" for _ in sources)
        rows = self._c.execute(
            f"SELECT DISTINCT p.id, p.company, p.title, p.description, p.location, "
            f"p.remote, p.url, p.salary_min, p.salary_max, p.salary_currency, "
            f"p.published_at, p.first_seen_at, p.last_seen_at "
            f"FROM postings p JOIN posting_sources ps ON ps.posting_id = p.id "
            f"WHERE ps.source IN ({placeholders}) "
            f"ORDER BY p.last_seen_at DESC LIMIT ?",
            (*sources, limit),
        ).fetchall()
        posts = [_to_pool_posting(r) for r in rows]
        prov = self._sources_for([p.id for p in posts])
        for p in posts:
            p.sources = prov.get(p.id, [])
        return posts

    def search(
        self,
        *,
        q: str | None = None,
        source: str | None = None,
        remote: bool | None = None,
        seen_within_days: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[PoolPosting], int]:
        """Filtered, paginated pool browse for the admin console.

        Returns (page of postings ordered by most-recently-seen, total matched).
        All filters are optional and combine with AND; text `q` matches title,
        company, or description (case-insensitive substring).
        """
        where: list[str] = []
        params: list[Any] = []
        if q and q.strip():
            like = f"%{q.strip().lower()}%"
            where.append("(LOWER(p.title) LIKE ? OR LOWER(p.company) LIKE ? "
                         "OR LOWER(p.description) LIKE ?)")
            params += [like, like, like]
        if source:
            where.append("p.id IN (SELECT posting_id FROM posting_sources WHERE source=?)")
            params.append(source)
        if remote is not None:
            where.append("p.remote = ?")
            params.append(1 if remote else 0)
        if seen_within_days is not None:
            cutoff = (datetime.now(timezone.utc)
                      - timedelta(days=seen_within_days)).isoformat()
            where.append("p.last_seen_at >= ?")
            params.append(cutoff)
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        total = self._c.execute(
            f"SELECT COUNT(*) FROM postings p{clause}", tuple(params)
        ).fetchone()[0]
        rows = self._c.execute(
            f"SELECT {_POSTING_COLS} FROM postings p{clause} "
            f"ORDER BY p.last_seen_at DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()
        posts = [_to_pool_posting(r) for r in rows]
        prov = self._sources_for([p.id for p in posts])
        for p in posts:
            p.sources = prov.get(p.id, [])
        return posts, total

    def count(self) -> int:
        return self._c.execute("SELECT COUNT(*) FROM postings").fetchone()[0]

    def counts_by_source(self) -> list[tuple[str, int]]:
        """Distinct pool postings per source (provenance), most first — for the
        admin 'jobs by source' view."""
        rows = self._c.execute(
            "SELECT source, COUNT(DISTINCT posting_id) AS n FROM posting_sources "
            "GROUP BY source ORDER BY n DESC, source"
        ).fetchall()
        return [(r[0], r[1]) for r in rows]

    def purge_older_than(self, days: int) -> int:
        """Delete pool postings whose last_seen_at is older than `days`. Returns count."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        cur = self._c.execute("DELETE FROM postings WHERE last_seen_at < ?", (cutoff,))
        self._c.commit()
        return cur.rowcount if cur.rowcount is not None else 0


# --------------------------------------------------------------------------- profiles


@dataclass
class StoredProfile:
    id: str
    user_id: str
    name: str
    titles: list[str]
    required_skills: list[str]
    nice_to_have_skills: list[str]
    keywords: list[str]
    exclude_keywords: list[str]
    remote_only: bool
    salary_floor: float
    exclude_non_latin: bool
    weights: dict[str, float]
    origin: str
    created_at: str
    updated_at: str

    def criteria(self) -> Profile:
        """Map to the scoring `Profile` (config) domain model."""
        return Profile(
            titles=self.titles,
            required_skills=self.required_skills,
            nice_to_have_skills=self.nice_to_have_skills,
            keywords=self.keywords,
            exclude_keywords=self.exclude_keywords,
            remote_only=self.remote_only,
            salary_floor=self.salary_floor,
            exclude_non_latin=self.exclude_non_latin,
            weights=Weights(**self.weights) if self.weights else Weights(),
        )

    def search_terms(self) -> list[str]:
        """Terms this profile contributes to a scheduled scrape's union scope."""
        seen: list[str] = []
        for term in [*self.titles, *self.keywords, *self.required_skills]:
            t = term.strip()
            if t and t.lower() not in {s.lower() for s in seen}:
                seen.append(t)
        return seen


_PROFILE_COLS = (
    "id, user_id, name, titles, required_skills, nice_to_have_skills, keywords, "
    "exclude_keywords, remote_only, salary_floor, exclude_non_latin, weights, "
    "origin, created_at, updated_at"
)


def _to_profile(row: Any) -> StoredProfile:
    return StoredProfile(
        id=row[0], user_id=row[1], name=row[2],
        titles=json.loads(row[3]), required_skills=json.loads(row[4]),
        nice_to_have_skills=json.loads(row[5]), keywords=json.loads(row[6]),
        exclude_keywords=json.loads(row[7]), remote_only=bool(row[8]),
        salary_floor=row[9], exclude_non_latin=bool(row[10]),
        weights=json.loads(row[11]) if row[11] else {}, origin=row[12],
        created_at=row[13], updated_at=row[14],
    )


class ProfileRepo:
    """Per-user search profiles. Free tier allows exactly one (enforced above)."""

    def __init__(self, conn: Any):
        self._c = conn

    def list_for(self, user_id: str) -> list[StoredProfile]:
        rows = self._c.execute(
            f"SELECT {_PROFILE_COLS} FROM profiles WHERE user_id=? ORDER BY created_at",
            (user_id,),
        ).fetchall()
        return [_to_profile(r) for r in rows]

    def get(self, profile_id: str) -> StoredProfile | None:
        row = self._c.execute(
            f"SELECT {_PROFILE_COLS} FROM profiles WHERE id=?", (profile_id,)
        ).fetchone()
        return _to_profile(row) if row else None

    def primary_for(self, user_id: str) -> StoredProfile | None:
        row = self._c.execute(
            f"SELECT {_PROFILE_COLS} FROM profiles WHERE user_id=? "
            "ORDER BY created_at LIMIT 1", (user_id,),
        ).fetchone()
        return _to_profile(row) if row else None

    def count_for(self, user_id: str) -> int:
        return self._c.execute(
            "SELECT COUNT(*) FROM profiles WHERE user_id=?", (user_id,)
        ).fetchone()[0]

    def upsert(self, user_id: str, name: str, fields: dict[str, Any], *,
               origin: str = "manual", profile_id: str | None = None) -> StoredProfile:
        """Create or replace a profile. `fields` uses `Profile`-style keys."""
        ts = now_iso()
        weights = fields.get("weights") or {}
        if isinstance(weights, Weights):
            weights = weights.model_dump()
        vals = (
            name,
            _dumps(fields.get("titles", [])),
            _dumps(fields.get("required_skills", [])),
            _dumps(fields.get("nice_to_have_skills", [])),
            _dumps(fields.get("keywords", [])),
            _dumps(fields.get("exclude_keywords", [])),
            1 if fields.get("remote_only", True) else 0,
            float(fields.get("salary_floor", 0) or 0),
            1 if fields.get("exclude_non_latin", True) else 0,
            _dumps(weights),
            origin,
        )
        if profile_id:
            self._c.execute(
                "UPDATE profiles SET name=?, titles=?, required_skills=?, "
                "nice_to_have_skills=?, keywords=?, exclude_keywords=?, remote_only=?, "
                "salary_floor=?, exclude_non_latin=?, weights=?, origin=?, updated_at=? "
                "WHERE id=?",
                (*vals, ts, profile_id),
            )
            pid = profile_id
        else:
            pid = _new_id()
            self._c.execute(
                "INSERT INTO profiles (id, user_id, name, titles, required_skills, "
                "nice_to_have_skills, keywords, exclude_keywords, remote_only, "
                "salary_floor, exclude_non_latin, weights, origin, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (pid, user_id, *vals, ts, ts),
            )
        self._c.commit()
        return self.get(pid)  # type: ignore[return-value]

    def delete(self, profile_id: str) -> None:
        self._c.execute("DELETE FROM profiles WHERE id=?", (profile_id,))
        self._c.commit()


class ActiveUsersRepo:
    """Reads the union of active users' profile terms (scheduled-scrape scope)."""

    def __init__(self, conn: Any):
        self._c = conn

    def profile_terms(self, window_days: int) -> list[str]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat()
        rows = self._c.execute(
            f"SELECT {_PROFILE_COLS} FROM profiles p WHERE p.user_id IN "
            "(SELECT id FROM users WHERE status='active' AND "
            " (last_login_at IS NULL OR last_login_at >= ?))",
            (cutoff,),
        ).fetchall()
        terms: list[str] = []
        seen: set[str] = set()
        for r in rows:
            for t in _to_profile(r).search_terms():
                if t.lower() not in seen:
                    seen.add(t.lower())
                    terms.append(t)
        return terms


# --------------------------------------------------------------------------- resumes


@dataclass
class StoredResume:
    user_id: str
    filename: str | None
    content_type: str | None
    size_bytes: int
    extracted_text: str
    created_at: str
    updated_at: str


class ResumeRepo:
    def __init__(self, conn: Any):
        self._c = conn

    def upsert(self, user_id: str, *, filename: str | None, content_type: str | None,
               blob: bytes, extracted_text: str) -> None:
        ts = now_iso()
        self._c.execute(
            "INSERT INTO resumes (user_id, filename, content_type, size_bytes, "
            "file_blob, extracted_text, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET filename=excluded.filename, "
            "content_type=excluded.content_type, size_bytes=excluded.size_bytes, "
            "file_blob=excluded.file_blob, extracted_text=excluded.extracted_text, "
            "updated_at=excluded.updated_at",
            (user_id, filename, content_type, len(blob), blob, extracted_text, ts, ts),
        )
        self._c.commit()

    def get_meta(self, user_id: str) -> StoredResume | None:
        row = self._c.execute(
            "SELECT user_id, filename, content_type, size_bytes, extracted_text, "
            "created_at, updated_at FROM resumes WHERE user_id=?", (user_id,),
        ).fetchone()
        if row is None:
            return None
        return StoredResume(row[0], row[1], row[2], row[3], row[4] or "", row[5], row[6])

    def get_text(self, user_id: str) -> str | None:
        row = self._c.execute(
            "SELECT extracted_text FROM resumes WHERE user_id=?", (user_id,)
        ).fetchone()
        return row[0] if row else None


# --------------------------------------------------------------------------- user sources


class UserSourceRepo:
    """The <=3 boards a free user searches / sees (gates feed visibility)."""

    def __init__(self, conn: Any):
        self._c = conn

    def list_for(self, user_id: str) -> list[str]:
        rows = self._c.execute(
            "SELECT source_type FROM user_sources WHERE user_id=? ORDER BY position",
            (user_id,),
        ).fetchall()
        return [r[0] for r in rows]

    def set_for(self, user_id: str, sources: list[str]) -> None:
        """Replace the user's chosen sources (order preserved as position)."""
        ts = now_iso()
        self._c.execute("DELETE FROM user_sources WHERE user_id=?", (user_id,))
        for pos, src in enumerate(sources):
            self._c.execute(
                "INSERT INTO user_sources (user_id, source_type, position, created_at) "
                "VALUES (?,?,?,?)",
                (user_id, src, pos, ts),
            )
        self._c.commit()


# --------------------------------------------------------------------------- overlays


@dataclass
class Overlay:
    score: float | None
    first_matched_at: str | None
    seen_at: str | None
    saved: bool
    drafted_at: str | None


class OverlayRepo:
    """Per-user overlay on the shared pool: score, "new" badge, saved, drafted."""

    def __init__(self, conn: Any):
        self._c = conn

    def get_many(self, user_id: str, posting_ids: list[str]) -> dict[str, Overlay]:
        if not posting_ids:
            return {}
        placeholders = ",".join("?" for _ in posting_ids)
        rows = self._c.execute(
            f"SELECT posting_id, score, first_matched_at, seen_at, saved, drafted_at "
            f"FROM user_posting_overlay WHERE user_id=? AND posting_id IN ({placeholders})",
            (user_id, *posting_ids),
        ).fetchall()
        return {
            r[0]: Overlay(r[1], r[2], r[3], bool(r[4]), r[5]) for r in rows
        }

    def upsert_score(self, user_id: str, posting_id: str, score: float,
                     breakdown: dict[str, Any]) -> None:
        """Record the match score; set first_matched_at on first match only."""
        ts = now_iso()
        self._c.execute(
            "INSERT INTO user_posting_overlay (user_id, posting_id, score, "
            "score_breakdown, first_matched_at) VALUES (?,?,?,?,?) "
            "ON CONFLICT(user_id, posting_id) DO UPDATE SET score=excluded.score, "
            "score_breakdown=excluded.score_breakdown",
            (user_id, posting_id, score, _dumps(breakdown), ts),
        )
        self._c.commit()

    def mark_seen(self, user_id: str, posting_id: str) -> None:
        ts = now_iso()
        self._c.execute(
            "INSERT INTO user_posting_overlay (user_id, posting_id, first_matched_at, "
            "seen_at) VALUES (?,?,?,?) ON CONFLICT(user_id, posting_id) "
            "DO UPDATE SET seen_at=excluded.seen_at",
            (user_id, posting_id, ts, ts),
        )
        self._c.commit()

    def set_saved(self, user_id: str, posting_id: str, saved: bool) -> None:
        ts = now_iso()
        self._c.execute(
            "INSERT INTO user_posting_overlay (user_id, posting_id, first_matched_at, "
            "saved) VALUES (?,?,?,?) ON CONFLICT(user_id, posting_id) "
            "DO UPDATE SET saved=excluded.saved",
            (user_id, posting_id, ts, 1 if saved else 0),
        )
        self._c.commit()

    def mark_drafted(self, user_id: str, posting_id: str) -> None:
        ts = now_iso()
        self._c.execute(
            "INSERT INTO user_posting_overlay (user_id, posting_id, first_matched_at, "
            "drafted_at) VALUES (?,?,?,?) ON CONFLICT(user_id, posting_id) "
            "DO UPDATE SET drafted_at=excluded.drafted_at",
            (user_id, posting_id, ts, ts),
        )
        self._c.commit()


# --------------------------------------------------------------------------- enrichment cache


class EnrichmentRepo:
    """Shared enrichment cache keyed by (posting, profile_hash, model)."""

    def __init__(self, conn: Any):
        self._c = conn

    def get(self, posting_id: str, profile_hash: str, model: str) -> str | None:
        row = self._c.execute(
            "SELECT data FROM enrichments WHERE posting_id=? AND profile_hash=? AND model=?",
            (posting_id, profile_hash, model),
        ).fetchone()
        return row[0] if row else None

    def put(self, posting_id: str, profile_hash: str, model: str, data: str) -> None:
        self._c.execute(
            "INSERT INTO enrichments (posting_id, profile_hash, model, data, created_at) "
            "VALUES (?,?,?,?,?) ON CONFLICT(posting_id, profile_hash, model) "
            "DO UPDATE SET data=excluded.data, created_at=excluded.created_at",
            (posting_id, profile_hash, model, data, now_iso()),
        )
        self._c.commit()


# --------------------------------------------------------------------------- drafts


@dataclass
class Draft:
    id: str
    user_id: str
    profile_id: str | None
    posting_id: str | None
    job_source: str
    source_url: str | None
    resume_md: str | None
    cover_letter_md: str | None
    stretch_claims_md: str | None
    provider: str | None
    model: str | None
    key_source: str | None
    created_at: str
    updated_at: str


_DRAFT_COLS = (
    "id, user_id, profile_id, posting_id, job_source, source_url, resume_md, "
    "cover_letter_md, stretch_claims_md, provider, model, key_source, "
    "created_at, updated_at"
)


def _to_draft(row: Any) -> Draft:
    return Draft(*row)


class DraftRepo:
    """Private per-user drafts (markdown + optional PDF blobs)."""

    def __init__(self, conn: Any):
        self._c = conn

    def create(self, user_id: str, *, profile_id: str | None, posting_id: str | None,
               job_source: str, source_url: str | None, resume_md: str,
               cover_letter_md: str, stretch_claims_md: str | None, provider: str | None,
               model: str | None, key_source: str | None,
               resume_pdf: bytes | None = None,
               cover_letter_pdf: bytes | None = None) -> str:
        did = _new_id()
        ts = now_iso()
        self._c.execute(
            "INSERT INTO drafts (id, user_id, profile_id, posting_id, job_source, "
            "source_url, resume_md, cover_letter_md, stretch_claims_md, resume_pdf, "
            "cover_letter_pdf, provider, model, key_source, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (did, user_id, profile_id, posting_id, job_source, source_url, resume_md,
             cover_letter_md, stretch_claims_md, resume_pdf, cover_letter_pdf,
             provider, model, key_source, ts, ts),
        )
        self._c.commit()
        return did

    def get(self, draft_id: str, user_id: str) -> Draft | None:
        row = self._c.execute(
            f"SELECT {_DRAFT_COLS} FROM drafts WHERE id=? AND user_id=?",
            (draft_id, user_id),
        ).fetchone()
        return _to_draft(row) if row else None

    def get_pdf(self, draft_id: str, user_id: str, which: str) -> bytes | None:
        col = "resume_pdf" if which == "resume" else "cover_letter_pdf"
        row = self._c.execute(
            f"SELECT {col} FROM drafts WHERE id=? AND user_id=?", (draft_id, user_id)
        ).fetchone()
        if not row or row[0] is None:
            return None
        return bytes(row[0])

    def list_for(self, user_id: str, *, limit: int = 50) -> list[Draft]:
        rows = self._c.execute(
            f"SELECT {_DRAFT_COLS} FROM drafts WHERE user_id=? "
            "ORDER BY created_at DESC LIMIT ?", (user_id, limit),
        ).fetchall()
        return [_to_draft(r) for r in rows]


# --------------------------------------------------------------------------- async jobs


@dataclass
class JobRecord:
    id: str
    user_id: str | None
    kind: str
    status: str
    params: dict[str, Any]
    result: dict[str, Any] | None
    error: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None


_JOB_COLS = ("id, user_id, kind, status, params, result, error, created_at, "
             "started_at, finished_at")


def _to_job(row: Any) -> JobRecord:
    return JobRecord(
        id=row[0], user_id=row[1], kind=row[2], status=row[3],
        params=json.loads(row[4]) if row[4] else {},
        result=json.loads(row[5]) if row[5] else None,
        error=row[6], created_at=row[7], started_at=row[8], finished_at=row[9],
    )


class JobRepo:
    """Durable mirror of async jobs backing job_id polling + admin monitoring."""

    def __init__(self, conn: Any):
        self._c = conn

    def create(self, kind: str, *, user_id: str | None,
               params: dict[str, Any] | None = None, job_id: str | None = None) -> str:
        jid = job_id or _new_id()
        self._c.execute(
            "INSERT INTO jobs (id, user_id, kind, status, params, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (jid, user_id, kind, "queued", _dumps(params or {}), now_iso()),
        )
        self._c.commit()
        return jid

    def get(self, job_id: str) -> JobRecord | None:
        row = self._c.execute(
            f"SELECT {_JOB_COLS} FROM jobs WHERE id=?", (job_id,)
        ).fetchone()
        return _to_job(row) if row else None

    def mark_running(self, job_id: str) -> None:
        self._c.execute(
            "UPDATE jobs SET status='running', started_at=? WHERE id=?",
            (now_iso(), job_id),
        )
        self._c.commit()

    def mark_succeeded(self, job_id: str, result: dict[str, Any]) -> None:
        self._c.execute(
            "UPDATE jobs SET status='succeeded', result=?, finished_at=? WHERE id=?",
            (_dumps(result), now_iso(), job_id),
        )
        self._c.commit()

    def mark_failed(self, job_id: str, error: str) -> None:
        self._c.execute(
            "UPDATE jobs SET status='failed', error=?, finished_at=? WHERE id=?",
            (error[:2000], now_iso(), job_id),
        )
        self._c.commit()

    def list_recent(self, *, limit: int = 50, kind: str | None = None,
                    status: str | None = None) -> list[JobRecord]:
        where, params = [], []
        if kind:
            where.append("kind=?"); params.append(kind)
        if status:
            where.append("status=?"); params.append(status)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        rows = self._c.execute(
            f"SELECT {_JOB_COLS} FROM jobs {clause} ORDER BY created_at DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
        return [_to_job(r) for r in rows]

    def counts_by_status(self) -> dict[str, int]:
        rows = self._c.execute(
            "SELECT status, COUNT(*) FROM jobs GROUP BY status"
        ).fetchall()
        return {r[0]: r[1] for r in rows}


class AuditRepo:
    """Append-only admin action log (who / what / when / before -> after)."""

    def __init__(self, conn: Any):
        self._c = conn

    def record(self, *, admin_user_id: str | None, action: str,
               target_type: str | None = None, target_id: str | None = None,
               before: Any = None, after: Any = None, note: str | None = None) -> None:
        self._c.execute(
            "INSERT INTO admin_audit (id, ts, admin_user_id, action, target_type, "
            "target_id, before, after, note) VALUES (?,?,?,?,?,?,?,?,?)",
            (_new_id(), now_iso(), admin_user_id, action, target_type, target_id,
             _dumps(before) if before is not None else None,
             _dumps(after) if after is not None else None, note),
        )
        self._c.commit()

    def list_recent(self, *, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._c.execute(
            "SELECT ts, admin_user_id, action, target_type, target_id, before, after, "
            "note FROM admin_audit ORDER BY ts DESC LIMIT ?", (limit,),
        ).fetchall()
        out = []
        for r in rows:
            out.append({
                "ts": r[0], "admin_user_id": r[1], "action": r[2],
                "target_type": r[3], "target_id": r[4],
                "before": json.loads(r[5]) if r[5] else None,
                "after": json.loads(r[6]) if r[6] else None, "note": r[7],
            })
        return out


# --------------------------------------------------------------------------- LLM ledger


class LLMUsageRepo:
    """Detailed per-user token/cost ledger (admin visibility + cost tracking)."""

    def __init__(self, conn: Any):
        self._c = conn

    def record(self, user_id: str, *, action: str, provider: str, model: str,
               key_source: str, input_tokens: int, output_tokens: int,
               est_cost_usd: float | None = None, job_id: str | None = None) -> None:
        self._c.execute(
            "INSERT INTO llm_usage_events (id, user_id, ts, action, provider, model, "
            "key_source, input_tokens, output_tokens, est_cost_usd, job_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (_new_id(), user_id, now_iso(), action, provider, model, key_source,
             input_tokens, output_tokens, est_cost_usd, job_id),
        )
        self._c.commit()

    def total_tokens_for(self, user_id: str) -> int:
        row = self._c.execute(
            "SELECT COALESCE(SUM(input_tokens + output_tokens), 0) "
            "FROM llm_usage_events WHERE user_id=?", (user_id,),
        ).fetchone()
        return row[0] if row else 0
