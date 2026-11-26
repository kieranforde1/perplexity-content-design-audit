"""`audit view`: build one offline HTML page to browse the audit.

The page has all its data built in, so it opens from disk with no server and loads
nothing from the web. Text from crawled pages is inserted as plain text, never as HTML.
`audit review` serves the same page with editing switched on.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Callable
from dataclasses import asdict
from datetime import date
from pathlib import Path

from audit import evidence, snippets, typed
from audit.config import Target

TEMPLATE = Path(__file__).parent / "viewer.html"
PLACEHOLDER = "__AUDIT_DATA__"


def embed(data: object) -> str:
    """JSON that is safe inside a <script> tag: no '<' can close the tag early."""
    return json.dumps(data, ensure_ascii=True).replace("<", "\\u003c")


def read_csv(path: Path | None) -> list[dict[str, str]]:
    if path is None or not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build_data(target: Target, today: date, *, editable: bool = False) -> dict[str, object]:
    rows, full = evidence.load_table(target)
    terms = read_csv(target.data_dir / "terms.csv")
    pages = {s.source_url for s in rows}
    dates = sorted({s.captured_on for s in rows})
    reviewed = sum(1 for t in terms if t.get("review"))
    span = f"{dates[0]} to {dates[-1]}" if dates else "no dates"
    which = (
        "" if full else " Showing committed evidence only: run `audit extract` for every excerpt."
    )
    return {
        "display_name": target.display_name,
        "editable": editable,
        "today": today.isoformat(),
        "summary": (
            f"{len(rows):,} snippets from {len(pages):,} public pages, captured {span}. "
            f"{len(terms)} terms proposed, {reviewed} reviewed.{which}"
        ),
        "footer": (
            f"Built by `audit view` on {today.isoformat()}. Findings are observations from "
            "public, first-party sources. They make no claims about how or why the company "
            "made its decisions."
        ),
        "values": {
            "surface": sorted({s.surface for s in rows}),
            "kind": sorted({s.kind for s in rows}),
            "stage": sorted({s.stage for s in rows}),
        },
        "allowed": {
            "kind": list(snippets.KINDS),
            "surface": list(snippets.SURFACES),
            "stage": list(snippets.STAGES),
        },
        "terms": terms,
        "typed_strings": typed.read(target.typed_strings),
        "snippets": [asdict(s) for s in rows],
    }


def render(target: Target, *, editable: bool = False, today: date | None = None) -> str:
    data = build_data(target, today or date.today(), editable=editable)
    return TEMPLATE.read_text(encoding="utf-8").replace(PLACEHOLDER, embed(data))


def run(
    target: Target,
    *,
    today: Callable[[], date] = date.today,
    log: Callable[[str], None] = print,
) -> Path:
    out = target.root / "viewer" / target.name / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(target, today=today()), encoding="utf-8")
    log(f"Wrote {out} ({out.stat().st_size / 1_000_000:.1f} MB). Open it in a browser.")
    return out
