import csv
import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

from audit import config, review, snippets, terms

TERM_ROW = {c: "" for c in terms.TERM_COLUMNS} | {
    "term": "Search API", "key": "searchapi", "status": "question",
}


@pytest.fixture
def server(tmp_path: Path) -> Iterator[tuple[str, config.Target]]:
    (tmp_path / "targets").mkdir()
    (tmp_path / "targets" / "example.yaml").write_text(
        "name: example\ndisplay_name: Example\n"
        "sources:\n  - name: docs\n    surface: docs\n    urls: [https://docs.example.com/a]\n"
        "typed_strings: data/example/typed_strings.csv\n"
    )
    target = config.load("example", tmp_path)
    s = snippets.build("Use the Search API.", "sentence", "https://docs.example.com/a",
                       "docs", "other", "2026-11-25", "crawl")
    snippets.write(target.data_dir / "snippets.csv", [s])
    with (target.data_dir / "terms.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=terms.TERM_COLUMNS)
        writer.writeheader()
        writer.writerow(TERM_ROW)

    httpd = review.make_server(target, port=0)
    thread = threading.Thread(target=httpd.serve_forever, args=(0.05,), daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}", target
    httpd.shutdown()
    httpd.server_close()


def call(
    base: str, path: str, body: object | None = None, headers: dict[str, str] | None = None
) -> tuple[int, dict[str, object] | str]:
    sent = {"X-Audit-Review": "1", "Origin": base, "Content-Type": "application/json"}
    if headers is not None:
        sent = headers
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(base + path, data=data, headers=sent)
    try:
        with urllib.request.urlopen(request) as r:
            raw = r.read().decode()
            status = r.status
    except urllib.error.HTTPError as e:
        raw, status = e.read().decode(), e.code
    try:
        return status, json.loads(raw)
    except json.JSONDecodeError:
        return status, raw


def term_row(target: config.Target) -> dict[str, str]:
    with (target.data_dir / "terms.csv").open() as f:
        return next(csv.DictReader(f))


def typed(target: config.Target) -> list[dict[str, str]]:
    assert target.typed_strings is not None
    if not target.typed_strings.exists():
        return []
    with target.typed_strings.open() as f:
        return list(csv.DictReader(f))


STRING = {
    "text": "Ask anything", "kind": "button", "surface": "web-app", "stage": "first-use",
    "captured_on": "2026-11-26", "source_url": "https://app.example.com/",
}


def test_page_is_the_viewer_in_review_mode(server: tuple[str, config.Target]) -> None:
    base, _ = server
    status, page = call(base, "/", headers={})
    assert status == 200
    assert isinstance(page, str)
    assert '"editable": true' in page
    assert "App strings" in page


def test_saving_a_review_writes_terms_csv(server: tuple[str, config.Target]) -> None:
    base, target = server
    body = {"key": "searchapi", "review": "accept", "definition": "Returns  web results."}
    status, result = call(base, "/api/term", body)
    assert status == 200
    row = term_row(target)
    assert row["review"] == "accept"
    assert row["definition"] == "Returns web results."
    assert row["status"] == "question"


def test_bad_review_values_are_refused(server: tuple[str, config.Target]) -> None:
    base, target = server
    status, result = call(base, "/api/term", {"key": "searchapi", "review": "maybe"})
    assert status == 400
    assert term_row(target)["review"] == ""
    status, _ = call(base, "/api/term", {"key": "nothere", "review": "accept"})
    assert status == 400


def test_saves_without_the_page_header_are_refused(server: tuple[str, config.Target]) -> None:
    base, target = server
    body = {"key": "searchapi", "review": "accept"}
    status, _ = call(base, "/api/term", body, headers={"Content-Type": "application/json"})
    assert status == 403
    other_site = {"X-Audit-Review": "1", "Origin": "https://evil.example"}
    status, _ = call(base, "/api/term", body, headers=other_site)
    assert status == 403
    assert term_row(target)["review"] == ""


def test_requests_for_another_host_name_are_refused(server: tuple[str, config.Target]) -> None:
    base, _ = server
    status, _ = call(base, "/", headers={"Host": "rebind.example:80"})
    assert status == 403


def test_the_glossary_cannot_be_edited_from_the_page(server: tuple[str, config.Target]) -> None:
    base, target = server
    target.glossary.write_text("term,status,use_instead,definition,basis,source_url\n")
    before = target.glossary.read_text()
    body = {"term": "Search API", "status": "avoid", "basis": "published"}
    status, _ = call(base, "/api/glossary", body)
    assert status == 404
    assert target.glossary.read_text() == before


def test_adding_and_removing_app_strings(server: tuple[str, config.Target]) -> None:
    base, target = server
    status, _ = call(base, "/api/strings/add", STRING)
    assert status == 200
    assert typed(target) == [STRING]
    status, result = call(base, "/api/strings/add", STRING)
    assert status == 400 and "already" in str(result)
    status, _ = call(base, "/api/strings/remove", STRING)
    assert status == 200
    assert typed(target) == []


@pytest.mark.parametrize(
    "change, message",
    [
        ({"text": " ".join(["word"] * 21)}, "keep it to 20"),
        ({"source_url": "javascript:alert(1)"}, "https://"),
        ({"surface": "billboard"}, "surface"),
        ({"captured_on": "yesterday"}, "date"),
        ({"text": "   "}, "text is empty"),
    ],
)
def test_bad_app_strings_are_refused(
    server: tuple[str, config.Target], change: dict[str, str], message: str
) -> None:
    base, target = server
    status, result = call(base, "/api/strings/add", STRING | change)
    assert status == 400
    assert message in str(result).lower()
    assert typed(target) == []


def test_a_description_is_accepted_where_there_is_no_web_address(
    server: tuple[str, config.Target],
) -> None:
    base, target = server
    status, _ = call(base, "/api/strings/add", STRING | {"source_url": "iOS app, settings screen"})
    assert status == 200
    assert typed(target)[0]["source_url"] == "iOS app, settings screen"
