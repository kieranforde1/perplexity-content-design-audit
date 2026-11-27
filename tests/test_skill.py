"""Tests for `audit skill` and the check script it ships. Every term and sentence here is
invented, not copied from a real page, except where a test reads the committed skill."""

import csv
import importlib.util
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from audit import check, config, pattern_table, skill, snippets

REPO_ROOT = Path(__file__).resolve().parent.parent
GLOSSARY_HEADER = "term,status,use_instead,definition,basis,source_url\n"
GLOSSARY = (
    "Help Panel,use,,The panel of tips on the right.,observed,\n"
    "Deep Dive,use,,A long search.,observed,\n"
    "Gadget,deprecated,Tool,The old name for a Tool.,observed,\n"
    "disabled,avoid,turned off,,recommendation,\n"
    "Admin Portal,avoid,Admin Console,,recommendation,\n"
    "portal,avoid,Admin Console,,recommendation,\n"
)
# (line in a draft, what the checker should report as (category, term)), all invented.
CASES = [
    ("Turn on the Help Panel to see tips.", []),
    ("Turn on the help Panel from settings.", [("capitalization", "Help Panel")]),
    ("The help panel opens on the right.", []),
    ("# Open The Help Panel", []),
    ("This setting is disabled for guests.", [("avoided term", "disabled")]),
    ("Gadgets were renamed last year.", [("deprecated name", "Gadget")]),
    ("Your gadget list is empty.", []),
    ("Open the Admin Portal to start.", [("avoided term", "Admin Portal")]),
    ("Try a deep Dive on long questions.", [("capitalization", "Deep Dive")]),
    ("Try a Deep-Dive today.", [("spelling or spacing", "Deep Dive")]),
]
PATTERNS_HEADER = ",".join(pattern_table.COLUMNS) + "\n"
PROPOSALS_HEADER = ",".join(pattern_table.PROPOSAL_COLUMNS) + "\n"


def write_target(root: Path) -> config.Target:
    """An invented target with committed data only: strings, glossary and one pattern."""
    (root / "targets").mkdir()
    (root / "targets" / "example.yaml").write_text(
        "name: example\ndisplay_name: Example\nsources:\n  - name: help\n    surface: help\n"
        "    urls: [https://e.com/h1]\n  - name: brand\n    surface: brand\n"
        "    urls: [https://e.com/brand]\n"
    )
    target = config.load("example", root)
    rows = [
        snippets.build("Ask your admin to turn it on.", "sentence", "https://e.com/h1", "help",
                       "other", "2026-11-20", "crawl"),
        snippets.build("Ask an admin for access.", "sentence", "https://e.com/h2", "help",
                       "other", "2026-11-22", "crawl"),
    ]
    snippets.write(target.public_snippets, rows)
    target.glossary.write_text(GLOSSARY_HEADER + GLOSSARY)
    ids = " ".join(r.id for r in rows)
    pattern = (
        f"ask-admin,You can't fix this yourself.,Ask your admin to [action].,recommendation,"
        f"2,2,help,Is there one admin role?,{ids}"
    )
    target.pattern_table.write_text(PATTERNS_HEADER + pattern + "\n")
    target.pattern_proposals.write_text(
        PROPOSALS_HEADER + pattern + ",How to use it: Name the action. More notes.,accept\n"
    )
    return target


def load_script(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_text", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def built(tmp_path: Path) -> Path:
    target = write_target(tmp_path)
    skill.run(target, log=lambda _: None)
    return skill.skill_dir(target)


def test_skill_writes_its_files(built: Path) -> None:
    files = sorted(str(p.relative_to(built)) for p in built.rglob("*") if p.is_file())
    assert files == [
        "SKILL.md", "references/glossary.csv", "references/patterns.csv",
        "scripts/check_text.py",
    ]
    text = (built / "SKILL.md").read_text()
    assert text.startswith("---\nname: content-standards\n")
    assert "{{" not in text
    assert "evidence_captured: '2026-11-20 to 2026-11-22'" in text
    assert "| Gadget | Tool |" in text
    assert "| Admin Portal, portal | Admin Console |" in text
    # SKILL.md lists which messages have a string. The strings stay in the references,
    # so a long string isn't loaded every time the skill is.
    assert "Ask your admin to [action]." not in text
    assert "(https://e.com/brand)" in text
    with (built / "references" / "patterns.csv").open(newline="") as f:
        (row,) = list(csv.DictReader(f))
    assert row["shared_wording"] == "Ask your admin to [action]."
    # Only the first sentence of the "How to use it:" note is for the writer.
    assert row["how_to_use"] == "Name the action."
    assert list(row) == list(skill.PATTERN_COLUMNS)
    assert 'COMPANY = "Example"' in (built / "scripts" / "check_text.py").read_text()


def test_words_to_avoid_are_in_alphabetical_order(built: Path) -> None:
    text = (built / "SKILL.md").read_text()
    table = text.split("### Words to avoid")[1].split("\n\n")[1]
    first_words = [line.split(" | ")[0].lstrip("| ") for line in table.splitlines()[2:]]
    assert first_words == sorted(first_words, key=str.lower)


def test_the_config_names_the_skill_and_its_folder(tmp_path: Path) -> None:
    target = write_target(tmp_path)
    assert skill.skill_dir(target) == tmp_path / "content-standards"
    assert config.load("perplexity", REPO_ROOT).skill_name == "pplx-content"


def test_script_flags_each_case(built: Path) -> None:
    script = load_script(built / "scripts" / "check_text.py")
    entries = script.read_glossary()
    for line, expected in CASES:
        found = [
            (rule.split(" '")[0], term) for _, _, term, rule in script.problems([line], entries)
        ]
        assert found == expected, line


def test_script_reports_line_and_column_and_exits_1(built: Path, tmp_path: Path) -> None:
    draft = tmp_path / "draft.txt"
    draft.write_text("All good here.\nOpen the Admin Portal.\n")
    result = subprocess.run(
        [sys.executable, str(built / "scripts" / "check_text.py"), str(draft)],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert result.stdout == "2:10: avoided term 'Admin Portal'. Use 'Admin Console' instead.\n"


def test_script_passes_clean_text_from_stdin(built: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(built / "scripts" / "check_text.py")],
        input="Turn on the Help Panel.\nThe help panel opens.\n", capture_output=True, text=True,
    )
    assert (result.returncode, result.stdout) == (0, "")


def test_script_skips_code_in_backticks(built: Path) -> None:
    script = load_script(built / "scripts" / "check_text.py")
    assert script.problems(["Set `disabled` to true."], script.read_glossary()) == []


def test_script_and_audit_check_agree(built: Path, tmp_path: Path) -> None:
    """The same invented sentences, run through `audit check` and through the script,
    give the same (sentence, category, term) problems."""
    root = tmp_path / "check"
    (root / "targets").mkdir(parents=True)
    (root / "targets" / "example.yaml").write_text(
        "name: example\ndisplay_name: Example\nsources:\n  - name: help\n    surface: help\n"
        "    urls: [https://e.com/h1]\n"
    )
    target = config.load("example", root)
    pieces = []
    for i, (line, _) in enumerate(CASES):
        heading = line.startswith("# ")
        text = line.removeprefix("# ")
        pieces.append((text, "heading" if heading else "sentence", f"https://e.com/p{i}"))
    rows = [snippets.build(t, k, u, "help", "other", "2026-11-26", "crawl") for t, k, u in pieces]
    snippets.write(target.local_snippets, rows)
    with target.full_text.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "text"])
        writer.writerows([(s.id, t) for s, (t, _, _) in zip(rows, pieces, strict=True)])
    target.data_dir.mkdir(parents=True)
    target.glossary.write_text(GLOSSARY_HEADER + GLOSSARY)
    text_of = {s.id: t for s, (t, _, _) in zip(rows, pieces, strict=True)}
    from_check = {
        (text_of[i], f["category"], f["term"])
        for f in check.run(target, log=lambda _: None)
        for i in f["snippet_ids"].split()
    }

    script = load_script(built / "scripts" / "check_text.py")
    entries = script.read_glossary()
    from_script = {
        (line.removeprefix("# "), rule.split(" '")[0], term)
        for line, _ in CASES
        for _, _, term, rule in script.problems([line], entries)
    }
    assert from_script == from_check
    assert len(from_check) == sum(len(expected) for _, expected in CASES)


# The committed skill.

COMMITTED = REPO_ROOT / config.load("perplexity", REPO_ROOT).skill_name


def test_committed_skill_matches_a_fresh_build() -> None:
    """If this fails, run `uv run audit skill --target perplexity` and commit the result."""
    fresh = skill.render(config.load("perplexity", REPO_ROOT))
    on_disk = {
        str(p.relative_to(COMMITTED)): p.read_text(encoding="utf-8")
        for p in COMMITTED.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    }
    assert sorted(on_disk) == sorted(fresh)
    for name, text in fresh.items():
        assert on_disk[name] == text, f"{name} is stale: see this test's docstring"


def committed_text() -> str:
    files = sorted(p for p in COMMITTED.rglob("*") if p.is_file() and p.suffix != ".pyc")
    return "\n".join(p.read_text(encoding="utf-8") for p in files)


@pytest.mark.parametrize("name", ["glossary.csv", "patterns.csv"])
def test_committed_skill_quotes_are_short(name: str) -> None:
    """Text in quotation marks in the references is 20 words at most. This one runs in CI,
    where there's no cache to compare with."""
    with (COMMITTED / "references" / name).open(newline="", encoding="utf-8") as f:
        too_long = [p for row in csv.DictReader(f) for p in pattern_table.long_quotes(row)]
    assert not too_long


def test_committed_skill_has_no_long_excerpt_from_the_cache() -> None:
    """No run of 21 words in the skill matches the full text of any Perplexity string.

    Only runs where the local cache is there (it's gitignored, so not in CI)."""
    full_text = config.load("perplexity", REPO_ROOT).full_text
    if not full_text.exists():
        pytest.skip("no local cache")
    size = snippets.EXCERPT_MAX_WORDS + 1
    word = re.compile(r"[a-z0-9]+")

    def runs(text: str) -> set[str]:
        words = word.findall(text.lower())
        return {" ".join(words[i:i + size]) for i in range(len(words) - size + 1)}

    in_skill = runs(committed_text())
    with full_text.open(newline="", encoding="utf-8") as f:
        copied = [r["id"] for r in csv.DictReader(f) if runs(r["text"]) & in_skill]
    assert not copied, f"the skill copies more than 20 words from: {copied[:5]}"
