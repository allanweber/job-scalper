"""Command-line interface: a thin dispatch shell over `scalper.commands`.

The CLI owns argument parsing, all printing, exit codes, and the browser launch;
the actual work lives in the front-end-agnostic command layer (`scalper.commands`),
so the same logic can later back a web/desktop/mobile app. See PLAN.md Phase 6.
"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from datetime import datetime, timedelta, timezone

from scalper import __version__
from scalper.commands import CommandError
from scalper.commands.collect import run_collect
from scalper.commands.report import run_report
from scalper.commands.sources import run_sources
from scalper.config import load_config
from scalper.report import write_report
from scalper.semantic import DEFAULT_MODEL


def _err(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)


def _out(msg: str) -> None:
    print(msg)


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
    try:
        result = run_collect(
            config, db=args.db, only_sources=args.source,
            on_info=_out, on_warning=_err,
        )
    except CommandError as e:
        _err(str(e))
        return 1
    print(f"\nCollected into {result.db}: {result.total_new} new, "
          f"{result.total_updated} updated, {result.total_stored} total stored.")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    config = load_config(args.config)

    cutoff = None
    if args.since:
        try:
            cutoff = _parse_since(args.since)
        except ValueError as e:
            _err(str(e))
            return 1

    # Stream each LLM request/response to stderr so it's visible but doesn't
    # pollute the report summary on stdout; --quiet-llm silences it.
    enrich_log = None if args.quiet_llm else (lambda msg: print(msg, file=sys.stderr))

    try:
        result = run_report(
            config, args.profile,
            db=args.db, limit=args.limit, since=cutoff, dedup=args.dedup,
            semantic=not args.no_semantic, model=args.model,
            enrich=args.enrich, top=args.top, enrich_model=args.enrich_model,
            on_info=_out, on_warning=_err, on_enrich_log=enrich_log,
        )
    except CommandError as e:
        _err(str(e))
        return 1

    out = write_report(args.out, result.html)
    enriched_note = f", {result.enriched_count} enriched" if result.enriched_count else ""
    print(f"Scored {result.total_considered} stored posting(s) → {result.matched} matched profile "
          f"'{result.profile_name}'{enriched_note}. Report: {out}")
    for s in result.scored[:10]:
        print(f"  {s.percent:3d}%  {s.posting.title}  —  {s.posting.company}")

    if args.open:
        webbrowser.open(out.resolve().as_uri())
    return 0


def cmd_sources(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    result = run_sources(config, db=args.db)

    print(f"Configured sources ({len(result.configured)}) — stored counts from {result.db}:")
    for row in result.configured:
        print(f"  {row.type:<16} {row.tier:<12} {row.stored:>6} stored")

    if result.registered_unconfigured:
        print(f"\nRegistered but not in config ({len(result.registered_unconfigured)}):")
        print("  " + ", ".join(result.registered_unconfigured))

    if result.orphaned:
        print("\nStored from sources no longer in config:")
        for row in result.orphaned:
            print(f"  {row.type:<16} {'':<12} {row.stored:>6} stored")

    print(f"\n{result.total_stored} posting(s) stored across {result.source_count} source(s).")
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
