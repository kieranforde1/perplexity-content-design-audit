"""`audit extract`: turn cached pages into rows in the snippets table.

From each page we keep the pieces of text a reader meets: the title, headings,
navigation and button labels, parameter names, error messages and sentences.
Code samples are skipped, except for error messages inside them.

Two files come out:
- data/<target>/snippets.csv: committed. Short excerpts only.
- cache/<target>/snippets_full.csv: gitignored. Full text by snippet ID, so later
  steps (like counting term variants) see whole sentences, not cut-off excerpts.
"""

from __future__ import annotations

import csv
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

from audit import snippets
from audit.config import Target
from audit.fetch import read_manifest
from audit.snippets import Snippet


@dataclass(frozen=True)
class Piece:
    """One bit of text found on a page, before it becomes a snippet."""

    kind: str
    text: str


# Short sentences under this many words are usually fragments ("See below.").
MIN_SENTENCE_WORDS = 3

FENCE = re.compile(r"^\s*(```|~~~)")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{2,}")
BLOCKQUOTE = re.compile(r"^\s*(?:>\s?)+")
CARD = re.compile(r"^\[card\]\s*")
LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
CODE_SPAN = re.compile(r"`([^`]+)`")
BOLD = re.compile(r"\*\*([^*]+)\*\*")
STAR_EMPHASIS = re.compile(r"(\*\*|\*)(?=\S)(.+?)(?<=\S)\1")
# Underscores count as emphasis only at word edges, so max_results stays intact.
UNDERSCORE_EMPHASIS = re.compile(r"(?<!\w)(__|_)(?=\S)(.+?)(?<=\S)\1(?!\w)")
TAG = re.compile(r"<[^>]+>")
IDENTIFIER = re.compile(r"^[A-Za-z_][\w.\-/]*$")
ERROR_MESSAGE = re.compile(r'"(?:message|error|detail)"\s*:\s*"([^"]{3,200})"')
SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'“(])")

# Words just before a bold label that tell us what kind of label it is.
# "Click **Save**" is a button. "Open **Settings**" is a place in the navigation.
BUTTON_VERBS = ("click", "select", "tap", "press", "choose")
NAV_VERBS = ("open", "go to", "navigate to", "visit")


def plain(text: str) -> str:
    """Markdown and inline HTML stripped down to the words a reader sees."""
    text = LINK.sub(r"\1", text)
    text = CODE_SPAN.sub(r"\1", text)
    text = STAR_EMPHASIS.sub(r"\2", text)
    text = UNDERSCORE_EMPHASIS.sub(r"\2", text)
    text = TAG.sub(" ", text)
    return " ".join(text.split())


def split_sentences(text: str) -> list[str]:
    return [s for s in SENTENCE_END.split(text) if len(s.split()) >= MIN_SENTENCE_WORDS]


def pieces_from_inline(text: str) -> list[Piece]:
    found: list[Piece] = []
    for code in CODE_SPAN.findall(text):
        if IDENTIFIER.match(code) and len(code) <= 60:
            found.append(Piece("parameter", code))
    for match in BOLD.finditer(text):
        before = plain(text[: match.start()]).lower().rstrip()
        label = plain(match.group(1))
        if before.endswith(BUTTON_VERBS):
            found.append(Piece("button", label))
        elif before.endswith(NAV_VERBS):
            found.append(Piece("nav", label))
    found += [Piece("sentence", s) for s in split_sentences(plain(text))]
    return found


def extract_markdown(text: str, boilerplate: tuple[str, ...] = ()) -> list[Piece]:
    found: list[Piece] = []
    paragraph: list[str] = []
    code: list[str] = []
    in_code = False
    has_title = False

    def flush() -> None:
        if paragraph:
            found.extend(pieces_from_inline(" ".join(paragraph)))
            paragraph.clear()

    for raw_line in text.splitlines():
        if FENCE.match(raw_line):
            if in_code:
                found += [Piece("error", m) for m in ERROR_MESSAGE.findall("\n".join(code))]
                code.clear()
            else:
                flush()
            in_code = not in_code
            continue
        if in_code:
            code.append(raw_line)
            continue

        line = BLOCKQUOTE.sub("", raw_line).strip()
        if not line or any(b in line for b in boilerplate):
            flush()
            continue

        heading = HEADING.match(line)
        if heading:
            flush()
            kind = "title" if len(heading.group(1)) == 1 and not has_title else "heading"
            has_title = has_title or kind == "title"
            found.append(Piece(kind, plain(heading.group(2))))
        elif CARD.match(line):
            flush()
            found += [Piece("nav", plain(label)) for label in LINK.findall(line)]
        elif line.startswith("|"):
            flush()
            if not TABLE_SEPARATOR.match(line):
                for cell in line.strip("|").split("|"):
                    found.extend(pieces_from_inline(cell))
        elif LIST_ITEM.match(line):
            flush()
            paragraph.append(LIST_ITEM.sub("", line))
        else:
            paragraph.append(line)
    flush()
    return [p for p in found if p.text]


class _HtmlPieces(HTMLParser):
    """Collects text from the HTML elements we care about.

    Each element we care about opens a "frame". Text goes to the innermost open frame,
    so a link inside a list item is counted once, not twice.
    """

    SKIP = {"script", "style", "noscript", "svg", "template"}
    CAPTURE = {"title", "h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "td", "th", "dd",
               "dt", "button", "label", "summary", "figcaption", "a"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found: list[Piece] = []
        self._frames: list[tuple[str, str, list[str]]] = []
        self._open: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._open.append(tag)
        if tag in self.SKIP:
            self._skip_depth += 1
            return
        attributes = {k: v or "" for k, v in attrs}
        kind = self._kind(tag, attributes)
        if kind:
            self._frames.append((tag, kind, []))

    def _kind(self, tag: str, attributes: dict[str, str]) -> str | None:
        if attributes.get("role") == "alert" or "error" in attributes.get("class", ""):
            return "error"
        if tag == "title":
            return "title"
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            return "heading"
        if tag == "button" or attributes.get("role") == "button":
            return "button"
        if tag == "a":
            return "nav" if "nav" in self._open else None
        if tag in self.CAPTURE:
            return "sentence"
        return None

    def handle_endtag(self, tag: str) -> None:
        if tag not in self._open:
            return
        while self._open:
            closed = self._open.pop()
            if closed in self.SKIP:
                self._skip_depth -= 1
            if self._frames and self._frames[-1][0] == closed:
                _, kind, parts = self._frames.pop()
                self._emit(kind, " ".join(" ".join(parts).split()))
            if closed == tag:
                break

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0 and self._frames:
            self._frames[-1][2].append(data)

    def _emit(self, kind: str, text: str) -> None:
        if not text:
            return
        if kind == "sentence":
            self.found += [Piece("sentence", s) for s in split_sentences(text)]
        else:
            self.found.append(Piece(kind, text))


def extract_html(text: str, boilerplate: tuple[str, ...] = ()) -> list[Piece]:
    parser = _HtmlPieces()
    parser.feed(text)
    parser.close()
    return [p for p in parser.found if not any(b in p.text for b in boilerplate)]


def is_markdown(url: str, content_type: str) -> bool:
    return url.endswith((".md", ".txt")) or content_type in {
        "text/markdown",
        "text/x-markdown",
        "text/plain",
    }


def snippets_from_cache(target: Target) -> tuple[list[Snippet], dict[str, str]]:
    found: list[Snippet] = []
    full_text: dict[str, str] = {}
    for url, row in sorted(read_manifest(target.cache_dir).items()):
        page = (target.cache_dir / row["file"]).read_text(encoding="utf-8")
        parse = extract_markdown if is_markdown(url, row["content_type"]) else extract_html
        for piece in parse(page, target.boilerplate):
            s = snippets.build(
                text=piece.text,
                kind=piece.kind,
                source_url=url,
                surface=row["surface"],
                stage=target.stage_for(url),
                captured_on=row["fetched_on"],
                method="crawl",
            )
            # The same text on the same page counts once.
            if s.id not in full_text:
                found.append(s)
                full_text[s.id] = " ".join(piece.text.split())
    return found, full_text


def snippets_from_typed(path: Path | None) -> tuple[list[Snippet], dict[str, str]]:
    if path is None or not path.exists():
        return [], {}
    found: list[Snippet] = []
    full_text: dict[str, str] = {}
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            s = snippets.build(
                text=row["text"],
                kind=row["kind"],
                source_url=row["source_url"],
                surface=row["surface"],
                stage=row["stage"],
                captured_on=row["captured_on"],
                method="typed",
            )
            if s.id not in full_text:
                found.append(s)
                full_text[s.id] = " ".join(row["text"].split())
    return found, full_text


def run(
    target: Target, *, dry_run: bool = False, log: Callable[[str], None] = print
) -> list[Snippet]:
    crawled, crawled_text = snippets_from_cache(target)
    typed, typed_text = snippets_from_typed(target.typed_strings)
    all_snippets = crawled + [s for s in typed if s.id not in crawled_text]
    full_text = {**typed_text, **crawled_text}

    by_kind = Counter(s.kind for s in all_snippets)
    by_surface = Counter(s.surface for s in all_snippets)
    log(f"{len(all_snippets)} snippets ({len(crawled)} crawled, {len(typed)} typed)")
    log("  by surface: " + ", ".join(f"{k} {v}" for k, v in by_surface.most_common()))
    log("  by kind: " + ", ".join(f"{k} {v}" for k, v in by_kind.most_common()))

    if dry_run:
        log("Dry run: nothing written.")
        return all_snippets

    out = target.data_dir / "snippets.csv"
    snippets.write(out, all_snippets)
    full_path = target.cache_dir / "snippets_full.csv"
    full_path.parent.mkdir(parents=True, exist_ok=True)
    with full_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "text"])
        for s in all_snippets:
            writer.writerow([s.id, full_text[s.id]])
    log(f"Wrote {out} and {full_path}")
    return all_snippets
