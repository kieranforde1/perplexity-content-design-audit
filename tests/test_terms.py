import csv
from pathlib import Path

import pytest

from audit import config, snippets, terms
from audit.cli import main
from audit.terms import inside_identifier, term_key

SENTENCES = {
    "https://docs.example.com/a.md": [
        ("title", "Search API"),
        ("sentence", "Use the Search API to find pages with a query."),
        ("sentence", "Results come back with titles and with dates."),
        ("sentence", "Move from Sonar to the Agent API when you can."),
        ("sentence", "Open SKILL.md to read the skill file."),
    ],
    "https://docs.example.com/b.md": [
        ("sentence", "Call the Search API with a filter."),
        ("sentence", "The search API returns ranked results with snippets."),
        ("sentence", "Every Agent API run can call tools with a budget."),
        ("sentence", "Check twice, With care, then test results with a script."),
        ("sentence", "Code in Python calls the Agent API with one request."),
        ("sentence", "The old sonar-pro model still answers Sonar requests."),
    ],
    "https://docs.example.com/cookbook/app.md": [
        ("sentence", "This tutorial uses the Search Api with an example app."),
    ],
}


def write_target(root: Path) -> config.Target:
    (root / "targets").mkdir(parents=True)
    (root / "targets" / "example.yaml").write_text(
        "name: example\n"
        "display_name: Example\n"
        "sources:\n"
        "  - name: docs\n"
        "    surface: docs\n"
        "    index: https://docs.example.com/llms.txt\n"
        "analysis_exclude: [/cookbook/]\n"
        "terms:\n"
        "  seeds: [Agent API, Spaces]\n"
        "  not_terms: [Python]\n"
        "  legacy_names:\n"
        "    - old: Sonar\n"
        "      current: Agent API\n"
        "      source: https://docs.example.com/migrate.md\n"
    )
    target = config.load("example", root)
    rows, full = [], {}
    for url, pieces in SENTENCES.items():
        for kind, text in pieces:
            s = snippets.build(text, kind, url, "docs", "other", "2026-11-25", "crawl")
            rows.append(s)
            full[s.id] = text
    snippets.write(target.local_snippets, rows)
    with target.full_text.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "text"])
        writer.writerows(full.items())
    return target


def by_term(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {r["term"]: r for r in rows}


def candidates(target: config.Target) -> dict[str, dict[str, str]]:
    with (target.data_dir / "term_candidates.csv").open() as f:
        return {r["key"]: r for r in csv.DictReader(f)}


def test_variants_share_a_key() -> None:
    forms = ["Search API", "search API", "Search-API", "Example Search APIs", "search-api"]
    assert {term_key(f, "Example") for f in forms} == {"searchapi"}


def test_identifiers_are_not_uses() -> None:
    assert inside_identifier("Open SKILL.md now", 5, 10)
    assert inside_identifier("Use sonar-deep-research here", 10, 23)
    assert inside_identifier("Set model to sonar-pro now", 13, 22)
    assert not inside_identifier("Use Deep Research here", 4, 17)


def test_possessives_share_the_key() -> None:
    assert term_key("Agent API's", "Example") == term_key("Agent API", "Example")
    assert term_key("Computer’s", "Example") == term_key("Computer", "Example")


def test_preferred_form_skips_surfaces_with_only_lowercase() -> None:
    cluster = terms.Cluster("deepresearch")
    cluster.form_by_surface["pricing"]["deep research"] = 1
    cluster.form_by_surface["docs"]["Deep Research"] = 50
    cluster.uses.update({"deep research": 1, "Deep Research": 50})
    assert terms.preferred_form(cluster, "Example") == "Deep Research"


def test_names_are_proposed_with_their_variants(tmp_path: Path) -> None:
    target = write_target(tmp_path)
    rows = by_term(terms.run(target, log=lambda _: None))
    search = rows["Search API"]
    assert search["status"] == "question"
    assert "search API (1)" in search["variants"]
    assert "lowercase" in search["question"]
    # Cookbook pages are left out of analysis.
    assert "Search Api" not in search["variants"]
    assert search["pages"] == "2"


def test_legacy_names_raise_a_question(tmp_path: Path) -> None:
    target = write_target(tmp_path)
    rows = by_term(terms.run(target, log=lambda _: None))
    assert "'Sonar' still appears on 2 pages" in rows["Agent API"]["question"]
    assert "https://docs.example.com/migrate.md" in rows["Agent API"]["question"]


def test_general_words_and_not_terms_are_rejected_with_a_reason(tmp_path: Path) -> None:
    target = write_target(tmp_path)
    terms.run(target, log=lambda _: None)
    found = candidates(target)
    assert found["with"]["decision"] == "rejected"
    assert "general word" in found["with"]["reason"]
    assert found["python"]["reason"] == "on the not_terms list"
    assert found["space"]["reason"] == "seed not found in first-party snippets"
    assert "skill" not in found or found["skill"]["decision"] != "proposed"


def test_reviewer_edits_survive_a_rerun(tmp_path: Path) -> None:
    target = write_target(tmp_path)
    terms.run(target, log=lambda _: None)
    path = target.data_dir / "terms.csv"
    with path.open() as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        if row["term"] == "Search API":
            row["review"] = "accept"
            row["definition"] = "Returns ranked web results for a query."
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=terms.TERM_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    again = by_term(terms.run(target, log=lambda _: None))
    assert again["Search API"]["review"] == "accept"
    assert again["Search API"]["definition"] == "Returns ranked web results for a query."


def edit_row(path: Path, which: str, **changes: str) -> None:
    with path.open() as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        if row["term"] == which:
            row.update(changes)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=terms.TERM_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def test_edits_survive_renaming_the_term_cell(tmp_path: Path) -> None:
    target = write_target(tmp_path)
    terms.run(target, log=lambda _: None)
    path = target.data_dir / "terms.csv"
    edit_row(
        path, "Search API", term="Search API (web)", review="accept", definition="Web results."
    )
    again = by_term(terms.run(target, log=lambda _: None))
    assert again["Search API (web)"]["definition"] == "Web results."


def test_edits_survive_a_term_dropping_out_for_a_run(tmp_path: Path) -> None:
    target = write_target(tmp_path)
    terms.run(target, log=lambda _: None)
    path = target.data_dir / "terms.csv"
    edit_row(path, "Search API", review="accept", definition="Web results.")

    # Hide the term for one run by putting it on the not_terms list.
    yaml = tmp_path / "targets" / "example.yaml"
    original = yaml.read_text()
    yaml.write_text(original.replace("not_terms: [Python]", "not_terms: [Python, Search API]"))
    hidden = by_term(terms.run(config.load("example", tmp_path), log=lambda _: None))
    assert hidden["Search API"]["definition"] == "Web results."
    assert "Not proposed this run (on the not_terms list)" in hidden["Search API"]["question"]

    yaml.write_text(original)
    back = by_term(terms.run(config.load("example", tmp_path), log=lambda _: None))
    assert back["Search API"]["review"] == "accept"
    assert back["Search API"]["pages"] == "2"


def test_questions_quote_forms_that_appear(tmp_path: Path) -> None:
    target = write_target(tmp_path)
    rows = by_term(terms.run(target, log=lambda _: None))
    question = rows["Search API"]["question"]
    assert "('search API', 1 time)" in question
    assert "1 times" not in question


def add_rows(target: config.Target, pieces: list[tuple[str, str, str]]) -> None:
    """Add (kind, text, url) snippets to the local tables."""
    rows = snippets.read(target.local_snippets)
    extra = [snippets.build(t, k, u, "docs", "other", "2026-11-25", "crawl") for k, t, u in pieces]
    snippets.write(target.local_snippets, rows + extra)
    with target.full_text.open("a", newline="") as f:
        csv.writer(f).writerows([(s.id, s.excerpt) for s in extra])


def test_labels_and_running_text_are_compared_separately(tmp_path: Path) -> None:
    target = write_target(tmp_path)
    pages = [f"https://docs.example.com/ref{i}.md" for i in range(3)]
    add_rows(target, [("nav", "API Reference", u) for u in pages])
    add_rows(target, [("sentence", f"See the API reference for page {i}.", u)
                      for i, u in enumerate(pages)])
    rows = by_term(terms.run(target, log=lambda _: None))
    ref = next(r for k, r in rows.items() if k.lower() == "api reference")
    # The case difference between nav and sentences is a note, not a question.
    assert ref["status"] == "consistent"
    assert "ways" not in ref["question"]
    assert ref["note"] == (
        "Labels use title case ('API Reference') and running text uses sentence case "
        "('API reference')."
    )


def test_months_units_and_formats_are_rejected_by_rule(tmp_path: Path) -> None:
    target = write_target(tmp_path)
    pages = [f"https://docs.example.com/m{i}.md" for i in range(2)]
    add_rows(target, [("sentence", f"Released in November with a PNG export of 5 MiB {i}.", u)
                      for i, u in enumerate(pages)])
    terms.run(target, log=lambda _: None)
    found = candidates(target)
    assert found["november"]["reason"] == "a month name"
    assert found["png"]["reason"] == "a file format"
    assert found["mib"]["reason"] == "a unit"


def test_thin_evidence_is_too_few_to_tell(tmp_path: Path) -> None:
    target = write_target(tmp_path)
    pages = [f"https://docs.example.com/c{i}.md" for i in range(2)]
    add_rows(target, [("sentence", f"Open the Control Room on page {i}.", u)
                      for i, u in enumerate(pages)])
    rows = by_term(terms.run(target, log=lambda _: None))
    assert rows["Control Room"]["status"] == "too few to tell"
    assert "too few to tell" in rows["Control Room"]["question"]


def test_a_form_counts_once_per_page_and_excerpt(tmp_path: Path) -> None:
    target = write_target(tmp_path)
    url = "https://docs.example.com/twice.md"
    add_rows(target, [
        ("sentence", "The Agent API calls the Agent API again for you.", url),
        ("heading", "The Agent API calls the Agent API again for you.", url),
    ])
    before = int(by_term(terms.run(write_target(tmp_path / "plain"), log=lambda _: None))
                 ["Agent API"]["uses"])
    after = int(by_term(terms.run(target, log=lambda _: None))["Agent API"]["uses"])
    assert after == before + 1


def test_approved_repeated_text_counts_on_one_page(tmp_path: Path) -> None:
    target = write_target(tmp_path)
    pages = [f"https://docs.example.com/n{i}.md" for i in range(12)]
    add_rows(target, [("nav", "Fleet Manager", u) for u in pages])
    add_rows(target, [("sentence", "Use the Fleet Manager to see runs.", pages[0])])
    terms.run(target, log=lambda _: None)
    with (target.cache_dir / "repeated_text.csv").open() as f:
        repeats = {r["text"]: r for r in csv.DictReader(f)}
    assert repeats["Fleet Manager"]["pages"] == "12"
    assert repeats["Fleet Manager"]["approved"] == ""

    yaml = tmp_path / "targets" / "example.yaml"
    approved = "terms:\n  repeated_text: [Fleet Manager]\n"
    yaml.write_text(yaml.read_text().replace("terms:\n", approved))
    rows = by_term(terms.run(config.load("example", tmp_path), log=lambda _: None))
    assert rows["Fleet Manager"]["uses"] == "2"


def test_terms_without_the_local_table_says_what_to_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = write_target(tmp_path)
    target.local_snippets.unlink()
    assert main(["terms", "--target", "example", "--root", str(tmp_path)]) == 2
    err = capsys.readouterr().err
    assert "Run `audit fetch --target example` and then `audit extract" in err
    assert "Traceback" not in err


def test_title_only_labels_are_not_terms(tmp_path: Path) -> None:
    target = write_target(tmp_path)
    rows = snippets.read(target.local_snippets)
    extra = [
        snippets.build("Use Search", "title", url, "docs", "other", "2026-11-25", "crawl")
        for url in ("https://docs.example.com/c.md", "https://docs.example.com/d.md")
    ]
    snippets.write(target.local_snippets, rows + extra)
    with target.full_text.open("a", newline="") as f:
        csv.writer(f).writerows([(s.id, "Use Search") for s in extra])
    terms.run(target, log=lambda _: None)
    found = candidates(target)
    assert found["usesearch"]["decision"] == "rejected"
    assert "never capitalised in running text" in found["usesearch"]["reason"]
