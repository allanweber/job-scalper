"""`draft` command core: Application Drafts (tailored resume + cover letter) for one or
more postings (Phase 10/13).

Follows the purity contract (no argparse/print/exit): failures raise `CommandError`
subclasses instead of printing a hint directly, so the CLI can render them uniformly.
Each posting gets its own folder `[profile]_[position_name]_[uid]/` under the resolved
output folder (`out_dir`, else `config.draft_output_dir`, else `drafts/` under
`config.output_dir`), holding `resume.md`, `cover_letter.md`, an optional
`stretch_claims.md`, and — when the `[pdf]` extra is installed — `resume.pdf` /
`cover_letter.pdf`. PDF rendering is best-effort: missing it never blocks the markdown.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import httpx

from scalper.app_draft import draft_application, draft_folder_name, split_draft
from scalper.commands import CommandError
from scalper.config import Config
from scalper.enrich import Usage, format_usage
from scalper.llm import build_provider
from scalper.pdf import (
    COVER_LETTER_MD,
    RESUME_MD,
    install_hint,
    pdf_available,
    render_draft_folder,
)
from scalper.models import JobPosting
from scalper.resume import load_resume
from scalper.scoring import score_posting
from scalper.store import JobStore
from scalper.url_fetch import fetch_posting

_STRETCH_CLAIMS_MD = "stretch_claims.md"


class ResumeNotFoundError(CommandError):
    """The given resume file does not exist."""


class LLMUnavailableError(CommandError):
    """No LLM provider available (missing `[llm]` extra or API key)."""


class ProfileNotFoundError(CommandError):
    """The requested profile is not defined in the config."""


class StoreNotFoundError(CommandError):
    """No store exists yet — `collect` has not been run."""


class PostingNotFoundError(CommandError):
    """One or more requested uids aren't in the store."""


class UrlFetchError(CommandError):
    """A URL could not be fetched or parsed into a posting."""


def _noop(_msg: str) -> None:
    pass


@dataclass
class DraftedApplication:
    uid: str
    title: str
    company: str
    folder: Path
    #: Markdown files written (resume, cover letter, and stretch claims when present).
    md_files: list[Path]
    #: PDF files rendered (empty when the `[pdf]` extra is unavailable or rendering failed).
    pdf_files: list[Path]
    has_stretch_claims: bool


@dataclass
class DraftResult:
    profile_name: str
    drafts: list[DraftedApplication] = field(default_factory=list)
    #: Postings whose draft couldn't be produced (uid, reason); fail-soft, never partial.
    failures: list[tuple[str, str]] = field(default_factory=list)


def _load_resume_text(resume: str | Path) -> str:
    try:
        return load_resume(resume)
    except FileNotFoundError as e:
        raise ResumeNotFoundError(str(e)) from None


def run_draft(
    config: Config,
    profile_name: str,
    uids: list[str],
    resume: str | Path,
    *,
    urls: list[str] | None = None,
    db: str | None = None,
    out_dir: str | Path | None = None,
    model: str | None = None,
    on_info: Callable[[str], None] = _noop,
    on_warning: Callable[[str], None] = _noop,
    on_llm_log: Callable[[str], None] | None = None,
) -> DraftResult:
    """Draft an Application Draft for each posting uid or URL, scored against `profile_name`.

    `uids` are looked up in the store; `urls` are fetched and parsed into ephemeral
    postings (never stored). Exactly one of the two must be non-empty. An unknown uid
    raises `PostingNotFoundError`; a URL that fails to fetch raises `UrlFetchError` —
    both are raised before any LLM call is made. Each posting's folder is written only
    when both the resume and cover letter parsed — a malformed LLM reply is a per-posting
    failure (recorded in `DraftResult.failures`, never a partial folder). PDFs are
    rendered when the `[pdf]` extra is present; otherwise the markdown is still written
    and a one-time install hint is emitted via `on_warning`.

    Every LLM call is logged: the request/response stream through `on_llm_log` (`None`
    to silence it) and a token/cost summary is always emitted through `on_info`, the
    same observability contract as `report --enrich` and `profile from-resume`.
    """
    db = config.database_path(db)
    try:
        profile = config.profile(profile_name)
    except KeyError as e:
        raise ProfileNotFoundError(str(e)) from None

    resume_text = _load_resume_text(resume)

    provider = build_provider(config.llm.provider, api_key=config.llm.api_key)
    if provider is None:
        raise LLMUnavailableError(
            "LLM unavailable — install it with: pip install -e '.[llm]' and set "
            "llm.api_key in config (or ANTHROPIC_API_KEY)"
        )

    postings: dict[str, JobPosting] = {}
    url_postings: list[JobPosting] = []

    if uids:
        if not Path(db).exists():
            raise StoreNotFoundError(f"no store at {db}. Run `scalper collect` first.")
        with JobStore(db) as store:
            found = store.get_postings_by_uid(uids)
        missing = [u for u in uids if u not in found]
        if missing:
            raise PostingNotFoundError(f"posting uid(s) not found in the store: {', '.join(missing)}")
        postings.update(found)

    for url in (urls or []):
        on_info(f"fetching {url} …")
        try:
            p = fetch_posting(url)
        except (httpx.HTTPError, httpx.InvalidURL, Exception) as e:
            raise UrlFetchError(f"could not fetch {url}: {e}") from None
        postings[p.uid] = p
        url_postings.append(p)

    used_model = model or config.llm.draft_model
    usage = Usage(model=used_model)
    target_dir = config.draft_dir(out_dir)

    can_pdf = pdf_available()
    if not can_pdf:
        on_warning(f"PDFs skipped — {install_hint()}")

    drafts: list[DraftedApplication] = []
    failures: list[tuple[str, str]] = []
    for uid, posting in postings.items():
        scored = score_posting(profile, posting)
        raw, comp = draft_application(
            provider, used_model, profile_name, resume_text, scored, logger=on_llm_log
        )
        usage.add(comp)

        try:
            parts = split_draft(raw)
        except ValueError as e:
            failures.append((uid, str(e)))
            on_warning(f"{uid}: draft skipped — {e}")
            continue

        folder = target_dir / draft_folder_name(profile_name, posting.title, uid)
        folder.mkdir(parents=True, exist_ok=True)

        _write(folder / "apply.md", f"# Apply\n\n{posting.url}\n")
        md_files = [
            _write(folder / RESUME_MD, parts.resume),
            _write(folder / COVER_LETTER_MD, parts.cover_letter),
        ]
        if parts.stretch_claims:
            md_files.append(_write(folder / _STRETCH_CLAIMS_MD, parts.stretch_claims))

        pdf_files: list[Path] = []
        if can_pdf:
            try:
                pdf_files = render_draft_folder(folder)
            except Exception as e:  # noqa: BLE001 — rendering must never lose the markdown
                on_warning(f"{uid}: PDF rendering failed ({e}); markdown kept")

        drafts.append(
            DraftedApplication(
                uid=uid, title=posting.title, company=posting.company,
                folder=folder, md_files=md_files, pdf_files=pdf_files,
                has_stretch_claims=parts.stretch_claims is not None,
            )
        )

    # Persist URL postings and mark all successful drafts in the store.
    if drafts:
        drafted_uids = [d.uid for d in drafts]
        with JobStore(db) as store:
            if url_postings:
                store.upsert_many([p for p in url_postings if p.uid in set(drafted_uids)])
            store.mark_drafted(drafted_uids)

    on_info(format_usage(usage, config.llm, label="LLM application-draft usage"))
    return DraftResult(profile_name=profile_name, drafts=drafts, failures=failures)


def _write(path: Path, text: str) -> Path:
    path.write_text(text if text.endswith("\n") else text + "\n")
    return path
