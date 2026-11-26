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


def write_target(root: Path, glossary_rows: str) -> config.Target:
    (root / "targets").mkdir()
    (root / "targets" / "example.yaml").write_text(
        "name: example\ndisplay_name: Example\nsources:\n  - name: docs\n    surface: docs\n"
        "    urls: [https://e.com/d1]\n"
    )
    target = config.load("example", root)
    rows = [snippets.build(t, k, u, s, "other", "2026-11-26", "crawl") for k, t, u, s in PIECES]
    snippets.write(target.local_snippets, rows)
    with target.full_text.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "text"])
        writer.writerows([(s.id, t) for s, (_, t, _, _) in zip(rows, PIECES, strict=True)])
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
    target = write_target(tmp_path, "Help Panels,use,,,observed,\n")
    running = next(r for r in findings(target) if "running text" in r["observation"])
    # The text says "help Panel", not the plural, so that's what gets quoted.
    assert "'help Panel' (1)" in running["observation"]
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
