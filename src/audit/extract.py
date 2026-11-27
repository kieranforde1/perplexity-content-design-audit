"""`audit extract`: turn cached pages into rows in the snippets table.

From each page we keep the pieces of text a reader meets: the title, headings,
navigation and button labels, parameter names, error messages and sentences.
Code samples are skipped, except for error messages inside them.

Three files come out:
- cache/<target>/snippets.csv: the full table, every excerpt. Local only.
- cache/<target>/full_text.csv: full text by snippet ID, so later steps (like counting
  term variants) see whole sentences, not cut-off excerpts. Local only.
- data/<target>/snippets.csv: the committed copy, with excerpts only for evidence rows.
  See evidence.py.

Typed app strings that break the rules in typed.py are skipped, with a message.
"""

from __future__ import annotations

import csv
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

from audit import evidence, snippets, typed
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

# A code fence is 3 or more backticks or tildes. A block only closes on a fence of the
# same character that is at least as long, so ```` can wrap an example containing ```.
FENCE = re.compile(r"^(`{3,}|~{3,})(.*)$")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{2,}")
BLOCKQUOTE = re.compile(r"^\s*(?:>\s?)+")
# Docs-site components written as a marker at the start of a line, like "[card] [Title](url)".
COMPONENT = re.compile(r"^\[(card|accordion|tab)\]\s*(.*)$")
# Images are swapped for their alt text first, so a linked screenshot, [![alt](img)](url),
# leaves only the alt text.
IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
# A backslash before punctuation shows the character literally, as in "\*" or "\-".
ESCAPED = re.compile(r"\\([\\`*_{}\[\]()#+\-.!|<>~$&])")
# YAML front matter at the top of a page: settings, not text a reader sees.
FRONT_MATTER = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
CODE_SPAN = re.compile(r"`([^`]+)`")
BOLD = re.compile(r"\*\*([^*]+)\*\*")
STAR_EMPHASIS = re.compile(r"(\*\*|\*)(?=\S)(.+?)(?<=\S)\1")
# Underscores count as emphasis only at word edges, so max_results stays intact.
UNDERSCORE_EMPHASIS = re.compile(r"(?<!\w)(__|_)(?=\S)(.+?)(?<=\S)\1(?!\w)")
TAG = re.compile(r"<[^>]+>")
IDENTIFIER = re.compile(r"^[A-Za-z_][\w.\-/]*$")
# The value of a "message", "error" or "detail" field in a code sample, allowing escaped
# quotes inside it.
ERROR_MESSAGE = re.compile(r'"(?:message|error|detail)"\s*:\s*"((?:[^"\\]|\\.){3,200})"')
# Single words ("slow") are field values, not messages a reader would see.
MIN_ERROR_WORDS = 2
SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'“(])")

# Words just before a bold label that tell us what kind of label it is.
# "Click **Save**" is a button. "Open **Settings**" is a place in the navigation.
BUTTON_VERBS = ("click", "select", "tap", "press", "choose")
NAV_VERBS = ("open", "go to", "navigate to", "visit")


def plain(text: str) -> str:
    """Markdown and inline HTML stripped down to the words a reader sees."""
    text = IMAGE.sub(r"\1", text)
    text = LINK.sub(r"\1", text)
    text = CODE_SPAN.sub(r"\1", text)
    text = STAR_EMPHASIS.sub(r"\2", text)
    text = UNDERSCORE_EMPHASIS.sub(r"\2", text)
    text = TAG.sub(" ", text)
    text = ESCAPED.sub(r"\1", text)
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
    open_fence = ""
    has_title = False

    def flush() -> None:
        if paragraph:
            found.extend(pieces_from_inline(" ".join(paragraph)))
            paragraph.clear()

    def closes(fence: re.Match[str]) -> bool:
        marker, rest = fence.group(1), fence.group(2)
        return marker[0] == open_fence[0] and len(marker) >= len(open_fence) and not rest.strip()

    for raw_line in FRONT_MATTER.sub("", text).splitlines():
        # Strip quote marks first: code samples often sit inside quoted blocks.
        line = BLOCKQUOTE.sub("", raw_line).strip()
        fence = FENCE.match(line)
        if open_fence:
            if fence and closes(fence):
                for message in ERROR_MESSAGE.findall("\n".join(code)):
                    message = message.replace('\\"', '"')
                    if len(message.split()) >= MIN_ERROR_WORDS:
                        found.append(Piece("error", message))
                code.clear()
                open_fence = ""
            else:
                code.append(line)
            continue
        if fence:
            flush()
            open_fence = fence.group(1)
            continue

        # A backslash at the end of a line is a line break, so the next line is new text.
        line_break = line.endswith("\\") and not line.endswith("\\\\")
        if line_break:
            line = line[:-1].rstrip()

        if not line or any(b in line for b in boilerplate):
            flush()
            continue

        heading = HEADING.match(line)
        if heading:
            flush()
            kind = "title" if len(heading.group(1)) == 1 and not has_title else "heading"
            has_title = has_title or kind == "title"
            found.append(Piece(kind, plain(heading.group(2))))
        elif component := COMPONENT.match(line):
            flush()
            if component.group(1) == "card":
                found += [Piece("nav", plain(label)) for label in LINK.findall(line)]
            else:
                # Accordion and tab titles act as headings for the panel below them.
                found.append(Piece("heading", plain(component.group(2))))
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
        if line_break:
            flush()
    flush()
    return [p for p in found if p.text]


class _HtmlPieces(HTMLParser):
    """Collects text from the HTML elements we care about.

    Each element we care about opens a "frame". Text goes to the innermost open frame,
    so a link inside a list item is counted once, not twice.
    """

    # A footer is the same site links on every page ("Trust center", "Careers"), so it would
    # count once per page and swamp the real uses.
    SKIP = {"script", "style", "noscript", "svg", "template", "footer"}
    CAPTURE = {"title", "h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "td", "th", "dd",
               "dt", "button", "label", "summary", "figcaption", "a"}
    # Layout boxes. Pricing cards keep plan names, prices and feature lines in these, so
    # their own text is kept as a label, unless a sentence or heading already holds it.
    BOXES = {"div", "span"}
    # Longer text in a box is running text, so it's split into sentences instead.
    LABEL_MAX_WORDS = 12

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found: list[Piece] = []
        self._frames: list[tuple[str, str, list[str]]] = []
        self._open: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._open.append(tag)
        attributes = {k: v or "" for k, v in attrs}
        # A logo drawn as an image, like a plan name, is read by its accessible name.
        if tag == "svg" and attributes.get("role") == "img" and attributes.get("aria-label"):
            self.handle_data(" " + attributes["aria-label"] + " ")
        if tag in self.SKIP:
            self._skip_depth += 1
            return
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
        if tag in self.BOXES and all(kind == "label" for _, kind, _ in self._frames):
            return "label"
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
        # One character on its own is an icon or a font sample, not words.
        if kind in {"label", "button"} and len(text) <= 1:
            return
        if kind == "label" and len(text.split()) > self.LABEL_MAX_WORDS:
            kind = "sentence"
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


def snippets_from_typed(
    path: Path | None, log: Callable[[str], None] = print
) -> tuple[list[Snippet], dict[str, str]]:
    if path is None or not path.exists():
        return [], {}
    found: list[Snippet] = []
    full_text: dict[str, str] = {}
    with path.open(newline="", encoding="utf-8") as f:
        for line, row in enumerate(csv.DictReader(f), start=2):
            wrong = typed.problems(row)
            if wrong:
                log(f"Skipped typed string on line {line}: {'; '.join(wrong)}")
                continue
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
    typed_rows, typed_text = snippets_from_typed(target.typed_strings, log)
    all_snippets = crawled + [s for s in typed_rows if s.id not in crawled_text]
    full_text = {**typed_text, **crawled_text}

    by_kind = Counter(s.kind for s in all_snippets)
    by_surface = Counter(s.surface for s in all_snippets)
    log(f"{len(all_snippets)} snippets ({len(crawled)} crawled, {len(typed_rows)} typed)")
    log("  by surface: " + ", ".join(f"{k} {v}" for k, v in by_surface.most_common()))
    log("  by kind: " + ", ".join(f"{k} {v}" for k, v in by_kind.most_common()))

    if dry_run:
        log("Dry run: nothing written.")
        return all_snippets

    snippets.write(target.local_snippets, all_snippets)
    with target.full_text.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "text"])
        for s in all_snippets:
            writer.writerow([s.id, full_text[s.id]])
    filled = evidence.write_public_copy(target, all_snippets, log=log)
    log(f"Wrote {target.local_snippets} and {target.full_text} (local only)")
    log(f"Wrote {target.public_snippets} (committed, {filled} evidence excerpts)")
    return all_snippets
