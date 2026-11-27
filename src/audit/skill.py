"""`audit skill`: build a content skill from the glossary and the patterns.

The skill is what a writer, or an AI writing tool, uses on new text: the settled terms,
the strings to reuse, and a script that checks a draft the same way every time. It's
written to a folder at the top of the repo, named by the config's `skill.name`, and
committed.

SKILL.md holds the rules and the way of working, plus the two short lists a writer has
to keep in mind while drafting (retired names and words to avoid). The full glossary and
the pattern strings live only in references/, so they're read when needed, not every
time the skill loads.

Everything in it comes from committed data (glossary.csv, patterns.csv and the "How to
use it:" start of each note in pattern_proposals.csv), so the audit and the skill can't
drift apart. There's no build date: the only dates are the evidence range, taken from
the strings table. So the same data always gives the same files, and a test can compare
the committed copy with a fresh build.

The layout of SKILL.md is in skill_template.md. The check script is skill_check_text.py,
copied with the company name filled in.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Callable
from pathlib import Path

from audit import glossary, pattern_table, patterns, snippets
from audit.config import Target

VERSION = "0.3"
TEMPLATE = Path(__file__).parent / "skill_template.md"
SCRIPT = Path(__file__).parent / "skill_check_text.py"
PATTERN_COLUMNS = ("pattern_id", "message", "shared_wording", "how_to_use", "question")
HOW_TO_USE = "How to use it:"
# Benchmark prompts that don't depend on the data. The rest are built from it.
GENERAL_PROMPTS = (
    "Write the empty state for a list the reader hasn't added anything to yet.",
    "Decide whether a new feature name belongs in the glossary, and say what evidence it needs.",
    "Audit a short help article that names one plan two ways, and return the QA report.",
)


def skill_dir(target: Target) -> Path:
    return target.root / target.skill_name


def to_csv(columns: tuple[str, ...], rows: list[dict[str, str]]) -> str:
    """A CSV file's text, with plain newlines so the output is the same on every machine."""
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=columns, lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def cell(text: str) -> str:
    """Text that's safe inside a Markdown table cell."""
    return " ".join(text.split()).replace("|", "\\|")


def how_to_use(note: str) -> str:
    """The first sentence after "How to use it:" in a proposal's note, or ''.

    The rest of a note explains how the draft was made, which is for the reviewer, not
    the writer."""
    note = note.strip()
    if not note.startswith(HOW_TO_USE):
        return ""
    return patterns.SENTENCE_END.split(note.removeprefix(HOW_TO_USE).strip())[0]


def evidence_dates(target: Target) -> tuple[str, str]:
    """The first and last capture dates in the committed strings table."""
    with target.public_snippets.open(newline="", encoding="utf-8") as f:
        dates = sorted({r["captured_on"] for r in csv.DictReader(f) if r["captured_on"]})
    if not dates:
        raise ValueError(f"No capture dates in {target.public_snippets}")
    return dates[0], dates[-1]


def brand_link(target: Target) -> str:
    """A link to the company's brand page, if the config lists one."""
    for source in target.sources:
        if source.surface == "brand" and source.urls:
            return f" ({source.urls[0]})"
    return ""


def alphabetical(text: str) -> str:
    return text.lower()


def terms_section(entries: list[dict[str, str]], company: str) -> str:
    """The two lists a writer keeps in mind while drafting. Everything else about a term,
    including the words to use, is in references/glossary.csv."""
    bases = {b: sum(1 for e in entries if e["basis"] == b) for b in glossary.BASES}
    lines = [
        f"`references/glossary.csv` has {len(entries)} terms. {bases['published']} come "
        f"from {company}'s own pages, {bases['observed']} from how its public text uses "
        f"them, and {bases['recommendation']} are this audit's suggestions.",
        "",
        "### Retired names",
        "",
        "| Retired name | Current name |",
        "| --- | --- |",
    ]
    retired = [e for e in entries if e["status"] == "deprecated"]
    for e in sorted(retired, key=lambda e: alphabetical(e["term"])):
        lines.append(f"| {cell(e['term'])} | {cell(e['use_instead'])} |")
    # Words with the same replacement share a row, so the table stays short. Rows sort by
    # the first word to avoid, so a writer can find a word quickly.
    by_replacement: dict[str, list[str]] = {}
    for e in entries:
        if e["status"] == "avoid":
            replacement = e["use_instead"].strip() or "Reword without it"
            by_replacement.setdefault(replacement, []).append(e["term"])
    avoid_rows = [
        (sorted(avoided, key=alphabetical), replacement)
        for replacement, avoided in by_replacement.items()
    ]
    avoid_rows.sort(key=lambda row: alphabetical(row[0][0]))
    lines += ["", "### Words to avoid", "", "| Avoid | Instead |", "| --- | --- |"]
    for avoided, replacement in avoid_rows:
        lines.append(f"| {cell(', '.join(avoided))} | {cell(replacement)} |")
    return "\n".join(lines)


def patterns_section(rows: list[dict[str, str]], company: str) -> str:
    """Which messages already have a string. The strings themselves, how to use them and
    the open questions are in references/patterns.csv."""
    lines = [
        f"These {len(rows)} messages each have one string to reuse, in "
        f"`references/patterns.csv`. The strings are this audit's suggestions, not "
        f"wording {company} has published.",
        "",
    ]
    for row in rows:
        lines.append(f"- `{row['pattern_id']}`: {row['message']}")
    return "\n".join(lines)


def benchmark_prompts(
    entries: list[dict[str, str]], rows: list[dict[str, str]], company: str
) -> list[str]:
    """Test requests built from real terms and patterns, plus a few general ones."""
    prompts = []
    # The four shortest strings make the clearest tests. They stay in file order.
    shortest = sorted(rows, key=lambda r: len(r["shared_wording"]))[:4]
    for row in rows:
        if row in shortest:
            surface = row["surfaces"].split()[0] if row["surfaces"].split() else "help"
            prompts.append(f"Write the {surface} text for this message: {row['message']}")
    retired = [e for e in entries if e["status"] == "deprecated" and e["basis"] == "published"]
    if retired:
        old, new = retired[0]["term"], retired[0]["use_instead"]
        prompts.append(
            f"Rename {old} to {new} in a help article, and keep the old name findable once."
        )
    avoided: dict[str, str] = {}
    for e in entries:
        replacement = e["use_instead"].strip().lower()
        if e["status"] == "avoid" and replacement and replacement not in avoided:
            avoided[replacement] = e["term"]
    words = [f"'{w}'" for w in list(avoided.values())[:3]]
    if len(words) == 3:
        prompts.append(f"Repair a draft that uses {words[0]}, {words[1]} and {words[2]}.")
    if len(avoided) > 3:
        word = list(avoided.values())[3]
        prompts.append(f"A request asks for '{word}' on a settings page. Answer as the rules say.")
    for e in entries:
        # The company name in front doesn't count, so "Perplexity Pro" is one word here.
        words_in = e["term"].split()
        if words_in[0].lower() == company.lower():
            words_in = words_in[1:]
        if e["status"] == "use" and len(words_in) == 2 and words_in[1][:1].isupper():
            wrong = f"{words_in[0]} {words_in[1].lower()}"
            prompts.append(f"Fix the term in this sentence: \"This works on {wrong}.\"")
            break
    return prompts + list(GENERAL_PROMPTS)


def pattern_rows(target: Target) -> list[dict[str, str]]:
    """patterns.csv, with each pattern's "How to use it:" note from the proposals."""
    proposals = pattern_table.read(target.pattern_proposals)
    notes = {p["pattern_id"]: p.get("note", "") for p in proposals}
    return [
        {**row, "how_to_use": how_to_use(notes.get(row["pattern_id"], ""))}
        for row in pattern_table.read(target.pattern_table)
    ]


def render(target: Target) -> dict[str, str]:
    """Every file in the skill folder, by path inside it. Nothing is written here."""
    problems = glossary.check_file(target.glossary)
    if problems:
        line, problem = problems[0]
        raise ValueError(f"Fix the glossary first (line {line}: {problem}).")
    known = pattern_table.known_ids(target.public_snippets)
    pattern_problems = pattern_table.check_file(target.pattern_table, known)
    if pattern_problems:
        line, problem = pattern_problems[0]
        raise ValueError(f"Fix the patterns table first (line {line}: {problem}).")
    entries = glossary.read(target.glossary)
    if not entries:
        raise FileNotFoundError(f"No glossary rows in {target.glossary}")
    rows = pattern_rows(target)
    first, last = evidence_dates(target)
    company = target.display_name

    values = {
        "skill_name": target.skill_name,
        "skill_title": target.skill_title,
        "display_name": company,
        "target": target.name,
        "version": VERSION,
        "captured_from": first,
        "captured_to": last,
        "brand_link": brand_link(target),
        "stages": " | ".join(snippets.STAGES),
        "terms": terms_section(entries, company),
        "patterns": patterns_section(rows, company),
        "benchmarks": "\n".join(f"- {p}" for p in benchmark_prompts(entries, rows, company)),
        "term_count": str(len(entries)),
        "pattern_count": str(len(rows)),
    }
    text = TEMPLATE.read_text(encoding="utf-8")
    for name, value in values.items():
        text = text.replace("{{" + name + "}}", value)
    if "{{" in text:
        raise ValueError(f"{TEMPLATE.name} has a placeholder that nothing fills in")
    return {
        "SKILL.md": text,
        "references/glossary.csv": to_csv(glossary.COLUMNS, entries),
        "references/patterns.csv": to_csv(PATTERN_COLUMNS, rows),
        "scripts/check_text.py": SCRIPT.read_text(encoding="utf-8").replace(
            "{{display_name}}", company
        ),
    }


def run(target: Target, *, log: Callable[[str], None] = print) -> dict[str, str]:
    files = render(target)
    folder = skill_dir(target)
    for name, text in files.items():
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    log(f"Wrote {len(files)} files to {folder}")
    return files
