"""The snippets table: one row per piece of public text.

Every step reads this table, so its columns are fixed. Change them only on purpose:
later steps (patterns, style, tone labels) refer to snippets by `id`.
"""

from __future__ import annotations

import csv
import hashlib
from dataclasses import asdict, dataclass, fields
from pathlib import Path

SURFACES = ("docs", "help", "pricing", "blog", "changelog", "web-app", "ios-app", "comet")
STAGES = ("sign-up", "first-use", "answering", "error", "upgrade", "settings", "other")
KINDS = ("title", "heading", "nav", "button", "parameter", "error", "sentence")
METHODS = ("crawl", "typed")

# Committed data keeps excerpts short. The full text stays in the gitignored cache.
EXCERPT_MAX_WORDS = 20


@dataclass(frozen=True)
class Snippet:
    id: str
    excerpt: str
    kind: str
    source_url: str
    surface: str
    stage: str
    captured_on: str
    method: str
    hash: str


COLUMNS = tuple(f.name for f in fields(Snippet))


def make_excerpt(text: str) -> str:
    words = text.split()
    if len(words) <= EXCERPT_MAX_WORDS:
        return " ".join(words)
    return " ".join(words[:EXCERPT_MAX_WORDS]) + " …"


def make_id(source_url: str, kind: str, text: str) -> str:
    """A short ID that stays the same every time the same page is re-crawled.

    It changes only if the text, its kind or its URL changes. That keeps hand labels
    attached to the snippet they were written for.
    """
    key = f"{source_url}\n{kind}\n{text}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def make_hash(text: str) -> str:
    """Fingerprint of the full text, so anyone can check an excerpt against the source."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def build(
    text: str,
    kind: str,
    source_url: str,
    surface: str,
    stage: str,
    captured_on: str,
    method: str,
) -> Snippet:
    text = " ".join(text.split())
    for value, allowed, name in (
        (kind, KINDS, "kind"),
        (surface, SURFACES, "surface"),
        (stage, STAGES, "stage"),
        (method, METHODS, "method"),
    ):
        if value not in allowed:
            raise ValueError(f"Unknown {name} {value!r}. Use one of: {', '.join(allowed)}")
    return Snippet(
        id=make_id(source_url, kind, text),
        excerpt=make_excerpt(text),
        kind=kind,
        source_url=source_url,
        surface=surface,
        stage=stage,
        captured_on=captured_on,
        method=method,
        hash=make_hash(text),
    )


def write(path: Path, snippets: list[Snippet]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for s in snippets:
            writer.writerow(asdict(s))


def read(path: Path) -> list[Snippet]:
    with path.open(newline="", encoding="utf-8") as f:
        return [Snippet(**row) for row in csv.DictReader(f)]
