from pathlib import Path

import pytest

from audit import snippets


def make(text: str = "Click Save to keep your changes.") -> snippets.Snippet:
    return snippets.build(
        text=text,
        kind="sentence",
        source_url="https://docs.example.com/a",
        surface="docs",
        stage="other",
        captured_on="2026-11-25",
        method="crawl",
    )


def test_id_is_stable_and_depends_on_text() -> None:
    assert make().id == make().id
    assert make().id != make("Something else entirely.").id


def test_whitespace_does_not_change_id() -> None:
    assert make("Click  Save to keep\nyour changes.").id == make().id


def test_excerpt_is_capped() -> None:
    long_text = " ".join(f"word{i}" for i in range(40))
    s = make(long_text)
    assert s.excerpt.split()[: snippets.EXCERPT_MAX_WORDS] == long_text.split()[:20]
    assert s.excerpt.endswith("…")
    assert s.hash == snippets.make_hash(long_text)


def test_unknown_values_are_rejected() -> None:
    with pytest.raises(ValueError, match="surface"):
        snippets.build("Hello there friend", "sentence", "u", "twitter", "other", "d", "crawl")


def test_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "snippets.csv"
    snippets.write(path, [make()])
    assert snippets.read(path) == [make()]
