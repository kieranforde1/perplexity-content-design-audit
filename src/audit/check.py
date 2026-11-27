"""`audit check`: test the public text against the glossary and the patterns table.

Three kinds of finding come out, one row each in data/<target>/findings.csv:

- Words to avoid and deprecated (retired) names: where each one still appears, one row
  per surface. Developer docs often use words like "disabled" as a setting's value, so
  surfaces are kept apart rather than added together.
- Terms to use: other spellings of the glossary form, with labels and running text kept
  apart, because labels use title case on purpose. All-lowercase uses are left out: they
  may be the general word ("a project"), which only a person can tell. A term with two
  kinds of variant (capitals and hyphens, say) gets one row for each kind.
- Same message, different words: for each row of patterns.csv, the strings that don't use
  its shared wording. One row per pattern.

Each finding has a category (see CATEGORIES) and short fields, so the viewer can show
them as columns. The wording is a content designer's note to the team: what's wrong, the
fix, and a question only where the answer isn't in the text. Whether a rule was
published or is a recommendation is shown once, in the glossary, not repeated on every
fix. Every finding lists the
IDs of every snippet it counts, so each one can be traced. Readers see a snippet as a
"string", so the wording the viewer shows says "string".
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field

from audit import evidence, glossary, pattern_table, patterns, snippets, terms
from audit.config import Target
from audit.terms import Text

FINDING_COLUMNS = (
    "finding_id", "standard_id", "category", "term", "written", "count", "surfaces",
    "issue", "fix", "question", "snippet_ids",
)

# The kinds of mismatch, in the order the viewer groups them. There's no separate
# "retired name": the glossary marks a retired name as `deprecated`, so it's the same thing.
PATTERN_CATEGORY = "same message, different words"
CATEGORIES = (
    "capitalisation", "spelling or spacing", "deprecated name", "avoided term",
    "other variant", PATTERN_CATEGORY,
)
# A [slot] in a shared wording stands for one to four words, the same short gap that
# `audit patterns` allows in a template.
SLOT = re.compile(r"\[[^\]]*\]")
SLOT_WORDS = rf"\S+(?: \S+){{0,{patterns.MAX_SLOT_WORDS - 1}}}"
STATUS_CATEGORIES = {"deprecated": "deprecated name", "avoid": "avoided term"}


@dataclass(frozen=True)
class Use:
    """One place a glossary term appears."""

    text: Text
    form: str
    start: int


def spans_of(phrases: tuple[str, ...], text: str) -> list[tuple[int, int]]:
    """Where each phrase appears in the text, in any case."""
    found = []
    for phrase in phrases:
        for m in re.finditer(re.escape(phrase), text, re.IGNORECASE):
            found.append((m.start(), m.end()))
    return found


def is_inside(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    return any(s <= start and end <= e for s, e in spans)


def uses_of(
    term: str, texts: list[Text], company: str, other_things: tuple[str, ...] = ()
) -> list[Use]:
    """Every use of a term in prose, in any spelling. Code parameters and matches inside
    file names, URLs or IDs don't count. Neither do matches inside a phrase that names
    something else (the config's `other_things`), like "RTX PRO" for Perplexity Pro."""
    pattern = terms.form_pattern(term, company)
    words = terms.strip_company(term.replace("-", " ").split(), company)
    first = words[0].lower()
    stem = first.removesuffix("s")
    found = []
    for t in texts:
        if t.snippet.kind == "parameter":
            continue
        if not {first, stem, stem + "s", stem + "es"} & t.tokens:
            continue
        elsewhere = spans_of(other_things, t.text)
        for match in pattern.finditer(t.text):
            if terms.inside_identifier(t.text, match.start(), match.end()):
                continue
            if is_inside(match.start(), match.end(), elsewhere):
                continue
            found.append(Use(t, match.group(), match.start()))
    return found


def is_plural(form: str) -> bool:
    last = terms.strip_possessive(form).split()[-1] if form.split() else ""
    return len(last) > 3 and last.endswith("s") and not last.endswith("ss")


def longer_uses(
    entry: dict[str, str],
    entries: list[dict[str, str]],
    texts: list[Text],
    target: Target,
) -> dict[str, list[tuple[int, int]]]:
    """Where longer glossary terms that contain this one appear, by snippet ID.

    "API Portal" and "portal" are both in the glossary. A use of "portal" inside "API
    Portal" is already counted under the longer term, so counting it again would report
    the same words twice."""
    own = entry["term"].lower()
    spans: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for other in entries:
        term = other["term"]
        if len(term) <= len(own) or own not in term.lower():
            continue
        phrases = target.check.other_things.get(term, ())
        for use in uses_of(term, texts, target.display_name, phrases):
            spans[use.text.snippet.id].append((use.start, use.start + len(use.form)))
    return spans


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


def squash(text: str) -> str:
    """The letters alone, in lowercase: what's left once case, spaces and hyphens go."""
    return re.sub(r"[\s-]", "", text).lower()


def variant_category(written: str, allowed: set[str]) -> str:
    """What kind of variant a spelling is, compared with the forms allowed in its place."""
    if written.lower() in {a.lower() for a in allowed}:
        return "capitalisation"
    if squash(written) in {squash(a) for a in allowed}:
        return "spelling or spacing"
    # The matcher only finds changes of case, spaces and hyphens today, so this is a
    # safety net for anything else it may find later.
    return "other variant"


@dataclass
class Finding:
    standard_id: str
    group: str
    category: str
    term: str
    written: str
    issue: str
    fix: str
    question: str = ""
    snippet_ids: list[str] = field(default_factory=list)
    surfaces: set[str] = field(default_factory=set)

    def row(self) -> dict[str, str]:
        key = f"{self.standard_id}\n{self.group}\n{self.category}"
        return {
            "finding_id": hashlib.sha1(key.encode("utf-8")).hexdigest()[:10],
            "standard_id": self.standard_id,
            "category": self.category,
            "term": self.term,
            "written": self.written,
            "count": str(len(self.snippet_ids)),
            "surfaces": " ".join(s for s in terms.AUTHORITY if s in self.surfaces),
            "issue": self.issue,
            "fix": self.fix,
            "question": self.question,
            "snippet_ids": " ".join(self.snippet_ids),
        }


def is_correct_in_context(entry: dict[str, str], text: Text, target: Target) -> bool:
    """True where the name has to be said, so saying it isn't a mistake:

    - on a changelog or other record of the past, where it was right on the day
    - on the page that announces the rename (the glossary row's source_url)
    - on pages about moving off the old name (the config's `rename_pages`)
    - on pages that list the word as a value shown on screen (`screen_value_pages`)
    """
    snippet = text.snippet
    if snippet.surface in target.check.history_surfaces:
        return True
    value_pages = target.check.screen_value_pages.get(entry["term"], ())
    if any(fragment in snippet.source_url for fragment in value_pages):
        return True
    if entry["status"] != "deprecated":
        return False
    if entry["source_url"] and snippet.source_url == entry["source_url"]:
        return True
    return any(fragment in snippet.source_url for fragment in target.check.rename_pages)


def avoid_findings(
    entry: dict[str, str],
    texts: list[Text],
    target: Target,
    entries: list[dict[str, str]],
) -> list[Finding]:
    """Where a word to avoid, or a deprecated name, still appears. One finding per surface."""
    term = entry["term"]
    company = target.display_name
    inside_longer = longer_uses(entry, entries, texts, target)
    by_surface: dict[str, list[Use]] = defaultdict(list)
    phrases = target.check.other_things.get(term, ())
    for use in uses_of(term, texts, company, phrases):
        if is_correct_in_context(entry, use.text, target):
            continue
        if is_inside(use.start, use.start + len(use.form), inside_longer[use.text.snippet.id]):
            continue
        # A deprecated name is a name, so lowercase "space" is the general word, not the
        # old product. Words to avoid count in any case.
        is_lowercase = use.form == use.form.lower() and term != term.lower()
        if entry["status"] == "deprecated" and is_lowercase:
            continue
        by_surface[use.text.snippet.surface].append(use)
    category = STATUS_CATEGORIES[entry["status"]]
    replacement = entry["use_instead"].strip()
    findings = []
    for surface in terms.AUTHORITY:
        found = by_surface.get(surface)
        if not found:
            continue
        ids = list(dict.fromkeys(u.text.snippet.id for u in found))
        pages = {u.text.snippet.source_url for u in found}
        forms = Counter(u.form for u in found)
        written = ", ".join(f"'{f}' ({n})" for f, n in forms.most_common(3))
        what = "a deprecated name" if entry["status"] == "deprecated" else "a word to avoid"
        question = ""
        if replacement:
            fix = f"Use '{replacement}' instead."
            # Developer docs can use the word as a literal value in code, which has to
            # stay. Only the team knows which uses those are.
            if entry["status"] == "avoid" and surface == "docs":
                most_used = forms.most_common(1)[0][0]
                question = (
                    f"Is '{most_used}' a literal value in code or the API here? "
                    "If so, keep it."
                )
        else:
            fix = f"Reword without '{term}'."
            question = f"What should these pages say instead of '{term}'?"
        findings.append(Finding(
            standard_id=f"glossary:{term}",
            group=surface,
            category=category,
            term=term,
            written=written,
            issue=(
                f"'{term}' is {what} but appears in {terms.plural(len(ids), 'string')} "
                f"on {terms.plural(len(pages), surface + ' page')}, written {written}."
            ),
            fix=fix,
            question=question,
            snippet_ids=ids,
            surfaces={surface},
        ))
    return findings


def spelling_findings(entry: dict[str, str], texts: list[Text], target: Target) -> list[Finding]:
    """Other spellings of a term to use, with labels and running text kept apart."""
    term = entry["term"]
    company = target.display_name
    by_group: dict[tuple[str, str], list[Use]] = defaultdict(list)
    as_glossary: Counter[str] = Counter()
    for use in uses_of(term, texts, company, target.check.other_things.get(term, ())):
        group = terms.group_of(use.text.snippet.kind)
        if group is None:
            continue
        written = terms.shape(use.form, company)
        if written == written.lower() and term != term.lower():
            continue
        # ALL CAPS is styling, usually a header, not a different spelling.
        if len(written) > 1 and written == written.upper() and term != term.upper():
            continue
        # "AI Assistant" is the name of one thing, not a variant of "AI assistants". Only
        # this direction is skipped: a plural of a singular term ("API Keys") still has
        # its capitals to compare.
        if is_plural(term) and not is_plural(use.form):
            continue
        at_start = not terms.is_mid_sentence(use.text.text, use.start)
        allowed = expected_shapes(term, group, at_start, company)
        if written in allowed:
            as_glossary[group] += 1
        else:
            by_group[(group, variant_category(written, allowed))].append(use)
    findings = []
    for group in ("labels", "running"):
        for category in CATEGORIES:
            found = by_group.get((group, category))
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
                category=category,
                term=term,
                written=written,
                issue=(
                    f"In {terms.GROUP_NAMES[group]}, '{term}' is written {written} in "
                    f"{terms.plural(len(ids), 'string')} on "
                    f"{terms.plural(len(pages), 'page')}. The glossary form appears "
                    f"{terms.plural(as_glossary[group], 'time')}."
                ),
                fix=f"Write '{term}'.",
                snippet_ids=ids,
                surfaces={u.text.snippet.surface for u in found},
            ))
    return findings


def wording_patterns(shared_wording: str) -> list[re.Pattern[str]]:
    """Each sentence of a shared wording, as a pattern to match against cleaned words.

    Words are cleaned as `audit patterns` cleans them: lower-cased, with punctuation and
    parameters removed. Each [slot] matches one to four words.
    """
    found = []
    for sentence in patterns.SENTENCE_END.split(shared_wording.strip()):
        parts: list[str] = []
        for i, piece in enumerate(SLOT.split(sentence)):
            if i:
                parts.append(SLOT_WORDS)
            parts += [re.escape(word) for word in patterns.clean(piece)]
        if parts:
            found.append(re.compile(" ".join(parts)))
    return found


def uses_shared_wording(text: str, wording: list[re.Pattern[str]]) -> bool:
    """True if one sentence of the string is word for word one sentence of the shared
    wording, once both are cleaned. A long shared wording is often split across a page,
    so a string only has to match one of its sentences."""
    return any(
        pattern.fullmatch(" ".join(patterns.clean(sentence)))
        for sentence in patterns.SENTENCE_END.split(text)
        for pattern in wording
    )


def pattern_finding(row: dict[str, str], by_id: dict[str, Text]) -> Finding | None:
    """The strings in a pattern that say its message without its shared wording, as one
    finding. None if every string already uses the shared wording.

    Strings on pages left out of analysis (the config's `analysis_exclude`) aren't counted,
    as with the glossary.
    """
    wording = wording_patterns(row["shared_wording"])
    found = [by_id[i] for i in row["string_ids"].split() if i in by_id]
    variants = [t for t in found if not uses_shared_wording(t.text, wording)]
    if not variants:
        return None
    matched = len(found) - len(variants)
    # Grouped by cleaned wording, most common first. The first string of each wording goes
    # first in the list, so the few committed as evidence show the different wordings.
    by_wording: dict[str, list[Text]] = defaultdict(list)
    for t in variants:
        by_wording[" ".join(patterns.clean(t.text))].append(t)
    wordings = sorted(by_wording.values(), key=len, reverse=True)
    firsts = [w[0].snippet.id for w in wordings]
    ids = firsts + [t.snippet.id for w in wordings for t in w[1:]]
    written = ", ".join(f"'{w[0].snippet.excerpt}' ({len(w)})" for w in wordings[:3])

    pages = {t.snippet.source_url for t in variants if t.snippet.method == "crawl"}
    in_app = sum(1 for t in variants if t.snippet.method == "typed")
    if pages and in_app:
        where = f"on {terms.plural(len(pages), 'page')} and in the app"
    elif pages:
        where = f"on {terms.plural(len(pages), 'page')}"
    else:
        where = "in the app"
    say = "says" if len(variants) == 1 else "say"
    ways = "another way" if len(wordings) == 1 else f"{len(wordings)} different ways"
    issue = (
        f"{row['message']} {terms.plural(len(variants), 'string')} {where} {say} it {ways}."
    )
    if matched:
        uses = "uses" if matched == 1 else "use"
        issue += f" {terms.plural(matched, 'string')} already {uses} the shared wording."

    fix = f"Use one string everywhere: '{row['shared_wording']}'"
    if SLOT.search(row["shared_wording"]):
        fix += " Fill in the parts in [brackets] each time."
    # App text isn't on any public page, so editing the pages can't change it.
    if in_app:
        are = "is" if in_app == 1 else "are"
        them = "it" if in_app == 1 else "them"
        fix += (
            f" {terms.plural(in_app, 'string')} {are} app text, so changing the public "
            f"pages alone won't fix {them}."
        )
    return Finding(
        standard_id=f"pattern:{row['pattern_id']}",
        group="",
        category=PATTERN_CATEGORY,
        term=row["pattern_id"],
        written=written,
        issue=issue,
        fix=fix,
        question=row["question"],
        snippet_ids=ids,
        surfaces={t.snippet.surface for t in variants},
    )


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
    texts = terms.load_texts(target)
    table = snippets.read(target.local_snippets)
    pattern_problems = pattern_table.check_file(target.pattern_table, {s.id for s in table})
    if pattern_problems:
        line, problem = pattern_problems[0]
        raise ValueError(
            f"Fix the patterns table first (line {line}: {problem}). "
            f"See `audit patterns --check --target {target.name}`."
        )
    pattern_rows = pattern_table.read(target.pattern_table)

    findings: list[Finding] = []
    for entry in entries:
        if entry["status"] in ("avoid", "deprecated"):
            findings += avoid_findings(entry, texts, target, entries)
        else:
            findings += spelling_findings(entry, texts, target)
    by_id = {t.snippet.id: t for t in texts}
    for pattern in pattern_rows:
        found = pattern_finding(pattern, by_id)
        if found:
            findings.append(found)

    rows = [f.row() for f in findings]
    path = target.data_dir / "findings.csv"
    terms.write_csv(path, FINDING_COLUMNS, rows)
    # Findings decide part of the evidence, so the committed copy is redone.
    filled = evidence.write_public_copy(target, table, log=log)
    per_category = Counter(f.category for f in findings)
    log(f"{len(entries)} glossary rows checked against {len(texts)} strings.")
    log(f"{len(pattern_rows)} patterns checked.")
    breakdown = ", ".join(f"{per_category[c]} {c}" for c in CATEGORIES if per_category[c])
    log(f"{len(rows)} findings" + (f": {breakdown}." if breakdown else "."))
    log(f"Wrote {path}")
    log(f"Wrote {target.public_snippets} (committed, {filled} evidence excerpts)")
    return rows
