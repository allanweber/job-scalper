"""Draft a complete tailored resume + cover letter for one posting (Phase 10/13).

One call per posting, grounded in the posting text, the user's Resume, and the Profile's
matched/missing skills from Stage 1 scoring (`scalper.scoring`). The model rephrases the
user's real resume into the posting's language under a three-tier skill rule (see ADR
0006); output is markdown for the user to review/edit — never sent anywhere by the tool
(see the Application Draft term in CONTEXT.md).

The model emits three sentinel-delimited parts — `<<<RESUME>>>`, `<<<COVER_LETTER>>>`,
and an optional `<<<STRETCH_CLAIMS>>>` ledger — which `split_draft` separates into files.
Sentinels (not markdown headings) delimit the parts so the resume can freely contain its
own `#`/`##`/`###` headings without ambiguity.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from scalper.prompts import APP_DRAFT_SYSTEM as _SYSTEM

if TYPE_CHECKING:
    from scalper.llm.base import Completion, LLMProvider
    from scalper.scoring import ScoredPosting

#: Logger callback: receives a single formatted log line/block (e.g. `print`).
Logger = Callable[[str], None]

#: Trim the resume/posting before prompting, to bound token cost.
_RESUME_LIMIT = 8000
_DESC_LIMIT = 3000

#: A full resume + cover letter is far longer than the old bullet output.
_MAX_TOKENS = 4096

_SLUG_RE = re.compile(r"[^a-z0-9]+")

RESUME_MARK = "<<<RESUME>>>"
COVER_LETTER_MARK = "<<<COVER_LETTER>>>"
STRETCH_CLAIMS_MARK = "<<<STRETCH_CLAIMS>>>"


def slugify(text: str) -> str:
    """Lowercase, hyphen-joined slug safe for use in a path component."""
    return _SLUG_RE.sub("-", text.lower()).strip("-") or "untitled"


def draft_folder_name(profile_name: str, position_name: str, uid: str) -> str:
    """`[profile]_[position_name]_[uid]`, each component slugified.

    Keeps the profile in the name so the same posting drafted under two profiles
    lands in distinct folders (each profile tailors a different resume).
    """
    return f"{slugify(profile_name)}_{slugify(position_name)}_{slugify(uid)}"


@dataclass
class DraftParts:
    """The three parts of one Application Draft, split from the LLM output."""

    resume: str
    cover_letter: str
    #: Present only when the model bridged at least one adjacent (Tier-2) skill.
    stretch_claims: str | None = None


def split_draft(text: str) -> DraftParts:
    """Split sentinel-delimited LLM output into resume / cover letter / stretch claims.

    Raises `ValueError` when either required part (resume, cover letter) is missing or
    empty — the caller turns that into a per-posting failure (no partial folder written).
    """
    marks = [RESUME_MARK, COVER_LETTER_MARK, STRETCH_CLAIMS_MARK]
    # Locate each sentinel; a part runs from after its mark to the next present mark.
    positions: list[tuple[int, int, str]] = []
    for mark in marks:
        idx = text.find(mark)
        if idx != -1:
            positions.append((idx, len(mark), mark))
    positions.sort()

    found: dict[str, str] = {}
    for i, (idx, length, mark) in enumerate(positions):
        start = idx + length
        end = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        found[mark] = text[start:end].strip()

    resume = found.get(RESUME_MARK, "")
    cover_letter = found.get(COVER_LETTER_MARK, "")
    if not resume:
        raise ValueError("LLM output had no resume section")
    if not cover_letter:
        raise ValueError("LLM output had no cover-letter section")

    stretch = found.get(STRETCH_CLAIMS_MARK) or None
    return DraftParts(resume=resume, cover_letter=cover_letter, stretch_claims=stretch)


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
    """Call the LLM once to draft a tailored resume + cover letter for one posting.

    Every LLM call must be observable (request, response, token usage) — mirrors
    `Enricher._call` / `draft_profile`. Returns the raw markdown text (the caller
    splits it via `split_draft`) and the `Completion` so the caller can tally cost.
    """
    log = logger or (lambda _msg: None)
    p = scored.posting
    prompt = build_prompt(profile_name, resume_text, scored)
    log(
        f"\n─── application draft (model={model}) {p.uid} — {p.title} ({p.company}) ───\n"
        f"REQUEST:\n[system]\n{_SYSTEM}\n[user]\n{prompt}"
    )
    comp = provider.complete(prompt, model=model, system=_SYSTEM, max_tokens=_MAX_TOKENS)
    log(f"RESPONSE (in={comp.input_tokens} out={comp.output_tokens} tok):\n{comp.text}")
    return comp.text.strip() + "\n", comp
