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


def test_longer_fence_is_not_closed_by_a_shorter_one() -> None:
    page = (
        "# Page\n\n"
        "````yaml\n"
        "example: |\n"
        "  ```\n"
        "  components: schemas: Request\n"
        "````\n\n"
        "This sentence comes after the code block.\n"
    )
    pieces = extract_markdown(page)
    assert not any("components" in p.text for p in pieces)
    assert Piece("sentence", "This sentence comes after the code block.") in pieces


def test_error_messages_allow_escaped_quotes_and_skip_single_words() -> None:
    page = (
        "```json\n"
        '{"message": "Field \\"model\\" is required", "detail": "slow"}\n'
        "```\n"
    )
    pieces = extract_markdown(page)
    assert Piece("error", 'Field "model" is required') in pieces
    assert not any(p.text == "slow" for p in pieces)


def test_markdown_code_inside_quoted_blocks_is_skipped() -> None:
    assert not any("third-party page title" in p.text for p in md_pieces())


def test_markdown_accordion_and_tab_titles_are_headings() -> None:
    pieces = md_pieces()
    assert Piece("heading", "Example response") in pieces
    assert Piece("heading", "Python") in pieces
    assert not any(p.text.startswith("[") for p in pieces)


def test_markdown_line_break_backslash_ends_the_text() -> None:
    pieces = extract_markdown(
        "**Short answer:** No, you can use it without one.\\\n\\\nIt updates itself.\\\n"
    )
    assert Piece("sentence", "Short answer: No, you can use it without one.") in pieces
    assert Piece("sentence", "It updates itself.") in pieces
    assert not any("\\" in p.text for p in pieces)


def test_markdown_escaped_punctuation_is_shown_plainly() -> None:
    pieces = extract_markdown("Plans cost \\$5\\* less on the yearly option.")
    assert pieces == [Piece("sentence", "Plans cost $5* less on the yearly option.")]


def test_markdown_list_item_line_break_backslash_is_dropped() -> None:
    pieces = extract_markdown("- Open the store in your browser.\\\n- Search for the extension.\n")
    assert Piece("sentence", "Open the store in your browser.") in pieces


def test_markdown_linked_screenshot_leaves_only_its_alt_text() -> None:
    pieces = extract_markdown("[![Delete account dialog in settings](https://e.com/a.png)](https://e.com/a.png)")
    assert pieces == [Piece("sentence", "Delete account dialog in settings")]


def test_markdown_front_matter_is_skipped() -> None:
    page = "---\ntitle: Example plan\ndescription: Not reader text.\n---\n\n# Example plan\n"
    assert extract_markdown(page) == [Piece("title", "Example plan")]


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


PRICING_CARD = """
<div class="card">
  <div><svg role="img" aria-label="Example Plus"><use href="#logo"></use></svg></div>
  <p>Built for people who use it every single day.</p>
  <div><span>$12</span><span>per month</span></div>
  <div><span><svg aria-hidden="true"></svg></span><span>500 bonus credits</span></div>
  <p>Switch plans <span>at any time</span> from settings.</p>
  <button>A</button>
  <span>A long box of text that goes on well past a label. It reads like running text.</span>
</div>
"""


def test_html_box_text_is_kept_as_labels() -> None:
    pieces = extract_html(PRICING_CARD)
    assert Piece("label", "Example Plus") in pieces
    assert Piece("label", "$12") in pieces
    assert Piece("label", "per month") in pieces
    assert Piece("label", "500 bonus credits") in pieces
    # A span inside a sentence stays part of that sentence.
    assert Piece("sentence", "Switch plans at any time from settings.") in pieces
    assert not any(p.text == "at any time" for p in pieces)
    # One character on its own is a font sample or icon.
    assert not any(p.text == "A" for p in pieces)
    # Long box text is split into sentences instead.
    assert Piece("sentence", "It reads like running text.") in pieces


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


def test_run_writes_the_local_table_and_a_committed_copy(tmp_path: Path) -> None:
    write_target(tmp_path)
    target = config.load("example", tmp_path)
    extract.run(target, log=lambda _: None)

    local = snippets.read(target.local_snippets)
    header = target.public_snippets.read_text().splitlines()[0]
    assert header == ",".join(snippets.COLUMNS)
    assert {r.method for r in local} == {"crawl", "typed"}
    crawled = [r for r in local if r.method == "crawl"]
    assert {r.stage for r in crawled} == {"first-use"}
    assert all(r.excerpt for r in local)

    # The committed copy keeps every row, but with no terms.csv yet only typed strings
    # are evidence, so only they keep their excerpt.
    public = snippets.read(target.public_snippets)
    assert [r.id for r in public] == [r.id for r in local]
    assert {r.method for r in public if r.excerpt} == {"typed"}

    full = target.full_text.read_text()
    assert "Invalid API key provided" in full
    assert len(full.splitlines()) == len(local) + 1


def test_bad_typed_strings_are_skipped_with_their_line(tmp_path: Path) -> None:
    write_target(tmp_path)
    with (tmp_path / "data" / "example" / "typed_strings.csv").open("a") as f:
        f.write("Too far,button,https://app.example.com/,billboard,first-use,2026-11-20\n")
    messages: list[str] = []
    extract.run(config.load("example", tmp_path), log=messages.append)
    assert any("line 3" in m and "surface" in m for m in messages)


def test_run_dry_run_writes_nothing(tmp_path: Path) -> None:
    write_target(tmp_path)
    target = config.load("example", tmp_path)
    found = extract.run(target, dry_run=True, log=lambda _: None)
    assert found
    assert not target.public_snippets.exists()
    assert not target.local_snippets.exists()
