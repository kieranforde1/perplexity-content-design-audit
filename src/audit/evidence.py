"""Which excerpts get committed.

The repo commits evidence, not a copy of the company's pages. There are two copies of
the snippets table:

- cache/<target>/snippets.csv, on your computer only: every row, every excerpt.
- data/<target>/snippets.csv, committed: every row, so IDs, kinds and source links are
  all there, but the excerpt is only filled in for evidence. Evidence means the snippets
  the term map cites as examples, the first few snippets each finding lists, and every
  typed app string.

`extract`, `terms` and `check` all rewrite the committed copy, and all three read both
terms.csv and findings.csv, so whichever runs last keeps the same evidence.
"""

from __future__ import annotations

import csv
from collections.abc import Callable
from dataclasses import replace

from audit import snippets
from audit.config import Target
from audit.snippets import Snippet


def cited_ids(target: Target) -> set[str]:
    """Snippet IDs that terms.csv cites as examples."""
    path = target.data_dir / "terms.csv"
    if not path.exists():
        return set()
    with path.open(newline="", encoding="utf-8") as f:
        return {i for row in csv.DictReader(f) for i in (row.get("example_ids") or "").split()}


def finding_ids(target: Target) -> set[str]:
    """The first few snippet IDs of each finding in findings.csv.

    A finding can list hundreds of snippets. A few are enough to show what it points at.
    """
    path = target.data_dir / "findings.csv"
    if not path.exists():
        return set()
    keep = target.evidence_per_finding
    with path.open(newline="", encoding="utf-8") as f:
        return {
            i for row in csv.DictReader(f) for i in (row.get("snippet_ids") or "").split()[:keep]
        }


def public_copy(rows: list[Snippet], cited: set[str]) -> list[Snippet]:
    return [
        s if s.method == "typed" or s.id in cited else replace(s, excerpt="")
        for s in rows
    ]


def write_public_copy(
    target: Target, rows: list[Snippet], *, log: Callable[[str], None] = print
) -> int:
    """Write the committed table and return how many excerpts it fills in."""
    public = public_copy(rows, cited_ids(target) | finding_ids(target))
    snippets.write(target.public_snippets, public)
    filled = sum(1 for s in public if s.excerpt)
    if filled > target.max_committed_excerpts:
        log(
            f"Warning: {filled} excerpts would be committed, over the limit of "
            f"{target.max_committed_excerpts} in the config. The committed-data test will fail."
        )
    return filled


def load_table(target: Target, *, committed_only: bool = False) -> tuple[list[Snippet], bool]:
    """The fullest table available, and whether it's the full local one.

    On a fresh clone only the committed copy exists, so the viewer still works.
    `committed_only` skips the local copy, for a build that holds only what's committed.
    """
    if target.local_snippets.exists() and not committed_only:
        return snippets.read(target.local_snippets), True
    if target.public_snippets.exists():
        return snippets.read(target.public_snippets), False
    return [], False
