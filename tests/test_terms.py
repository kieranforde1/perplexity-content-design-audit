import csv
from pathlib import Path

from audit import config, snippets, terms
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
    (root / "targets").mkdir()
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
    snippets.write(target.data_dir / "snippets.csv", rows)
    target.cache_dir.mkdir(parents=True)
    with (target.cache_dir / "snippets_full.csv").open("w", newline="") as f:
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
    assert not inside_identifier("Use Deep Research here", 4, 17)


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
