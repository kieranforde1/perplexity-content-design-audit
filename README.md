Unofficial: no affiliation with Perplexity.

# Outside-in product language audit

A small tool that audits a company's published product language from the outside, using
public sources only. Perplexity is the first target. Any company can be audited by adding
a config file in `targets/`.

The tool proposes and a person decides: terms are reviewed by hand, and app text is
typed in by hand from normal use.

Working on this with an AI tool, or contributing? Start with [AGENTS.md](AGENTS.md).

## How it works

1. **Collect** a company's public text into one table of snippets, each with its source link.
2. **Find the terms** and show where the wording varies.
3. **Group repeated content structures** into patterns. *(second pass)*
4. **Score tone across stages**, and report how far the scores can be trusted. *(second pass)*

Every step reads the snippets table and writes its own table. Adding a step later means
adding a file, not rebuilding.

## Limits

- Outside-in. Everything here comes from public, first-party pages. It says nothing about
  how or why the company made its decisions. Findings are observations and questions.
- A snapshot. Pages change. Each snippet records the date it was captured.
- Paid-only features are covered only through their public help pages and launch posts.
- App text is typed in by hand from normal use. Nothing automates the app.

## Status

The term map, the offline viewer, the glossary and the first check (against the
glossary) work. Terms have been reviewed once.
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

`fetch` reads robots.txt and obeys it, waits at least a second between requests, and
saves full pages to `cache/`, which is never committed. `extract` builds the snippets
table from those pages. `terms` writes `data/<target>/terms.csv` for review and
`term_candidates.csv`, which lists every candidate with its decision and the reason, so
nothing is dropped silently.

On a fresh clone, run `fetch` and `extract` before `terms`. The viewer also works from
the committed data alone.

### Review terms and add app strings

```bash
uv run audit review --target perplexity    # opens http://127.0.0.1:8765
```

This opens the viewer with editing switched on:

- **Terms tab:** accept or reject each term and write its definition.
- **App strings tab:** add text typed in from normal use of the app.

Edits save straight into `data/<target>/terms.csv` and `typed_strings.csv` on your
computer. The page only answers requests from your own machine. Nothing is hosted and
nothing is stored anywhere else.

### The glossary and the check

`data/<target>/glossary.csv` holds the terms a person has settled on: each one's status
(use, avoid or deprecated), what to use instead, a definition, and its basis (published by
the company, observed in its text, or the reviewer's recommendation). Only a person edits
it.

```bash
uv run audit glossary --check --target perplexity   # reports problems by line
uv run audit check --target perplexity              # writes data/<target>/findings.csv
```

`check` reports where words to avoid and retired names still appear, one finding per
surface, and other spellings of the terms to use, with labels and running text compared
separately. Each finding starts "Observed:", names its glossary row and lists every
snippet it counts.

### Typed app strings

A typed string is a short piece of text you saw while using the product normally, such
as a button label, an error or an empty state, copied in by hand. Screenshots don't
count, and nothing is collected automatically. Each one is 20 words at most and says
where you saw it: a web address, or a short description like "web app, sign-up screen".

```bash
uv run audit typed --template                  # the CSV header and two example rows
uv run audit typed --check --target perplexity # reports problems by line
```

After adding strings, run `extract` and `terms` again to include them.

## The snippets table

| Column | What it holds |
| --- | --- |
| id | Short ID. Stays the same when the same text is re-crawled. |
| excerpt | The text, cut to 20 words at most. |
| kind | title, heading, nav, button, label, parameter, error or sentence |
| source_url | Where the text was found |
| surface | docs, help, pricing, blog, brand, changelog, web-app, ios-app or comet |
| stage | sign-up, first-use, answering, error, upgrade, settings or other |
| captured_on | Date fetched or typed |
| method | crawl or typed |
| hash | Fingerprint of the full text |

The repo commits evidence, not a copy of the company's pages. `extract` writes the full
table, with every excerpt, to `cache/<target>/snippets.csv` on your computer. The
committed `data/<target>/snippets.csv` keeps every row, but only fills in the excerpt for
evidence: snippets the term map cites as examples, the first few snippets of each
finding from `audit check` (`evidence_per_finding` in the config), and every typed string.

## Licence

MIT
