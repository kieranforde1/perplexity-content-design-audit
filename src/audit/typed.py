"""Typed app strings: text a person saw while using the product and typed in by hand.

These rules are used in three places, so they can't disagree: `audit typed --check`,
`audit extract` (which skips rows that break them) and the review page.
"""

from __future__ import annotations

import csv
import re
from datetime import date
from pathlib import Path

from audit import snippets

COLUMNS = ("text", "kind", "source_url", "surface", "stage", "captured_on")
APP_SURFACES = ("web-app", "ios-app", "comet")
# Parameters come from API docs, not from using the app.
APP_KINDS = tuple(k for k in snippets.KINDS if k != "parameter")
# A description of where the text was seen, for screens with no web address.
MAX_DESCRIPTION_CHARS = 80
# Anything shaped like a web address ("javascript:", "http://") must be a real https link.
LOOKS_LIKE_ADDRESS = re.compile(r"^[a-z][a-z0-9+.-]*:", re.IGNORECASE)

EXAMPLES = (
    ("EXAMPLE Ask anything", "button", "https://www.example.com/", "web-app", "first-use",
     "2026-11-26"),
    ("EXAMPLE Something went wrong. Try again.", "error", "iOS app, answer screen",
     "ios-app", "error", "2026-11-26"),
)


def template() -> str:
    lines = [",".join(COLUMNS)]
    lines.append("")
    lines.append("# Two example rows. They start with EXAMPLE: don't copy them into the file.")
    for row in EXAMPLES:
        lines.append(",".join(f'"{v}"' if "," in v else v for v in row))
    return "\n".join(lines)


def problems(row: dict[str, str]) -> list[str]:
    """Everything wrong with one row, in plain words. An empty list means it's fine."""
    found = []
    text = " ".join((row.get("text") or "").split())
    source = (row.get("source_url") or "").strip()
    if not text:
        found.append("text is empty")
    elif len(text.split()) > snippets.EXCERPT_MAX_WORDS:
        found.append(
            f"text is {len(text.split())} words; keep it to {snippets.EXCERPT_MAX_WORDS}"
        )
    if row.get("kind") not in APP_KINDS:
        found.append(f"kind {row.get('kind')!r} isn't one of: {', '.join(APP_KINDS)}")
    if not source:
        found.append(
            "source_url is missing. Use a web address, or a short description "
            "such as 'web app, sign-up screen'"
        )
    elif LOOKS_LIKE_ADDRESS.match(source) and not source.startswith("https://"):
        found.append("source_url looks like a web address, so it must start with https://")
    elif not source.startswith("https://") and len(source) > MAX_DESCRIPTION_CHARS:
        found.append(f"source_url description is over {MAX_DESCRIPTION_CHARS} characters")
    if row.get("surface") not in APP_SURFACES:
        found.append(f"surface {row.get('surface')!r} isn't one of: {', '.join(APP_SURFACES)}")
    if row.get("stage") not in snippets.STAGES:
        found.append(f"stage {row.get('stage')!r} isn't one of: {', '.join(snippets.STAGES)}")
    captured = (row.get("captured_on") or "").strip()
    if not captured:
        found.append("captured_on is missing. Use a date like 2026-11-26")
    else:
        try:
            date.fromisoformat(captured)
        except ValueError:
            found.append(f"captured_on {captured!r} isn't a date like 2026-11-26")
    return found


def read(path: Path | None) -> list[dict[str, str]]:
    if path is None or not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def check_file(path: Path | None) -> list[tuple[int, str]]:
    """(line number, problem) for every problem in the file. Line 1 is the header."""
    if path is None:
        return [(0, "this target has no typed_strings file set in its config")]
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            return [(1, f"the header is missing: {', '.join(missing)}")]
        found = []
        for line, row in enumerate(reader, start=2):
            found += [(line, p) for p in problems(row)]
        return found
