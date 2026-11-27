"""`audit view`: build one offline HTML page to browse the audit.

The page has all its data built in, so it opens from disk with no server and loads
nothing from the web. Text from crawled pages is inserted as plain text, never as HTML.
`audit review` serves the same page with editing switched on.

`--evidence-only` builds from committed data alone and keeps only snippets with an
excerpt, so the page is small and holds nothing the repo doesn't.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Callable
from dataclasses import asdict
from datetime import date
from pathlib import Path

from audit import evidence, glossary, snippets, typed
from audit.config import Target
from audit.snippets import Snippet

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


def finding_evidence(finding: dict[str, str], by_id: dict[str, Snippet]) -> list[dict[str, str]]:
    """Each snippet a finding counts, with its excerpt if this build has one."""
    found = []
    for snippet_id in finding.get("snippet_ids", "").split():
        s = by_id.get(snippet_id)
        found.append({
            "id": snippet_id,
            "excerpt": s.excerpt if s else "",
            "source_url": s.source_url if s else "",
        })
    return found


def build_data(
    target: Target, today: date, *, editable: bool = False, evidence_only: bool = False
) -> dict[str, object]:
    rows, full = evidence.load_table(target, committed_only=evidence_only)
    # Findings are resolved before rows are dropped, so a finding still links to the page
    # for a snippet whose excerpt isn't in this build.
    by_id = {s.id: s for s in rows}
    findings = [
        {**f, "evidence": finding_evidence(f, by_id)}
        for f in read_csv(target.data_dir / "findings.csv")
    ]
    if evidence_only:
        rows = [s for s in rows if s.excerpt]
    terms = read_csv(target.data_dir / "terms.csv")
    glossary_rows = glossary.read(target.glossary)
    pages = {s.source_url for s in rows}
    dates = sorted({s.captured_on for s in rows})
    reviewed = sum(1 for t in terms if t.get("review"))
    span = f"{dates[0]} to {dates[-1]}" if dates else "no dates"
    if evidence_only:
        which = " Evidence only: just the snippets whose excerpts are committed."
    elif not full:
        which = " Showing committed evidence only: run `audit extract` for every excerpt."
    else:
        which = ""
    return {
        "display_name": target.display_name,
        "editable": editable,
        "today": today.isoformat(),
        "summary": (
            f"{len(rows):,} snippets from {len(pages):,} public pages, captured {span}. "
            f"{len(terms)} terms proposed, {reviewed} reviewed. "
            f"{len(glossary_rows)} glossary rows, {len(findings)} findings.{which}"
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
            "glossary_status": list(glossary.STATUSES),
            "glossary_basis": list(glossary.BASES),
        },
        "terms": terms,
        "glossary": glossary_rows,
        # Drafts for the reviewer only, so the plain and evidence-only pages leave them out.
        "glossary_proposals": (
            read_csv(target.data_dir / "glossary_proposals.csv") if editable else []
        ),
        "findings": findings,
        "typed_strings": typed.read(target.typed_strings),
        "snippets": [asdict(s) for s in rows],
    }


def render(
    target: Target,
    *,
    editable: bool = False,
    evidence_only: bool = False,
    today: date | None = None,
) -> str:
    data = build_data(
        target, today or date.today(), editable=editable, evidence_only=evidence_only
    )
    return TEMPLATE.read_text(encoding="utf-8").replace(PLACEHOLDER, embed(data))


def run(
    target: Target,
    *,
    evidence_only: bool = False,
    today: Callable[[], date] = date.today,
    log: Callable[[str], None] = print,
) -> Path:
    # A separate file, so the evidence build never overwrites the full one.
    name = "evidence.html" if evidence_only else "index.html"
    out = target.root / "viewer" / target.name / name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(target, evidence_only=evidence_only, today=today()), encoding="utf-8")
    log(f"Wrote {out} ({out.stat().st_size / 1_000_000:.1f} MB). Open it in a browser.")
    return out
