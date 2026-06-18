"""`draft` command core: Application Drafts (cover letter + resume bullets) for one or
more postings (Phase 10).

Follows the purity contract (no argparse/print/exit): failures raise `CommandError`
subclasses instead of printing a hint directly, so the CLI can render them uniformly.
Each posting's draft is always written to its own file (never just printed), named
`[profile]_[position_name]_[uid].md` under the resolved output folder — `out_dir` arg,
else `config.draft_output_dir`, else `drafts/` under `config.output_dir`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from scalper.app_draft import draft_application, draft_filename
from scalper.commands import CommandError
from scalper.config import Config
from scalper.enrich import Usage, format_usage
from scalper.llm import build_provider
from scalper.resume import load_resume
from scalper.scoring import score_posting
from scalper.store import JobStore


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


def _noop(_msg: str) -> None:
    pass


@dataclass
class DraftedApplication:
    uid: str
    title: str
    company: str
    markdown: str
    written_to: Path


@dataclass
class DraftResult:
    profile_name: str
    drafts: list[DraftedApplication] = field(default_factory=list)


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
    db: str | None = None,
    out_dir: str | Path | None = None,
    model: str | None = None,
    on_info: Callable[[str], None] = _noop,
    on_llm_log: Callable[[str], None] | None = None,
) -> DraftResult:
    """Draft an Application Draft for each posting `uid`, scored against `profile_name`.

    Every uid must already be in the store (run `collect` first); an unknown uid raises
    `PostingNotFoundError` listing all of them before any LLM call is made. Each draft is
    saved to its own file under the resolved output folder (`out_dir`, else
    `config.draft_output_dir`, else `drafts/` under `config.output_dir`) as
    `[profile]_[position_name]_[uid].md`, combining the cover letter and resume bullets
    in one file. Raises a `CommandError` subclass instead of exiting when the resume
    file, profile, store, or LLM provider is unavailable.

    Every LLM call is logged: the request/response stream through `on_llm_log` (`None`
    to silence it) and a token/cost summary is always emitted through `on_info`, the
    same observability contract as `report --enrich` and `profile from-resume`.
    """
    db = config.database_path(db)
    try:
        profile = config.profile(profile_name)
    except KeyError as e:
        raise ProfileNotFoundError(str(e)) from None

    if not Path(db).exists():
        raise StoreNotFoundError(f"no store at {db}. Run `scalper collect` first.")

    resume_text = _load_resume_text(resume)

    provider = build_provider(config.llm.provider)
    if provider is None:
        raise LLMUnavailableError(
            "LLM unavailable — install it with: pip install -e '.[llm]' and set "
            "ANTHROPIC_API_KEY"
        )

    with JobStore(db) as store:
        found = store.get_postings_by_uid(uids)

    missing = [u for u in uids if u not in found]
    if missing:
        raise PostingNotFoundError(f"posting uid(s) not found in the store: {', '.join(missing)}")

    used_model = model or config.llm.draft_model
    usage = Usage(model=used_model)
    target_dir = config.draft_dir(out_dir)

    drafts: list[DraftedApplication] = []
    for uid in uids:
        posting = found[uid]
        scored = score_posting(profile, posting)
        markdown, comp = draft_application(
            provider, used_model, profile_name, resume_text, scored, logger=on_llm_log
        )
        usage.add(comp)

        header = f"# {posting.title} — {posting.company}\n[View posting]({posting.url})\n\n"
        markdown = header + markdown

        path = target_dir / draft_filename(profile_name, posting.title, uid)
        path.write_text(markdown)
        drafts.append(
            DraftedApplication(
                uid=uid, title=posting.title, company=posting.company,
                markdown=markdown, written_to=path,
            )
        )

    on_info(format_usage(usage, config.llm, label="LLM application-draft usage"))
    return DraftResult(profile_name=profile_name, drafts=drafts)
