"""The `audit` command. Each subcommand is one step; every step reads the snippets table."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from audit import (
    check,
    config,
    extract,
    fetch,
    glossary,
    pattern_table,
    patterns,
    review,
    skill,
    terms,
    typed,
    view,
)

NOT_BUILT = "Not built yet. See ROADMAP.md"


def _add_target(p: argparse.ArgumentParser) -> None:
    p.add_argument("--target", default="perplexity", help="Config name in targets/")
    p.add_argument("--root", type=Path, default=Path("."), help=argparse.SUPPRESS)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="audit",
        description="Audit a company's public product text from the outside. Unofficial.",
        epilog="The numbers follow the method: 1 collect, 2 settle the words, 3 check, "
        "4 find repeated messages.",
    )
    # Listed in the order of the method, so the help reads as the steps.
    sub = parser.add_subparsers(dest="command", required=True, metavar="command")

    p = sub.add_parser("fetch", help="1. Download the public pages, politely")
    _add_target(p)
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="List the pages it would fetch. Still reads robots.txt and index pages.",
    )
    p.add_argument("--limit", type=int, help="Fetch at most this many pages")
    p.add_argument("--refresh", action="store_true", help="Fetch again even if cached")

    p = sub.add_parser("extract", help="1. Split the pages into strings")
    _add_target(p)
    p.add_argument("--dry-run", action="store_true", help="Count strings without writing")

    p = sub.add_parser("terms", help="2. List the words that are written more than one way")
    _add_target(p)

    p = sub.add_parser("review", help="2. Decide terms and add app strings in your browser")
    _add_target(p)
    p.add_argument("--port", type=int, default=review.DEFAULT_PORT, help="Port on 127.0.0.1")
    p.add_argument("--no-browser", action="store_true", help="Don't open a browser tab")

    p = sub.add_parser("glossary", help="2. Check the glossary file")
    _add_target(p)
    p.add_argument("--check", action="store_true", required=True, help="Check glossary.csv")

    p = sub.add_parser("check", help="3. Test the text against the glossary and patterns")
    _add_target(p)

    p = sub.add_parser("patterns", help="4. Find sentences that say the same thing differently")
    _add_target(p)
    p.add_argument(
        "--check",
        action="store_true",
        help="Check patterns.csv and pattern_proposals.csv by line, instead of writing candidates",
    )

    p = sub.add_parser(
        "skill", help="Build a content-standards skill from the glossary and patterns"
    )
    _add_target(p)

    p = sub.add_parser("view", help="Build the offline viewer to see the results")
    _add_target(p)
    p.add_argument(
        "--evidence-only",
        action="store_true",
        help="Build from committed data only, into viewer/<target>/evidence.html",
    )

    p = sub.add_parser("typed", help="Help with app strings typed in by hand")
    _add_target(p)
    what = p.add_mutually_exclusive_group(required=True)
    what.add_argument("--template", action="store_true", help="Print the header and examples")
    what.add_argument("--check", action="store_true", help="Check typed_strings.csv by line")

    # Paused steps (ROADMAP.md, "Later"). They still answer "Not built yet", but have no
    # help text, so `audit --help` only lists what works.
    for name in ("recommend", "style", "tone"):
        _add_target(sub.add_parser(name))
    return parser


def check_patterns(target: config.Target) -> int:
    """Check both pattern files, like `audit glossary --check`. 1 if either has problems."""
    known = pattern_table.known_ids(target.public_snippets)
    total = 0
    for path, proposal in ((target.pattern_table, False), (target.pattern_proposals, True)):
        found = pattern_table.check_file(path, known, proposal=proposal)
        for line, problem in found:
            print(f"{path.name} line {line}: {problem}")
        print(f"{path}: {len(pattern_table.read(path))} rows, {len(found)} problems.")
        total += len(found)
    return 1 if total else 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "fetch":
            target = config.load(args.target, args.root)
            contact = fetch.contact_from_env()
            report = fetch.run(
                target, contact, dry_run=args.dry_run, limit=args.limit, refresh=args.refresh
            )
            return 1 if report.failed else 0
        if args.command == "extract":
            target = config.load(args.target, args.root)
            extract.run(target, dry_run=args.dry_run)
            return 0
        if args.command == "terms":
            terms.run(config.load(args.target, args.root))
            return 0
        if args.command == "patterns":
            target = config.load(args.target, args.root)
            if args.check:
                return check_patterns(target)
            patterns.run(target)
            return 0
        if args.command == "check":
            check.run(config.load(args.target, args.root))
            return 0
        if args.command == "skill":
            skill.run(config.load(args.target, args.root))
            return 0
        if args.command == "view":
            view.run(config.load(args.target, args.root), evidence_only=args.evidence_only)
            return 0
        if args.command == "typed":
            if args.template:
                print(typed.template())
                return 0
            path = config.load(args.target, args.root).typed_strings
            found = typed.check_file(path)
            for line, problem in found:
                print(f"line {line}: {problem}")
            rows = len(typed.read(path))
            print(f"{path}: {rows} rows, {len(found)} problems." if path else "")
            return 1 if found else 0
        if args.command == "glossary":
            path = config.load(args.target, args.root).glossary
            problems = glossary.check_file(path)
            for line, problem in problems:
                print(f"line {line}: {problem}")
            print(f"{path}: {len(glossary.read(path))} rows, {len(problems)} problems.")
            return 1 if problems else 0
        if args.command == "review":
            target = config.load(args.target, args.root)
            review.run(target, port=args.port, open_browser=not args.no_browser)
            return 0
        print(NOT_BUILT)
        return 0
    except (config.ConfigError, fetch.FetchError, FileNotFoundError, ValueError) as e:
        print(f"audit {args.command}: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
