from pathlib import Path

from audit import config, extract, snippets
from audit.extract import Piece, extract_html, extract_markdown

FIXTURES = Path(__file__).parent / "fixtures"
BOILERPLATE = ("Documentation Index", "Fetch the complete documentation index")


def md_pieces() -> list[Piece]:
    return extract_markdown((FIXTURES / "docs_page.md").read_text(), BOILERPLATE)


def test_markdown_title_and_headings() -> None:
    pieces = md_pieces()
    assert Piece("title", "Quickstart") in pieces
    assert Piece("heading", "Create an API key") in pieces


def test_markdown_skips_boilerplate() -> None:
    assert not any("Documentation Index" in p.text for p in md_pieces())


def test_markdown_ui_labels_use_the_verb_before_them() -> None:
    pieces = md_pieces()
    assert Piece("nav", "API Keys") in pieces
    assert Piece("button", "+ New key") in pieces
    # Bold used for emphasis is not a label.
    assert not any(p.text == "only once" for p in pieces)


def test_markdown_parameters_keep_underscores() -> None:
    pieces = md_pieces()
    assert Piece("parameter", "max_results") in pieces
    assert Piece("parameter", "search_type") in pieces
    sentence = next(p for p in pieces if p.text.startswith("Set max_results"))
    assert sentence.kind == "sentence"


def test_markdown_sentences_are_plain_text() -> None:
    pieces = md_pieces()
    assert Piece("sentence", "Use the search filters to narrow them.") in pieces
    assert Piece("sentence", "Make your first request in a few minutes.") in pieces


def test_markdown_cards_are_nav() -> None:
    assert Piece("nav", "Search API") in md_pieces()


def test_markdown_tables_give_cells() -> None:
    assert Piece("sentence", "Which kind of search to run.") in md_pieces()


def test_markdown_error_messages_come_from_code_but_code_does_not() -> None:
    pieces = md_pieces()
    assert Piece("error", "Invalid API key provided") in pieces
    assert not any("code sample" in p.text for p in pieces)


def test_markdown_code_inside_quoted_blocks_is_skipped() -> None:
    assert not any("third-party page title" in p.text for p in md_pieces())


def test_markdown_accordion_and_tab_titles_are_headings() -> None:
    pieces = md_pieces()
    assert Piece("heading", "Example response") in pieces
    assert Piece("heading", "Python") in pieces
    assert not any(p.text.startswith("[") for p in pieces)


def test_html_pieces() -> None:
    pieces = extract_html((FIXTURES / "help_page.html").read_text())
    assert Piece("title", "Change your plan | Example Help") in pieces
    assert Piece("heading", "Change your plan") in pieces
    assert Piece("nav", "Plans") in pieces
    assert Piece("nav", "Billing") in pieces
    assert Piece("button", "Upgrade now") in pieces
    assert Piece("error", "Your card was declined.") in pieces
    assert Piece("sentence", "You can switch plans at any time.") in pieces
    assert not any("script text" in p.text for p in pieces)
    # Fragments under three words are dropped.
    assert not any(p.text == "Ok." for p in pieces)


def write_target(root: Path) -> None:
    (root / "targets").mkdir()
    (root / "targets" / "example.yaml").write_text(
        "name: example\n"
        "sources:\n"
        "  - name: docs\n"
        "    surface: docs\n"
        "    index: https://docs.example.com/llms.txt\n"
        "stages:\n"
        "  - match: /quickstart\n"
        "    stage: first-use\n"
        "boilerplate: [Documentation Index]\n"
        "typed_strings: data/example/typed_strings.csv\n"
    )
    cache = root / "cache" / "example"
    (cache / "pages").mkdir(parents=True)
    (cache / "pages" / "a.txt").write_text((FIXTURES / "docs_page.md").read_text())
    (cache / "manifest.csv").write_text(
        "url,file,surface,fetched_on,content_type\n"
        "https://docs.example.com/quickstart.md,pages/a.txt,docs,2026-11-25,text/markdown\n"
    )
    (root / "data" / "example").mkdir(parents=True)
    (root / "data" / "example" / "typed_strings.csv").write_text(
        "text,kind,source_url,surface,stage,captured_on\n"
        "Ask anything,button,https://app.example.com/,web-app,first-use,2026-11-20\n"
    )


def test_run_writes_both_tables(tmp_path: Path) -> None:
    write_target(tmp_path)
    target = config.load("example", tmp_path)
    extract.run(target, log=lambda _: None)

    rows = snippets.read(tmp_path / "data" / "example" / "snippets.csv")
    header = (tmp_path / "data" / "example" / "snippets.csv").read_text().splitlines()[0]
    assert header == ",".join(snippets.COLUMNS)
    assert {r.method for r in rows} == {"crawl", "typed"}
    crawled = [r for r in rows if r.method == "crawl"]
    assert {r.stage for r in crawled} == {"first-use"}
    assert all(len(r.excerpt.split()) <= snippets.EXCERPT_MAX_WORDS + 1 for r in rows)

    full = (tmp_path / "cache" / "example" / "snippets_full.csv").read_text()
    assert "Invalid API key provided" in full
    assert len(full.splitlines()) == len(rows) + 1


def test_run_dry_run_writes_nothing(tmp_path: Path) -> None:
    write_target(tmp_path)
    target = config.load("example", tmp_path)
    found = extract.run(target, dry_run=True, log=lambda _: None)
    assert found
    assert not (tmp_path / "data" / "example" / "snippets.csv").exists()
