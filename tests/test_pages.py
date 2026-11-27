"""The GitHub Pages copy in docs/ must match a fresh evidence-only build.

docs/index.html is a copy of `audit view --evidence-only`, committed so Pages can serve
it from main. A copy can go stale, so this rebuilds the page from committed data and
compares. If it fails, run:

    uv run audit view --target perplexity --evidence-only
    cp viewer/perplexity/evidence.html docs/index.html
"""

import re
from datetime import date
from pathlib import Path

from audit import config, view

REPO_ROOT = Path(__file__).resolve().parent.parent
PAGE = REPO_ROOT / "docs" / "index.html"


def test_pages_copy_matches_a_fresh_evidence_build() -> None:
    published = PAGE.read_text(encoding="utf-8")
    # The build date is part of the page, so rebuild with the date the copy was made.
    found = re.search(r'"today": "(\d{4}-\d{2}-\d{2})"', published)
    assert found, "docs/index.html has no build date"
    target = config.load("perplexity", REPO_ROOT)
    fresh = view.render(target, evidence_only=True, today=date.fromisoformat(found[1]))
    assert published == fresh, "docs/index.html is stale: see this file's docstring"


def test_pages_copy_asks_crawlers_to_stay_out() -> None:
    assert 'name="robots" content="noindex, nofollow, noarchive, noai, noimageai"' in (
        PAGE.read_text(encoding="utf-8")
    )
