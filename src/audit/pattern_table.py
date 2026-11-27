"""The patterns table: messages that should read the same everywhere they're said.

Two files, both written by a person:
- patterns.csv: the patterns that are real. There's no status column, because a row is
  only added once a person has accepted it, and `audit check` will read every row.
- pattern_proposals.csv: drafted rows for a person to accept or reject. The same columns,
  plus a note on how the draft was made and the decision.

No code writes either file. `audit patterns --check` tests both, line by line.

This is its own module, not part of patterns.py, because patterns.py finds candidates in
the local cache, while this file checks what a person wrote in the committed data. The
two never share rows.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from audit import glossary, patterns
from audit.snippets import EXCERPT_MAX_WORDS, SURFACES

COLUMNS = (
    "pattern_id", "message", "shared_wording", "basis", "variants", "pages", "surfaces",
    "question", "string_ids",
)
PROPOSAL_COLUMNS = (*COLUMNS, "note", "decision")
# Blank means nobody has decided yet.
DECISIONS = ("", "accept", "reject")
# Every row needs these. The question matters most: outside-in work can't know why the
# wording differs, so each pattern asks the team.
REQUIRED = ("pattern_id", "message", "shared_wording", "question")
# Straight and curly double quotes. Anything inside them is quoted text, which follows the
# same 20-word limit as committed excerpts.
QUOTED = re.compile(r'"([^"]*)"|“([^”]*)”')


def read(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def known_ids(snippets_path: Path) -> set[str]:
    """Every string ID in the committed snippets table."""
    with snippets_path.open(newline="", encoding="utf-8") as f:
        return {row["id"] for row in csv.DictReader(f)}


def count(value: str) -> int | None:
    """A whole number above 0, or None if it isn't one."""
    value = value.strip()
    return int(value) if value.isdigit() and int(value) > 0 else None


def long_quotes(row: dict[str, str]) -> list[str]:
    """Quoted passages, in any column, that are over the excerpt limit."""
    found = []
    for column, value in row.items():
        # A line with too many fields puts the extras in a list. They aren't text to read.
        if not isinstance(value, str):
            continue
        for straight, curly in QUOTED.findall(value):
            quote = straight or curly
            if len(quote.split()) > EXCERPT_MAX_WORDS:
                found.append(f"{column} quotes more than {EXCERPT_MAX_WORDS} words")
    return found


def problems(row: dict[str, str], known: set[str], *, proposal: bool = False) -> list[str]:
    """Everything wrong with one row, in plain words. An empty list means it's fine."""
    def get(column: str) -> str:
        return (row.get(column) or "").strip()

    found = [f"{column} is empty" for column in REQUIRED if not get(column)]
    # More than one sentence means the message is really two messages.
    if len(patterns.SENTENCE_END.split(get("message"))) > 1:
        found.append("message is more than one sentence")
    if get("basis") not in glossary.BASES:
        found.append(f"basis {get('basis')!r} isn't one of: {', '.join(glossary.BASES)}")

    variants, pages = count(get("variants")), count(get("pages"))
    if variants is None:
        found.append(f"variants {get('variants')!r} isn't a whole number above 0")
    if pages is None:
        found.append(f"pages {get('pages')!r} isn't a whole number above 0")

    surfaces = get("surfaces").split()
    if not surfaces:
        found.append("surfaces is empty")
    for surface in surfaces:
        if surface not in SURFACES:
            found.append(f"surface {surface!r} isn't one of: {', '.join(SURFACES)}")

    # IDs are separated by spaces, as in the candidate list. A comma leaves two IDs stuck
    # together, which then don't match any string.
    ids = get("string_ids").split()
    if not ids:
        found.append("string_ids is empty")
    for string_id in ids:
        if string_id not in known:
            found.append(f"string ID {string_id!r} isn't in the snippets table")
    # Each string is on one page, so there can't be more pages than strings.
    if pages is not None and ids and pages > len(ids):
        found.append(f"pages is {pages}, but there are only {len(ids)} string IDs")

    if proposal and get("decision") not in DECISIONS:
        found.append(f"decision {get('decision')!r} isn't blank, accept or reject")
    return found + long_quotes(row)


def check_rows(
    columns: list[str], rows: list[dict[str, str]], known: set[str], *, proposal: bool = False
) -> list[tuple[int, str]]:
    """(line number, problem) for every problem, as if the rows were a file with this
    header. Line 1 is the header."""
    expected = PROPOSAL_COLUMNS if proposal else COLUMNS
    # Later steps read these columns by name, and the review tab will write them, so the
    # header has to match exactly, in order.
    if tuple(columns) != expected:
        return [(1, f"the header must be exactly: {','.join(expected)}")]
    found = []
    seen: dict[str, int] = {}
    for line, row in enumerate(rows, start=2):
        found += [(line, p) for p in problems(row, known, proposal=proposal)]
        pattern_id = (row.get("pattern_id") or "").strip()
        if pattern_id in seen:
            found.append((line, f"pattern_id repeats line {seen[pattern_id]}"))
        elif pattern_id:
            seen[pattern_id] = line
    return found


def check_file(path: Path, known: set[str], *, proposal: bool = False) -> list[tuple[int, str]]:
    """(line number, problem) for every problem in the file. Line 1 is the header."""
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return check_rows(list(reader.fieldnames or []), list(reader), known, proposal=proposal)
