import csv
import json
import re
from dataclasses import asdict, replace
from datetime import date
from pathlib import Path

import pytest

from audit import check, config, glossary, pattern_table, snippets, view


def make_target(root: Path) -> config.Target:
    (root / "targets").mkdir()
    (root / "targets" / "example.yaml").write_text(
        "name: example\ndisplay_name: Example\n"
        "sources:\n  - name: docs\n    surface: docs\n    urls: [https://docs.example.com/a]\n"
    )
    target = config.load("example", root)
    hostile = snippets.build(
        "Close the tag </script><script>alert(1)</script> early",
        "sentence", "javascript:alert(1)", "docs", "other", "2026-11-25", "crawl",
    )
    normal = snippets.build(
        "Use the Search API.", "sentence", "https://docs.example.com/a", "docs", "first-use",
        "2026-11-25", "crawl",
    )
    snippets.write(target.data_dir / "snippets.csv", [hostile, normal])
    return target


def test_viewer_is_offline_and_labelled(tmp_path: Path) -> None:
    target = make_target(tmp_path)
    out = view.run(target, today=lambda: date(2026, 11, 26), log=lambda _: None)
    html = out.read_text()
    assert out == tmp_path / "viewer" / "example" / "index.html"
    assert "An unofficial audit of the words " in html
    # Nothing loads from the web, and no font is bundled.
    assert not re.search(r'<(script|link|img)[^>]+(src|href)="https?://', html)
    assert "@font-face" not in html and "url(" not in html
    # The overview comes first and the source data last. The review tabs that follow are
    # hidden unless the page is served by `audit review`.
    tabs = re.findall(r'role="tab" id="tab-([a-z-]+)"[^>]*?(hidden)?>', html)
    assert [t for t, hidden in tabs if not hidden] == [
        "overview", "check", "patterns", "glossary", "source",
    ]
    assert ">Check</button>" in html and ">Findings</button>" not in html
    assert ">Source data</button>" in html
    # headlines.csv keeps `findings` as the tab's value, and a card names the tab Check.
    assert 'findings: "Check"' in html


def test_page_asks_crawlers_not_to_index_or_train(tmp_path: Path) -> None:
    html = view.run(make_target(tmp_path), log=lambda _: None).read_text()
    head = html.split("</head>", 1)[0]
    assert '<meta name="robots" content="noindex, nofollow, noarchive, noai, noimageai">' in head


def test_page_text_cannot_break_out_of_the_data_block(tmp_path: Path) -> None:
    html = view.run(make_target(tmp_path), log=lambda _: None).read_text()
    block = html.split('type="application/json">', 1)[1].split("</script>", 1)[0]
    data = json.loads(block)
    assert "</script><script>alert(1)" in data["snippets"][0]["excerpt"]
    assert "<script>alert" not in block


def write_csv(path: Path, columns: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def add_glossary_and_findings(target: config.Target, snippet_ids: str) -> None:
    write_csv(target.glossary, glossary.COLUMNS, [
        {"term": "Search API", "status": "use", "use_instead": "", "definition": "",
         "basis": "published", "source_url": "https://docs.example.com/a"},
        {"term": "Widget", "status": "avoid", "use_instead": "Tool", "definition": "",
         "basis": "recommendation", "source_url": ""},
    ])
    write_csv(target.data_dir / "findings.csv", check.FINDING_COLUMNS, [
        FINDING | {"snippet_ids": snippet_ids},
    ])


FINDING = {
    "finding_id": "abc", "standard_id": "glossary:Search API", "category": "capitalisation",
    "term": "Search API", "written": "'search API' (2)", "count": "2", "surfaces": "docs",
    "issue": "In running text, 'Search API' is written 'search API' (2).",
    "fix": "Write 'Search API'.", "question": "", "snippet_ids": "",
}


def test_glossary_and_rules_are_included(tmp_path: Path) -> None:
    target = make_target(tmp_path)
    normal = snippets.read(target.public_snippets)[1]
    add_glossary_and_findings(target, f"{normal.id} notarealid")
    data = view.build_data(target, date(2026, 11, 26))
    assert data["glossary"] == glossary.read(target.glossary)
    assert data["rules"] == [{
        "standard_id": "glossary:Search API", "kind": "write", "term": "Search API",
        "use_instead": "", "wording": "", "forms": ["search API"],
        "categories": ["capitalisation"], "count": 2, "surfaces": ["docs"],
        # "Search API" is the glossary form, so nothing in this string is marked.
        "strings": [{
            "id": normal.id, "parts": [("Use the Search API.", False)],
            "source_url": normal.source_url,
        }],
        # An ID the table doesn't have is still counted, so the gap is visible.
        "more": {"strings": 1, "pages": []},
    }]
    assert data["overview"]["glossary_terms"] == 2  # type: ignore[index]
    assert data["overview"]["rules"] == 1  # type: ignore[index]
    assert data["overview"]["breaking_strings"] == 2  # type: ignore[index]
    # The Check tab offers categories in reading order.
    assert data["allowed"]["finding_category"] == list(view.READING_ORDER)  # type: ignore[index]
    assert set(view.READING_ORDER) == set(check.CATEGORIES)


def finding(standard_id: str, category: str, ids: list[str], **more: str) -> dict[str, str]:
    return FINDING | {
        "standard_id": standard_id, "category": category, "term": standard_id.split(":")[1],
        "snippet_ids": " ".join(ids), "count": str(len(ids)),
    } | more


def snippet(text: str, url: str, excerpt: bool = True) -> snippets.Snippet:
    s = snippets.build(text, "sentence", url, "help", "other", "2026-11-25", "crawl")
    return s if excerpt else replace(s, excerpt="")


GLOSSARY = [
    {"term": "Widget", "status": "avoid", "use_instead": "Tool"},
    {"term": "Gizmo", "status": "avoid", "use_instead": ""},
    {"term": "Gadget", "status": "deprecated", "use_instead": "Tool"},
    {"term": "API key", "status": "use", "use_instead": ""},
]


def test_findings_for_one_rule_become_one_row() -> None:
    a = snippet("Open the Widget here.", "https://e.com/a")
    b = snippet("Widgets help.", "https://e.com/b")
    by_id = {s.id: s for s in (a, b)}
    findings = [
        # The same string on two surfaces' findings is still one string.
        finding("glossary:Widget", "avoided term", [a.id], surfaces="help",
                written="'Widget' (1)"),
        finding("glossary:Widget", "avoided term", [b.id, a.id], surfaces="docs help",
                written="'Widgets' (1), 'Widget' (1)"),
    ]
    (rule,) = view.check_rules(findings, GLOSSARY, {}, by_id, "Example")
    assert rule["kind"] == "replace" and rule["use_instead"] == "Tool"
    assert rule["count"] == 2
    assert rule["surfaces"] == ["docs", "help"]
    assert rule["forms"] == ["Widget", "Widgets"]
    # The words that break the rule are marked.
    assert rule["strings"][0]["parts"] == [  # type: ignore[index]
        ("Open the ", False), ("Widget", True), (" here.", False),
    ]


def test_rules_are_stated_from_the_data_and_sorted_for_reading() -> None:
    s = snippet("Copy the API Key, then the API-key.", "https://e.com/a")
    by_id = {s.id: s}
    findings = [
        finding("glossary:API key", "capitalisation", [s.id], written="'API Key' (1)"),
        finding("glossary:API key", "spelling or spacing", [s.id], written="'API-key' (1)"),
        finding("glossary:Gizmo", "avoided term", [s.id, "x1", "x2"]),
        finding("glossary:Widget", "avoided term", [s.id]),
        finding("glossary:Gadget", "deprecated name", [s.id]),
        finding("pattern:reset-link", check.PATTERN_CATEGORY, [s.id]),
    ]
    wordings = {"reset-link": "Check your email for a reset link."}
    rules = view.check_rules(findings, GLOSSARY, wordings, by_id, "Example")
    # Patterns first, then retired names, words to avoid (most strings first), capitals.
    assert [(r["standard_id"], r["kind"]) for r in rules] == [
        ("pattern:reset-link", "pattern"),
        ("glossary:Gadget", "retired"),
        ("glossary:Gizmo", "avoid"),
        ("glossary:Widget", "replace"),
        ("glossary:API key", "write"),
    ]
    assert rules[0]["wording"] == "Check your email for a reset link."
    api_key = rules[-1]
    assert api_key["categories"] == ["capitalisation", "spelling or spacing"]
    assert api_key["forms"] == ["API Key", "API-key"]
    assert [p for p, marked in api_key["strings"][0]["parts"] if marked] == [  # type: ignore[index]
        "API Key", "API-key",
    ]


def test_strings_without_text_are_one_line_with_their_pages() -> None:
    shown = snippet("Open the Widget here.", "https://e.com/a")
    hidden = [snippet(f"Widget number {n}.", f"https://e.com/{n % 2}", excerpt=False)
              for n in range(3)]
    by_id = {s.id: s for s in [shown, *hidden]}
    ids = [shown.id] + [s.id for s in hidden]
    (rule,) = view.check_rules(
        [finding("glossary:Widget", "avoided term", ids)], GLOSSARY, {}, by_id, "Example"
    )
    assert [s["id"] for s in rule["strings"]] == [shown.id]  # type: ignore[attr-defined]
    # Three strings on two pages, each page listed once.
    assert rule["more"] == {"strings": 3, "pages": ["https://e.com/0", "https://e.com/1"]}


def test_check_tab_says_more_strings_once_not_per_string(tmp_path: Path) -> None:
    html = view.run(make_target(tmp_path), log=lambda _: None).read_text()
    assert '"more string"' in html and '"more strings"' in html
    assert "Not in this copy" not in html
    # The generated sentence and the team question aren't on the Check tab.
    script = html.split("// Check:", 1)[1].split("// Patterns", 1)[0]
    assert ".issue" not in script and ".question" not in script


def test_evidence_only_build_uses_committed_rows_with_excerpts(tmp_path: Path) -> None:
    target = make_target(tmp_path)
    hostile, normal = snippets.read(target.public_snippets)
    # The committed copy keeps one excerpt. The local copy has a row the build must not see.
    snippets.write(target.public_snippets, [hostile, replace(normal, excerpt="")])
    local_only = snippets.build(
        "Only on this computer.", "sentence", "https://docs.example.com/a", "docs", "other",
        "2026-11-25", "crawl",
    )
    target.local_snippets.parent.mkdir(parents=True)
    snippets.write(target.local_snippets, [hostile, normal, local_only])
    add_glossary_and_findings(target, normal.id)

    data = view.build_data(target, date(2026, 11, 26), evidence_only=True)
    assert data["snippets"] == [asdict(hostile)]
    assert "only the strings cited as evidence" in str(data["notice"])
    # The numbers still count every committed row, not just the ones with an excerpt.
    assert data["overview"]["strings"] == 2  # type: ignore[index]
    # The dropped row's excerpt is gone, but the rule still links to its page.
    rules = data["rules"]
    assert isinstance(rules, list)
    (rule,) = rules
    assert rule["strings"] == []
    assert rule["more"] == {"strings": 1, "pages": [normal.source_url]}

    out = view.run(target, evidence_only=True, log=lambda _: None)
    assert out.name == "evidence.html"
    assert not (out.parent / "index.html").exists()
    assert "Only on this computer" not in out.read_text()


def test_glossary_proposals_are_only_in_review_mode(tmp_path: Path) -> None:
    target = make_target(tmp_path)
    (target.data_dir / "glossary_proposals.csv").write_text(
        "section,term,change,decision\ndefinitions,Search API,update,\n"
    )
    assert view.build_data(target, date(2026, 11, 26))["glossary_proposals"] == []
    evidence = view.build_data(target, date(2026, 11, 26), evidence_only=True)
    assert evidence["glossary_proposals"] == []
    review_page = view.build_data(target, date(2026, 11, 26), editable=True)
    assert review_page["glossary_proposals"] == [
        {"section": "definitions", "term": "Search API", "change": "update", "decision": ""}
    ]


def test_front_page_numbers(tmp_path: Path) -> None:
    target = make_target(tmp_path)
    typed_row = snippets.build(
        "Ask anything", "button", "web app, home screen", "web-app", "first-use",
        "2026-11-25", "typed",
    )
    snippets.write(target.public_snippets, [*snippets.read(target.public_snippets), typed_row])
    write_csv(target.data_dir / "findings.csv", check.FINDING_COLUMNS, [
        FINDING | {"snippet_ids": "a b"},
        FINDING | {"finding_id": "def", "category": "avoided term", "snippet_ids": "b c"},
        FINDING | {"finding_id": "ghi", "standard_id": "glossary:Widget", "snippet_ids": "d"},
    ])
    data = view.build_data(target, date(2026, 11, 26))
    assert data["overview"] == {
        # A typed app string is a string, but it has no public page.
        "pages": 2, "app_strings": 1, "strings": 3, "glossary_terms": 0,
        # A string that breaks two findings is counted once, and two findings of one
        # rule are one rule.
        "breaking_strings": 4, "rules": 2, "patterns": 0,
    }
    # No local cache here, so the page says most of the text is missing.
    assert "audit extract" in str(data["notice"])
    assert data["values"] == {"surface": ["docs", "web-app"]}


HEADLINES = (
    "title,line,tab,term\n"
    '"Two names, one thing","The Widget page and the Gadget page name the same tool.",'
    "findings,Widget\n"
    "Settled,The glossary says Search API.,glossary,Search API\n"
)


def test_headlines_are_read_from_the_committed_file(tmp_path: Path) -> None:
    target = make_target(tmp_path)
    assert view.build_data(target, date(2026, 11, 26))["headlines"] == []
    (target.data_dir / "headlines.csv").write_text(HEADLINES)
    assert view.build_data(target, date(2026, 11, 26))["headlines"] == [
        {"title": "Two names, one thing",
         "line": "The Widget page and the Gadget page name the same tool.",
         "tab": "findings", "term": "Widget"},
        {"title": "Settled", "line": "The glossary says Search API.", "tab": "glossary",
         "term": "Search API"},
    ]


def test_a_bad_headline_stops_the_build(tmp_path: Path) -> None:
    path = tmp_path / "headlines.csv"
    long_line = " ".join(["word"] * (view.HEADLINE_MAX_WORDS + 1))
    for bad, problem in [
        (f"Long,{long_line},findings,Widget", "keep the line"),
        ("Nowhere,A short line.,strings,Widget", "tab must be one of"),
        ("No term,A short line.,findings,", "term is blank"),
    ]:
        path.write_text("title,line,tab,term\n" + bad + "\n")
        with pytest.raises(ValueError, match=problem):
            view.read_headlines(path)


def test_a_patterns_card_names_a_pattern(tmp_path: Path) -> None:
    path = tmp_path / "headlines.csv"
    path.write_text("title,line,tab,term\nTwo limits,A short line.,patterns,plan-lines\n")
    assert view.read_headlines(path, {"plan-lines"})[0]["tab"] == "patterns"
    with pytest.raises(ValueError, match="not a pattern_id"):
        view.read_headlines(path, {"other-pattern"})


def test_front_page_leads_with_four_cards_and_more_behind_a_button(tmp_path: Path) -> None:
    html = view.run(make_target(tmp_path), log=lambda _: None).read_text()
    assert "var LEAD_CARDS = 4;" in html
    button = re.search(r'<button[^>]+id="more-cards-button"[^>]*>', html)
    assert button, "no More findings button"
    # A real button, so it works from the keyboard, and it says whether it's open.
    assert 'aria-expanded="false"' in button[0] and 'aria-controls="more-cards"' in button[0]
    assert '<div class="cards" id="more-cards" hidden>' in html


PATTERN = {
    "pattern_id": "search-api-intro", "message": "Say what the Search API does.",
    "shared_wording": "Use the Search API to [task].", "basis": "recommendation",
    "variants": "2", "pages": "1", "surfaces": "docs", "question": "Is this the right intro?",
}


def test_patterns_carry_their_advice_and_strings(tmp_path: Path) -> None:
    target = make_target(tmp_path)
    hostile, normal = snippets.read(target.public_snippets)
    # One string without an excerpt, which the Patterns tab has no text to show for.
    snippets.write(target.public_snippets, [replace(hostile, excerpt=""), normal])
    ids = f"{normal.id} {hostile.id}"
    write_csv(target.pattern_table, pattern_table.COLUMNS, [PATTERN | {"string_ids": ids}])
    note = "How to use it: Put it first on the page. The drafts came from two pages."
    write_csv(target.pattern_proposals, pattern_table.PROPOSAL_COLUMNS, [
        PATTERN | {"string_ids": ids, "note": note, "decision": "accept"},
    ])
    data = view.build_data(target, date(2026, 11, 26))
    assert data["patterns"] == [
        PATTERN | {
            "string_ids": ids,
            # Only the advice is shown, not the rest of the note.
            "how_to_use": "Put it first on the page.",
            "strings": [
                {"id": normal.id, "excerpt": "Use the Search API.",
                 "source_url": normal.source_url},
            ],
        }
    ]
    assert data["overview"]["patterns"] == 1  # type: ignore[index]


def test_a_note_without_advice_shows_nothing() -> None:
    assert view.how_to_use("Changed from the research notes. How to use it: later.") == ""
    assert view.how_to_use("How to use it: Example: Ask your admin. Then more.") == (
        "Example: Ask your admin."
    )
