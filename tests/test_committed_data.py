"""Checks on the data that's actually published in this repo, not just the code that writes it.

The rules come from how the audit handles other people's text: the repo commits evidence,
not a copy of the company's pages. So only a capped number of excerpts are filled in,
each one is short, every crawled snippet links to a real public page, and the table's
shape never drifts.
"""

import csv
import re
from pathlib import Path

import pytest

from audit import config, glossary, pattern_table, snippets, view
from audit.cli import main

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
def test_only_evidence_excerpts_are_committed(path: Path) -> None:
    limit = config.load(path.parent.name, REPO_ROOT).max_committed_excerpts
    filled = sum(1 for r in rows(path) if r["excerpt"])
    assert filled <= limit, f"{filled} excerpts committed, over the limit of {limit}"


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


@pytest.mark.parametrize(
    "path", sorted(REPO_ROOT.glob("data/*/typed_strings.csv")), ids=lambda p: p.parent.name
)
def test_typed_app_strings_are_short(path: Path) -> None:
    limit = snippets.EXCERPT_MAX_WORDS
    too_long = [r["text"] for r in rows(path) if len(r["text"].split()) > limit]
    assert not too_long, f"typed strings over {snippets.EXCERPT_MAX_WORDS} words: {too_long}"


@pytest.mark.parametrize(
    "path", sorted(REPO_ROOT.glob("data/*/glossary_proposals.csv")), ids=lambda p: p.parent.name
)
def test_glossary_proposals_can_be_applied(path: Path) -> None:
    # The review page finds a proposal by its term, and an update needs a row to replace.
    proposals = rows(path)
    terms = [glossary.key(r["term"]) for r in proposals]
    assert len(terms) == len(set(terms)), "a term is proposed twice"
    have = {glossary.key(r["term"]) for r in glossary.read(path.parent / "glossary.csv")}
    for r in proposals:
        assert r["change"] in glossary.CHANGES, r["term"]
        assert r["decision"] in ("", "accept", "reject", "applied"), r["term"]
        if r["change"] == "update":
            assert glossary.key(r["term"]) in have, f"{r['term']}: no glossary row to update"


@pytest.mark.parametrize(
    "path", sorted(REPO_ROOT.glob("data/*/headlines.csv")), ids=lambda p: p.parent.name
)
def test_headlines_are_short_and_lead_to_evidence(path: Path) -> None:
    pattern_ids = {p["pattern_id"] for p in pattern_table.read(path.parent / "patterns.csv")}
    headlines = view.read_headlines(path, pattern_ids)
    assert headlines, "headlines.csv has no rows"
    glossary_terms = {glossary.key(r["term"]) for r in glossary.read(path.parent / "glossary.csv")}
    for h in headlines:
        # A patterns card opens one pattern, so its term has to be a pattern_id. Every other
        # card opens its tab searched for the term, so the term has to be a glossary term.
        if h["tab"] == "patterns":
            assert h["term"] in pattern_ids, f"{h['term']}: not in patterns.csv"
        else:
            assert glossary.key(h["term"]) in glossary_terms, f"{h['term']}: not in the glossary"
        # Anything quoted from the company's text follows the excerpt limit.
        for quote in re.findall(r'"([^"]+)"', h["line"]):
            assert len(quote.split()) <= snippets.EXCERPT_MAX_WORDS, quote


@pytest.mark.parametrize(
    "path", sorted(REPO_ROOT.glob("data/*/pattern_proposals.csv")), ids=lambda p: p.parent.name
)
def test_pattern_files_pass_their_check(path: Path) -> None:
    # The same check a person runs: `audit patterns --check`. Every string ID has to be in
    # the committed snippets table, so a re-crawl that changes an ID shows up here.
    target = path.parent.name
    assert main(["patterns", "--check", "--target", target, "--root", str(REPO_ROOT)]) == 0


@pytest.mark.parametrize("path", SNIPPET_FILES, ids=lambda p: p.parent.name)
def test_ids_are_unique(path: Path) -> None:
    ids = [r["id"] for r in rows(path)]
    assert len(ids) == len(set(ids))
