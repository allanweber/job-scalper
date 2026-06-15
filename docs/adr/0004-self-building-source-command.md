# 0004 — Self-building `add-source` command: tiered build behind an approval gate

- Status: Accepted
- Date: 2026-06-15

## Context

Extensibility is a core goal, and the user wants to add a new Source by pointing the tool
at it rather than hand-writing an adapter each time. The naive reading — "the LLM writes a
new Python adapter for every source and wires it in" — is both unreliable (LLM-generated
scrapers are fragile) and unsafe (it would generate and then silently execute arbitrary
code against arbitrary sites inside the collection pipeline).

Crucially, most Sources the user will add are not unique: ATS platforms (Greenhouse, Lever,
Ashby, Workable) share URL/API patterns, and many aggregators are plain JSON/RSS feeds.
These don't need generated code at all — they need configuration over a generic adapter.

## Decision

Add `scalper add-source <url> [--name X]` that builds a Source via **tiered detection**,
preferring no-code paths and gating everything behind explicit approval:

1. **Config tier** — URL matches a known ATS pattern → emit a Source Definition for the
   existing hand-written Generic Adapter. No new code.
2. **Declarative tier** — clean JSON/RSS endpoint → emit a field-mapping Source Definition
   for the generic API/RSS adapter. No new code.
3. **Codegen tier** — bespoke HTML, no API → the LLM generates a site-specific Adapter
   module from sampled pages. The only path that produces executable code.

**Approval gate (nothing joins the collection chain until the user approves):**
- All tiers: build the artifact → **dry-run against the live source** → validate output
  conforms to `JobPosting` (postings returned, required fields present, sane dates/salary)
  → show a sample of normalized postings → register only on explicit approval.
- Codegen tier additionally: show the generated adapter code and require approval
  **before it is ever executed**, since running it is the risky step.

Artifacts are written to disk (Source Definition file, or a generated `.py` adapter) so
they are inspectable, diffable, and hand-editable before approval.

Model usage is **per-task**: `add-source` defaults to a stronger reasoning model
(Sonnet/Opus-class) for mapping inference and codegen — it runs rarely, so the cost is
negligible and correctness matters most — while per-job enrichment (ADR 0003) stays on
cheap Haiku. Both are swappable via the existing `LLMProvider` config.

## Alternatives considered

- **Always LLM-generate a bespoke adapter per source.** Uniform but maximally fragile and
  unsafe; throws away the robustness of parameterized adapters for cases config handles
  perfectly. Rejected.
- **Config/declarative only, no codegen.** Safest, but bespoke HTML sites couldn't be
  auto-added at all. Rejected — codegen is kept as a gated last resort instead.
- **Auto-register on passing validation (no human approval).** Faster, but means trusting
  generated scrapers and inferred mappings blindly as they enter the pipeline. Rejected;
  the gate is the whole point.
- **Explicit `--type` hint / interactive wizard for input.** More predictable, but slower
  for the common, detectable cases. Detection-first with a fallback to asking on ambiguity
  was preferred.

## Consequences

- The dangerous path (generating and executing code) is the rare exception; common adds
  are reliable configuration, consistent with ADR 0001's source-agnostic core.
- A human gate stands between "built" and "in the chain," so a bad mapping or hostile/buggy
  generated adapter cannot silently enter collection. This adds friction to every add by
  design.
- Requires maintaining: platform-detection rules, Generic Adapters for each supported
  platform/feed shape, a Source Definition format and registry, and a validation harness.
- Generated bespoke adapters remain the most fragile Sources and the user's to maintain;
  they are stored as ordinary, hand-editable modules so they can be fixed or deleted.
- A second, stronger model tier is introduced for builds; the `LLMProvider` config must
  support per-task model selection.
