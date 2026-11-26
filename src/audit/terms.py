"""`audit terms`: find the names a company uses, and show where the wording varies.

How it works, step by step:

1. **Candidates.** A run of capitalised words ("Search API", "Deep Research") is a
   candidate if it's capitalised mid-sentence, or in a page title or nav label. Seeds from
   the config are always considered. Parameter names are listed separately.
2. **Cluster.** Forms that differ only by case, hyphens, spaces, a plural "s", a
   possessive "'s" or a leading company name share one key. "Perplexity Search APIs" and
   "search API's" are both forms of "Search API".
3. **Count** every form in every analysed snippet, using the full text, not the excerpt.
   Each form counts once per page and excerpt. Matches inside file names, URLs and code
   IDs (like "sonar-pro") don't count. Approved boilerplate counts on one page only.
4. **Propose** a term if it's in a title or nav label, or on 2 or more pages, or on 2 or
   more surfaces. It's rejected if it's on the not_terms or third_party list, if it's a
   single word that is a month, unit or file format, if it's usually lowercase
   mid-sentence (a general word), or if it's never capitalised in running text (a page
   title, not a name). Every candidate is logged with its decision and reason.
5. **Compare like with like.** Variants are compared within labels (titles, headings,
   nav, buttons) and within running text (sentences, errors), never across them. A
   difference between the two becomes a neutral note. A term on fewer pages than
   consistent_min_pages is "too few to tell", not "consistent".
6. **Write** term_candidates.csv (everything) and terms.csv (proposed terms, for review).
   Edits to the `review` and `definition` columns are matched on the `key` column, so
   they survive every re-run, even if the term drops off the list for a while.
"""

from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from audit import evidence, snippets
from audit.config import Target
from audit.snippets import Snippet

# When sources disagree, the higher one wins. The Brand Hub is the company's own published
# guidance, so it comes first. Changelog sits with the blog.
AUTHORITY = (
    "brand", "pricing", "docs", "help", "blog", "changelog", "web-app", "ios-app", "comet",
)

# No apostrophes inside a word, so "Agent API's" is read as "Agent API".
CAP_WORD = r"[A-Z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*"
CAP_RUN = re.compile(rf"\b{CAP_WORD}(?:[ -]{CAP_WORD}){{0,3}}\b")
TOKEN = re.compile(r"[a-z0-9]+")
# A capital straight after one of these is a sentence start, not evidence of a name.
SENTENCE_BREAK = re.compile(r"[.!?:;\"'“(\[]\s*$")

# A name is capitalised at least this often when it appears mid-sentence.
MIN_CAPITALISED_SHARE = 0.5
# ...judged only once it has appeared mid-sentence at least this many times.
MIN_MID_SENTENCE_USES = 3

# Labels and running text use case differently on purpose ("API Reference" in nav,
# "API reference" in a sentence), so variants are only compared within a group.
LABELS = ("title", "heading", "nav", "button", "label")
RUNNING_TEXT = ("sentence", "error")
GROUP_NAMES = {"labels": "labels", "running": "running text"}

# Single words that are never this company's terms, whatever the company.
MONTHS = {
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december",
}
UNITS = {
    "kb", "mb", "gb", "tb", "kib", "mib", "gib", "tib", "ms", "px", "pt", "em", "rem",
    "usd", "eur", "gbp",
}
FILE_FORMATS = {
    "png", "jpg", "jpeg", "gif", "svg", "webp", "pdf", "csv", "json", "jsonl", "yaml",
    "yml", "xml", "html", "txt", "md", "mp3", "mp4", "wav", "zip", "docx", "xlsx",
}
# Text on more than this many pages is listed as a boilerplate candidate for review.
REPEATED_ON_PAGES = 10


def group_of(kind: str) -> str | None:
    if kind in LABELS:
        return "labels"
    if kind in RUNNING_TEXT:
        return "running"
    return None


def is_mid_sentence(text: str, start: int) -> bool:
    return start > 0 and not SENTENCE_BREAK.search(text[:start])


def inside_identifier(text: str, start: int, end: int) -> bool:
    """True for a match that's part of a file name, URL or code ID rather than prose.

    Examples: the "SKILL" in "SKILL.md", the "deep-research" in "sonar-deep-research",
    and "sonar-pro" on its own (a lowercase name joined by a hyphen is a model or tool ID).
    """
    matched = text[start:end]
    before = text[start - 1] if start > 0 else ""
    after = text[end] if end < len(text) else ""
    after_next = text[end + 1] if end + 1 < len(text) else ""
    if before and before in "-_/.":
        return True
    if after and after in "-_/":
        return True
    if after == "." and after_next.isalnum():
        return True
    if "-" in matched and matched == matched.lower():
        return True
    return False


CANDIDATE_COLUMNS = (
    "key", "form", "type", "pages", "surfaces", "in_title_or_nav", "seed", "decision", "reason",
)
TERM_COLUMNS = (
    "term", "review", "definition", "preferred_form", "status", "question", "note",
    "variants", "uses", "pages", "surfaces", "sources", "example_ids", "key",
)
# Columns a person fills in. They survive every re-run.
HUMAN_COLUMNS = ("review", "definition")


def strip_company(words: list[str], company: str) -> list[str]:
    if len(words) > 1 and words[0].lower() == company.lower():
        return words[1:]
    return words


def strip_possessive(form: str) -> str:
    return re.sub(r"['’]s$", "", form)


def plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def term_key(form: str, company: str) -> str:
    """Everything that doesn't change the name: case, spaces, hyphens, plural, possessive
    and company prefix."""
    words = strip_company(strip_possessive(form).replace("-", " ").split(), company)
    key = "".join(words).lower()
    if len(key) > 3 and key.endswith("s") and not key.endswith("ss"):
        key = key[:-1]
    return key


def shape(form: str, company: str) -> str:
    """The parts of a form that count as a real variant: case, spacing and hyphens.

    A plural or a leading company name is a normal grammatical choice, so they're
    ignored here. They still show up in the variant counts.
    """
    words = strip_company(form.split(), company)
    text = " ".join(words)
    if len(text) > 3 and text.endswith("s") and not text.endswith("ss"):
        text = text[:-1]
    return text


def form_pattern(form: str, company: str) -> re.Pattern[str]:
    """Matches a term in any case, with spaces or hyphens, plural or not, with or without
    the company name in front."""
    words = strip_company(form.replace("-", " ").split(), company)
    words[-1] = words[-1].removesuffix("s") if len(words[-1]) > 3 else words[-1]
    body = r"[\s-]?".join(re.escape(w) for w in words)
    return re.compile(rf"\b(?:{re.escape(company)}\s+)?{body}s?\b", re.IGNORECASE)


@dataclass
class Cluster:
    key: str
    forms_seen: Counter[str] = field(default_factory=Counter)
    seed: bool = False
    in_title_or_nav: bool = False
    uses: Counter[str] = field(default_factory=Counter)
    pages: set[str] = field(default_factory=set)
    surfaces: Counter[str] = field(default_factory=Counter)
    form_by_surface: dict[str, Counter[str]] = field(default_factory=lambda: defaultdict(Counter))
    # Forms split into labels and running text, so like is compared with like.
    form_by_group: dict[str, Counter[str]] = field(default_factory=lambda: defaultdict(Counter))
    example_ids: list[str] = field(default_factory=list)
    mid_capitalised: int = 0
    mid_lowercase: int = 0
    # (page, excerpt, form) already counted, so each form counts once per page and excerpt.
    counted: set[tuple[str, str, str]] = field(default_factory=set)
    # Approved repeated text already counted on one page.
    repeated_counted: set[str] = field(default_factory=set)

    @property
    def label(self) -> str:
        return self.forms_seen.most_common(1)[0][0]

    @property
    def capitalised_share(self) -> float:
        total = self.mid_capitalised + self.mid_lowercase
        return self.mid_capitalised / total if total else 1.0


@dataclass(frozen=True)
class Text:
    snippet: Snippet
    text: str
    tokens: frozenset[str]


def load_texts(target: Target) -> list[Text]:
    """Every analysed snippet with its full text, from the local tables extract writes."""
    if not target.local_snippets.exists() or not target.full_text.exists():
        raise FileNotFoundError(
            f"The local snippets table isn't there yet ({target.local_snippets}). "
            f"The committed copy only has evidence excerpts, so terms can't count from it. "
            f"Run `audit fetch --target {target.name}` and then "
            f"`audit extract --target {target.name}` first."
        )
    rows = snippets.read(target.local_snippets)
    with target.full_text.open(newline="", encoding="utf-8") as f:
        full = {row["id"]: row["text"] for row in csv.DictReader(f)}
    return [
        Text(s, full[s.id], frozenset(TOKEN.findall(full[s.id].lower())))
        for s in rows
        if target.analysed(s.source_url) and s.id in full
    ]


def find_candidates(texts: Iterable[Text], target: Target) -> dict[str, Cluster]:
    company = target.display_name
    clusters: dict[str, Cluster] = {}

    def add(form: str) -> Cluster:
        key = term_key(form, company)
        cluster = clusters.setdefault(key, Cluster(key))
        cluster.forms_seen[form] += 1
        return cluster

    for t in texts:
        if t.snippet.kind == "parameter":
            continue
        for match in CAP_RUN.finditer(t.text):
            if len(match.group()) < 2:
                continue
            labelled = t.snippet.kind in ("title", "nav")
            if not labelled and not is_mid_sentence(t.text, match.start()):
                continue
            cluster = add(match.group())
            if t.snippet.kind in ("title", "nav"):
                cluster.in_title_or_nav = True
    for seed in target.terms.seeds:
        add(seed).seed = True
    return clusters


def count_uses(
    clusters: dict[str, Cluster],
    texts: list[Text],
    company: str,
    repeated: Iterable[str] = (),
    not_names: Iterable[str] = (),
) -> None:
    """Count every form of every cluster.

    Each form counts once per page and excerpt, so a heading that says "Agent API Agent
    API" counts once. Text a person has approved as repeated boilerplate (the config's
    repeated_text) counts on one page only, not once per page it appears on.

    `not_names` are cluster keys from the not_terms list. They aren't names, so they don't
    hide the names inside them: rejecting the page title "Agent API Quickstart" still lets
    it count as a use of "Agent API".
    """
    skip_claim = set(not_names)
    approved = {" ".join(r.split()) for r in repeated}
    by_token: dict[str, list[Text]] = defaultdict(list)
    for t in texts:
        for token in t.tokens:
            by_token[token].append(t)

    company_prefix = re.compile(rf"^{re.escape(company)}\s+", re.IGNORECASE)
    # Longer names are counted first and claim their place in the text. Example: in
    # "Call the Agent API Models endpoint", "Agent API Models" is counted and claims those
    # characters, so "Agent API" and "Agent" don't count the same words again.
    claimed: dict[int, list[tuple[int, int]]] = defaultdict(list)
    longest_first = sorted(clusters.values(), key=lambda c: -len(c.label.split()))

    for cluster in longest_first:
        words = strip_company(cluster.label.replace("-", " ").split(), company)
        first_word = words[0].lower()
        # Only look in snippets that contain the first word, singular or plural.
        stem = first_word.removesuffix("s")
        pool = {id(t): t for w in (first_word, stem, stem + "s") for t in by_token.get(w, [])}
        pattern = form_pattern(cluster.label, company)
        for t in pool.values():
            for match in pattern.finditer(t.text):
                start, end = match.span()
                if any(s <= start and end <= e for s, e in claimed[id(t)]):
                    continue
                if inside_identifier(t.text, start, end):
                    continue
                form = match.group()
                name_part = company_prefix.sub("", form)
                # Only a written-as-a-name match claims its place. "with Comet" mustn't hide
                # a use of "Comet". This happens before the checks below, so a skipped
                # duplicate still stops shorter names counting inside it.
                if (
                    len(words) > 1
                    and cluster.key not in skip_claim
                    and all(w[:1].isupper() for w in name_part.split())
                ):
                    claimed[id(t)].append((start, end))
                once = (t.snippet.source_url, t.text, form)
                if once in cluster.counted:
                    continue
                if t.text in approved and t.text in cluster.repeated_counted:
                    continue
                cluster.counted.add(once)
                if t.text in approved:
                    cluster.repeated_counted.add(t.text)
                mid = t.snippet.kind == "sentence" and is_mid_sentence(t.text, start)
                if mid:
                    if name_part[:1].isupper():
                        cluster.mid_capitalised += 1
                    else:
                        cluster.mid_lowercase += 1
                cluster.uses[form] += 1
                cluster.pages.add(t.snippet.source_url)
                cluster.surfaces[t.snippet.surface] += 1
                cluster.form_by_surface[t.snippet.surface][form] += 1
                group = group_of(t.snippet.kind)
                if group:
                    cluster.form_by_group[group][form] += 1
                if len(cluster.example_ids) < 5 and t.snippet.id not in cluster.example_ids:
                    cluster.example_ids.append(t.snippet.id)


def general_word(cluster: Cluster, target: Target) -> str:
    """Why a single word can't be this company's term, or "" if it might be.

    Month names, units and file formats never are, whatever the company. Third-party
    products come from the config's third_party list.
    """
    third_party = {term_key(n, target.display_name) for n in target.terms.third_party}
    if cluster.key in third_party:
        return "a third-party product, on the third_party list"
    if len(cluster.label.split()) != 1:
        return ""
    word = cluster.label.lower()
    if word in MONTHS or cluster.key in MONTHS:
        return "a month name"
    if word in UNITS or cluster.key in UNITS:
        return "a unit"
    if word in FILE_FORMATS or cluster.key in FILE_FORMATS:
        return "a file format"
    return ""


def decide(cluster: Cluster, target: Target) -> tuple[str, str]:
    not_terms = {term_key(n, target.display_name) for n in target.terms.not_terms}
    if cluster.key in not_terms:
        return "rejected", "on the not_terms list"
    if cluster.key == term_key(target.display_name, ""):
        return "rejected", "the company name itself"
    general = general_word(cluster, target)
    if general:
        return "rejected", general
    if not cluster.uses:
        return "rejected", "seed not found in first-party snippets" if cluster.seed else "no uses"
    mid_uses = cluster.mid_capitalised + cluster.mid_lowercase
    if (
        not cluster.seed
        and mid_uses >= MIN_MID_SENTENCE_USES
        and cluster.capitalised_share < MIN_CAPITALISED_SHARE
    ):
        return "rejected", (
            f"capitalised in only {cluster.capitalised_share:.0%} of {mid_uses} mid-sentence "
            "uses, so probably a general word"
        )
    if not cluster.seed and cluster.mid_capitalised == 0:
        return "rejected", "never capitalised in running text, so a title or label, not a name"
    if not cluster.seed and len(cluster.label.split()) >= 3 and mid_uses < MIN_MID_SENTENCE_USES:
        return "rejected", "a page title or label, rarely used in running text"
    if cluster.in_title_or_nav:
        return "proposed", "in a page title or nav label"
    if len(cluster.pages) >= 2:
        return "proposed", f"on {len(cluster.pages)} pages"
    if len(cluster.surfaces) >= 2:
        return "proposed", f"on {len(cluster.surfaces)} surfaces"
    return "rejected", "on 1 page only, and not in a title or nav label"


def preferred_form(cluster: Cluster, company: str) -> str:
    """The most used capitalised spelling on the highest-authority surface that uses it.

    Plurals and the company prefix are grouped first, so "Skills" and "Skill" together
    outweigh "SKILL". The most common form in the winning group is returned. A surface
    that only uses lowercase forms is skipped, so one lowercase use on a pricing page can't
    outrank fifty capitalised uses in the docs.
    """

    def best_of(forms: dict[str, int]) -> str:
        by_shape: dict[str, Counter[str]] = defaultdict(Counter)
        for form, n in forms.items():
            by_shape[shape(form, company)][form] += n
        best = max(by_shape.values(), key=lambda c: (sum(c.values()), c.most_common(1)[0][1]))
        return best.most_common(1)[0][0]

    for surface in AUTHORITY:
        forms = cluster.form_by_surface.get(surface, Counter())
        capitalised = {f: n for f, n in forms.items() if f[:1].isupper()}
        if capitalised:
            return best_of(capitalised)
    if cluster.uses:
        return best_of(dict(cluster.uses))
    return cluster.label


def spellings(forms: Counter[str], company: str) -> list[Counter[str]]:
    """Real forms grouped by shape, most used first.

    Each group's most common real form is what gets quoted, so a question never quotes a
    spelling that doesn't appear in the text.
    """
    groups: dict[str, Counter[str]] = defaultdict(Counter)
    for form, n in forms.items():
        groups[shape(form, company)][form] += n
    return sorted(groups.values(), key=lambda c: -sum(c.values()))


def top(group: Counter[str]) -> str:
    return group.most_common(1)[0][0]


def quote(group: Counter[str]) -> str:
    return f"'{top(group)}' ({sum(group.values())})"


def is_title_case(form: str, company: str) -> bool:
    words = strip_company(form.split(), company)
    return len(words) > 1 and all(w[:1].isupper() for w in words)


def status_and_question(
    cluster: Cluster, preferred: str, target: Target, clusters: dict[str, Cluster]
) -> tuple[str, str, str]:
    """The term's status, the question to ask, and a neutral note.

    Variants are compared within labels and within running text, never across them,
    because labels often use title case on purpose. A difference between the two groups
    becomes a note, not a question.
    """
    company = target.display_name
    questions = []

    # Lowercase uses ("create a connector") are the general word or a slip, whatever the
    # group, so they're one question. Capitalised spellings are compared within a group.
    running = spellings(cluster.form_by_group["running"], company)
    labels = spellings(cluster.form_by_group["labels"], company)
    running_caps = [g for g in running if top(g)[:1].isupper()]
    label_caps = [g for g in labels if top(g)[:1].isupper()]
    lowercase = spellings(
        Counter({f: n for f, n in cluster.uses.items() if not f[:1].isupper()}), company
    )

    for name, caps in (("running text", running_caps), ("labels", label_caps)):
        if len(caps) > 1:
            listed = ", ".join(quote(g) for g in caps)
            questions.append(
                f"In {name}, written {len(caps)} ways: {listed}. Which form should be used?"
            )
    if lowercase and not (running_caps or label_caps):
        questions.append(
            f"Only ever written in lowercase ('{top(lowercase[0])}'). Is this a product name?"
        )
    elif lowercase:
        n = sum(sum(g.values()) for g in lowercase)
        questions.append(
            f"Also written in lowercase ('{top(lowercase[0])}', {plural(n, 'time')}). "
            "Is that the product name or the general word?"
        )

    note = ""
    if running_caps and label_caps:
        label_form, text_form = top(label_caps[0]), top(running_caps[0])
        if shape(label_form, company) != shape(text_form, company):
            if is_title_case(label_form, company) and not is_title_case(text_form, company):
                note = (
                    f"Labels use title case ('{label_form}') and running text uses sentence "
                    f"case ('{text_form}')."
                )
            else:
                note = f"Labels use '{label_form}' and running text uses '{text_form}'."
    for legacy in target.terms.legacy_names:
        if term_key(legacy.current, company) == cluster.key:
            old = clusters.get(term_key(legacy.old, company))
            pages = len(old.pages) if old else 0
            if pages:
                questions.append(
                    f"'{legacy.old}' still appears on {plural(pages, 'page')}. The docs "
                    f"describe moving from {legacy.old} to {legacy.current} "
                    f"({legacy.source}). Which of those pages should still say {legacy.old}?"
                )
    if questions:
        return "question", " ".join(questions), note
    pages = len(cluster.pages)
    if pages < target.terms.consistent_min_pages:
        return "too few to tell", (
            f"Only on {plural(pages, 'page')}, which is too few to tell whether it's used "
            "consistently."
        ), note
    return "consistent", (
        f"Written as '{preferred}' on all {pages} pages. "
        "Where do readers first learn what it means?"
    ), note


def sources_for(cluster: Cluster, texts_by_url_surface: dict[str, str]) -> list[str]:
    ranked = sorted(
        cluster.pages,
        key=lambda url: (AUTHORITY.index(texts_by_url_surface.get(url, "comet")), url),
    )
    return ranked[:3]


def parameter_candidates(texts: list[Text], company: str) -> list[dict[str, str]]:
    """Parameter names, clustered so max_results, maxResults and max-results meet."""
    by_key: dict[str, Counter[str]] = defaultdict(Counter)
    pages: dict[str, set[str]] = defaultdict(set)
    for t in texts:
        if t.snippet.kind == "parameter":
            key = re.sub(r"[_\-.]", "", t.text).lower()
            by_key[key][t.text] += 1
            pages[key].add(t.snippet.source_url)
    rows = []
    for key, forms in by_key.items():
        rows.append({
            "key": key,
            "form": " | ".join(f for f, _ in forms.most_common()),
            "type": "parameter",
            "pages": str(len(pages[key])),
            "surfaces": "",
            "in_title_or_nav": "",
            "seed": "",
            "decision": "listed",
            "reason": "parameter names are listed for review, not proposed as terms",
        })
    return rows


def read_human_edits(path: Path, company: str) -> dict[str, dict[str, str]]:
    """Every row a person has filled in, keyed by the `key` column.

    The key never changes, so editing the `term` cell doesn't lose the edits. Older files
    without a key column fall back to working the key out from the term.
    """
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as f:
        return {
            (row.get("key") or term_key(row["term"], company)): dict(row)
            for row in csv.DictReader(f)
            if any(row.get(c) for c in HUMAN_COLUMNS)
        }


def write_csv(path: Path, columns: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def repeated_text(texts: list[Text], target: Target) -> list[dict[str, str]]:
    """Excerpts on more than REPEATED_ON_PAGES pages: candidates for a person to approve
    as boilerplate. Approved ones go in the config's repeated_text list."""
    pages: dict[str, set[str]] = defaultdict(set)
    kinds: dict[str, set[str]] = defaultdict(set)
    for t in texts:
        if t.snippet.kind != "parameter":
            pages[t.text].add(t.snippet.source_url)
            kinds[t.text].add(t.snippet.kind)
    approved = set(target.terms.repeated_text)
    return [
        {
            "text": text,
            "pages": str(len(urls)),
            "kinds": " ".join(sorted(kinds[text])),
            "approved": "yes" if text in approved else "",
        }
        for text, urls in sorted(pages.items(), key=lambda item: (-len(item[1]), item[0]))
        if len(urls) > REPEATED_ON_PAGES
    ]


def run(target: Target, *, log: Callable[[str], None] = print) -> list[dict[str, str]]:
    company = target.display_name
    texts = load_texts(target)
    surface_of = {t.snippet.source_url: t.snippet.surface for t in texts}
    clusters = find_candidates(texts, target)
    not_names = {term_key(n, company) for n in target.terms.not_terms}
    count_uses(clusters, texts, company, target.terms.repeated_text, not_names)

    candidate_rows = []
    proposed: list[Cluster] = []
    for cluster in sorted(clusters.values(), key=lambda c: (-len(c.pages), c.key)):
        decision, reason = decide(cluster, target)
        if decision == "proposed":
            proposed.append(cluster)
        candidate_rows.append({
            "key": cluster.key,
            "form": cluster.label,
            "type": "name",
            "pages": str(len(cluster.pages)),
            "surfaces": " ".join(sorted(cluster.surfaces)),
            "in_title_or_nav": "yes" if cluster.in_title_or_nav else "",
            "seed": "yes" if cluster.seed else "",
            "decision": decision,
            "reason": reason,
        })

    edits = read_human_edits(target.data_dir / "terms.csv", company)
    # Seeds and anything a person has already reviewed come first, then the most widespread.
    proposed.sort(key=lambda c: (not (c.key in edits or c.seed), -len(c.pages), c.key))
    keep = proposed[: target.terms.max_proposed]
    keep += [c for c in proposed[target.terms.max_proposed :] if c.key in edits]
    for row in candidate_rows:
        if row["decision"] == "proposed" and row["key"] not in {c.key for c in keep}:
            row["decision"] = "not shown"
            row["reason"] += f"; outside the top {target.terms.max_proposed}"

    term_rows = []
    for cluster in keep:
        preferred = preferred_form(cluster, company)
        status, question, note = status_and_question(cluster, preferred, target, clusters)
        human = edits.get(cluster.key, {})
        term_rows.append({
            "term": human.get("term") or preferred,
            "review": human.get("review", ""),
            "definition": human.get("definition", ""),
            "preferred_form": preferred,
            "status": status,
            "question": question,
            "note": note,
            "variants": "; ".join(f"{f} ({n})" for f, n in cluster.uses.most_common()),
            "uses": str(sum(cluster.uses.values())),
            "pages": str(len(cluster.pages)),
            "surfaces": " ".join(s for s in AUTHORITY if s in cluster.surfaces),
            "sources": " | ".join(sources_for(cluster, surface_of)),
            "example_ids": " ".join(cluster.example_ids),
            "key": cluster.key,
        })

    # A reviewed term that isn't proposed this run stays in the file, so the review work
    # is never lost. The question says why it dropped out.
    reasons = {row["key"]: row["reason"] for row in candidate_rows}
    shown = {c.key for c in keep}
    for key, human in edits.items():
        if key in shown:
            continue
        reason = reasons.get(key, "not found in this run's snippets")
        term_rows.append({
            **{c: "" for c in TERM_COLUMNS},
            **{c: human.get(c, "") for c in ("term", *HUMAN_COLUMNS)},
            "status": "question",
            "question": f"Not proposed this run ({reason}). Keep it, or reject it?",
            "key": key,
        })

    candidate_rows += parameter_candidates(texts, company)
    write_csv(target.data_dir / "term_candidates.csv", CANDIDATE_COLUMNS, candidate_rows)
    write_csv(target.data_dir / "terms.csv", TERM_COLUMNS, term_rows)

    # Repeated text holds full excerpts, so the list stays on this computer.
    repeats = repeated_text(texts, target)
    write_csv(target.cache_dir / "repeated_text.csv", ("text", "pages", "kinds", "approved"),
              repeats)

    # The term map decides which snippets are evidence, so the committed copy is redone.
    filled = evidence.write_public_copy(target, snippets.read(target.local_snippets), log=log)

    decisions = Counter(r["decision"] for r in candidate_rows)
    statuses = Counter(r["status"] for r in term_rows)
    log(
        f"{len(texts)} snippets analysed. Candidates: "
        + ", ".join(f"{k} {v}" for k, v in decisions.most_common())
    )
    log(f"{len(term_rows)} terms for review: " + ", ".join(f"{k} {v}" for k, v in statuses.items()))
    waiting = sum(1 for r in repeats if not r["approved"])
    log(
        f"{len(repeats)} excerpts appear on more than {REPEATED_ON_PAGES} pages ({waiting} not "
        f"yet approved as boilerplate). See {target.cache_dir / 'repeated_text.csv'}."
    )
    log(f"Wrote {target.data_dir / 'terms.csv'} and {target.data_dir / 'term_candidates.csv'}")
    log(f"Wrote {target.public_snippets} (committed, {filled} evidence excerpts)")
    return term_rows
