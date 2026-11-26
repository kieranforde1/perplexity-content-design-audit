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
    assert docs["observation"].startswith("Observed: 'Disabled' appears in 1 snippet")
    assert "Glossary: avoid, use 'Turned off' instead (recommendation)." in helps["observation"]


def test_retired_name_carries_its_published_basis(tmp_path: Path) -> None:
    target = write_target(
        tmp_path, "Widgets,deprecated,Gadgets,,published,https://e.com/news\n"
    )
    (row,) = findings(target)
    assert row["standard_id"] == "glossary:Widgets"
    assert "Glossary: deprecated, use 'Gadgets' instead (published)." in row["observation"]


def test_other_spellings_compare_labels_and_running_text_apart(tmp_path: Path) -> None:
    target = write_target(tmp_path, "Help Panel,use,,,observed,\n")
    rows = {r["observation"].split(",")[0]: r for r in findings(target)}
    # "help Panel" is another spelling. "help panel" may be the general word, so it's
    # left out. "Help Panel" at the start of a sentence is the glossary form.
    running = next(r for k, r in rows.items() if "running text" in k)
    assert "'help Panel' (1)" in running["observation"]
    assert running["count"] == "1"
    # Title case in a heading is the label form, so labels have nothing to report.
    assert not any("labels" in k for k in rows)


def test_sentence_start_capital_is_not_another_spelling(tmp_path: Path) -> None:
    target = write_target(tmp_path, "help panel,use,,,observed,\n")
    observations = " ".join(r["observation"] for r in findings(target))
    assert "'Help Panel'" in observations
    assert "'Help panel'" not in observations


def test_finding_ids_stay_the_same_between_runs(tmp_path: Path) -> None:
    target = write_target(tmp_path, "Disabled,avoid,Turned off,,recommendation,\n")
    assert [r["finding_id"] for r in findings(target)] == [
        r["finding_id"] for r in findings(target)
    ]


def test_a_broken_glossary_stops_the_check(tmp_path: Path) -> None:
    target = write_target(tmp_path, "Widgets,deprecated,,,observed,\n")
    with pytest.raises(ValueError, match="Fix the glossary first"):
        findings(target)


def test_retired_name_ignores_the_lowercase_general_word(tmp_path: Path) -> None:
    target = write_target(tmp_path, "Help Panel,deprecated,Tips,,published,https://e.com/n\n")
    observations = " ".join(r["observation"] for r in findings(target))
    assert "'help panel'" not in observations
    assert "'Help Panel'" in observations


def test_spelling_findings_quote_real_forms_and_count_the_glossary_form(
    tmp_path: Path,
) -> None:
    pieces = [
        ("sentence", "Turn on the Help Panels from settings.", "https://e.com/p1", "help"),
        ("sentence", "Turn on the help Panels from settings.", "https://e.com/p2", "help"),
        ("sentence", "Open the Help Panels list.", "https://e.com/p3", "help"),
    ]
    target = write_target(tmp_path, "Help Panels,use,,,observed,\n", pieces)
    running = next(r for r in findings(target) if "running text" in r["observation"])
    # The text says "help Panels", not the singular, so that's what gets quoted.
    assert "'help Panels' (1)" in running["observation"]
    assert "The glossary form appears 2 times." in running["observation"]


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
    assert "'Gadget Helpers' (1)" in row["observation"]


def test_singular_use_of_a_plural_term_is_not_another_spelling(tmp_path: Path) -> None:
    pieces = [
        ("sentence", "Ask the Gadget Helpers for tips.", "https://e.com/a", "help"),
        ("sentence", "Ask the Gadget Helper for tips.", "https://e.com/b", "help"),
        ("sentence", "Ask the Gadget helpers for tips.", "https://e.com/c", "help"),
    ]
    target = write_target(tmp_path, "Gadget helpers,use,,,observed,\n", pieces)
    # The singular follows the sentence, so only "Gadget Helpers" is another spelling.
    (row,) = findings(target)
    assert "'Gadget Helpers' (1)" in row["observation"]
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
    assert "'Pro plan' (1)" in row["observation"]


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
