"""The glossary: the terms a person has settled on, including words to avoid.

A person owns this file. Code reads and checks it, and never writes to it. It's what
later checks test the public text against.

Each row says how sure we can be about it:
- published: Perplexity said it publicly, such as a migration guide that retires a name.
  source_url must point to where it said so.
- observed: Perplexity's own public text uses the term this way.
- recommendation: the reviewer's suggestion. It's never presented as Perplexity's rule.
"""

from __future__ import annotations

import csv
from pathlib import Path

COLUMNS = ("term", "status", "use_instead", "definition", "basis", "source_url")
# use: write it like this. avoid: don't write it. deprecated: an old name that was replaced.
STATUSES = ("use", "avoid", "deprecated")
BASES = ("published", "observed", "recommendation")


def problems(row: dict[str, str]) -> list[str]:
    """Everything wrong with one row, in plain words. An empty list means it's fine."""
    found = []
    term = (row.get("term") or "").strip()
    status = (row.get("status") or "").strip()
    basis = (row.get("basis") or "").strip()
    source = (row.get("source_url") or "").strip()
    if not term:
        found.append("term is empty")
    if status not in STATUSES:
        found.append(f"status {status!r} isn't one of: {', '.join(STATUSES)}")
    # An avoid word can wait for its replacement, but a retired name always has one.
    if status == "deprecated" and not (row.get("use_instead") or "").strip():
        found.append("a deprecated term needs use_instead: the name that replaced it")
    if basis not in BASES:
        found.append(f"basis {basis!r} isn't one of: {', '.join(BASES)}")
    if basis == "published" and not source.startswith("https://"):
        found.append("a published row needs source_url: the https page where it was said")
    elif source and not source.startswith("https://"):
        found.append("source_url must start with https://")
    return found


def read(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def check_file(path: Path) -> list[tuple[int, str]]:
    """(line number, problem) for every problem in the file. Line 1 is the header."""
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            return [(1, f"the header is missing: {', '.join(missing)}")]
        found = []
        seen: dict[str, int] = {}
        for line, row in enumerate(reader, start=2):
            found += [(line, p) for p in problems(row)]
            key = " ".join((row.get("term") or "").lower().split())
            if key in seen:
                found.append((line, f"term repeats line {seen[key]}"))
            elif key:
                seen[key] = line
        return found
