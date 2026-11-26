from pathlib import Path

from audit import config, evidence, snippets


def make(text: str, method: str = "crawl") -> snippets.Snippet:
    return snippets.build(
        text, "sentence", "https://docs.example.com/a", "docs", "other", "2026-11-25", method
    )


def target(root: Path, limit: int = 500) -> config.Target:
    (root / "targets").mkdir()
    (root / "targets" / "example.yaml").write_text(
        "name: example\nsources:\n  - name: docs\n    surface: docs\n"
        "    urls: [https://docs.example.com/a]\n"
        f"max_committed_excerpts: {limit}\n"
    )
    return config.load("example", root)


def test_only_cited_and_typed_rows_keep_their_excerpt() -> None:
    cited, other, mine = make("Cited sentence here."), make("Other sentence here."), make(
        "My typed string here.", "typed"
    )
    public = evidence.public_copy([cited, other, mine], {cited.id})
    assert [s.excerpt for s in public] == [cited.excerpt, "", mine.excerpt]
    # Everything else about each row stays the same.
    assert [s.id for s in public] == [cited.id, other.id, mine.id]
    assert [s.hash for s in public] == [cited.hash, other.hash, mine.hash]


def test_going_over_the_limit_is_reported(tmp_path: Path) -> None:
    t = target(tmp_path, limit=1)
    messages: list[str] = []
    rows = [make("One typed string.", "typed"), make("Two typed strings.", "typed")]
    assert evidence.write_public_copy(t, rows, log=messages.append) == 2
    assert any("over the limit of 1" in m for m in messages)


def test_viewer_falls_back_to_the_committed_copy(tmp_path: Path) -> None:
    t = target(tmp_path)
    assert evidence.load_table(t) == ([], False)
    snippets.write(t.public_snippets, [make("Committed row.")])
    rows, full = evidence.load_table(t)
    assert len(rows) == 1 and not full
    snippets.write(t.local_snippets, [make("Local row."), make("Another local row.")])
    rows, full = evidence.load_table(t)
    assert len(rows) == 2 and full
    # The evidence-only build skips the local copy even when it's there.
    rows, full = evidence.load_table(t, committed_only=True)
    assert [s.excerpt for s in rows] == ["Committed row."] and not full
