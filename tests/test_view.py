import json
import re
from datetime import date
from pathlib import Path

from audit import config, snippets, view


def make_target(root: Path) -> config.Target:
    (root / "targets").mkdir()
    (root / "targets" / "example.yaml").write_text(
        "name: example\ndisplay_name: Example\n"
        "sources:\n  - name: docs\n    surface: docs\n    urls: [https://docs.example.com/a]\n"
    )
    target = config.load("example", root)
    hostile = snippets.build(
        "Close the tag </script><script>alert(1)</script> early",
        "sentence", "javascript:alert(1)", "docs", "other", "2026-11-25", "crawl",
    )
    normal = snippets.build(
        "Use the Search API.", "sentence", "https://docs.example.com/a", "docs", "first-use",
        "2026-11-25", "crawl",
    )
    snippets.write(target.data_dir / "snippets.csv", [hostile, normal])
    return target


def test_viewer_is_offline_and_labelled(tmp_path: Path) -> None:
    target = make_target(tmp_path)
    out = view.run(target, today=lambda: date(2026, 11, 26), log=lambda _: None)
    html = out.read_text()
    assert out == tmp_path / "viewer" / "example" / "index.html"
    assert "Outside-in, public sources, unofficial" in html
    assert "Coming in pass 2" in html
    # Nothing loads from the web.
    assert not re.search(r'<(script|link|img)[^>]+(src|href)="https?://', html)


def test_page_text_cannot_break_out_of_the_data_block(tmp_path: Path) -> None:
    html = view.run(make_target(tmp_path), log=lambda _: None).read_text()
    block = html.split('type="application/json">', 1)[1].split("</script>", 1)[0]
    data = json.loads(block)
    assert "</script><script>alert(1)" in data["snippets"][0]["excerpt"]
    assert "<script>alert" not in block


def test_summary_counts(tmp_path: Path) -> None:
    data = view.build_data(make_target(tmp_path), date(2026, 11, 26))
    assert str(data["summary"]).startswith("2 snippets from 2 public pages")
    assert data["values"] == {
        "surface": ["docs"], "kind": ["sentence"], "stage": ["first-use", "other"],
    }
