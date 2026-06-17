"""Stage 2 LLM enrichment: structured insight on the shortlist only (ADR 0003).

Stage 1 scores *every* posting deterministically. Stage 2 spends an LLM call only on
the top-N already-scored postings to extract four things the text match can't reliably
read: remote status, seniority level, salary range, and timezone constraints.

Results are cached in the store keyed by posting `uid` + a hash of the profile criteria
+ the model + schema version, so re-reports are free until something changes. The whole
layer is optional and fail-soft: with no provider `build_enricher` returns ``None`` and
the report renders Stage 1 only.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from pydantic import BaseModel, field_validator

from scalper.config import LLMConfig, Profile
from scalper.llm import build_provider
from scalper.scoring import ScoredPosting

if TYPE_CHECKING:
    from scalper.llm.base import Completion, LLMProvider
    from scalper.store import JobStore

#: Logger callback: receives a single formatted log line/block (e.g. `print`).
Logger = Callable[[str], None]

#: Estimated Anthropic list prices, USD per 1M tokens (input, output). Used only
#: for the cost summary; override per-run via `llm.input/output_price_per_mtok`.
#: Longest-prefix match wins, so specific ids beat family prefixes.
_PRICING: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-3-5-haiku": (0.80, 4.0),
    "claude-sonnet-4": (3.0, 15.0),
    "claude-opus-4": (15.0, 75.0),
}


def _lookup_price(model: str) -> tuple[float, float] | None:
    matches = [(k, v) for k, v in _PRICING.items() if model.startswith(k)]
    if not matches:
        return None
    return max(matches, key=lambda kv: len(kv[0]))[1]

#: Trim posting descriptions before prompting, to bound token cost.
_DESC_LIMIT = 2000

#: Increment when the JSON schema changes so old cache entries are naturally invalidated.
_SCHEMA_VERSION = 2

_SYSTEM = """\
You are a concise hiring assistant. Read the single job posting and extract the \
following fields. Reply with STRICT JSON only — no prose, no code fences:
{
  "remote": true | false | null,
  "seniority": "junior" | "mid" | "senior" | "staff" | "principal" | null,
  "salary_range": {"min": integer | null, "max": integer | null, "currency": string | null} | null,
  "timezone_requirement": string | null
}
Rules:
- remote: true only if the role explicitly allows fully remote work; null if unclear
- seniority: infer from title + description; null if not determinable
- salary_range: extract numbers from text (e.g. "$120k–150k" → min:120000, max:150000, currency:"USD"); null if not mentioned
- timezone_requirement: quote any timezone constraint or "async-friendly" language; null if none mentioned\
"""


class SalaryRange(BaseModel):
    min: int | None = None
    max: int | None = None
    currency: str | None = None


class Enrichment(BaseModel):
    """LLM-extracted insight for one posting (Stage 2)."""

    remote: bool | None = None
    seniority: str | None = None
    salary_range: SalaryRange | None = None
    timezone_requirement: str | None = None

    @field_validator("remote", mode="before")
    @classmethod
    def _strict_bool(cls, v: object) -> bool | None:
        return v if isinstance(v, bool) or v is None else None


def profile_hash(profile: Profile) -> str:
    """Stable hash of the criteria fields that shape the prompt.

    Only the prompt-relevant fields are hashed, so tweaking weights or filters does
    not needlessly invalidate cached enrichments.
    """
    basis = json.dumps(
        {
            "titles": profile.titles,
            "required_skills": profile.required_skills,
            "nice_to_have_skills": profile.nice_to_have_skills,
            "keywords": profile.keywords,
        },
        sort_keys=True,
    )
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


def build_prompt(profile: Profile, scored: ScoredPosting) -> str:
    p = scored.posting
    desc = p.description.strip()
    if len(desc) > _DESC_LIMIT:
        desc = desc[:_DESC_LIMIT].rsplit(" ", 1)[0] + " …"
    return (
        f"Job title: {p.title}\n"
        f"Company: {p.company}\n"
        f"Location: {p.location or '(not specified)'}\n"
        f"Posting:\n{desc}"
    )


def _parse(text: str) -> Enrichment:
    """Parse the model's JSON reply, tolerating stray fences/prose; fail soft."""
    text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return Enrichment.model_validate(json.loads(text[start : end + 1]))
        except Exception:
            pass
    return Enrichment()


@dataclass
class Usage:
    """Running token/cost tally across one enrichment run."""

    model: str = ""
    calls: int = 0  # postings that hit the LLM
    cached: int = 0  # postings served from the store cache (free)
    input_tokens: int = 0
    output_tokens: int = 0

    def add(self, comp: "Completion") -> None:
        self.calls += 1
        self.input_tokens += comp.input_tokens
        self.output_tokens += comp.output_tokens

    def cost(
        self, input_price: float | None = None, output_price: float | None = None
    ) -> tuple[float, float] | None:
        """Return (input_cost, output_cost) in USD, or ``None`` if price unknown."""
        if input_price is None or output_price is None:
            looked = _lookup_price(self.model)
            if looked is None:
                return None
            input_price = input_price if input_price is not None else looked[0]
            output_price = output_price if output_price is not None else looked[1]
        return (
            self.input_tokens / 1_000_000 * input_price,
            self.output_tokens / 1_000_000 * output_price,
        )


def format_usage(usage: Usage, config: LLMConfig | None = None, *, label: str = "LLM enrichment usage") -> str:
    """Human-readable token + cost summary for an LLM run (enrichment, profile draft, …)."""
    ip = config.input_price_per_mtok if config else None
    op = config.output_price_per_mtok if config else None
    lines = [
        f"{label} ({usage.model}):",
        f"  calls:          {usage.calls}  ({usage.cached} served from cache)",
        f"  input tokens:   {usage.input_tokens:,}",
        f"  output tokens:  {usage.output_tokens:,}",
    ]
    cost = usage.cost(ip, op)
    if cost is None:
        lines.append("  est. cost:      n/a (no pricing for this model; "
                     "set llm.input/output_price_per_mtok)")
    else:
        in_c, out_c = cost
        lines.append(
            f"  est. cost:      ${in_c + out_c:.4f}  (input ${in_c:.4f} + output ${out_c:.4f})"
        )
    return "\n".join(lines)


class Enricher:
    """Enrich the top-N scored postings, reading/writing the store cache."""

    def __init__(
        self,
        provider: "LLMProvider",
        model: str,
        store: "JobStore | None" = None,
        logger: Logger | None = None,
    ):
        self.provider = provider
        self.model = model
        self._store = store
        self._log = logger or (lambda _msg: None)
        self._cache_model = f"{model}/v{_SCHEMA_VERSION}"
        self.usage = Usage(model=model)

    def enrich(
        self, profile: Profile, scored: list[ScoredPosting], top_n: int
    ) -> dict[str, Enrichment]:
        """Return `{uid: Enrichment}` for the top `top_n` postings (cache-first)."""
        shortlist = scored[: max(0, top_n)]
        if not shortlist:
            return {}

        ph = profile_hash(profile)
        uids = [s.posting.uid for s in shortlist]
        out: dict[str, Enrichment] = {}

        if self._store is not None:
            for uid, data in self._store.get_enrichments(uids, ph, self._cache_model).items():
                try:
                    out[uid] = Enrichment.model_validate_json(data)
                except Exception:
                    pass  # corrupt cache entry → recompute below

        fresh: list[tuple[str, str]] = []
        n = len(shortlist)
        for i, s in enumerate(shortlist, 1):
            uid = s.posting.uid
            if uid in out:
                self.usage.cached += 1
                self._log(f"[{i}/{n}] cache hit: {uid} — {s.posting.title} "
                          f"({s.posting.company})")
                continue
            enr = self._call(profile, s, i, n)
            out[uid] = enr
            fresh.append((uid, enr.model_dump_json()))

        if self._store is not None and fresh:
            self._store.put_enrichments(ph, self._cache_model, fresh)
        return out

    def _call(
        self, profile: Profile, scored: ScoredPosting, i: int = 1, n: int = 1
    ) -> Enrichment:
        prompt = build_prompt(profile, scored)
        p = scored.posting
        self._log(
            f"\n─── enrich [{i}/{n}] {p.uid} — {p.title} ({p.company}) ───\n"
            f"REQUEST (model={self.model}):\n"
            f"[system]\n{_SYSTEM}\n[user]\n{prompt}"
        )
        comp = self.provider.complete(prompt, model=self.model, system=_SYSTEM)
        self.usage.add(comp)
        self._log(
            f"RESPONSE (in={comp.input_tokens} out={comp.output_tokens} tok):\n{comp.text}"
        )
        return _parse(comp.text)


def build_enricher(
    config: LLMConfig,
    store: "JobStore | None" = None,
    *,
    model: str | None = None,
    enabled: bool = True,
    logger: Logger | None = None,
) -> Enricher | None:
    """Return an `Enricher`, or ``None`` if disabled or no provider is available."""
    if not enabled:
        return None
    provider = build_provider(config.provider)
    if provider is None:
        return None
    return Enricher(provider, model or config.enrich_model, store=store, logger=logger)
