Unofficial: no affiliation with Perplexity.

# Outside-in content audit

A small tool that reads a company's public product text and shows where the words don't
agree: one thing with two names, a retired name still in use, the same message written
five ways. Perplexity is the first company it's been run on. It only uses pages anyone
can read without signing in.

To see the results, open [`docs/index.html`](docs/index.html) in a browser.

## How it works

1. **Collect.** Download the public pages and split them into strings, each with a link to
   where it came from. App text is typed in by hand from normal use.
2. **Settle the words.** The tool lists the words that are written more than one way. A
   person decides which to use, which to avoid and what each one means. That's the
   glossary.
3. **Check.** Every string is tested against the glossary and the patterns, like a spell
   checker: the same text always gives the same result. The Check tab shows each rule, how
   many strings break it and where, with the words that break it marked.
4. **Find repeated messages.** The tool groups sentences that say the same thing in
   different words. A person picks the real ones and writes one string to reuse, so a
   change made once reaches every page. The check then reports the pages that still say it
   another way.

The tool suggests and a person decides, at every step.

Working on this with an AI tool, or contributing? Start with [AGENTS.md](AGENTS.md).

## Limits

- Outside-in. Everything here comes from public, first-party pages, so the reasons behind
  a choice aren't known. Where only the team can answer, the audit asks.
- A snapshot. Pages change. Each string records the date it was captured.
- Paid-only features are covered only through their public help pages and launch posts.
- App text is typed in by hand from normal use, or transcribed from screenshots of normal
  use. Nothing automates the app, and screenshots aren't committed.

## Status

All four steps work. Scoring tone across the product is planned for later. See
[ROADMAP.md](ROADMAP.md).

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
uv run audit check --target perplexity
uv run audit view --target perplexity    # then open viewer/perplexity/index.html
```

`uv run audit --help` lists the steps in order.

`fetch` reads robots.txt and obeys it, waits at least a second between requests, and
saves full pages to `cache/`, which is never committed. `extract` builds the strings
table from those pages. `terms` writes `data/<target>/terms.csv` for review and
`term_candidates.csv`, which lists every candidate with its decision and the reason, so
nothing is dropped silently.

On a fresh clone, run `fetch` and `extract` before `terms`. The viewer also works from
the committed data alone. Its Overview page explains the method and leads with the cards
in `data/<target>/headlines.csv`, which a person writes. The first four rows are shown
first.

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

`check` reports where words to avoid and deprecated names still appear, one finding per
surface, and other spellings of the terms to use, with labels and running text compared
separately. It also reports, for each pattern in `data/<target>/patterns.csv`, the
strings that say its message without its shared wording. Each finding has a category
(capitalisation, spelling or spacing, deprecated name, avoided term, other variant, or
same message, different words), the term or pattern, what was written, what's wrong, the
fix and, where only the team can answer, a question. It lists every string it counts.

### Patterns

A pattern is a message said in more than one place that should read the same each time,
such as an instruction or a plan description.

```bash
uv run audit patterns --target perplexity           # writes cache/<target>/pattern_candidates.csv
uv run audit patterns --check --target perplexity   # checks the two pattern files by line
```

The candidate list quotes whole sentences, so it stays in `cache/`. A person decides
which candidates are real: drafts go in `data/<target>/pattern_proposals.csv`, and
accepted ones in `data/<target>/patterns.csv`.

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

## The strings table

Each row is one string: a piece of text collected from a page or typed in from the app.
The file and code still call a row a snippet (`snippets.csv`), because later steps
depend on those names.

| Column | What it holds |
| --- | --- |
| id | Short ID. Stays the same when the same text is re-crawled. |
| excerpt | The text, cut to 20 words at most. |
| kind | title, heading, nav, button, label, parameter, error or sentence |
| source_url | Where the text was found |
| surface | docs, help, pricing, blog, brand, changelog, web-app, ios-app, comet or email |
| stage | sign-up, first-use, answering, error, upgrade, settings or other |
| captured_on | Date fetched or typed |
| method | crawl or typed |
| hash | Fingerprint of the full text |

The repo commits evidence, not a copy of the company's pages. `extract` writes the full
table, with every excerpt, to `cache/<target>/snippets.csv` on your computer. The
committed `data/<target>/snippets.csv` keeps every row, but only fills in the excerpt for
evidence: strings the term map cites as examples, the first few strings of each
finding from `audit check` (`evidence_per_finding` in the config), and every typed string.

## Licence

MIT
