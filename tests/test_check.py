"""Tests for `audit check`. Every snippet here is invented, not copied from a real page."""

import csv
from pathlib import Path

import pytest

from audit import check, config, snippets, terms

HEADER = "term,status,use_instead,definition,basis,source_url\n"

PIECES = [
    # (kind, text, url, surface)
    ("sentence", "Turn on the Help Panel to see more tips.", "https://e.com/h1", "help"),
    ("sentence", "Turn on the help Panel from settings.", "https://e.com/h2", "help"),
    ("sentence", "The help panel opens on the right.", "https://e.com/h3", "help"),
    ("heading", "Open The Help Panel", "https://e.com/h4", "help"),
    ("sentence", "Help Panel tips appear here first.", "https://e.com/h5", "help"),
    ("sentence", "This setting is disabled for guests.", "https://e.com/h1", "help"),
    ("sentence", "Set mode to disabled to stop it.", "https://e.com/d1", "docs"),
    ("parameter", "disabled", "https://e.com/d1", "docs"),
    ("sentence", "Read the old Widgets guide before you move.", "https://e.com/d2", "docs"),
]


def write_target(
    root: Path,
    glossary_rows: str,
    pieces: list[tuple[str, str, str, str]] = PIECES,
    check_yaml: str = "",
) -> config.Target:
    (root / "targets").mkdir()
    (root / "targets" / "example.yaml").write_text(
        "name: example\ndisplay_name: Example\nsources:\n  - name: docs\n    surface: docs\n"
        "    urls: [https://e.com/d1]\n" + check_yaml
    )
    target = config.load("example", root)
    rows = [snippets.build(t, k, u, s, "other", "2026-11-26", "crawl") for k, t, u, s in pieces]
    snippets.write(target.local_snippets, rows)
    with target.full_text.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "text"])
        writer.writerows([(s.id, t) for s, (_, t, _, _) in zip(rows, pieces, strict=True)])
    target.data_dir.mkdir(parents=True, exist_ok=True)
    target.glossary.write_text(HEADER + glossary_rows)
    return target


def findings(target: config.Target) -> list[dict[str, str]]:
    return check.run(target, log=lambda _: None)


def test_avoid_word_is_counted_per_surface_and_skips_parameters(tmp_path: Path) -> None:
    target = write_target(tmp_path, "Disabled,avoid,Turned off,,recommendation,\n")
    rows = findings(target)
    assert [r["surfaces"] for r in rows] == ["docs", "help"]
    docs, helps = rows
    # The parameter "disabled" isn't prose, so only the docs sentence counts.
    assert docs["count"] == "1"
    assert docs["category"] == helps["category"] == "avoided term"
    assert docs["issue"].startswith("'Disabled' is a word to avoid but appears in 1 snippet")
    assert helps["fix"] == (
        "Use 'Turned off' instead. This is a recommendation, not a published rule."
    )
    # Docs may use the word as a value in code, which only the team can confirm.
    assert "literal value" in docs["question"]
    assert helps["question"] == ""


def test_findings_are_written_for_the_team_not_as_observations(tmp_path: Path) -> None:
    target = write_target(tmp_path, "Disabled,avoid,Turned off,,recommendation,\n")
    for row in findings(target):
        assert not row["issue"].startswith("Observed")
        assert "how or why" not in " ".join(row.values())


def test_deprecated_name_carries_its_published_basis(tmp_path: Path) -> None:
    target = write_target(
        tmp_path, "Widgets,deprecated,Gadgets,,published,https://e.com/news\n"
    )
    (row,) = findings(target)
    assert row["standard_id"] == "glossary:Widgets"
    assert row["category"] == "deprecated name"
    assert row["term"] == "Widgets"
    assert row["written"] == "'Widgets' (1)"
    assert row["fix"] == "Use 'Gadgets' instead. This is the published replacement."


def test_an_avoid_word_with_no_replacement_asks_the_team(tmp_path: Path) -> None:
    pieces = [("sentence", "Open the Gizmo from the menu.", "https://e.com/a", "help")]
    target = write_target(tmp_path, "Gizmo,avoid,,,recommendation,\n", pieces)
    (row,) = findings(target)
    assert row["fix"].startswith("Reword without 'Gizmo'.")
    assert row["question"] == "What should these pages say instead of 'Gizmo'?"


def test_other_spellings_compare_labels_and_running_text_apart(tmp_path: Path) -> None:
    target = write_target(tmp_path, "Help Panel,use,,,observed,\n")
    rows = findings(target)
    # "help Panel" is another spelling. "help panel" may be the general word, so it's
    # left out. "Help Panel" at the start of a sentence is the glossary form. Title case
    # in a heading is the label form, so labels have nothing to report.
    (running,) = rows
    assert running["issue"].startswith("In running text,")
    assert running["written"] == "'help Panel' (1)"
    assert running["category"] == "capitalisation"
    assert running["fix"] == "Write 'Help Panel'."
    assert running["count"] == "1"


def test_sentence_start_capital_is_not_another_spelling(tmp_path: Path) -> None:
    target = write_target(tmp_path, "help panel,use,,,observed,\n")
    written = " ".join(r["written"] for r in findings(target))
    assert "'Help Panel'" in written
    assert "'Help panel'" not in written


def test_each_kind_of_variant_gets_its_own_category(tmp_path: Path) -> None:
    pieces = [
        ("sentence", "Make an API key first.", "https://e.com/a", "docs"),
        ("sentence", "Copy the API Key to your app.", "https://e.com/b", "docs"),
        ("sentence", "Send the API-key in a header.", "https://e.com/c", "docs"),
    ]
    target = write_target(tmp_path, "API key,use,,,observed,\n", pieces)
    by_category = {r["category"]: r for r in findings(target)}
    # Case alone is capitalisation. A change of spaces or hyphens is spelling or spacing.
    assert set(by_category) == {"capitalisation", "spelling or spacing"}
    assert by_category["capitalisation"]["written"] == "'API Key' (1)"
    assert by_category["spelling or spacing"]["written"] == "'API-key' (1)"
    # Each row is its own finding, so the two IDs differ.
    assert len({r["finding_id"] for r in by_category.values()}) == 2


def test_variant_category_rules() -> None:
    allowed = {"API key"}
    assert check.variant_category("API Key", allowed) == "capitalisation"
    assert check.variant_category("API-key", allowed) == "spelling or spacing"
    assert check.variant_category("API-Key", allowed) == "spelling or spacing"
    assert check.variant_category("API token", allowed) == "other variant"


def test_finding_ids_stay_the_same_between_runs(tmp_path: Path) -> None:
    target = write_target(tmp_path, "Disabled,avoid,Turned off,,recommendation,\n")
    assert [r["finding_id"] for r in findings(target)] == [
        r["finding_id"] for r in findings(target)
    ]


def test_a_broken_glossary_stops_the_check(tmp_path: Path) -> None:
    target = write_target(tmp_path, "Widgets,deprecated,,,observed,\n")
    with pytest.raises(ValueError, match="Fix the glossary first"):
        findings(target)


def test_deprecated_name_ignores_the_lowercase_general_word(tmp_path: Path) -> None:
    target = write_target(tmp_path, "Help Panel,deprecated,Tips,,published,https://e.com/n\n")
    written = " ".join(r["written"] for r in findings(target))
    assert "'help panel'" not in written
    assert "'Help Panel'" in written


def test_spelling_findings_quote_real_forms_and_count_the_glossary_form(
    tmp_path: Path,
) -> None:
    pieces = [
        ("sentence", "Turn on the Help Panels from settings.", "https://e.com/p1", "help"),
        ("sentence", "Turn on the help Panels from settings.", "https://e.com/p2", "help"),
        ("sentence", "Open the Help Panels list.", "https://e.com/p3", "help"),
    ]
    target = write_target(tmp_path, "Help Panels,use,,,observed,\n", pieces)
    running = next(r for r in findings(target) if "running text" in r["issue"])
    # The text says "help Panels", not the singular, so that's what gets quoted.
    assert running["written"] == "'help Panels' (1)"
    assert "The glossary form appears 2 times." in running["issue"]


def test_finding_evidence_is_committed_and_kept_by_terms(tmp_path: Path) -> None:
    target = write_target(tmp_path, "Disabled,avoid,Turned off,,recommendation,\n")
    cited = {i for r in findings(target) for i in r["snippet_ids"].split()}

    def committed() -> set[str]:
        return {s.id for s in snippets.read(target.public_snippets) if s.excerpt}

    assert cited and cited <= committed()
    # `terms` rewrites the committed copy too, and must not drop the findings evidence.
    terms.run(target, log=lambda _: None)
    assert cited <= committed()


def test_all_caps_header_is_styling_not_a_spelling(tmp_path: Path) -> None:
    pieces = [
        ("sentence", "Open the Help Panel here.", "https://e.com/a", "help"),
        ("sentence", "HELP PANEL", "https://e.com/b", "help"),
    ]
    target = write_target(tmp_path, "Help Panel,use,,,observed,\n", pieces)
    assert findings(target) == []


def test_a_plural_of_a_singular_term_still_counts_as_another_spelling(tmp_path: Path) -> None:
    pieces = [
        ("sentence", "Ask the Gadget Helpers for tips.", "https://e.com/a", "help"),
        ("sentence", "Ask the Gadget helper for tips.", "https://e.com/b", "help"),
    ]
    target = write_target(tmp_path, "Gadget helper,use,,,observed,\n", pieces)
    (row,) = findings(target)
    assert "'Gadget Helpers' (1)" in row["written"]


def test_singular_use_of_a_plural_term_is_not_another_spelling(tmp_path: Path) -> None:
    pieces = [
        ("sentence", "Ask the Gadget Helpers for tips.", "https://e.com/a", "help"),
        ("sentence", "Ask the Gadget Helper for tips.", "https://e.com/b", "help"),
        ("sentence", "Ask the Gadget helpers for tips.", "https://e.com/c", "help"),
    ]
    target = write_target(tmp_path, "Gadget helpers,use,,,observed,\n", pieces)
    # The singular follows the sentence, so only "Gadget Helpers" is another spelling.
    (row,) = findings(target)
    assert "'Gadget Helpers' (1)" in row["written"]
    assert row["count"] == "1"


def test_phrases_that_name_something_else_are_skipped(tmp_path: Path) -> None:
    pieces = [
        ("sentence", "Use a Zed Pro plan for faster renders.", "https://e.com/a", "help"),
        ("sentence", "Upgrade to the Pro plan today.", "https://e.com/b", "help"),
        ("sentence", "Upgrade to the Pro Plan today.", "https://e.com/c", "help"),
    ]
    yaml = "check:\n  other_things:\n    Pro Plan:\n      - Zed Pro plan\n"
    target = write_target(tmp_path, "Pro Plan,use,,,observed,\n", pieces, yaml)
    (row,) = findings(target)
    # "Zed Pro plan" is another company's, so only the one Pro plan sentence counts.
    assert row["count"] == "1"
    assert "'Pro plan' (1)" in row["written"]


def test_a_longer_glossary_term_is_not_counted_again_by_the_shorter_one(
    tmp_path: Path,
) -> None:
    pieces = [
        ("sentence", "Sign in to the Admin Gate to start.", "https://e.com/a", "docs"),
        ("sentence", "Ask your admin to open the gate.", "https://e.com/b", "docs"),
    ]
    rows = "Gate,avoid,,,recommendation,\nAdmin Gate,avoid,,,recommendation,\n"
    target = write_target(tmp_path, rows, pieces)
    by_term = {r["standard_id"]: r for r in findings(target)}
    # The first sentence is reported once, under the longer name.
    assert by_term["glossary:Admin Gate"]["count"] == "1"
    assert by_term["glossary:Gate"]["count"] == "1"
    assert by_term["glossary:Gate"]["snippet_ids"] != by_term["glossary:Admin Gate"]["snippet_ids"]


RETIRED = "Widgets,deprecated,Gadgets,,published,https://e.com/news\n"
RETIRED_PIECES = [
    ("sentence", "Widgets are now Gadgets.", "https://e.com/news", "blog"),
    ("sentence", "Move your Widgets to Gadgets.", "https://e.com/migrate/how-to", "docs"),
    ("sentence", "Added Widgets to the list on 3 March.", "https://e.com/log", "changelog"),
    ("sentence", "Open Widgets from the sidebar.", "https://e.com/guide", "help"),
]
RETIRED_YAML = "check:\n  history_surfaces: [changelog]\n  rename_pages: [/migrate/]\n"


def test_retired_name_is_fine_on_changelog_rename_and_migration_pages(tmp_path: Path) -> None:
    target = write_target(tmp_path, RETIRED, RETIRED_PIECES, RETIRED_YAML)
    (row,) = findings(target)
    assert row["surfaces"] == "help"
    assert row["count"] == "1"


def test_without_the_config_a_retired_name_is_reported_everywhere(tmp_path: Path) -> None:
    target = write_target(tmp_path, RETIRED, RETIRED_PIECES)
    # The announcement page is skipped by the glossary row's own source_url, nothing else is.
    assert sorted(r["surfaces"] for r in findings(target)) == ["changelog", "docs", "help"]


def test_unknown_history_surface_is_a_config_error(tmp_path: Path) -> None:
    with pytest.raises(config.ConfigError, match="history_surfaces"):
        write_target(tmp_path, RETIRED, RETIRED_PIECES, "check:\n  history_surfaces: [diary]\n")
