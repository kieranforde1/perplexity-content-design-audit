"""`audit view`: build one offline HTML page to browse the audit.

The page has all its data built in, so it opens from disk with no server and loads
nothing from the web. Text from crawled pages is inserted as plain text, never as HTML.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Callable
from dataclasses import asdict
from datetime import date
from pathlib import Path

from audit import snippets
from audit.config import Target

TEMPLATE = Path(__file__).parent / "viewer.html"
PLACEHOLDER = "__AUDIT_DATA__"


def embed(data: object) -> str:
    """JSON that is safe inside a <script> tag: no '<' can close the tag early."""
    return json.dumps(data, ensure_ascii=True).replace("<", "\\u003c")


def read_terms(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build_data(target: Target, today: date) -> dict[str, object]:
    rows = snippets.read(target.data_dir / "snippets.csv")
    terms = read_terms(target.data_dir / "terms.csv")
    pages = {s.source_url for s in rows}
    dates = sorted({s.captured_on for s in rows})
    reviewed = sum(1 for t in terms if t.get("review"))
    span = f"{dates[0]} to {dates[-1]}" if dates else "no dates"
    return {
        "display_name": target.display_name,
        "summary": (
            f"{len(rows):,} snippets from {len(pages):,} public pages, captured {span}. "
            f"{len(terms)} terms proposed, {reviewed} reviewed."
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
        "terms": terms,
        "snippets": [asdict(s) for s in rows],
    }


def run(
    target: Target,
    *,
    today: Callable[[], date] = date.today,
    log: Callable[[str], None] = print,
) -> Path:
    html = TEMPLATE.read_text(encoding="utf-8")
    page = html.replace(PLACEHOLDER, embed(build_data(target, today())))
    out = target.root / "viewer" / target.name / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    log(f"Wrote {out} ({out.stat().st_size / 1_000_000:.1f} MB). Open it in a browser.")
    return out
