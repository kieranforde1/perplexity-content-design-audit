"""Checks on the data that's actually published in this repo, not just the code that writes it.

The rules come from how the audit handles other people's text: short excerpts only, every
crawled snippet links to a real public page, and the table's shape never drifts.
"""

import csv
from pathlib import Path

import pytest

from audit import snippets

REPO_ROOT = Path(__file__).resolve().parent.parent
SNIPPET_FILES = sorted(REPO_ROOT.glob("data/*/snippets.csv"))


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_there_is_committed_data_to_check() -> None:
    assert SNIPPET_FILES, "no data/*/snippets.csv files found"


@pytest.mark.parametrize("path", SNIPPET_FILES, ids=lambda p: p.parent.name)
def test_columns_match_the_snippets_table(path: Path) -> None:
    with path.open(newline="", encoding="utf-8") as f:
        header = next(csv.reader(f))
    assert tuple(header) == snippets.COLUMNS


@pytest.mark.parametrize("path", SNIPPET_FILES, ids=lambda p: p.parent.name)
def test_excerpts_are_short(path: Path) -> None:
    too_long = [
        r["id"]
        for r in rows(path)
        if len(r["excerpt"].removesuffix(" …").split()) > snippets.EXCERPT_MAX_WORDS
    ]
    assert not too_long, f"{len(too_long)} excerpts over {snippets.EXCERPT_MAX_WORDS} words"


@pytest.mark.parametrize("path", SNIPPET_FILES, ids=lambda p: p.parent.name)
def test_crawled_snippets_link_to_public_pages(path: Path) -> None:
    bad = [
        r["id"]
        for r in rows(path)
        if r["method"] == "crawl" and not r["source_url"].startswith("https://")
    ]
    assert not bad, f"{len(bad)} crawled snippets without an https:// source"


@pytest.mark.parametrize("path", SNIPPET_FILES, ids=lambda p: p.parent.name)
def test_values_are_ones_the_table_allows(path: Path) -> None:
    allowed = {
        "kind": set(snippets.KINDS),
        "surface": set(snippets.SURFACES),
        "stage": set(snippets.STAGES),
        "method": set(snippets.METHODS),
    }
    for row in rows(path):
        for column, values in allowed.items():
            assert row[column] in values, f"{row['id']}: unknown {column} {row[column]!r}"


@pytest.mark.parametrize("path", SNIPPET_FILES, ids=lambda p: p.parent.name)
def test_ids_are_unique(path: Path) -> None:
    ids = [r["id"] for r in rows(path)]
    assert len(ids) == len(set(ids))
