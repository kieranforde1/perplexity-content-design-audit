Unofficial: no affiliation with Perplexity.

# Outside-in product language audit

A small tool that reads a company's published product language from the outside, using
public sources only. Perplexity is the first target. Any company can be audited by adding
a config file in `targets/`.

## How it works

1. **Collect** a company's public text into one table of snippets, each with its source link.
2. **Find the terms** and show where the wording varies.
3. **Check** the text against a register of standards, each with its source and authority.
4. **Recommend** changes, each linked to its evidence: fix the strings, the pattern or the system.
5. **Group repeated structures and score tone**, and report how far the scores can be trusted. *(second pass)*

Every step reads the snippets table and writes its own table. Adding a step later means
adding a file, not rebuilding.

## Limits

- Outside-in. Everything here comes from public, first-party pages. It says nothing about
  how or why the company made its decisions. Findings are observations. Recommendations
  are suggestions backed by that evidence, each with a question for the team.
- Standards say where their authority comes from. None is presented as a company rule
  unless the company published it.
- A snapshot. Pages change. Each snippet records the date it was captured.
- Paid-only features are covered only through their public help pages and launch posts.
- App text is typed in by hand from normal use. Nothing automates the app.

## Status

Phase 2 of 4: the term map and the offline viewer work, with 60 terms proposed for review.
Next: standards, checks and recommendations.
See [ROADMAP.md](ROADMAP.md).

## Run it

Needs [uv](https://docs.astral.sh/uv/) and Python 3.12. uv reads `.python-version` and
uses 3.12 for you. Python 3.13 and later can reject valid cross-signed certificate
chains, which makes fetch fail on some sites. If fetch still reports a certificate error,
your Python's list of trusted certificates may be out of date. Point `SSL_CERT_FILE` at a
current one, such as the one Homebrew's OpenSSL installs.

```bash
export AUDIT_CONTACT=you@example.com   # sent in the user agent so site owners can reach you
uv run audit fetch --target perplexity --dry-run
uv run audit fetch --target perplexity
uv run audit extract --target perplexity
uv run audit terms --target perplexity
uv run audit view --target perplexity    # then open viewer/perplexity/index.html
```

`terms` writes `data/<target>/terms.csv` for review and `term_candidates.csv`, which
lists every candidate with its decision and the reason. That includes rejected ones,
so nothing is dropped silently. Fill in the `review` (accept or reject) and
`definition` columns in `terms.csv`. They're kept every time `terms` runs again.

`fetch` reads robots.txt and obeys it, waits at least a second between requests, and
saves full pages to `cache/`, which is never committed. `extract` writes
`data/<target>/snippets.csv`, which holds only short excerpts and links back to each source.

## The snippets table

| Column | What it holds |
| --- | --- |
| id | Short ID. Stays the same when the same text is re-crawled. |
| excerpt | The text, cut to 20 words at most. |
| kind | title, heading, nav, button, parameter, error or sentence |
| source_url | Where the text was found |
| surface | docs, help, pricing, blog, changelog, web-app, ios-app or comet |
| stage | sign-up, first-use, answering, error, upgrade, settings or other |
| captured_on | Date fetched or typed |
| method | crawl or typed |
| hash | Fingerprint of the full text |

## Licence

MIT
