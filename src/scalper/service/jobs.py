"""Async job work + dispatch (ADR 0009).

User-facing heavy operations run as jobs returning a `job_id` the client polls:
**profile-from-resume, draft, enrich**. System jobs (**scrape, purge**) are
scheduled/admin-only. Each job opens its own DB connection (matching the RQ
worker), records status transitions in the `jobs` table, routes LLM work through
`LLMRouter` (platform vs BYO), enforces quotas, and shares the enrichment cache.

`JobQueue.enqueue` runs jobs **inline ("eager")** when no Redis is configured — so
the API is fully testable without a worker — and via RQ otherwise. Both paths call
the same `execute` dispatch, so behaviour is identical.
"""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Callable, Iterator

from scalper.app_draft import draft_application, split_draft
from scalper.enrich import Enrichment, build_prompt as build_enrich_prompt, profile_hash
from scalper.profile_draft import draft_profile, profile_fields
from scalper.prompts import ENRICH_SYSTEM
from scalper.scoring import score_posting
from scalper.service.content_repos import (
    DraftRepo,
    EnrichmentRepo,
    JobRepo,
    OverlayRepo,
    PostingRepo,
    ProfileRepo,
    ResumeRepo,
)
from scalper.service.llm_router import LLMRouter
from scalper.service.quota import QuotaExceeded, QuotaService
from scalper.service.repositories import LLMCredentialRepo, UserRepo

if TYPE_CHECKING:
    from scalper.service.container import Container

_log = logging.getLogger(__name__)

# Job kinds.
KIND_PROFILE = "profile"
KIND_DRAFT = "draft"
KIND_ENRICH = "enrich"
KIND_SCRAPE = "scrape"
KIND_PURGE = "purge"

USER_KINDS = {KIND_PROFILE, KIND_DRAFT, KIND_ENRICH}

#: Job kind -> the quota metric it consumes (system jobs have none).
_KIND_METRIC = {KIND_PROFILE: "profile_build", KIND_DRAFT: "draft", KIND_ENRICH: "enrich"}


class JobError(Exception):
    """A job failed for a business reason (message stored on the job record)."""


@contextmanager
def _reserved(quota: QuotaService, user: Any, metric: str, *,
              unlimited: bool) -> Iterator[None]:
    """Reserve one quota unit for an LLM job, refunding it if the body fails.

    Quota is consumed up-front to reserve capacity before the (slow, costly) LLM
    call, but a failed call — provider error, timeout — must not cost the user a
    credit. On any exception the unit is refunded and the error re-raised.
    """
    try:
        quota.consume(user, metric, unlimited=unlimited)
    except QuotaExceeded as e:
        raise JobError(f"quota_exceeded:{e.status.metric}") from e
    try:
        yield
    except Exception:
        quota.refund(user, metric)
        raise


def _has_byo(container: "Container", conn: Any, user_id: str) -> bool:
    return container.vault is not None and LLMCredentialRepo(conn).has_valid(user_id)


def _parse_enrichment(text: str) -> Enrichment:
    text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return Enrichment.model_validate(json.loads(text[start:end + 1]))
        except Exception:  # noqa: BLE001 — fail soft to an empty enrichment
            pass
    return Enrichment()


# --------------------------------------------------------------------------- work funcs


def run_profile(container: "Container", conn: Any, job_id: str, user_id: str,
                params: dict[str, Any]) -> dict[str, Any]:
    """Build/replace the user's profile from their stored resume via the LLM."""
    resume_text = ResumeRepo(conn).get_text(user_id)
    if not resume_text:
        raise JobError("no resume on file — upload a resume first")

    settings = container.settings(conn)
    router = LLMRouter(conn, settings, container.vault, environ=container.environ,
                       provider_builder=container.provider_builder)
    quota = QuotaService(conn=conn, settings=settings)
    user = UserRepo(conn).get(user_id)
    unlimited = _has_byo(container, conn, user_id)
    with _reserved(quota, user, "profile_build", unlimited=unlimited):
        decision = router.resolve(user_id, "profile_build")
        draft, comp = draft_profile(decision.provider, decision.model, resume_text)
        router.record_usage(user_id, action="profile_build", decision=decision,
                            input_tokens=comp.input_tokens,
                            output_tokens=comp.output_tokens, job_id=job_id)

        profiles = ProfileRepo(conn)
        existing = profiles.primary_for(user_id)
        name = params.get("name") or (existing.name if existing else "default")
        stored = profiles.upsert(user_id, name, profile_fields(draft), origin="resume",
                                 profile_id=existing.id if existing else None)
        return {
            "profile_id": stored.id,
            "titles": stored.titles,
            "required_skills": stored.required_skills,
            "key_source": decision.key_source,
        }


def run_draft(container: "Container", conn: Any, job_id: str, user_id: str,
              params: dict[str, Any]) -> dict[str, Any]:
    """Draft a tailored resume + cover letter for one pool posting.

    The endpoint may have already created a 'pending' draft row (its id passed
    as ``draft_id``); we fill it in and flip it to 'ready'. Any failure marks
    that row 'failed' with the reason so the client stops polling and shows it.
    """
    posting_id = params.get("posting_id")
    draft_id = params.get("draft_id")
    try:
        if not posting_id:
            raise JobError("posting_id is required")
        resume_text = ResumeRepo(conn).get_text(user_id)
        if not resume_text:
            raise JobError("no resume on file — upload a resume first")

        profiles = ProfileRepo(conn)
        profile = profiles.primary_for(user_id)
        if profile is None:
            raise JobError("no profile — build one from your resume first")

        pool = PostingRepo(conn).get(posting_id)
        if pool is None:
            raise JobError("posting not found in the pool")

        settings = container.settings(conn)
        router = LLMRouter(conn, settings, container.vault, environ=container.environ,
                           provider_builder=container.provider_builder)
        quota = QuotaService(conn=conn, settings=settings)
        user = UserRepo(conn).get(user_id)
        unlimited = _has_byo(container, conn, user_id)
        with _reserved(quota, user, "draft", unlimited=unlimited):
            scored = score_posting(profile.criteria(), pool.to_job_posting())
            decision = router.resolve(user_id, "draft")
            text, comp = draft_application(decision.provider, decision.model,
                                           profile.name, resume_text, scored)
            parts = split_draft(text)
            router.record_usage(user_id, action="draft", decision=decision,
                                input_tokens=comp.input_tokens,
                                output_tokens=comp.output_tokens, job_id=job_id)

            if draft_id:
                DraftRepo(conn).mark_ready(
                    draft_id, user_id, profile_id=profile.id,
                    resume_md=parts.resume, cover_letter_md=parts.cover_letter,
                    stretch_claims_md=parts.stretch_claims,
                    provider=decision.provider_name, model=decision.model,
                    key_source=decision.key_source,
                )
            else:
                draft_id = DraftRepo(conn).create(
                    user_id, profile_id=profile.id, posting_id=posting_id,
                    job_source="pool", source_url=None, resume_md=parts.resume,
                    cover_letter_md=parts.cover_letter,
                    stretch_claims_md=parts.stretch_claims,
                    provider=decision.provider_name, model=decision.model,
                    key_source=decision.key_source,
                )
            OverlayRepo(conn).mark_drafted(user_id, posting_id)
            return {"draft_id": draft_id, "key_source": decision.key_source}
    except Exception as exc:  # noqa: BLE001 — surface the reason on the draft row
        if draft_id:
            DraftRepo(conn).mark_failed(draft_id, user_id, str(exc))
        raise


def run_enrich(container: "Container", conn: Any, job_id: str, user_id: str,
               params: dict[str, Any]) -> dict[str, Any]:
    """LLM-enrich one posting, using/filling the shared enrichment cache."""
    posting_id = params.get("posting_id")
    if not posting_id:
        raise JobError("posting_id is required")
    profile = ProfileRepo(conn).primary_for(user_id)
    if profile is None:
        raise JobError("no profile — build one first")
    pool = PostingRepo(conn).get(posting_id)
    if pool is None:
        raise JobError("posting not found in the pool")

    settings = container.settings(conn)
    router = LLMRouter(conn, settings, container.vault, environ=container.environ,
                       provider_builder=container.provider_builder)
    decision = router.resolve(user_id, "enrich")
    ph = profile_hash(profile.criteria())
    cache = EnrichmentRepo(conn)

    cached = cache.get(posting_id, ph, decision.model)
    if cached is not None:
        return {"enrichment": json.loads(cached), "cached": True,
                "key_source": decision.key_source}

    # Cache miss: this one costs a call, so it counts against the quota.
    quota = QuotaService(conn=conn, settings=settings)
    user = UserRepo(conn).get(user_id)
    unlimited = _has_byo(container, conn, user_id)
    with _reserved(quota, user, "enrich", unlimited=unlimited):
        scored = score_posting(profile.criteria(), pool.to_job_posting())
        comp = decision.provider.complete(
            build_enrich_prompt(profile.criteria(), scored),
            model=decision.model, system=ENRICH_SYSTEM)
        enrichment = _parse_enrichment(comp.text)
        cache.put(posting_id, ph, decision.model, enrichment.model_dump_json())
        router.record_usage(user_id, action="enrich", decision=decision,
                            input_tokens=comp.input_tokens,
                            output_tokens=comp.output_tokens, job_id=job_id)
        return {"enrichment": enrichment.model_dump(), "cached": False,
                "key_source": decision.key_source}


def run_scrape(container: "Container", conn: Any, job_id: str,
               params: dict[str, Any]) -> dict[str, Any]:
    """System job: fill the shared pool (scheduled or admin 'run now')."""
    from scalper.service.ingest import Ingestor

    settings = container.settings(conn)
    ing = Ingestor(conn, settings, adapter_builder=container.adapter_builder)
    return ing.run(sources=params.get("sources"), terms=params.get("terms"))


def run_purge(container: "Container", conn: Any, job_id: str,
              params: dict[str, Any]) -> dict[str, Any]:
    """System job: retention auto-purge of stale pool postings."""
    from scalper.service.ingest import Ingestor

    settings = container.settings(conn)
    return Ingestor(conn, settings).purge()


_DISPATCH: dict[str, Callable[..., dict[str, Any]]] = {
    KIND_PROFILE: run_profile,
    KIND_DRAFT: run_draft,
    KIND_ENRICH: run_enrich,
}


# --------------------------------------------------------------------------- dispatch


def execute(container: "Container", job_id: str) -> None:
    """Run a queued job to completion, recording status on the job record."""
    conn = container.connect()
    try:
        jobs = JobRepo(conn)
        rec = jobs.get(job_id)
        if rec is None:
            raise JobError(f"job {job_id} not found")
        jobs.mark_running(job_id)
        try:
            if rec.kind in _DISPATCH:
                result = _DISPATCH[rec.kind](container, conn, job_id, rec.user_id,
                                             rec.params)
            elif rec.kind == KIND_SCRAPE:
                result = run_scrape(container, conn, job_id, rec.params)
            elif rec.kind == KIND_PURGE:
                result = run_purge(container, conn, job_id, rec.params)
            else:
                raise JobError(f"unknown job kind: {rec.kind}")
            jobs.mark_succeeded(job_id, result)
        except Exception as e:  # noqa: BLE001 — persist failure for the poller
            # RQ only sees that execute() returned, so a swallowed job failure
            # otherwise shows up as "Job OK" in the worker log with no reason.
            # Log the traceback so operators can see *why* a job failed.
            _log.warning("job %s (%s) failed: %s", job_id, rec.kind, e,
                         exc_info=True)
            # A failed DB statement leaves Postgres' transaction aborted; clear it
            # so the mark_failed UPDATE can run (harmless no-op on sqlite).
            try:
                conn.rollback()
            except Exception:  # noqa: BLE001
                pass
            jobs.mark_failed(job_id, str(e))
    finally:
        conn.close()


def execute_job(job_id: str) -> None:
    """RQ entrypoint: rebuild the container from env, then execute (worker path)."""
    from scalper.service.container import Container

    execute(Container.from_env(), job_id)


class JobQueue:
    """Creates job records and runs them eagerly (no Redis) or via RQ."""

    def __init__(self, container: "Container"):
        self._c = container

    def enqueue(self, conn: Any, kind: str, *, user_id: str | None,
                params: dict[str, Any] | None = None) -> str:
        job_id = JobRepo(conn).create(kind, user_id=user_id, params=params)
        if self._c.eager_jobs:
            execute(self._c, job_id)
        else:
            self._enqueue_rq(job_id)
        return job_id

    def _enqueue_rq(self, job_id: str) -> None:  # pragma: no cover - needs Redis
        from redis import Redis
        from rq import Queue

        queue = Queue("scalper", connection=Redis.from_url(self._c.redis_url))
        queue.enqueue(execute_job, job_id, job_id=job_id)
