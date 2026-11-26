"""The `audit` command. Each subcommand is one step; every step reads the snippets table."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from audit import check, config, extract, fetch, glossary, review, terms, typed, view

NOT_BUILT = "Not built yet. See ROADMAP.md"


def _add_target(p: argparse.ArgumentParser) -> None:
    p.add_argument("--target", default="perplexity", help="Config name in targets/")
    p.add_argument("--root", type=Path, default=Path("."), help=argparse.SUPPRESS)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="audit",
        description="Outside-in audit of published product language. Unofficial.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("fetch", help="Download public pages into cache/")
    _add_target(p)
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="List the pages it would fetch. Still reads robots.txt and index pages.",
    )
    p.add_argument("--limit", type=int, help="Fetch at most this many pages")
    p.add_argument("--refresh", action="store_true", help="Fetch again even if cached")

    p = sub.add_parser("extract", help="Turn cached pages into data/<target>/snippets.csv")
    _add_target(p)
    p.add_argument("--dry-run", action="store_true", help="Count snippets without writing")

    p = sub.add_parser("typed", help="Help with typed app strings")
    _add_target(p)
    what = p.add_mutually_exclusive_group(required=True)
    what.add_argument("--template", action="store_true", help="Print the header and examples")
    what.add_argument("--check", action="store_true", help="Check typed_strings.csv by line")

    p = sub.add_parser("glossary", help="Check the glossary")
    _add_target(p)
    p.add_argument("--check", action="store_true", required=True, help="Check glossary.csv")

    p = sub.add_parser("review", help="Review terms and add app strings in your browser")
    _add_target(p)
    p.add_argument("--port", type=int, default=review.DEFAULT_PORT, help="Port on 127.0.0.1")
    p.add_argument("--no-browser", action="store_true", help="Don't open a browser tab")

    p = sub.add_parser("view", help="Build the offline viewer")
    _add_target(p)
    p.add_argument(
        "--evidence-only",
        action="store_true",
        help="Build from committed data only, into viewer/<target>/evidence.html",
    )

    for name, help_text in (
        ("terms", "Build the term map"),
        ("check", "Check the public text against the glossary"),
        ("recommend", "Turn findings into recommendations"),
        ("skill", "Build a content-standards skill from the audit"),
        ("patterns", "Group repeated content structures (pass 2)"),
        ("style", "Write observed style (pass 2)"),
        ("tone", "Score tone across stages (pass 2)"),
    ):
        p = sub.add_parser(name, help=help_text)
        _add_target(p)
    return parser


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
        if args.command == "check":
            check.run(config.load(args.target, args.root))
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
