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
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict
from datetime import date
from pathlib import Path

from audit import check, evidence, glossary, pattern_table, snippets, typed
from audit.config import Target
from audit.snippets import Snippet
from audit.terms import AUTHORITY

TEMPLATE = Path(__file__).parent / "viewer.html"
PLACEHOLDER = "__AUDIT_DATA__"
CHECK_SCRIPT = Path(__file__).parent / "viewer_check.js"
CHECK_PLACEHOLDER = "__CHECK_TEXT_JS__"

# A headline card opens one of these tabs, searched for the card's term. A patterns card
# opens the Patterns tab at one pattern, so its term is a pattern_id.
HEADLINE_TABS = ("findings", "glossary", "terms", "patterns")
HEADLINE_COLUMNS = ("title", "line", "tab", "term")
# The front page is for scanning, so a headline's line stays short.
HEADLINE_MAX_WORDS = 24
# A pattern proposal's note can start with advice for the team. Only that first sentence
# is shown, because the rest of the note is about how the draft was made.
HOW_TO_USE = "How to use it:"


def embed(data: object) -> str:
    """JSON that is safe inside a <script> tag: no '<' can close the tag early."""
    return json.dumps(data, ensure_ascii=True).replace("<", "\\u003c")


def read_csv(path: Path | None) -> list[dict[str, str]]:
    if path is None or not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_headlines(path: Path, pattern_ids: set[str] | None = None) -> list[dict[str, str]]:
    """The front page's headline cards, written by a person in headlines.csv.

    A mistake stops the build with the line number, rather than showing a broken card.
    Given `pattern_ids`, a patterns card's term has to be one of them."""
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
        if row["tab"] == "patterns" and pattern_ids is not None:
            if row["term"].strip() not in pattern_ids:
                raise ValueError(f"{path} line {line}: {row['term']} is not a pattern_id")
    return [{c: row[c].strip() for c in HEADLINE_COLUMNS} for row in rows]


def overview(
    rows: list[Snippet],
    glossary_rows: list[dict[str, str]],
    findings: Sequence[Mapping[str, str]],
    pattern_rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """The numbers in the front page's steps. Counted before an evidence-only build drops
    rows, because the committed table still has every row, only without most excerpts."""
    return {
        # Typed app strings have no public page, so only crawled rows count as pages.
        "pages": len({s.source_url for s in rows if s.method == "crawl"}),
        "app_strings": sum(1 for s in rows if s.method == "typed"),
        "strings": len(rows),
        "glossary_terms": len(glossary_rows),
        # A string that breaks two rules is counted once.
        "breaking_strings": len({i for f in findings for i in f["snippet_ids"].split()}),
        "rules": len({f["standard_id"] for f in findings}),
        "patterns": len(pattern_rows),
    }


# The Check tab's default order: the problems a newcomer understands at once come first, so
# one message in many wordings, then old names and two spellings of one thing. Style
# choices come last.
READING_ORDER = (
    check.PATTERN_CATEGORY, "deprecated name", "other variant", "avoided term",
    "capitalization", "spelling or spacing",
)
# A finding's `written` column quotes up to three forms, each with its count.
QUOTED_FORM = re.compile(r"'(.*?)' \(\d+\)(?:, |$)")


def string_parts(text: str, spans: list[tuple[int, int]]) -> list[tuple[str, bool]]:
    """The text cut into pieces, each marked True if it breaks the rule."""
    parts: list[tuple[str, bool]] = []
    at = 0
    for start, end in sorted(spans):
        if start < at:
            continue
        if start > at:
            parts.append((text[at:start], False))
        parts.append((text[start:end], True))
        at = end
    if at < len(text):
        parts.append((text[at:], False))
    return parts


def rule_kind(source: str, entry: dict[str, str] | None) -> str:
    """How the Check tab states a rule: "pattern" (one string to reuse), "write" (the
    glossary form), "replace" or "retired" (a word and what to use instead), or "avoid"
    (a word with nothing to use instead)."""
    if entry is None:
        return "pattern" if source == "pattern" else "avoid"
    if entry["status"] == "use":
        return "write"
    if not entry["use_instead"].strip():
        return "avoid"
    return "retired" if entry["status"] == "deprecated" else "replace"


def check_rules(
    findings: list[dict[str, str]],
    glossary_rows: list[dict[str, str]],
    wordings: dict[str, str],
    by_id: dict[str, Snippet],
    company: str,
) -> list[dict[str, object]]:
    """One row per rule for the Check tab. A rule can have several findings, one per
    surface or kind of variant, so they're put together and each string counted once.

    Strings with text in this build are listed with the words that break the rule marked.
    The rest are counted, with the pages they're on, so the reader can still open them.
    `wordings` is each pattern's shared wording, by pattern_id."""
    by_rule: dict[str, list[dict[str, str]]] = {}
    for f in findings:
        by_rule.setdefault(f["standard_id"], []).append(f)
    entries = {g["term"]: g for g in glossary_rows}
    ranked: list[tuple[tuple[int, int, str], dict[str, object]]] = []
    for standard_id, group in by_rule.items():
        source, _, name = standard_id.partition(":")
        entry = entries.get(name) if source == "glossary" else None
        kind = rule_kind(source, entry)
        categories = [c for c in READING_ORDER if any(f["category"] == c for f in group)]
        ids = list(dict.fromkeys(i for f in group for i in f["snippet_ids"].split()))
        forms = list(dict.fromkeys(
            form for f in group for form in QUOTED_FORM.findall(f["written"])
        ))
        marked: list[dict[str, object]] = []
        unmarked: list[dict[str, object]] = []
        hidden: list[str] = []
        for snippet_id in ids:
            s = by_id.get(snippet_id)
            if s and s.excerpt:
                spans = check.marks(entry, s.excerpt, s.kind, company) if entry else []
                # An excerpt stops at 20 words, so the words that break a glossary rule
                # can fall past its end. Strings that show them go first.
                (marked if spans or not entry else unmarked).append({
                    "id": snippet_id,
                    "parts": string_parts(s.excerpt, spans),
                    "source_url": s.source_url,
                })
            else:
                hidden.append(s.source_url if s else "")
        shown = marked + unmarked
        surfaces = {s for f in group for s in f["surfaces"].split()}
        rule: dict[str, object] = {
            "standard_id": standard_id,
            "kind": kind,
            "term": name,
            "use_instead": entry["use_instead"].strip() if entry else "",
            "wording": wordings.get(name, "") if source == "pattern" else "",
            # Only other spellings are shown next to the rule. A word to avoid is wrong in
            # any form, but every form is searchable.
            "forms": forms if source == "glossary" else [],
            "categories": categories,
            "count": len(ids),
            "surfaces": [s for s in AUTHORITY if s in surfaces],
            "strings": shown,
            "more": {
                "strings": len(hidden),
                "pages": list(dict.fromkeys(url for url in hidden if url)),
            },
        }
        rank = READING_ORDER.index(categories[0]) if categories else len(READING_ORDER)
        ranked.append(((rank, -len(ids), name.lower()), rule))
    return [rule for _, rule in sorted(ranked, key=lambda pair: pair[0])]


def how_to_use(note: str) -> str:
    """The first sentence after "How to use it:" in a proposal's note, or blank."""
    if not note.startswith(HOW_TO_USE):
        return ""
    rest = note.removeprefix(HOW_TO_USE).strip()
    return re.split(r"(?<=\.)\s+(?=[A-Z])", rest, maxsplit=1)[0]


def pattern_strings(pattern: dict[str, str], by_id: dict[str, Snippet]) -> list[dict[str, str]]:
    """The pattern's strings that have text in this build, so each version can be read."""
    found = []
    for snippet_id in pattern.get("string_ids", "").split():
        s = by_id.get(snippet_id)
        if s and s.excerpt:
            found.append({"id": snippet_id, "excerpt": s.excerpt, "source_url": s.source_url})
    return found


def read_patterns(target: Target, by_id: dict[str, Snippet]) -> list[dict[str, object]]:
    """patterns.csv, each row with its how-to-use line from the proposal and its strings."""
    advice = {
        p["pattern_id"]: how_to_use(p.get("note", ""))
        for p in pattern_table.read(target.pattern_proposals)
    }
    return [
        {**p, "how_to_use": advice.get(p["pattern_id"], ""), "strings": pattern_strings(p, by_id)}
        for p in pattern_table.read(target.pattern_table)
    ]


def build_data(
    target: Target, today: date, *, editable: bool = False, evidence_only: bool = False
) -> dict[str, object]:
    rows, full = evidence.load_table(target, committed_only=evidence_only)
    # Rules are resolved before rows are dropped, so a rule still links to the page for a
    # snippet whose excerpt isn't in this build.
    by_id = {s.id: s for s in rows}
    findings = read_csv(target.data_dir / "findings.csv")
    patterns = read_patterns(target, by_id)
    glossary_rows = glossary.read(target.glossary)
    wordings = {str(p["pattern_id"]): str(p["shared_wording"]) for p in patterns}
    rules = check_rules(findings, glossary_rows, wordings, by_id, target.display_name)
    numbers = overview(rows, glossary_rows, findings, patterns)
    if evidence_only:
        rows = [s for s in rows if s.excerpt]
    terms = read_csv(target.data_dir / "terms.csv")
    # Said on the Source data tab, only when it holds fewer strings than the numbers count.
    if evidence_only:
        notice = (
            "This copy shows only the strings cited as evidence. "
            "The full table stays on the computer that built it."
        )
    elif not full:
        notice = "Most of the strings' text isn't on this computer. Run `audit extract` to get it."
    else:
        notice = ""
    return {
        "display_name": target.display_name,
        "editable": editable,
        "today": today.isoformat(),
        "notice": notice,
        "overview": numbers,
        "headlines": read_headlines(
            target.data_dir / "headlines.csv", {str(p["pattern_id"]) for p in patterns}
        ),
        "values": {"surface": sorted({s.surface for s in rows})},
        "allowed": {
            "kind": list(snippets.KINDS),
            "surface": list(snippets.SURFACES),
            "stage": list(snippets.STAGES),
            "glossary_status": list(glossary.STATUSES),
            "glossary_basis": list(glossary.BASES),
            # The Check tab offers categories in this order.
            "finding_category": list(READING_ORDER),
        },
        "terms": terms,
        "glossary": glossary_rows,
        # Drafts for the reviewer only, so the plain and evidence-only pages leave them out.
        "glossary_proposals": (
            read_csv(target.data_dir / "glossary_proposals.csv") if editable else []
        ),
        "rules": rules,
        "patterns": patterns,
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
    page = TEMPLATE.read_text(encoding="utf-8")
    page = page.replace(CHECK_PLACEHOLDER, CHECK_SCRIPT.read_text(encoding="utf-8"))
    return page.replace(PLACEHOLDER, embed(data))


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
