# 0003 — Scoring funnel: deterministic match %, LLM enrichment on the shortlist only

- Status: Accepted
- Date: 2026-06-15

## Context

The user wants a Match % against their criteria, a skill-gap view, and a readable summary
per job. The naive approach — call an LLM on every posting to score and summarize it — is
the dominant cost and latency driver: a single collect run can surface thousands of
postings, and most will never be looked at. The user explicitly prioritizes
cost-effectiveness, reporting speed, and *confidence* in the match number.

Two coupled questions: (1) how many postings the LLM touches, and (2) whether the headline
Match % is computed deterministically or judged by the LLM.

## Decision

Use a two-stage **funnel** and keep the headline number deterministic:

- **Stage 1 — all postings, no LLM.** Hard filters (remote, freshness window) gate first.
  Surviving postings get a deterministic Match % = weighted blend of **skill coverage**
  (% of required skills found), **title/role match**, and **semantic similarity** (cosine
  over local sentence-transformers embeddings). The blend weights are configurable per
  Profile, and the report shows the breakdown.
- **Stage 2 — shortlist only.** Only postings above a threshold are sent to an LLM (Haiku
  by default, behind a swappable `LLMProvider` interface), which produces the summary and
  skill-gap narrative — and may raise a low-confidence flag — but does **not** set the
  headline %.

## Alternatives considered

- **LLM scores and summarizes everything.** Simplest mental model, but cost grows linearly
  with collection volume, reports are slow, and the % varies run-to-run. Rejected.
- **LLM judges the %.** More holistic, but a black box, non-reproducible, and a reasoning
  call per shortlisted job. Rejected for the headline; the LLM may still surface qualitative
  confidence signals.
- **No LLM at all.** Cheapest and fully offline, but no polished summaries or skill-gap
  reasoning. Rejected — but the deterministic Stage 1 is designed to stand alone, so this
  remains a viable degraded mode.

## Consequences

- LLM spend is bounded by shortlist size, not collection volume; reports stay fast.
- The Match % is reproducible and auditable (visible breakdown), satisfying the confidence
  requirement; the LLM adds nuance without destabilizing the number.
- Two notions of "match" coexist (deterministic score vs. LLM narrative); the report must
  present them so the distinction is clear and divergence is legible.
- Requires a local embedding model dependency (~100–400MB) and a threshold to tune; too
  high a threshold starves Stage 2, too low inflates LLM cost.
