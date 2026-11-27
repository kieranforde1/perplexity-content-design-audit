import csv
import io
import json
from pathlib import Path

import pytest

from audit import config, extract, snippets, terms, typed, view
from audit.cli import main

GOOD = {
    "text": "Ask anything", "kind": "button", "source_url": "https://app.example.com/",
    "surface": "web-app", "stage": "first-use", "captured_on": "2026-11-26",
}


def test_template_has_the_header_and_marked_examples(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["typed", "--template"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == ",".join(typed.COLUMNS)
    examples = [line for line in out if line.startswith("EXAMPLE") or "EXAMPLE" in line[:12]]
    assert len(examples) == 2


def test_a_good_row_has_no_problems() -> None:
    assert typed.problems(GOOD) == []


def test_a_description_can_stand_in_for_a_web_address() -> None:
    assert typed.problems(GOOD | {"source_url": "web app, sign-up screen"}) == []


def test_text_from_an_email_is_accepted_and_ranked_with_app_text() -> None:
    assert typed.problems(GOOD | {"surface": "email", "source_url": "email, task complete"}) == []
    assert "email" in snippets.SURFACES
    assert terms.AUTHORITY.index("email") > terms.AUTHORITY.index("web-app")


@pytest.mark.parametrize(
    "change, expected",
    [
        ({"text": " ".join(["word"] * 21)}, "21 words"),
        ({"source_url": ""}, "short description"),
        ({"source_url": "http://app.example.com/"}, "https://"),
        ({"captured_on": ""}, "captured_on is missing"),
        ({"surface": "docs"}, "surface 'docs'"),
        ({"stage": "checkout"}, "stage 'checkout'"),
        ({"kind": "parameter"}, "kind 'parameter'"),
    ],
)
def test_problems_are_named_in_plain_words(change: dict[str, str], expected: str) -> None:
    assert any(expected in p for p in typed.problems(GOOD | change))


def write_target(root: Path, rows: list[dict[str, str]]) -> config.Target:
    (root / "targets").mkdir()
    (root / "targets" / "example.yaml").write_text(
        "name: example\ndisplay_name: Example\n"
        "sources:\n  - name: docs\n    surface: docs\n    urls: [https://docs.example.com/a.md]\n"
        "terms:\n  seeds: [Ask Mode]\n"
        "typed_strings: data/example/typed_strings.csv\n"
    )
    target = config.load("example", root)
    assert target.typed_strings is not None
    target.typed_strings.parent.mkdir(parents=True)
    with target.typed_strings.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=typed.COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return target


def test_check_reports_problems_by_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_target(tmp_path, [GOOD, GOOD | {"surface": "docs", "captured_on": ""}])
    assert main(["typed", "--check", "--target", "example", "--root", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "line 3: surface 'docs'" in out
    assert "line 3: captured_on is missing" in out
    assert "line 2" not in out


def test_check_passes_a_clean_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_target(tmp_path, [GOOD])
    assert main(["typed", "--check", "--target", "example", "--root", str(tmp_path)]) == 0
    assert "0 problems" in capsys.readouterr().out


def test_typed_rows_flow_through_extract_terms_and_view(tmp_path: Path) -> None:
    # Two made-up rows, used only in this test. No crawled pages at all.
    rows = [
        GOOD | {"text": "Try Ask Mode for quick answers", "kind": "sentence"},
        GOOD | {"text": "Turn on Ask Mode", "source_url": "iOS app, settings screen",
                "surface": "ios-app", "stage": "settings"},
    ]
    target = write_target(tmp_path, rows)
    target.cache_dir.mkdir(parents=True)

    extract.run(target, log=lambda _: None)
    local = snippets.read(target.local_snippets)
    assert {s.method for s in local} == {"typed"}
    assert len(local) == 2

    found = {r["term"]: r for r in terms.run(target, log=lambda _: None)}
    assert "Ask Mode" in found
    assert found["Ask Mode"]["surfaces"] == "web-app ios-app"

    html = view.render(target)
    data = json.loads(html.split('type="application/json">', 1)[1].split("</script>", 1)[0])
    assert {s["method"] for s in data["snippets"]} == {"typed"}

    # Typed strings are always evidence, so their text is committed.
    public = snippets.read(target.public_snippets)
    assert all(s.excerpt for s in public)


def test_template_rows_are_valid_once_the_marker_is_removed() -> None:
    reader = csv.DictReader(io.StringIO("\n".join(
        line for line in typed.template().splitlines() if line and not line.startswith("#")
    )))
    for row in reader:
        row["text"] = row["text"].removeprefix("EXAMPLE ")
        assert typed.problems(row) == []
