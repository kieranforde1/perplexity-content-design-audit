"""The `audit` command. Each subcommand is one step; every step reads the snippets table."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from audit import config, extract, fetch

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
    p.add_argument("--dry-run", action="store_true", help="List pages without fetching them")
    p.add_argument("--limit", type=int, help="Fetch at most this many pages")
    p.add_argument("--refresh", action="store_true", help="Fetch again even if cached")

    p = sub.add_parser("extract", help="Turn cached pages into data/<target>/snippets.csv")
    _add_target(p)
    p.add_argument("--dry-run", action="store_true", help="Count snippets without writing")

    for name, help_text in (
        ("terms", "Build the term map"),
        ("view", "Build the offline viewer"),
        ("check", "Check snippets against the standards register"),
        ("recommend", "Turn findings into recommendations"),
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
        print(NOT_BUILT)
        return 0
    except (config.ConfigError, fetch.FetchError) as e:
        print(f"audit {args.command}: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
