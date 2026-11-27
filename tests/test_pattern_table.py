import csv
from pathlib import Path

import pytest

from audit import config, pattern_table, snippets
from audit.cli import main

KNOWN = {"aaa111", "bbb222", "ccc333"}


def row(**values: str) -> dict[str, str]:
    base = {
        "pattern_id": "reset-link",
        "message": "We sent you a link to reset your password.",
        "shared_wording": "Check your email for a link to reset your password.",
        "basis": "recommendation",
        "variants": "2",
        "pages": "2",
        "surfaces": "help docs",
        "question": "Does the link expire, and should the message say when?",
        "string_ids": "aaa111 bbb222",
    }
    return base | values


def problems(**values: str) -> list[str]:
    return pattern_table.problems(row(**values), KNOWN)


def test_a_plain_row_is_fine() -> None:
    assert problems() == []


def test_required_columns_cant_be_empty() -> None:
    found = problems(pattern_id="", message=" ", shared_wording="", question="")
    for column in ("pattern_id", "message", "shared_wording", "question"):
        assert f"{column} is empty" in found


def test_basis_is_one_the_glossary_allows() -> None:
    assert problems(basis="hunch") == [
        "basis 'hunch' isn't one of: published, observed, recommendation"
    ]


@pytest.mark.parametrize("value", ["0", "-1", "two", "1.5", ""])
def test_counts_are_whole_numbers_above_zero(value: str) -> None:
    found = problems(variants=value, pages=value)
    assert f"variants {value!r} isn't a whole number above 0" in found
    assert f"pages {value!r} isn't a whole number above 0" in found


def test_there_cant_be_more_pages_than_strings() -> None:
    assert problems(pages="3") == ["pages is 3, but there are only 2 string IDs"]


def test_string_ids_are_needed_and_must_be_known() -> None:
    assert "string_ids is empty" in problems(string_ids="")
    assert problems(string_ids="aaa111 zzz999") == [
        "string ID 'zzz999' isn't in the snippets table"
    ]


def test_string_ids_are_separated_by_spaces_not_commas() -> None:
    found = problems(string_ids="aaa111,bbb222", pages="1")
    assert found == ["string ID 'aaa111,bbb222' isn't in the snippets table"]


def test_surfaces_are_ones_the_snippets_table_allows() -> None:
    assert "surfaces is empty" in problems(surfaces="")
    found = problems(surfaces="help forum")
    assert found == [f"surface 'forum' isn't one of: {', '.join(snippets.SURFACES)}"]


def test_message_is_one_sentence() -> None:
    found = problems(message="We sent you a link. Check your email.")
    assert found == ["message is more than one sentence"]


def test_quotes_follow_the_excerpt_limit() -> None:
    long = " ".join(["word"] * 21)
    assert problems(question=f'Is "{long}" right?') == ["question quotes more than 20 words"]
    assert problems(note=f"They wrote “{long}”.") == ["note quotes more than 20 words"]
    short = " ".join(["word"] * 20)
    assert problems(question=f'Is "{short}" right?') == []


def test_decision_is_checked_on_proposals_only() -> None:
    assert pattern_table.problems(row(decision="maybe"), KNOWN) == []
    found = pattern_table.problems(row(decision="maybe"), KNOWN, proposal=True)
    assert found == ["decision 'maybe' isn't blank, accept or reject"]
    for decision in pattern_table.DECISIONS:
        assert pattern_table.problems(row(decision=decision), KNOWN, proposal=True) == []


def test_header_must_match_exactly() -> None:
    columns = list(pattern_table.COLUMNS)
    assert pattern_table.check_rows(columns, [row()], KNOWN) == []
    swapped = [columns[1], columns[0], *columns[2:]]
    assert pattern_table.check_rows(swapped, [row()], KNOWN)[0][0] == 1
    # The proposals file needs its two extra columns, and patterns.csv mustn't have them.
    assert pattern_table.check_rows(columns, [], KNOWN, proposal=True)[0][0] == 1
    proposal_columns = list(pattern_table.PROPOSAL_COLUMNS)
    assert pattern_table.check_rows(proposal_columns, [], KNOWN)[0][0] == 1


def test_pattern_id_is_unique() -> None:
    found = pattern_table.check_rows(list(pattern_table.COLUMNS), [row(), row()], KNOWN)
    assert found == [(3, "pattern_id repeats line 2")]


def write(path: Path, columns: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def make_target(root: Path) -> config.Target:
    (root / "targets").mkdir()
    (root / "targets" / "example.yaml").write_text(
        "name: example\nsources:\n  - name: docs\n    surface: docs\n"
        "    urls: [https://docs.example.com/a.md]\n"
    )
    target = config.load("example", root)
    target.data_dir.mkdir(parents=True)
    strings = [
        snippets.build(text, "sentence", url, "help", "other", "2026-11-27", "crawl")
        for text, url in (
            ("Check your inbox for the reset link.", "https://help.example.com/a"),
            ("We emailed you a reset link.", "https://help.example.com/b"),
        )
    ]
    snippets.write(target.public_snippets, strings)
    ids = " ".join(s.id for s in strings)
    write(target.pattern_table, pattern_table.COLUMNS, [row(string_ids=ids, surfaces="help")])
    write(
        target.pattern_proposals,
        pattern_table.PROPOSAL_COLUMNS,
        [row(pattern_id="draft", string_ids=ids, surfaces="help", note="", decision="")],
    )
    return target


def test_patterns_check_command(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    target = make_target(tmp_path)
    args = ["patterns", "--check", "--target", "example", "--root", str(tmp_path)]
    assert main(args) == 0
    assert "pattern_proposals.csv: 1 rows, 0 problems." in capsys.readouterr().out

    rows = pattern_table.read(target.pattern_proposals)
    write(target.pattern_proposals, pattern_table.PROPOSAL_COLUMNS, [rows[0] | {"decision": "ok"}])
    assert main(args) == 1
    out = capsys.readouterr().out
    assert "pattern_proposals.csv line 2: decision 'ok' isn't blank, accept or reject" in out
    # The check only reads. It never writes the candidate list.
    assert not (target.cache_dir / "pattern_candidates.csv").exists()
