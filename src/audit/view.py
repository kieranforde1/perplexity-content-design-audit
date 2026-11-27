"""`audit view`: build one offline HTML page to browse the audit.

The page has all its data built in, so it opens from disk with no server and loads
nothing from the web. Text from crawled pages is inserted as plain text, never as HTML.
`audit review` serves the same page with editing switched on.

`--evidence-only` builds from committed data alone and keeps only snippets with an
excerpt, so the page is small and holds nothing the repo doesn't.

Readers see a snippet as a "string". The code keeps the name `snippet`, because the
snippets.csv data contract is locked.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict
from datetime import date
from pathlib import Path

from audit import check, evidence, glossary, snippets, typed
from audit.config import Target
from audit.snippets import Snippet

TEMPLATE = Path(__file__).parent / "viewer.html"
PLACEHOLDER = "__AUDIT_DATA__"

# A headline card opens one of these tabs, searched for the card's term.
HEADLINE_TABS = ("findings", "glossary", "terms")
HEADLINE_COLUMNS = ("title", "line", "tab", "term")
# The front page is for scanning, so a headline's line stays short.
HEADLINE_MAX_WORDS = 24


def embed(data: object) -> str:
    """JSON that is safe inside a <script> tag: no '<' can close the tag early."""
    return json.dumps(data, ensure_ascii=True).replace("<", "\\u003c")


def read_csv(path: Path | None) -> list[dict[str, str]]:
    if path is None or not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_headlines(path: Path) -> list[dict[str, str]]:
    """The front page's headline cards, written by a person in headlines.csv.

    A mistake stops the build with the line number, rather than showing a broken card."""
    rows = read_csv(path)
    for line, row in enumerate(rows, start=2):
        missing = [c for c in HEADLINE_COLUMNS if not (row.get(c) or "").strip()]
        if missing:
            raise ValueError(f"{path} line {line}: {', '.join(missing)} is blank")
        if row["tab"] not in HEADLINE_TABS:
            raise ValueError(
                f"{path} line {line}: tab must be one of {', '.join(HEADLINE_TABS)}"
            )
        if len(row["line"].split()) > HEADLINE_MAX_WORDS:
            raise ValueError(f"{path} line {line}: keep the line to {HEADLINE_MAX_WORDS} words")
    return [{c: row[c].strip() for c in HEADLINE_COLUMNS} for row in rows]


def overview(
    rows: list[Snippet],
    glossary_rows: list[dict[str, str]],
    findings: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """The front page's numbers. Counted before an evidence-only build drops rows, because
    the committed table still has every row, only without most excerpts."""
    per_category = Counter(f.get("category", "") for f in findings)
    return {
        # Typed app strings have no public page, so only crawled rows count as pages.
        "pages": len({s.source_url for s in rows if s.method == "crawl"}),
        "strings": len(rows),
        "glossary_terms": len(glossary_rows),
        "findings": len(findings),
        # In the order `audit check` defines, so the bars match the Findings tab.
        "by_category": [[c, per_category[c]] for c in check.CATEGORIES if per_category[c]],
    }


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
    glossary_rows = glossary.read(target.glossary)
    numbers = overview(rows, glossary_rows, findings)
    if evidence_only:
        rows = [s for s in rows if s.excerpt]
    terms = read_csv(target.data_dir / "terms.csv")
    # Said only when the Strings tab holds fewer strings than the numbers count.
    if evidence_only:
        notice = "Evidence copy: the Strings tab lists only strings with a committed excerpt."
    elif not full:
        notice = "Most excerpts aren't on this computer. Run `audit extract` to see them all."
    else:
        notice = ""
    return {
        "display_name": target.display_name,
        "editable": editable,
        "today": today.isoformat(),
        "notice": notice,
        "overview": numbers,
        "headlines": read_headlines(target.data_dir / "headlines.csv"),
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
            # The Findings tab groups and filters in this order.
            "finding_category": list(check.CATEGORIES),
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
