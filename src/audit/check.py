"""`audit check`: test the public text against the glossary.

Two kinds of finding come out, one row each in data/<target>/findings.csv:

- Words to avoid and retired names: where each one still appears, one row per surface.
  Developer docs often use words like "disabled" as a setting's value, so surfaces are
  kept apart rather than added together.
- Terms to use: other spellings of the glossary form, with labels and running text kept
  apart, because labels use title case on purpose. All-lowercase uses are left out: they
  may be the general word ("a project"), which only a person can tell.

Findings are observations. Each one names its glossary row, and that row's `basis` says
whether the standard is Perplexity's own (published, observed) or a recommendation.
Every finding lists the IDs of every snippet it counts, so each one can be traced.
"""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field

from audit import glossary, terms
from audit.config import Target
from audit.terms import Text

FINDING_COLUMNS = ("finding_id", "standard_id", "observation", "count", "surfaces", "snippet_ids")


@dataclass(frozen=True)
class Use:
    """One place a glossary term appears."""

    text: Text
    form: str
    start: int


def uses_of(term: str, texts: list[Text], company: str) -> list[Use]:
    """Every use of a term in prose, in any spelling. Code parameters and matches inside
    file names, URLs or IDs don't count."""
    pattern = terms.form_pattern(term, company)
    words = terms.strip_company(term.replace("-", " ").split(), company)
    first = words[0].lower()
    stem = first.removesuffix("s")
    found = []
    for t in texts:
        if t.snippet.kind == "parameter":
            continue
        if not {first, stem, stem + "s"} & t.tokens:
            continue
        for match in pattern.finditer(t.text):
            if not terms.inside_identifier(t.text, match.start(), match.end()):
                found.append(Use(t, match.group(), match.start()))
    return found


def title_case(text: str) -> str:
    return " ".join(w[:1].upper() + w[1:] for w in text.split())


def expected_shapes(term: str, group: str, at_start: bool, company: str) -> set[str]:
    """The spellings that match the glossary form in this place."""
    base = terms.shape(term, company)
    allowed = {base}
    if at_start:
        allowed.add(base[:1].upper() + base[1:])
    if group == "labels":
        allowed.add(title_case(base))
    return allowed


@dataclass
class Finding:
    standard_id: str
    group: str
    observation: str = ""
    snippet_ids: list[str] = field(default_factory=list)
    surfaces: set[str] = field(default_factory=set)

    def row(self) -> dict[str, str]:
        key = f"{self.standard_id}\n{self.group}"
        return {
            "finding_id": hashlib.sha1(key.encode("utf-8")).hexdigest()[:10],
            "standard_id": self.standard_id,
            "observation": self.observation,
            "count": str(len(self.snippet_ids)),
            "surfaces": " ".join(s for s in terms.AUTHORITY if s in self.surfaces),
            "snippet_ids": " ".join(self.snippet_ids),
        }


def glossary_note(entry: dict[str, str]) -> str:
    replacement = entry["use_instead"].strip()
    instead = f", use '{replacement}' instead" if replacement else ""
    return f"Glossary: {entry['status']}{instead} ({entry['basis']})."


def avoid_findings(entry: dict[str, str], texts: list[Text], company: str) -> list[Finding]:
    """Where a word to avoid, or a retired name, still appears. One finding per surface."""
    term = entry["term"]
    by_surface: dict[str, list[Use]] = defaultdict(list)
    for use in uses_of(term, texts, company):
        # A retired name is a name, so lowercase "space" is the general word, not the old
        # product. Words to avoid count in any case.
        is_lowercase = use.form == use.form.lower() and term != term.lower()
        if entry["status"] == "deprecated" and is_lowercase:
            continue
        by_surface[use.text.snippet.surface].append(use)
    findings = []
    for surface in terms.AUTHORITY:
        found = by_surface.get(surface)
        if not found:
            continue
        ids = list(dict.fromkeys(u.text.snippet.id for u in found))
        pages = {u.text.snippet.source_url for u in found}
        forms = Counter(u.form for u in found)
        written = ", ".join(f"'{f}' ({n})" for f, n in forms.most_common(3))
        findings.append(Finding(
            standard_id=f"glossary:{entry['term']}",
            group=surface,
            observation=(
                f"Observed: '{entry['term']}' appears in {terms.plural(len(ids), 'snippet')} "
                f"on {terms.plural(len(pages), surface + ' page')}, written {written}. "
                + glossary_note(entry)
            ),
            snippet_ids=ids,
            surfaces={surface},
        ))
    return findings


def spelling_findings(entry: dict[str, str], texts: list[Text], company: str) -> list[Finding]:
    """Other spellings of a term to use, with labels and running text kept apart."""
    term = entry["term"]
    by_group: dict[str, list[Use]] = defaultdict(list)
    as_glossary: Counter[str] = Counter()
    for use in uses_of(term, texts, company):
        group = terms.group_of(use.text.snippet.kind)
        if group is None:
            continue
        written = terms.shape(use.form, company)
        if written == written.lower() and term != term.lower():
            continue
        at_start = not terms.is_mid_sentence(use.text.text, use.start)
        if written in expected_shapes(term, group, at_start, company):
            as_glossary[group] += 1
        else:
            by_group[group].append(use)
    findings = []
    for group in ("labels", "running"):
        found = by_group.get(group)
        if not found:
            continue
        ids = list(dict.fromkeys(u.text.snippet.id for u in found))
        pages = {u.text.snippet.source_url for u in found}
        # Quote each spelling's most common real form, so a finding never quotes a
        # spelling that doesn't appear in the text.
        spellings = terms.spellings(Counter(u.form for u in found), company)
        written = ", ".join(terms.quote(s) for s in spellings[:3])
        findings.append(Finding(
            standard_id=f"glossary:{term}",
            group=group,
            observation=(
                f"Observed: in {terms.GROUP_NAMES[group]}, '{term}' is also written "
                f"{written}, in {terms.plural(len(ids), 'snippet')} on "
                f"{terms.plural(len(pages), 'page')}. The glossary form appears "
                f"{terms.plural(as_glossary[group], 'time')}. " + glossary_note(entry)
            ),
            snippet_ids=ids,
            surfaces={u.text.snippet.surface for u in found},
        ))
    return findings


def run(target: Target, *, log: Callable[[str], None] = print) -> list[dict[str, str]]:
    problems = glossary.check_file(target.glossary)
    if problems:
        line, problem = problems[0]
        raise ValueError(
            f"Fix the glossary first (line {line}: {problem}). "
            f"See `audit glossary --check --target {target.name}`."
        )
    entries = glossary.read(target.glossary)
    if not entries:
        raise FileNotFoundError(f"No glossary rows in {target.glossary}")
    company = target.display_name
    texts = terms.load_texts(target)

    findings: list[Finding] = []
    for entry in entries:
        if entry["status"] in ("avoid", "deprecated"):
            findings += avoid_findings(entry, texts, company)
        else:
            findings += spelling_findings(entry, texts, company)

    rows = [f.row() for f in findings]
    path = target.data_dir / "findings.csv"
    terms.write_csv(path, FINDING_COLUMNS, rows)
    avoid = sum(1 for f in findings if f.group not in ("labels", "running"))
    log(f"{len(entries)} glossary rows checked against {len(texts)} snippets.")
    log(f"{len(rows)} findings: {avoid} for words to avoid or retired names, "
        f"{len(rows) - avoid} for other spellings.")
    log(f"Wrote {path}")
    return rows
