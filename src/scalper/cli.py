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
from scalper.commands.digest import run_digest
from scalper.commands.draft import run_draft
from scalper.commands.insights import run_insights
from scalper.commands.profile import run_from_resume
from scalper.commands.render import run_render
from scalper.commands.report import run_report, run_report_all
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
    source_log = (lambda msg: print(msg, file=sys.stderr)) if args.verbose_sources else None
    try:
        result = run_collect(
            config, db=args.db, only_sources=args.source,
            on_info=_out, on_warning=_err, on_source_log=source_log,
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
    common = dict(
        db=args.db, limit=args.limit, since=cutoff, dedup=not args.no_dedup,
        all_jobs=args.all_jobs,
        semantic=not args.no_semantic, model=args.model,
        enrich=args.enrich, top=args.top, enrich_model=args.enrich_model,
        on_info=_out, on_warning=_err, on_enrich_log=enrich_log,
    )

    if args.all_profiles:
        try:
            multi = run_report_all(config, list(config.profiles), **common)
        except CommandError as e:
            _err(str(e))
            return 1
        out = write_report(args.out, multi.html)
        enriched_note = f", {multi.enriched_count} enriched" if multi.enriched_count else ""
        print(f"Scored {multi.total_considered} stored posting(s) across "
              f"{len(multi.profiles)} profile(s){enriched_note}. Report: {out}")
        width = max((len(p.profile_name) for p in multi.profiles), default=0)
        for p in multi.profiles:
            note = f", {p.enriched_count} enriched" if p.enriched_count else ""
            print(f"  {p.profile_name:<{width}}  {p.matched:>4} matched{note}")
        if args.open:
            webbrowser.open(out.resolve().as_uri())
        return 0

    try:
        result = run_report(config, args.profile, **common)
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


def cmd_digest(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    profile_names = list(config.profiles) if args.all_profiles else [args.profile]
    source_log = (lambda msg: print(msg, file=sys.stderr)) if args.verbose_sources else None
    try:
        result = run_digest(
            config, profile_names, db=args.db, only_sources=args.source,
            semantic=not args.no_semantic, model=args.model,
            on_info=_out, on_warning=_err, on_source_log=source_log,
        )
    except CommandError as e:
        _err(str(e))
        return 1

    out = write_report(args.out, result.html)
    when = result.run_start.strftime("%Y-%m-%d %H:%M UTC")
    width = max((len(p.profile_name) for p in result.profiles), default=0)
    summary = " · ".join(f"{p.profile_name} {p.new} new" for p in result.profiles)
    print(f"{result.total_new} new since {when}{' · ' + summary if summary else ''}. Digest: {out}")
    for p in result.profiles:
        print(f"  {p.profile_name:<{width}}  {p.new:>4} new")

    if args.open:
        webbrowser.open(out.resolve().as_uri())
    return 0


def cmd_profile_from_resume(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    llm_log = None if args.quiet_llm else (lambda msg: print(msg, file=sys.stderr))
    try:
        result = run_from_resume(
            config, args.name, args.resume, config_path=args.config,
            write=args.write, force=args.force, model=args.model,
            on_info=_err, on_llm_log=llm_log,
        )
    except CommandError as e:
        _err(str(e))
        return 1
    print(result.yaml_block, end="")
    if result.written_to:
        print(f"\nWrote profile '{result.name}' to {result.written_to}.")
    return 0


def cmd_draft(args: argparse.Namespace) -> int:
    uids = args.uid or []
    urls = args.url or []
    if not uids and not urls:
        _err("draft: provide at least one uid or --url")
        return 1
    if uids and urls:
        _err("draft: --url and positional uids are mutually exclusive")
        return 1
    config = load_config(args.config)
    llm_log = None if args.quiet_llm else (lambda msg: print(msg, file=sys.stderr))
    try:
        result = run_draft(
            config, args.profile, uids, args.resume,
            urls=urls or None,
            db=args.db, out_dir=args.out, model=args.model,
            on_info=_err, on_warning=_err, on_llm_log=llm_log,
        )
    except CommandError as e:
        _err(str(e))
        return 1
    for d in result.drafts:
        kinds = [p.name for p in d.md_files] + [p.name for p in d.pdf_files]
        print(f"{d.uid}  {d.title} — {d.company}  →  {d.folder}")
        print(f"    {', '.join(kinds)}")
    for uid, reason in result.failures:
        print(f"{uid}  (skipped: {reason})")
    return 0 if result.drafts else 1


def cmd_render(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    try:
        result = run_render(config, args.path, on_warning=_err)
    except CommandError as e:
        _err(str(e))
        return 1
    for p in result.rendered:
        print(f"rendered  {p}")
    return 0 if result.rendered else 1


def cmd_insights(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    extra_skills = [s.strip() for s in args.skills.split(",")] if args.skills else None

    cutoff = None
    if args.since:
        try:
            cutoff = _parse_since(args.since)
        except ValueError as e:
            _err(str(e))
            return 1

    try:
        result = run_insights(config, since=cutoff, extra_skills=extra_skills, db=args.db)
    except CommandError as e:
        _err(str(e))
        return 1

    print(result.text)
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
    p_collect.add_argument("--verbose-sources", action="store_true",
                           help="log every HTTP request/response made by source adapters to stderr "
                                "(overrides verbose_sources in config)")
    p_collect.set_defaults(func=cmd_collect)

    p_report = sub.add_parser("report", help="score stored postings against a profile, emit HTML")
    p_target = p_report.add_mutually_exclusive_group(required=True)
    p_target.add_argument("-p", "--profile", help="profile name from config")
    p_target.add_argument("--all-profiles", action="store_true",
                          help="score every profile into one combined report (a tab per profile)")
    p_report.add_argument("-o", "--out", default="report.html", help="output HTML path")
    p_report.add_argument("--limit", type=int, default=None, help="cap number of results")
    p_report.add_argument("--since", default=None, metavar="DAYS|DATE",
                          help="only score postings published within the last N days, or on/after "
                               "an ISO date (YYYY-MM-DD); postings with no known date are kept")
    p_report.add_argument("--no-dedup", action="store_true",
                          help="disable cross-source dedup (dedup is on by default: collapses the "
                               "same job seen on multiple sources, keeps best-scoring row)")
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
    p_report.add_argument("--all-jobs", action="store_true",
                          help="ignore freshness_days and score all postings in the database")
    p_report.add_argument("--open", action="store_true", help="open the report in a browser")
    p_report.set_defaults(func=cmd_report)

    p_digest = sub.add_parser(
        "digest", help="collect, then report only newly-seen postings (the Fresh Catch)"
    )
    p_digest_target = p_digest.add_mutually_exclusive_group(required=True)
    p_digest_target.add_argument("-p", "--profile", help="profile name from config")
    p_digest_target.add_argument("--all-profiles", action="store_true",
                                 help="score every profile into one combined digest (a tab per profile)")
    p_digest.add_argument("-o", "--out", default="report.html", help="output HTML path")
    p_digest.add_argument("-s", "--source", nargs="+", metavar="TYPE",
                          help="collect only these source type(s) (default: every source in config)")
    p_digest.add_argument("--no-semantic", action="store_true",
                          help="skip the local semantic-similarity component")
    p_digest.add_argument("--model", default=DEFAULT_MODEL,
                          help=f"sentence-transformers model for semantic scoring (default: {DEFAULT_MODEL})")
    p_digest.add_argument("--verbose-sources", action="store_true",
                          help="log every HTTP request/response made by source adapters to stderr")
    p_digest.add_argument("--open", action="store_true", help="open the digest in a browser")
    p_digest.set_defaults(func=cmd_digest)

    p_draft = sub.add_parser(
        "draft", help="draft a tailored resume + cover letter for one or more postings"
    )
    p_draft.add_argument("uid", nargs="*", help="posting uid(s) to draft for (see report output)")
    p_draft.add_argument("--url", metavar="URL", action="append", default=[],
                         help="job posting URL to draft for (fetched ephemerally, not stored); "
                              "mutually exclusive with uid; repeat for multiple URLs")
    p_draft.add_argument("-p", "--profile", required=True, help="profile name from config")
    p_draft.add_argument("--resume", required=True, metavar="FILE",
                         help="path to the resume file (PDF, markdown, or plain text)")
    p_draft.add_argument("--out", default=None, metavar="DIR",
                         help="parent folder for the per-posting draft folders "
                              "(default: config draft_output_dir, else drafts/ under output_dir)")
    p_draft.add_argument("--model", default=None,
                         help="override the LLM model used for drafting "
                              "(default: llm.draft_model from config)")
    p_draft.add_argument("--quiet-llm", action="store_true",
                         help="suppress the per-request/response LLM log (keep the "
                              "usage summary); both go to stderr, never stdout")
    p_draft.set_defaults(func=cmd_draft)

    p_render = sub.add_parser(
        "render", help="(re)render draft PDFs from resume.md/cover_letter.md (no LLM)"
    )
    p_render.add_argument("path", nargs="+",
                          help="draft folder(s) and/or resume.md/cover_letter.md file(s) to render")
    p_render.set_defaults(func=cmd_render)

    p_insights = sub.add_parser(
        "insights", help="aggregate market view: skill demand, salary, source counts, weekly volume"
    )
    p_insights.add_argument(
        "--since", default=None, metavar="DAYS|DATE",
        help="only consider postings collected within the last N days or on/after an ISO date",
    )
    p_insights.add_argument(
        "--skills", default=None, metavar="SKILL1,SKILL2,...",
        help="comma-separated skills to include in demand counts "
             "(supplements profile skills; required when no profiles are configured)",
    )
    p_insights.set_defaults(func=cmd_insights)

    p_sources = sub.add_parser("sources", help="list registered adapters and configured sources + counts")
    p_sources.set_defaults(func=cmd_sources)

    p_profile = sub.add_parser("profile", help="draft a profile from your resume")
    profile_sub = p_profile.add_subparsers(dest="profile_command", required=True)

    p_from_resume = profile_sub.add_parser(
        "from-resume", help="extract titles/skills/keywords from a resume into a profile block"
    )
    p_from_resume.add_argument("--name", required=True, help="profile name to draft/write")
    p_from_resume.add_argument("--resume", required=True, metavar="FILE",
                               help="path to the resume file (PDF, markdown, or plain text)")
    p_from_resume.add_argument("--write", action="store_true",
                               help="append the drafted profile under this name in config.yaml "
                                    "(default: print the YAML block only)")
    p_from_resume.add_argument("--force", action="store_true",
                               help="with --write, overwrite an existing profile of the same name")
    p_from_resume.add_argument("--model", default=None,
                               help="override the LLM model used for drafting "
                                    "(default: llm.draft_model from config)")
    p_from_resume.add_argument("--quiet-llm", action="store_true",
                               help="suppress the per-request/response LLM log (keep the "
                                    "usage summary); both go to stderr, never stdout")
    p_from_resume.set_defaults(func=cmd_profile_from_resume)

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
