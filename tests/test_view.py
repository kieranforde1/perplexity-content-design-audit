import csv
import json
import re
from dataclasses import asdict, replace
from datetime import date
from pathlib import Path

from audit import check, config, glossary, snippets, view


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
    assert "Outside-in, public sources, unofficial" in html
    assert "Coming in pass 2" in html
    # Nothing loads from the web.
    assert not re.search(r'<(script|link|img)[^>]+(src|href)="https?://', html)


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
    "finding_id": "abc", "standard_id": "glossary:Search API",
    "observation": "Observed: 'Search API' is also written 'search API'.",
    "count": "2", "surfaces": "docs", "snippet_ids": "",
}


def test_glossary_and_findings_are_included(tmp_path: Path) -> None:
    target = make_target(tmp_path)
    normal = snippets.read(target.public_snippets)[1]
    add_glossary_and_findings(target, f"{normal.id} notarealid")
    data = view.build_data(target, date(2026, 11, 26))
    assert data["glossary"] == glossary.read(target.glossary)
    assert data["findings"] == [
        FINDING | {"snippet_ids": f"{normal.id} notarealid", "evidence": [
            {"id": normal.id, "excerpt": "Use the Search API.", "source_url": normal.source_url},
            # An ID the table doesn't have still shows, so the gap is visible.
            {"id": "notarealid", "excerpt": "", "source_url": ""},
        ]}
    ]
    assert "2 glossary rows, 1 findings" in str(data["summary"])


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
    assert "Evidence only" in str(data["summary"])
    # The dropped row's excerpt is gone, but the finding still links to its page.
    assert data["findings"] == [
        FINDING | {"snippet_ids": normal.id, "evidence": [
            {"id": normal.id, "excerpt": "", "source_url": normal.source_url},
        ]}
    ]

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


def test_summary_counts(tmp_path: Path) -> None:
    data = view.build_data(make_target(tmp_path), date(2026, 11, 26))
    assert str(data["summary"]).startswith("2 snippets from 2 public pages")
    assert data["values"] == {
        "surface": ["docs"], "kind": ["sentence"], "stage": ["first-use", "other"],
    }
