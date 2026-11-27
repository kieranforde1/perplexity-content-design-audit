"""`audit patterns`: find the same message said in different words.

A pattern is a message said in more than one place that should read the same each time,
such as an instruction, a notice or a plan description. This step lists candidates for a
person to judge. It never decides that a group is a real pattern.

The five rules (ROADMAP.md, agreed by the owner on 2026-11-27):

1. **Clean up** each sentence: lower-case it, remove punctuation, drop parameters and
   placeholders, and skip anything under four words.
2. **Look-alikes** share a three-word phrase and at least `min_overlap` of their words.
   Look-alikes chain into one group. Only groups on two or more pages count.
3. **Reason**: `link_text` (a page's title and the links to it, which belong to terms),
   `template` (one slot changes, such as a connector name) or `message` (the wording
   differs in more than one place).
4. **Rank** by pages times variants. `fact_clash` says where the variants disagree on a
   number, a time period or a plan name. Groups whose only difference is a glossary word to
   avoid are dropped, because `audit check` already reports those.
5. **Copied pages**: two pages that share ten or more groups are reported once, as one
   `copied_page` row, instead of as every group between them. Short app labels are too
   short for word overlap, so they're grouped by surface and stage, as `app_labels` rows.

Writes cache/<target>/pattern_candidates.csv. It quotes whole sentences, so it stays on
this computer and is never committed.
"""

from __future__ import annotations

import re
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from audit import glossary, terms
from audit.config import Target

# Splits a snippet that holds more than one sentence.
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
# Code names (max_results, maxResults) and slots ({name}) aren't wording a person chose.
PARAMETER = re.compile(r"\{[^}]*\}|\S*_\S*|\b[a-z]+[A-Z][A-Za-z0-9]*\b")
APOSTROPHE = re.compile(r"['’]")
# "1,000" is one number, not two.
DIGIT_COMMA = re.compile(r"(?<=\d),(?=\d{3})")
# Numbers keep their decimal point, so "1.5" and "15" stay different facts.
WORD = re.compile(r"[a-z0-9]+(?:\.[0-9]+)*")
# A word that is only a number. "1password" is a name, not a number.
NUMBER = re.compile(r"^[0-9]+(?:\.[0-9]+)*$")

MIN_WORDS = 4
PHRASE_WORDS = 3
# A phrase in more than this many different sentences is ordinary English ("you can
# use"), not a sign of a shared message. Skipping it keeps the pair search fast. Two
# sentences that share 75% of their words almost always share a rarer phrase as well.
COMMON_PHRASE = 50
# Two pages that share this many groups are copies of each other.
COPIED_PAGE_GROUPS = 10
# A slot is a short gap, such as a product name ("gmail and google calendar"). A longer
# gap is different wording.
MAX_SLOT_WORDS = 4

# Time periods, each mapped to one name, so "daily" and "per day" agree but "daily" and
# "weekly" don't.
TIME_WORDS = {
    "hourly": "hour", "hour": "hour", "hours": "hour",
    "daily": "day", "day": "day", "days": "day",
    "weekly": "week", "week": "week", "weeks": "week",
    "monthly": "month", "month": "month", "months": "month",
    "quarterly": "quarter", "quarter": "quarter", "quarters": "quarter",
    "yearly": "year", "annually": "year", "annual": "year", "year": "year", "years": "year",
    "minute": "minute", "minutes": "minute",
}

COLUMNS = (
    "group_id", "reason", "rank", "pages", "variants", "fact_clash", "surfaces", "stages",
    "example", "other_wording", "string_ids", "source_urls",
)


def clean(sentence: str) -> tuple[str, ...]:
    """The words of a sentence, lower-cased, without punctuation or parameters."""
    text = PARAMETER.sub(" ", sentence)
    text = DIGIT_COMMA.sub("", APOSTROPHE.sub("", text)).lower()
    return tuple(WORD.findall(text))


@dataclass
class Sentence:
    """One cleaned wording, and everywhere it appears."""

    words: tuple[str, ...]
    text: str
    string_ids: set[str] = field(default_factory=set)
    pages: set[str] = field(default_factory=set)
    surfaces: set[str] = field(default_factory=set)
    stages: set[str] = field(default_factory=set)
    kinds: set[str] = field(default_factory=set)


@dataclass
class Group:
    reason: str
    sentences: list[Sentence]
    fact_clash: str = ""

    @property
    def pages(self) -> set[str]:
        return {p for s in self.sentences for p in s.pages}

    @property
    def rank(self) -> int:
        return len(self.pages) * len(self.sentences)


def collect(
    texts: Iterable[terms.Text],
) -> tuple[list[Sentence], dict[tuple[str, str], list[Sentence]]]:
    """Every cleaned sentence of four words or more, and the short typed app labels by
    (surface, stage).

    Identical wordings are merged first, so a sentence repeated on 300 pages is one
    sentence with 300 pages, not 300 sentences to compare.
    """
    sentences: dict[tuple[str, ...], Sentence] = {}
    labels: dict[tuple[str, str, tuple[str, ...]], Sentence] = {}
    for t in texts:
        if t.snippet.kind == "parameter":
            continue
        for raw in SENTENCE_END.split(t.text):
            words = clean(raw)
            if len(words) >= MIN_WORDS:
                found = sentences.setdefault(words, Sentence(words, raw))
            elif words and t.snippet.method == "typed":
                key = (t.snippet.surface, t.snippet.stage, words)
                found = labels.setdefault(key, Sentence(words, raw))
            else:
                continue
            found.string_ids.add(t.snippet.id)
            found.pages.add(t.snippet.source_url)
            found.surfaces.add(t.snippet.surface)
            found.stages.add(t.snippet.stage)
            found.kinds.add(t.snippet.kind)
    by_screen: dict[tuple[str, str], list[Sentence]] = defaultdict(list)
    for (surface, stage, _), label in labels.items():
        by_screen[(surface, stage)].append(label)
    return list(sentences.values()), dict(by_screen)


def phrases(words: tuple[str, ...]) -> set[tuple[str, ...]]:
    return {words[i : i + PHRASE_WORDS] for i in range(len(words) - PHRASE_WORDS + 1)}


def overlap(a: set[str], b: set[str]) -> float:
    """Shared words as a share of all the words in either sentence."""
    return len(a & b) / len(a | b)


def look_alike_pairs(sentences: list[Sentence], min_overlap: float) -> list[tuple[int, int]]:
    """Pairs of sentences that share a three-word phrase and enough of their words.

    Comparing every sentence with every other would take hours, so a phrase index finds
    the pairs worth checking: only sentences that share a phrase are compared.
    """
    index: dict[tuple[str, ...], list[int]] = defaultdict(list)
    for i, s in enumerate(sentences):
        for phrase in phrases(s.words):
            index[phrase].append(i)
    word_sets = [set(s.words) for s in sentences]
    checked: set[tuple[int, int]] = set()
    pairs = []
    for ids in index.values():
        if len(ids) < 2 or len(ids) > COMMON_PHRASE:
            continue
        for n, i in enumerate(ids):
            for j in ids[n + 1 :]:
                if (i, j) in checked:
                    continue
                checked.add((i, j))
                if overlap(word_sets[i], word_sets[j]) >= min_overlap:
                    pairs.append((i, j))
    return pairs


def chain(count: int, pairs: Iterable[tuple[int, int]]) -> list[list[int]]:
    """Join pairs into groups: if A looks like B and B looks like C, all three are one group.

    Each sentence points to a leader. Joining two groups points one leader at the other.
    """
    leader = list(range(count))

    def find(i: int) -> int:
        while leader[i] != i:
            leader[i] = leader[leader[i]]
            i = leader[i]
        return i

    for i, j in pairs:
        leader[find(i)] = find(j)
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(count):
        groups[find(i)].append(i)
    return list(groups.values())


def one_slot(variants: list[tuple[str, ...]]) -> bool:
    """True when every variant has the same words before and after one short gap, and
    only the gap changes, as in "Connect Slack to Perplexity" and "Connect Google Drive
    to Perplexity"."""
    shortest = min(len(v) for v in variants)
    start = 0
    while start < shortest and len({v[start] for v in variants}) == 1:
        start += 1
    end = 0
    while end < shortest - start and len({v[len(v) - 1 - end] for v in variants}) == 1:
        end += 1
    gaps = [v[start : len(v) - end] for v in variants]
    return all(0 < len(gap) <= MAX_SLOT_WORDS for gap in gaps)


def reason_for(sentences: list[Sentence]) -> str:
    """link_text, template or message (rule 3).

    A group that holds a page title is the name of a page: the title itself, and the ways
    other pages link to it ("See What is Pro Search?"). Names belong in terms, so the group
    is link text. So is a group made only of navigation links.
    """
    if any("title" in s.kinds for s in sentences) or all(s.kinds == {"nav"} for s in sentences):
        return "link_text"
    if one_slot([s.words for s in sentences]):
        return "template"
    return "message"


def plan_forms(
    plan_names: Iterable[str], company: str, other_terms: Iterable[str] = ()
) -> dict[tuple[str, ...], str]:
    """Words to look for, and the plan each one names.

    Each plan name also counts without the company name ("pro" for "Perplexity Pro"),
    because the text often drops it. Other glossary terms map to "" so they can win a
    longer match: "pro search" is Pro Search, not the Pro plan.
    """
    forms: dict[tuple[str, ...], str] = {clean(t): "" for t in other_terms}
    for name in plan_names:
        words = clean(name)
        forms[words] = name
        if len(words) > 1 and words[0] == company.lower():
            forms.setdefault(words[1:], name)
    return forms


def plans_in(words: tuple[str, ...], forms: dict[tuple[str, ...], str]) -> set[str]:
    """Plan names in a sentence. The longest match wins, so "enterprise pro" is
    Enterprise Pro, not Perplexity Pro."""
    found = set()
    longest = sorted((f for f in forms if f), key=len, reverse=True)
    i = 0
    while i < len(words):
        for form in longest:
            if words[i : i + len(form)] == form:
                if forms[form]:
                    found.add(forms[form])
                i += len(form)
                break
        else:
            i += 1
    return found


def fact_clash(variants: list[tuple[str, ...]], forms: dict[tuple[str, ...], str]) -> str:
    """Where the variants disagree on a fact, such as "numbers: 10 / 20", or "".

    Variants that state no fact of a kind are left out of that comparison: a variant
    that leaves the number out isn't disagreeing with one that gives it.
    """
    kinds: dict[str, Callable[[tuple[str, ...]], frozenset[str]]] = {
        "numbers": lambda w: frozenset(x for x in w if NUMBER.match(x)),
        "time": lambda w: frozenset(TIME_WORDS[x] for x in w if x in TIME_WORDS),
        "plans": lambda w: frozenset(plans_in(w, forms)),
    }
    clashes = []
    for name, facts_of in kinds.items():
        stated = {facts_of(v) for v in variants} - {frozenset()}
        if len(stated) > 1:
            listed = " / ".join(sorted(", ".join(sorted(s)) for s in stated))
            clashes.append(f"{name}: {listed}")
    return "; ".join(clashes)


def avoided_words(rows: list[dict[str, str]]) -> list[tuple[tuple[str, ...], tuple[str, ...]]]:
    """(avoided words, the words to use instead) for glossary rows marked avoid or
    deprecated, longest first so "api portal" is replaced before "portal"."""
    swaps = [
        (clean(r.get("term") or ""), clean(r.get("use_instead") or ""))
        for r in rows
        if r.get("status") in ("avoid", "deprecated")
    ]
    return sorted((s for s in swaps if s[0]), key=lambda s: -len(s[0]))


def swap_avoided(
    words: tuple[str, ...], swaps: list[tuple[tuple[str, ...], tuple[str, ...]]]
) -> tuple[str, ...]:
    """The sentence with each avoided word replaced by the word to use, keeping a plural."""
    out: list[str] = []
    i = 0
    while i < len(words):
        for old, new in swaps:
            here = words[i : i + len(old)]
            plural = here[:-1] == old[:-1] and here[-1:] == (old[-1] + "s",)
            if len(here) == len(old) and (here == old or plural):
                out += list(new[:-1]) + [new[-1] + "s"] if plural and new else list(new)
                i += len(old)
                break
        else:
            out.append(words[i])
            i += 1
    return tuple(out)


def only_avoided_words_differ(
    variants: list[tuple[str, ...]], swaps: list[tuple[tuple[str, ...], tuple[str, ...]]]
) -> bool:
    return len({swap_avoided(v, swaps) for v in variants}) == 1


def copied_page_sets(groups: list[list[Sentence]]) -> list[set[str]]:
    """Sets of pages that copy each other: each pair shares COPIED_PAGE_GROUPS groups or
    more, and copies of copies join one set.

    Groups on more than terms.REPEATED_ON_PAGES pages are left out of the count. Text on
    that many pages is site-wide boilerplate, which every page shares, not a sign that two
    pages were copied from each other.
    """
    shared: Counter[tuple[str, str]] = Counter()
    for sentences in groups:
        pages = sorted({p for s in sentences for p in s.pages})
        if len(pages) > terms.REPEATED_ON_PAGES:
            continue
        for n, a in enumerate(pages):
            for b in pages[n + 1 :]:
                shared[(a, b)] += 1
    copied = [pair for pair, n in shared.items() if n >= COPIED_PAGE_GROUPS]
    pages = sorted({p for pair in copied for p in pair})
    number = {p: i for i, p in enumerate(pages)}
    sets = chain(len(pages), [(number[a], number[b]) for a, b in copied])
    return [{pages[i] for i in members} for members in sets]


@dataclass
class CopiedPages:
    pages: set[str]
    groups: list[list[Sentence]]
    # A copy that has drifted from its original matters more than the copy itself, so
    # fact clashes inside the shared groups are kept on the one row.
    clashes: list[str] = field(default_factory=list)


def by_reach(sentences: list[Sentence]) -> list[Sentence]:
    """Most pages first, so the example is the most common wording."""
    return sorted(sentences, key=lambda s: (-len(s.pages), s.text))


def plan_names(target: Target, log: Callable[[str], None]) -> dict[tuple[str, ...], str]:
    """The config's plan names that the glossary uses. A plan name must be a settled term,
    so a typo in the config can't create fact clashes."""
    usable = [
        r.get("term") or "" for r in glossary.read(target.glossary) if r.get("status") == "use"
    ]
    keys = {glossary.key(t) for t in usable}
    names = [n for n in target.patterns.plan_names if glossary.key(n) in keys]
    for name in target.patterns.plan_names:
        if name not in names:
            log(f"Plan name {name!r} isn't a 'use' term in the glossary, so it's ignored.")
    return plan_forms(names, target.display_name, usable)


def find_groups(
    sentences: list[Sentence], target: Target, log: Callable[[str], None]
) -> tuple[list[Group], list[CopiedPages]]:
    """Rules 2 to 5 for sentences of four words or more."""
    pairs = look_alike_pairs(sentences, target.patterns.min_overlap)
    chained = [[sentences[i] for i in ids] for ids in chain(len(sentences), pairs)]
    on_two_pages = [g for g in chained if len({p for s in g for p in s.pages}) >= 2]

    # Copies are found from every group, including ones with a single wording, because
    # copied pages mostly repeat each other word for word.
    copied = [CopiedPages(pages, []) for pages in copied_page_sets(on_two_pages)]
    swaps = avoided_words(glossary.read(target.glossary))
    forms = plan_names(target, log)

    groups = []
    dropped = 0
    for members in on_two_pages:
        pages = {p for s in members for p in s.pages}
        home = next((c for c in copied if pages <= c.pages), None)
        if home is not None:
            home.groups.append(members)
        # One wording on many pages is consistent, so there's nothing to compare.
        if len(members) < 2:
            continue
        variants = [s.words for s in members]
        if only_avoided_words_differ(variants, swaps):
            dropped += 1
            continue
        clash = fact_clash(variants, forms)
        if home is not None:
            if clash:
                home.clashes.append(clash)
            continue
        groups.append(Group(reason_for(members), members, clash))
    log(f"{dropped} groups dropped: they only differ by a glossary word to avoid.")
    return groups, copied


def app_label_groups(labels: dict[tuple[str, str], list[Sentence]]) -> list[Group]:
    """Short app labels, one group per surface and stage with two or more labels."""
    return [
        Group("app_labels", members)
        for _, members in sorted(labels.items())
        if len(members) >= 2
    ]


def group_row(group_id: str, group: Group) -> dict[str, str]:
    ordered = by_reach(group.sentences)
    # App labels are a list of a screen's labels, not look-alikes, so pages times
    # variants doesn't measure the same thing and they aren't ranked.
    rank = "" if group.reason == "app_labels" else str(group.rank)
    return {
        "group_id": group_id,
        "reason": group.reason,
        "rank": rank,
        "pages": str(len(group.pages)),
        "variants": str(len(group.sentences)),
        "fact_clash": group.fact_clash,
        "surfaces": " ".join(sorted({x for s in group.sentences for x in s.surfaces})),
        "stages": " ".join(sorted({x for s in group.sentences for x in s.stages})),
        "example": ordered[0].text,
        "other_wording": ordered[1].text if len(ordered) > 1 else "",
        "string_ids": " ".join(sorted({i for s in group.sentences for i in s.string_ids})),
        "source_urls": " | ".join(sorted(group.pages)),
    }


def copied_row(group_id: str, copied: CopiedPages) -> dict[str, str]:
    """One row for a set of copied pages, in place of every group they share.

    A row in the same file, rather than a separate file or column, keeps the copy in the
    same list a person works through, sorted after the ranked groups.
    """
    sentences = [s for g in copied.groups for s in g]
    biggest = max(copied.groups, key=len)
    return {
        "group_id": group_id,
        "reason": "copied_page",
        "rank": "",
        "pages": str(len(copied.pages)),
        "variants": str(len(sentences)),
        "fact_clash": "; ".join(sorted(set(copied.clashes))),
        "surfaces": " ".join(sorted({x for s in sentences for x in s.surfaces})),
        "stages": " ".join(sorted({x for s in sentences for x in s.stages})),
        "example": (
            f"These {len(copied.pages)} pages share {len(copied.groups)} groups of "
            "sentences, so they look copied from one another."
        ),
        "other_wording": by_reach(biggest)[0].text,
        "string_ids": " ".join(sorted({i for s in sentences for i in s.string_ids})),
        "source_urls": " | ".join(sorted(copied.pages)),
    }


def run(target: Target, *, log: Callable[[str], None] = print) -> list[dict[str, str]]:
    started = time.monotonic()
    if not target.local_snippets.exists() or not target.full_text.exists():
        raise FileNotFoundError(
            f"The local snippets table isn't there yet ({target.local_snippets}). Patterns "
            f"need whole sentences, which only the local copy has. Run `audit fetch "
            f"--target {target.name}` and then `audit extract --target {target.name}` first."
        )
    sentences, labels = collect(terms.load_texts(target))
    groups, copied = find_groups(sentences, target, log)
    groups.sort(key=lambda g: (-g.rank, -len(g.pages), by_reach(g.sentences)[0].text))

    rows: list[dict[str, str]] = []
    for group in groups:
        rows.append(group_row(f"g{len(rows) + 1:04d}", group))
    for pages in sorted(copied, key=lambda c: -len(c.groups)):
        rows.append(copied_row(f"g{len(rows) + 1:04d}", pages))
    for group in app_label_groups(labels):
        rows.append(group_row(f"g{len(rows) + 1:04d}", group))

    path = target.cache_dir / "pattern_candidates.csv"
    terms.write_csv(path, COLUMNS, rows)
    reasons = Counter(r["reason"] for r in rows)
    clashes = sum(1 for r in rows if r["fact_clash"])
    log(
        f"{len(sentences)} sentences of {MIN_WORDS} words or more, "
        f"{sum(len(v) for v in labels.values())} short app labels."
    )
    log(
        f"{len(rows)} rows: " + ", ".join(f"{k} {v}" for k, v in reasons.most_common())
        + f". {clashes} with a fact clash."
    )
    log(f"Wrote {path} (local only) in {time.monotonic() - started:.1f}s")
    return rows
