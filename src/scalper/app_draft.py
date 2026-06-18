"""Draft a cover letter + resume bullets for one posting (Phase 10).

One call per posting, grounded in the posting text, the user's Resume, and the Profile's
matched/missing skills from Stage 1 scoring (`scalper.scoring`). Output is markdown for
the user to review/edit — never sent anywhere
by the tool (see the Application Draft term in CONTEXT.md).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Callable

from scalper.prompts import APP_DRAFT_SYSTEM as _SYSTEM

if TYPE_CHECKING:
    from scalper.llm.base import Completion, LLMProvider
    from scalper.scoring import ScoredPosting

#: Logger callback: receives a single formatted log line/block (e.g. `print`).
Logger = Callable[[str], None]

#: Trim the resume/posting before prompting, to bound token cost.
_RESUME_LIMIT = 6000
_DESC_LIMIT = 3000

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    """Lowercase, hyphen-joined slug safe for use in a filename."""
    return _SLUG_RE.sub("-", text.lower()).strip("-") or "untitled"


def draft_filename(profile_name: str, position_name: str, uid: str) -> str:
    """`[profile]_[position_name]_[uid].md`, each component slugified."""
    return f"{slugify(profile_name)}_{slugify(position_name)}_{slugify(uid)}.md"


def build_prompt(profile_name: str, resume_text: str, scored: "ScoredPosting") -> str:
    p = scored.posting
    desc = p.description.strip()
    if len(desc) > _DESC_LIMIT:
        desc = desc[:_DESC_LIMIT].rsplit(" ", 1)[0] + " …"
    resume = resume_text.strip()
    if len(resume) > _RESUME_LIMIT:
        resume = resume[:_RESUME_LIMIT].rsplit(" ", 1)[0] + " …"

    matched = ", ".join(scored.matched_skills) or "(none)"
    missing = ", ".join(scored.missing_skills) or "(none)"
    return (
        f"Profile: {profile_name}\n"
        f"Job title: {p.title}\n"
        f"Company: {p.company}\n"
        f"Location: {p.location or '(not specified)'}\n"
        f"Matched skills: {matched}\n"
        f"Missing skills: {missing}\n"
        f"Posting:\n{desc}\n\n"
        f"Resume:\n{resume}"
    )


def draft_application(
    provider: "LLMProvider",
    model: str,
    profile_name: str,
    resume_text: str,
    scored: "ScoredPosting",
    *,
    logger: Logger | None = None,
) -> tuple[str, "Completion"]:
    """Call the LLM once to draft a cover letter + resume bullets for one posting.

    Every LLM call must be observable (request, response, token usage) — mirrors
    `Enricher._call` / `draft_profile`. Returns the markdown text and the
    `Completion` so the caller can tally cost/usage the same way.
    """
    log = logger or (lambda _msg: None)
    p = scored.posting
    prompt = build_prompt(profile_name, resume_text, scored)
    log(
        f"\n─── application draft (model={model}) {p.uid} — {p.title} ({p.company}) ───\n"
        f"REQUEST:\n[system]\n{_SYSTEM}\n[user]\n{prompt}"
    )
    comp = provider.complete(prompt, model=model, system=_SYSTEM, max_tokens=2048)
    log(f"RESPONSE (in={comp.input_tokens} out={comp.output_tokens} tok):\n{comp.text}")
    return comp.text.strip() + "\n", comp
