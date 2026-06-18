"""Draft a Profile from the user's Resume via the LLM (Phase 9).

One call extracts `titles`/`required_skills`/`nice_to_have_skills`/`keywords` from
free-text resume content; the result is rendered as a ready-to-paste `profiles:`-shaped
YAML block, never written without `--write`.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Callable

import yaml
from pydantic import BaseModel, Field, field_validator

from scalper.prompts import PROFILE_DRAFT_SYSTEM as _SYSTEM

if TYPE_CHECKING:
    from scalper.llm.base import Completion, LLMProvider

#: Logger callback: receives a single formatted log line/block (e.g. `print`).
Logger = Callable[[str], None]

#: Trim the resume before prompting, to bound token cost.
_RESUME_LIMIT = 6000

#: Defensive split for composite skills the model still joins despite the prompt
#: (e.g. "python / pandas data pipelines" → "python", "pandas data pipelines").
_COMPOUND_SPLIT_RE = re.compile(r"\s*/\s*")


def _split_compound_skills(items: list[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        out.extend(part.strip() for part in _COMPOUND_SPLIT_RE.split(item) if part.strip())
    return out


class ProfileDraft(BaseModel):
    """Extracted Profile fields, ready to render as YAML or hand to `Profile`."""

    titles: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    nice_to_have_skills: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)

    @field_validator("required_skills", "nice_to_have_skills")
    @classmethod
    def _no_compound_skills(cls, value: list[str]) -> list[str]:
        return _split_compound_skills(value)


class _IndentDumper(yaml.SafeDumper):
    """Indent list items under their key, matching config.example.yaml's style."""

    def increase_indent(self, flow=False, indentless=False):  # noqa: D102
        return super().increase_indent(flow, False)


def build_prompt(resume_text: str) -> str:
    text = resume_text.strip()
    if len(text) > _RESUME_LIMIT:
        text = text[:_RESUME_LIMIT].rsplit(" ", 1)[0] + " …"
    return f"Resume:\n{text}"


def parse_draft(text: str) -> ProfileDraft:
    """Parse the model's JSON reply, tolerating stray fences/prose; fail soft."""
    text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return ProfileDraft.model_validate_json(text[start : end + 1])
        except ValueError:
            pass
    return ProfileDraft()


def draft_profile(
    provider: "LLMProvider", model: str, resume_text: str, *, logger: Logger | None = None
) -> tuple[ProfileDraft, "Completion"]:
    """Call the LLM once to extract a `ProfileDraft`; always logs the request/response.

    Every LLM call must be observable (request, response, token usage) — mirrors
    `Enricher._call`. Returns the `Completion` too, so the caller can tally
    cost/usage the same way enrichment does.
    """
    log = logger or (lambda _msg: None)
    prompt = build_prompt(resume_text)
    log(
        f"\n─── profile draft (model={model}) ───\n"
        f"REQUEST:\n[system]\n{_SYSTEM}\n[user]\n{prompt}"
    )
    comp = provider.complete(prompt, model=model, system=_SYSTEM, max_tokens=1024)
    log(f"RESPONSE (in={comp.input_tokens} out={comp.output_tokens} tok):\n{comp.text}")
    return parse_draft(comp.text), comp


#: Hard-filter defaults appended to every drafted profile. The LLM only extracts
#: titles/skills/keywords; these never come from it, so they're always appended
#: at the end of the block unless the caller already has them set (see
#: `commands/profile.py::_write_profile`, which preserves existing values on
#: a `--force` overwrite instead of resetting them to these defaults).
DEFAULT_PROFILE_SETTINGS: dict[str, object] = {
    "remote_only": True,
    "salary_floor": 0,
    "exclude_non_latin": True,
}


def profile_fields(draft: ProfileDraft) -> dict[str, object]:
    """The plain dict shape stored under a profile name in config.yaml."""
    return {
        "titles": list(draft.titles),
        "required_skills": list(draft.required_skills),
        "nice_to_have_skills": list(draft.nice_to_have_skills),
        "keywords": list(draft.keywords),
        **DEFAULT_PROFILE_SETTINGS,
    }


def to_yaml_block_from_fields(name: str, fields: dict[str, object]) -> str:
    """Render a ready-to-paste `profiles:`-shaped YAML block from a plain fields dict."""
    body = {name: fields}
    return yaml.dump(body, Dumper=_IndentDumper, sort_keys=False, default_flow_style=False)


def to_yaml_block(name: str, draft: ProfileDraft) -> str:
    """Render a ready-to-paste `profiles:`-shaped YAML block for one profile."""
    return to_yaml_block_from_fields(name, profile_fields(draft))
