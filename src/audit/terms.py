"""`audit terms`: find the names a company uses, and show where the wording varies.

How it works, step by step:

1. **Candidates.** A run of capitalised words ("Search API", "Deep Research") is a
   candidate if it's capitalised mid-sentence, or in a page title or nav label. Seeds from
   the config are always considered. Parameter names are listed separately.
2. **Cluster.** Forms that differ only by case, hyphens, spaces, a plural "s", a
   possessive "'s" or a leading company name share one key. "Perplexity Search APIs" and
   "search API's" are both forms of "Search API".
3. **Count** every form in every analysed snippet, using the full text, not the excerpt.
   Matches inside file names, URLs and code IDs (like "sonar-pro") don't count.
4. **Propose** a term if it's in a title or nav label, or on 2 or more pages, or on 2 or
   more surfaces. It's rejected if it's on the config's not_terms list, if it's usually
   lowercase mid-sentence (a general word), or if it's never capitalised in running text
   (a page title, not a name). Every candidate is logged with its decision and reason.
5. **Write** term_candidates.csv (everything) and terms.csv (proposed terms, for review).
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

from audit import snippets
from audit.config import Target
from audit.snippets import Snippet

# When sources disagree, the higher one wins. Changelog sits with the blog.
AUTHORITY = ("pricing", "docs", "help", "blog", "changelog", "web-app", "ios-app", "comet")

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
    "term", "review", "definition", "preferred_form", "status", "question", "variants",
    "uses", "pages", "surfaces", "sources", "example_ids", "key",
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
    example_ids: list[str] = field(default_factory=list)
    mid_capitalised: int = 0
    mid_lowercase: int = 0

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
    rows = snippets.read(target.data_dir / "snippets.csv")
    full_path = target.cache_dir / "snippets_full.csv"
    if not full_path.exists():
        raise FileNotFoundError(f"{full_path} is missing. Run `audit extract` first.")
    with full_path.open(newline="", encoding="utf-8") as f:
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


def count_uses(clusters: dict[str, Cluster], texts: list[Text], company: str) -> None:
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
                mid = t.snippet.kind == "sentence" and is_mid_sentence(t.text, start)
                if mid:
                    if name_part[:1].isupper():
                        cluster.mid_capitalised += 1
                    else:
                        cluster.mid_lowercase += 1
                # Only a written-as-a-name match claims its place. "with Comet" mustn't hide
                # a use of "Comet".
                if len(words) > 1 and all(w[:1].isupper() for w in name_part.split()):
                    claimed[id(t)].append((start, end))
                cluster.uses[form] += 1
                cluster.pages.add(t.snippet.source_url)
                cluster.surfaces[t.snippet.surface] += 1
                cluster.form_by_surface[t.snippet.surface][form] += 1
                if len(cluster.example_ids) < 5 and t.snippet.id not in cluster.example_ids:
                    cluster.example_ids.append(t.snippet.id)


def decide(cluster: Cluster, target: Target) -> tuple[str, str]:
    not_terms = {term_key(n, target.display_name) for n in target.terms.not_terms}
    if cluster.key in not_terms:
        return "rejected", "on the not_terms list"
    if cluster.key == term_key(target.display_name, ""):
        return "rejected", "the company name itself"
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


def status_and_question(
    cluster: Cluster, preferred: str, target: Target, clusters: dict[str, Cluster]
) -> tuple[str, str]:
    company = target.display_name
    questions = []

    # Group the real forms by shape, and quote the most common real form of each group,
    # so a question never quotes a spelling that doesn't appear in the text.
    groups: dict[str, Counter[str]] = defaultdict(Counter)
    for form, n in cluster.uses.items():
        groups[shape(form, company)][form] += n
    ranked = sorted(groups.values(), key=lambda c: -sum(c.values()))
    capitalised = [g for g in ranked if g.most_common(1)[0][0][:1].isupper()]
    lowercase = [g for g in ranked if not g.most_common(1)[0][0][:1].isupper()]

    def quote(group: Counter[str]) -> str:
        return f"'{group.most_common(1)[0][0]}' ({sum(group.values())})"

    if len(capitalised) > 1:
        listed = ", ".join(quote(g) for g in capitalised)
        questions.append(f"Written {len(capitalised)} ways: {listed}. Which form should be used?")
    if lowercase and not capitalised:
        form = lowercase[0].most_common(1)[0][0]
        questions.append(f"Only ever written in lowercase ('{form}'). Is this a product name?")
    elif lowercase:
        n = sum(sum(g.values()) for g in lowercase)
        form = lowercase[0].most_common(1)[0][0]
        questions.append(
            f"Also written in lowercase ('{form}', {plural(n, 'time')}). "
            "Is that the product name or the general word?"
        )
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
        return "question", " ".join(questions)
    pages = len(cluster.pages)
    where = "on its only page" if pages == 1 else f"on all {pages} pages"
    return "consistent", (
        f"Written as '{preferred}' {where}. Where do readers first learn what it means?"
    )


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


def run(target: Target, *, log: Callable[[str], None] = print) -> list[dict[str, str]]:
    company = target.display_name
    texts = load_texts(target)
    surface_of = {t.snippet.source_url: t.snippet.surface for t in texts}
    clusters = find_candidates(texts, target)
    count_uses(clusters, texts, company)

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
        status, question = status_and_question(cluster, preferred, target, clusters)
        human = edits.get(cluster.key, {})
        term_rows.append({
            "term": human.get("term") or preferred,
            "review": human.get("review", ""),
            "definition": human.get("definition", ""),
            "preferred_form": preferred,
            "status": status,
            "question": question,
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

    decisions = Counter(r["decision"] for r in candidate_rows)
    statuses = Counter(r["status"] for r in term_rows)
    log(
        f"{len(texts)} snippets analysed. Candidates: "
        + ", ".join(f"{k} {v}" for k, v in decisions.most_common())
    )
    log(f"{len(term_rows)} terms for review: " + ", ".join(f"{k} {v}" for k, v in statuses.items()))
    log(f"Wrote {target.data_dir / 'terms.csv'} and {target.data_dir / 'term_candidates.csv'}")
    return term_rows
