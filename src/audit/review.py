"""`audit review`: the viewer with editing switched on, served from your own computer.

A person owns three things in this project, and this is where they're edited:

- terms.csv: the `review` (accept or reject) and `definition` columns
- typed_strings.csv: app text typed in from normal use of the product
- glossary_proposals.csv: a decision and edits for each drafted glossary row. "Apply
  accepted" then writes the accepted rows into glossary.csv. That click is the only way
  this page changes glossary.csv.

Edits go straight into those files, so the files in the repo are the only storage. The
server only listens on 127.0.0.1, and it refuses any request that doesn't come from its
own page. That way nothing else on the network, and no other website open in the
browser, can change the files.
"""

from __future__ import annotations

import csv
import json
import webbrowser
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import cast

from audit import glossary, typed, view
from audit.config import Target

HOST = "127.0.0.1"
DEFAULT_PORT = 8765
# The page sends this header with every save. A page on another website can't send a
# custom header to this server without the server agreeing to it first, which it never does.
SAVE_HEADER = "X-Audit-Review"
REVIEW_VALUES = ("", "accept", "reject")
# "applied" is set by the server after a row goes into glossary.csv, never by the page.
PROPOSAL_DECISIONS = ("", "accept", "reject")
PROPOSAL_EDITABLE = ("status", "use_instead", "definition", "basis")
MAX_DEFINITION_CHARS = 400
MAX_BODY_BYTES = 100_000


class EditError(ValueError):
    """An edit that can't be saved. The message is shown to the person."""


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists():
        return [], []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


def write_rows(path: Path, columns: list[str], rows: list[dict[str, str]]) -> None:
    # Write to a temporary file first, so a crash mid-write can't leave half a file.
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".csv.tmp")
    with temporary.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def save_term_edit(target: Target, key: str, review: str, definition: str) -> dict[str, str]:
    if review not in REVIEW_VALUES:
        raise EditError("Review must be accept, reject or blank.")
    definition = " ".join(definition.split())
    if len(definition) > MAX_DEFINITION_CHARS:
        raise EditError(f"Keep the definition under {MAX_DEFINITION_CHARS} characters.")
    path = target.data_dir / "terms.csv"
    columns, rows = read_rows(path)
    for row in rows:
        if row.get("key") == key:
            row["review"] = review
            row["definition"] = definition
            write_rows(path, columns, rows)
            return row
    raise EditError("That term isn't in terms.csv any more. Reload the page.")


def clean_typed_string(entry: dict[str, str]) -> dict[str, str]:
    """The same rules as `audit typed --check`, so the page and the check can't disagree."""
    row = {c: " ".join(str(entry.get(c, "")).split()) for c in typed.COLUMNS}
    wrong = typed.problems(row)
    if wrong:
        raise EditError("; ".join(wrong).capitalize() + ".")
    return row


def same_string(a: dict[str, str], b: dict[str, str]) -> bool:
    return all(a.get(c) == b.get(c) for c in ("text", "kind", "source_url"))


def add_typed_string(target: Target, entry: dict[str, str]) -> dict[str, str]:
    row = clean_typed_string(entry)
    if target.typed_strings is None:
        raise EditError("This target has no typed_strings file set in its config.")
    _, rows = read_rows(target.typed_strings)
    if any(same_string(row, existing) for existing in rows):
        raise EditError("That string is already in the list.")
    write_rows(target.typed_strings, list(typed.COLUMNS), rows + [row])
    return row


def remove_typed_string(target: Target, entry: dict[str, str]) -> None:
    if target.typed_strings is None:
        raise EditError("This target has no typed_strings file set in its config.")
    _, rows = read_rows(target.typed_strings)
    kept = [r for r in rows if not same_string(entry, r)]
    if len(kept) == len(rows):
        raise EditError("That string isn't in the list any more. Reload the page.")
    write_rows(target.typed_strings, list(typed.COLUMNS), kept)


def proposals_path(target: Target) -> Path:
    return target.data_dir / "glossary_proposals.csv"


def save_proposal_edit(target: Target, edit: dict[str, object]) -> dict[str, object]:
    """Save a person's decision and edits for one proposal. Only these fields change."""
    decision = str(edit.get("decision", ""))
    if decision not in PROPOSAL_DECISIONS:
        raise EditError("Decision must be accept, reject or blank.")
    changed = {c: " ".join(str(edit.get(c, "")).split()) for c in PROPOSAL_EDITABLE}
    if any(len(v) > MAX_DEFINITION_CHARS for v in changed.values()):
        raise EditError(f"Keep each field under {MAX_DEFINITION_CHARS} characters.")
    path = proposals_path(target)
    columns, rows = read_rows(path)
    for row in rows:
        if row.get("term") == edit.get("term"):
            if row.get("decision") == "applied":
                raise EditError("This row is already in glossary.csv. Edit the file to change it.")
            row.update(changed)
            row["decision"] = decision
            write_rows(path, columns, rows)
            # Problems are shown, not refused: a draft can be wrong until it's accepted.
            return {"row": row, "problems": glossary.problems(row)}
    raise EditError("That proposal isn't in glossary_proposals.csv any more. Reload the page.")


def apply_proposals(target: Target) -> dict[str, object]:
    """Write accepted proposals into glossary.csv, but only if the result passes the same
    check as `audit glossary --check`. If it doesn't, neither file changes."""
    path = proposals_path(target)
    columns, rows = read_rows(path)
    accepted = [r for r in rows if r.get("decision") == "accept"]
    if not accepted:
        raise EditError("No accepted rows to apply.")
    glossary_columns, current = read_rows(target.glossary)
    glossary_columns = glossary_columns or list(glossary.COLUMNS)
    try:
        merged = glossary.merge(current, accepted)
    except ValueError as e:
        raise EditError(f"Nothing was applied. {e}.") from e
    wrong = glossary.check_rows(glossary_columns, merged)
    if wrong:
        lines = "; ".join(f"line {n}: {p}" for n, p in wrong)
        raise EditError(f"Nothing was applied. glossary.csv would fail its check: {lines}.")
    write_rows(target.glossary, glossary_columns, merged)
    for row in accepted:
        row["decision"] = "applied"
    write_rows(path, columns, rows)
    return {"applied": len(accepted), "glossary": merged}


class ReviewHandler(BaseHTTPRequestHandler):
    target: Target

    def allowed_hosts(self) -> set[str]:
        port = cast(ThreadingHTTPServer, self.server).server_port
        return {f"127.0.0.1:{port}", f"localhost:{port}"}

    def from_own_page(self) -> bool:
        # Checking the Host header blocks a website that points its own name at this
        # computer (DNS rebinding). Checking Origin blocks saves started by other pages.
        if self.headers.get("Host") not in self.allowed_hosts():
            return False
        origin = self.headers.get("Origin")
        return origin is None or origin in {f"http://{h}" for h in self.allowed_hosts()}

    def send(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status: HTTPStatus, data: object) -> None:
        self.send(status, json.dumps(data).encode("utf-8"), "application/json")

    def do_GET(self) -> None:  # noqa: N802 (name set by the standard library)
        if not self.from_own_page():
            self.send_json(HTTPStatus.FORBIDDEN, {"error": "Not allowed."})
            return
        if self.path != "/":
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Not found."})
            return
        page = view.render(self.target, editable=True)
        self.send(HTTPStatus.OK, page.encode("utf-8"), "text/html; charset=utf-8")

    def do_POST(self) -> None:  # noqa: N802 (name set by the standard library)
        if not self.from_own_page() or self.headers.get(SAVE_HEADER) != "1":
            self.send_json(HTTPStatus.FORBIDDEN, {"error": "Not allowed."})
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY_BYTES:
            self.send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "Too much text."})
            return
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict):
                raise EditError("Expected a JSON object.")
            if self.path == "/api/term":
                result: object = save_term_edit(
                    self.target,
                    str(body.get("key", "")),
                    str(body.get("review", "")),
                    str(body.get("definition", "")),
                )
            elif self.path == "/api/strings/add":
                result = add_typed_string(self.target, body)
            elif self.path == "/api/strings/remove":
                remove_typed_string(self.target, body)
                result = {"removed": True}
            elif self.path == "/api/proposal":
                result = save_proposal_edit(self.target, body)
            elif self.path == "/api/proposals/apply":
                result = apply_proposals(self.target)
            else:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "Not found."})
                return
        except (EditError, ValueError) as e:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(e)})
            return
        self.send_json(HTTPStatus.OK, result)

    def log_message(self, format: str, *args: object) -> None:
        # Keep the terminal quiet. Errors still reach the page as messages.
        pass


def make_server(target: Target, port: int = DEFAULT_PORT) -> ThreadingHTTPServer:
    handler = type("Handler", (ReviewHandler,), {"target": target})
    return ThreadingHTTPServer((HOST, port), handler)


def run(
    target: Target,
    *,
    port: int = DEFAULT_PORT,
    open_browser: bool = True,
    log: Callable[[str], None] = print,
) -> None:
    server = make_server(target, port)
    url = f"http://{HOST}:{server.server_port}/"
    log(f"Review page for {target.display_name}: {url}")
    log("Edits save to data/ on this computer. Press Ctrl+C to stop.")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("Stopped.")
    finally:
        server.server_close()
