from pathlib import Path

import pytest

from audit import config, glossary
from audit.cli import main

HEADER = "term,status,use_instead,definition,basis,source_url\n"


def row(**values: str) -> dict[str, str]:
    base = {"term": "Projects", "status": "use", "use_instead": "", "definition": "",
            "basis": "observed", "source_url": ""}
    return base | values


def test_a_plain_use_row_is_fine() -> None:
    assert glossary.problems(row()) == []


def test_unknown_status_and_basis_are_named() -> None:
    found = glossary.problems(row(status="banned", basis="hunch"))
    assert "status 'banned' isn't one of: use, avoid, deprecated" in found
    assert "basis 'hunch' isn't one of: published, observed, recommendation" in found


def test_a_deprecated_term_needs_its_replacement() -> None:
    found = glossary.problems(row(term="Spaces", status="deprecated"))
    assert found == ["a deprecated term needs use_instead: the name that replaced it"]


def test_an_avoid_word_can_wait_for_its_replacement() -> None:
    assert glossary.problems(row(term="portal", status="avoid", basis="recommendation")) == []


def test_a_published_row_needs_a_source() -> None:
    found = glossary.problems(row(basis="published"))
    assert found == ["a published row needs source_url: the https page where it was said"]
    ok = row(basis="published", source_url="https://docs.example.com/migrate.md")
    assert glossary.problems(ok) == []


def test_check_file_reports_repeats_and_a_bad_header(tmp_path: Path) -> None:
    path = tmp_path / "glossary.csv"
    path.write_text(HEADER + "Projects,use,,,observed,\nprojects,use,,,observed,\n")
    assert glossary.check_file(path) == [(3, "term repeats line 2")]
    path.write_text("term,status\nProjects,use\n")
    assert glossary.check_file(path)[0][0] == 1


def test_merge_updates_in_place_and_adds_at_the_end() -> None:
    current = [row(), row(term="Spaces", status="deprecated", use_instead="Projects")]
    accepted = [
        row(term="Projects", definition="A shared  workspace.") | {"change": "update"},
        row(term="whitelist", status="avoid", basis="recommendation") | {"change": "add"},
    ]
    merged = glossary.merge(current, accepted)
    assert [r["term"] for r in merged] == ["Projects", "Spaces", "whitelist"]
    assert merged[0]["definition"] == "A shared workspace."
    assert "change" not in merged[2]
    assert current[0]["definition"] == ""


def test_merge_refuses_an_update_for_a_term_it_does_not_have() -> None:
    with pytest.raises(ValueError, match="no such term"):
        glossary.merge([row()], [row(term="Collections") | {"change": "update"}])
    with pytest.raises(ValueError, match="isn't one of"):
        glossary.merge([row()], [row(term="Collections") | {"change": "rename"}])


def test_check_rows_matches_check_file(tmp_path: Path) -> None:
    path = tmp_path / "glossary.csv"
    path.write_text(HEADER + "Projects,use,,,observed,\nprojects,use,,,observed,\n")
    rows = glossary.read(path)
    assert glossary.check_rows(list(glossary.COLUMNS), rows) == glossary.check_file(path)


def test_glossary_check_command(tmp_path: Path, capsys: object) -> None:
    (tmp_path / "targets").mkdir()
    (tmp_path / "targets" / "example.yaml").write_text(
        "name: example\nsources:\n  - name: docs\n    surface: docs\n"
        "    urls: [https://docs.example.com/a.md]\n"
    )
    target = config.load("example", tmp_path)
    target.data_dir.mkdir(parents=True)
    target.glossary.write_text(HEADER + "Spaces,deprecated,,,observed,\n")
    assert main(["glossary", "--check", "--target", "example", "--root", str(tmp_path)]) == 1


def test_committed_glossary_passes_its_check() -> None:
    target = config.load("perplexity", Path("."))
    assert glossary.check_file(target.glossary) == []
