"""Command-line interface: `collect` (slow, populates store) and `report` (instant)."""

from __future__ import annotations

import argparse
import sys
import webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scalper import __version__
from scalper.config import load_config
from scalper.enrich import build_enricher, format_usage
from scalper.report import render_report, write_report
from scalper.scoring import dedup_scored, score_all
from scalper.semantic import DEFAULT_MODEL, build_semantic_scorer, sentence_transformers_available
from scalper.sources import REGISTRY, build_adapter
from scalper.sources.base import TIER_STRUCTURED
from scalper.store import JobStore


def _err(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _parse_since(value: str) -> datetime:
    """Interpret `--since` as either a day count or an ISO date → aware cutoff."""
    try:
        return datetime.now(timezone.utc) - timedelta(days=int(value))
    except ValueError:
        pass
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError(
            f"--since must be a number of days or an ISO date (YYYY-MM-DD), got {value!r}"
        ) from None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def cmd_collect(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    db = args.db or config.database
    query = config.search
    total_new = total_updated = 0
    if query.terms:
        print(f"Searching for: {', '.join(query.terms)}")
    sources = config.sources
    if not sources:
        _err("no sources configured. Add some under `sources:` in your config.")
        return 1
    if args.source:
        wanted = {s.lower() for s in args.source}
        sources = [sc for sc in sources if sc.type.lower() in wanted]
        missing = wanted - {sc.type.lower() for sc in config.sources}
        for name in sorted(missing):
            _err(f"source {name!r} not found in config; skipping.")
        if not sources:
            _err("no matching sources to collect from.")
            return 1
        print(f"Collecting from: {', '.join(sc.type for sc in sources)}")

    with JobStore(db) as store:
        for sc in sources:
            try:
                adapter = build_adapter(sc.type, sc.params)
            except (KeyError, ValueError, TypeError) as e:
                _err(f"skipping source {sc.type} {sc.params}: {e}")
                continue
            # Apply a per-source cap if configured (keeps high-volume sources
            # like hackernews from dominating the store).
            src_query = query
            if sc.limit is not None:
                src_query = query.model_copy(update={"limit_per_source": sc.limit})
            try:
                postings = adapter.fetch(src_query)
            except Exception as e:  # noqa: BLE001 — one bad source must not abort the run
                _err(f"{adapter.name}: fetch failed: {e}")
                continue
            new, updated = store.upsert_many(postings)
            total_new += new
            total_updated += updated
            print(f"  {adapter.name}: {len(postings)} fetched ({new} new, {updated} updated)")
        print(f"\nCollected into {db}: {total_new} new, {total_updated} updated, "
              f"{store.count()} total stored.")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    db = args.db or config.database
    try:
        profile = config.profile(args.profile)
    except KeyError as e:
        _err(str(e))
        return 1

    if not Path(db).exists():
        _err(f"no store at {db}. Run `scalper collect` first.")
        return 1

    if args.since:
        try:
            cutoff = _parse_since(args.since)
        except ValueError as e:
            _err(str(e))
            return 1

    with JobStore(db) as store:
        postings = list(store.iter_postings())

        if args.since:
            # Keep postings with no known date (consistent with the freshness
            # filter); drop those published before the cutoff.
            postings = [
                p for p in postings
                if p.published_at is None or _aware(p.published_at) >= cutoff
            ]

        scorer = build_semantic_scorer(
            store, model_name=args.model, enabled=not args.no_semantic
        )
        if scorer is not None:
            try:
                scorer.prepare(postings)
            except Exception as e:  # noqa: BLE001 — semantic is optional; never abort report
                _err(f"semantic scoring unavailable ({e}); using deterministic scores.")
                scorer = None
        elif not args.no_semantic and not sentence_transformers_available():
            print("note: semantic scoring off — install it with: pip install -e '.[semantic]'")

        scored = score_all(profile, postings, semantic_scorer=scorer)
        if args.dedup:
            before = len(scored)
            scored = dedup_scored(scored)
            collapsed = before - len(scored)
            if collapsed:
                print(f"Deduped {collapsed} cross-source duplicate(s).")

        enrichments = {}
        if args.enrich or config.llm.enabled:
            top_n = args.top if args.top is not None else config.llm.top_n
            # Stream each request/response to stderr so it's visible but doesn't
            # pollute the report summary on stdout; --quiet-llm silences it.
            log = None if args.quiet_llm else (lambda msg: print(msg, file=sys.stderr))
            enricher = build_enricher(
                config.llm, store,
                model=args.enrich_model or config.llm.enrich_model,
                logger=log,
            )
            if enricher is None:
                print("note: enrichment off — install it with: pip install -e '.[llm]' "
                      "and set ANTHROPIC_API_KEY")
            else:
                try:
                    enrichments = enricher.enrich(profile, scored, top_n)
                    print(format_usage(enricher.usage, config.llm))
                except Exception as e:  # noqa: BLE001 — enrichment is optional; never abort report
                    _err(f"enrichment failed ({e}); rendering deterministic report.")

    if args.limit:
        scored = scored[: args.limit]

    html = render_report(args.profile, profile, scored, enrichments)
    out = write_report(args.out, html)
    enriched_note = f", {len(enrichments)} enriched" if enrichments else ""
    print(f"Scored {len(postings)} stored posting(s) → {len(scored)} matched profile "
          f"'{args.profile}'{enriched_note}. Report: {out}")
    for s in scored[:10]:
        print(f"  {s.percent:3d}%  {s.posting.title}  —  {s.posting.company}")

    if args.open:
        webbrowser.open(out.resolve().as_uri())
    return 0


def cmd_sources(args: argparse.Namespace) -> int:
    """List registered adapters and configured sources with stored counts."""
    config = load_config(args.config)
    db = args.db or config.database

    counts: dict[str, int] = {}
    if Path(db).exists():
        with JobStore(db) as store:
            counts = store.counts_by_source()

    configured = [sc.type for sc in config.sources]
    print(f"Configured sources ({len(configured)}) — stored counts from {db}:")
    for stype in configured:
        cls = REGISTRY.get(stype)
        tier = getattr(cls, "tier", TIER_STRUCTURED) if cls else "unregistered"
        print(f"  {stype:<16} {tier:<12} {counts.get(stype, 0):>6} stored")

    extra = sorted(set(REGISTRY) - set(configured))
    if extra:
        print(f"\nRegistered but not in config ({len(extra)}):")
        print("  " + ", ".join(extra))

    orphan = sorted(set(counts) - set(configured))
    if orphan:
        print("\nStored from sources no longer in config:")
        for stype in orphan:
            print(f"  {stype:<16} {'':<12} {counts[stype]:>6} stored")

    total = sum(counts.values())
    print(f"\n{total} posting(s) stored across {len(counts)} source(s).")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="scalper", description="Personal job scalper.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-c", "--config", default="config.yaml", help="path to config (default: config.yaml)")
    parser.add_argument("--db", default=None, help="override database path from config")
    sub = parser.add_subparsers(dest="command", required=True)

    p_collect = sub.add_parser("collect", help="fetch from all sources into the local store")
    p_collect.add_argument("-s", "--source", nargs="+", metavar="TYPE",
                           help="collect only these source type(s), e.g. -s indeed linkedin "
                                "(default: every source in config)")
    p_collect.set_defaults(func=cmd_collect)

    p_report = sub.add_parser("report", help="score stored postings against a profile, emit HTML")
    p_report.add_argument("-p", "--profile", required=True, help="profile name from config")
    p_report.add_argument("-o", "--out", default="report.html", help="output HTML path")
    p_report.add_argument("--limit", type=int, default=None, help="cap number of results")
    p_report.add_argument("--since", default=None, metavar="DAYS|DATE",
                          help="only score postings published within the last N days, or on/after "
                               "an ISO date (YYYY-MM-DD); postings with no known date are kept")
    p_report.add_argument("--dedup", action="store_true",
                          help="collapse the same job seen on multiple sources into one row "
                               "(keeps the best-scoring, lists the others as 'also seen on')")
    p_report.add_argument("--no-semantic", action="store_true",
                          help="skip the local semantic-similarity component")
    p_report.add_argument("--model", default=DEFAULT_MODEL,
                          help=f"sentence-transformers model for semantic scoring (default: {DEFAULT_MODEL})")
    p_report.add_argument("--enrich", action="store_true",
                          help="add Stage 2 LLM summaries to the top-scored postings (needs '.[llm]')")
    p_report.add_argument("--top", type=int, default=None,
                          help="how many top postings to enrich (default: llm.top_n from config)")
    p_report.add_argument("--enrich-model", default=None,
                          help="override the LLM model used for enrichment")
    p_report.add_argument("--quiet-llm", action="store_true",
                          help="suppress per-request/response LLM logs (keep the usage summary)")
    p_report.add_argument("--open", action="store_true", help="open the report in a browser")
    p_report.set_defaults(func=cmd_report)

    p_sources = sub.add_parser("sources", help="list registered adapters and configured sources + counts")
    p_sources.set_defaults(func=cmd_sources)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except FileNotFoundError as e:
        _err(str(e))
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
