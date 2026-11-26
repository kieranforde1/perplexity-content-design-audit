# Guide for AI tools and new contributors

Read this before changing anything. It covers what the project is for, the rules it
follows, where things live and how to work on it. [README.md](README.md) explains how to
run it, and [ROADMAP.md](ROADMAP.md) explains what's next.

## What this project is for

An outside-in audit of a company's published product language, built as a working tool
rather than a one-off report. Perplexity is the first target. The tool is meant to show
a systematic way of solving content problems:

1. Collect public text into one table, with a source link for every piece.
2. Find the terms and show where the wording varies.
3. Group repeated content structures into patterns (second pass).
4. Score tone across stages, and report how far the scores can be trusted (second pass).

A person settles the terms in a glossary, and `audit check` tests the public text against
it. The other checks, recommendations and a content-standards skill are paused. Their
designs are under "Later" in [ROADMAP.md](ROADMAP.md). Don't build them unless the owner
asks.

The code has to stay simple enough for a content designer to explain every part:
plain names, small files, and comments that say why. If a choice is between simple and
clever, choose simple.

## Rules you must follow

These aren't preferences. Breaking one can cause real harm to the owner or the company
being audited.

**Sources**
- Use first-party, public sources only: pages the company publishes itself, readable
  without signing in.
- Never use third-party coverage, brand analyses made by outsiders, community
  "design system" reconstructions, or leaked or compiled prompts.
- Never use anything behind a sign-in or an organisation-only page, even if an account
  could open it.
- Never automate the company's apps. App text is typed in by hand, or transcribed from
  the owner's own screenshots (see below). Screenshots are never committed.
- Fetch politely. `audit fetch` obeys robots.txt, waits at least a second between
  requests and names a contact in its user agent. Don't work around any of that, and
  don't crawl from CI.

**What gets committed**
- Committed data holds excerpts of 20 words at most. Full page text stays in `cache/`,
  which is gitignored and can be rebuilt with `audit fetch`.
- Never commit `cache/`, `private/`, `viewer/`, `reports/`, `.env` or `uv.lock`. Tests
  check that `private/` stays untracked and that committed excerpts stay short.
- No code reads `private/`. It's for the owner's own notes.
- Never name individual people who work at the company being audited, anywhere in the
  repo: code, data, docs or commit messages.
- No logos, brand fonts or screenshots.
- Don't publish anything (GitHub Pages, hosting, `reports/`) unless the owner asks.

**How findings are worded**
- Findings are observations from public text ("Observed: ..."). They never claim to
  know how or why the company made its decisions.
- Recommendations are suggestions backed by evidence. Each one carries a question for
  the team, because outside-in work can't know the reasons behind a choice.
- A standard is only called a company rule if the company published it.

**Ask the owner before you**
- change the columns of `data/<target>/snippets.csv` (later steps and hand labels
  depend on them)
- add a source, a surface or a stage
- add a dependency
- delete or overwrite anything a person has filled in (`review`, `definition`,
  `typed_strings.csv`, `glossary.csv`)
- run `audit terms` while the review page may be in use: it rewrites `terms.csv` and can
  overwrite edits saved during the run

## Where things live

| Path | What it is |
| --- | --- |
| `targets/<name>.yaml` | Everything company-specific: sources, stage rules, boilerplate, term settings |
| `src/audit/cli.py` | The `audit` command and its subcommands |
| `src/audit/fetch.py` | Polite crawler. Writes `cache/<target>/` |
| `src/audit/extract.py` | Turns cached pages into the snippets table |
| `src/audit/snippets.py` | The snippets table: columns, IDs, allowed values |
| `src/audit/terms.py` | The term map: candidates, clusters, decisions, questions |
| `src/audit/view.py`, `viewer.html` | The offline viewer |
| `src/audit/review.py` | The local review page, which saves a person's edits |
| `src/audit/typed.py` | Rules for typed app strings, used by `audit typed`, extract and review |
| `src/audit/glossary.py` | Rules for the glossary, used by `audit glossary --check` and by applying proposals |
| `src/audit/check.py` | `audit check`: tests the public text against the glossary |
| `src/audit/evidence.py` | Decides which excerpts are committed |
| `data/<target>/` | Committed outputs: the public snippets table, terms, term candidates, typed app strings |
| `later/` | Paused designs, such as the content-skill template |
| `tests/` | One test file per step, plus checks on the committed data |

### Data contracts

`snippets.csv` columns (locked): id, excerpt, kind, source_url, surface, stage,
captured_on, method, hash. Allowed values are in `src/audit/snippets.py`. There are two
copies of the table:

- `cache/<target>/snippets.csv` (local, gitignored): every row with its excerpt. `terms`
  and `view` read this when it exists.
- `data/<target>/snippets.csv` (committed): every row, but the excerpt is only filled in
  for evidence, meaning snippets cited in `terms.csv`, the first `evidence_per_finding`
  snippets of each row in `findings.csv`, and typed strings. The config's
  `max_committed_excerpts` caps how many, and a test enforces it. The repo commits
  evidence, not a copy of the company's pages.

`cache/<target>/full_text.csv` holds each snippet's full text by ID, for counting.

`terms.csv` is written by `audit terms`, but a person owns three columns: `term`,
`review` (accept, reject or blank) and `definition`. They're matched on the `key`
column and kept on every re-run. Never write to them from code, except through the
review page.

`glossary.csv` is written by a person, either directly or through "Apply accepted" on
the review page, and never by other code: term, status (use, avoid or deprecated),
use_instead, definition, basis and source_url. `basis` says how sure we can be:
`published` (Perplexity said it, and source_url points to where), `observed` (its public
text uses the term this way) or `recommendation` (the reviewer's suggestion, never
presented as Perplexity's rule). `audit glossary --check` checks the file.

`glossary_proposals.csv` holds drafted glossary rows for a person to review: section,
the glossary columns, change (`update` an existing term or `add` a new one), evidence_id,
note and decision (blank, accept, reject, or `applied` once "Apply accepted" has written
it into `glossary.csv`, after the same check as `audit glossary --check`).

`typed_strings.csv` holds app text from normal use of the product, typed in by hand or
transcribed from the owner's screenshots and checked by the owner: text, kind, source_url,
surface, stage, captured_on. 20 words at most per string. `source_url` is a web address,
or a short description such as "web app, sign-up screen". `audit typed --check` checks
the file. Never add strings that didn't come from a person's own use of the product, and
leave out anything personal: usernames, account details and the person's own chats.

## How people take part

The tool proposes and a person decides. Two steps need a person:

- **Reviewing terms:** accepting or rejecting each proposed term and writing definitions
  in their own words.
- **Adding app strings** from normal use of the product.

Both are done in the local review page:

```bash
uv run audit review --target perplexity
```

## How to work on it

```bash
uv sync                     # Python 3.12 is pinned in .python-version
uv run pytest -q            # tests
uv run ruff check .         # lint
uv run mypy                 # types
```

Run all three before committing. CI runs them on every pull request.

- **Work on a branch** and open a pull request into `main`.
- **Commit messages say why** the change was made. The diff already shows what changed.
- **Check `git config user.email` before committing.** Commits must use the owner's
  personal identity for this repo.
- **Fetch needs `AUDIT_CONTACT` set.** Most work doesn't need fetch at all: `extract`,
  `terms`, `view` and `review` all run from the cache and the committed data.
- **New behaviour gets a test.** Fixtures in `tests/fixtures/` are invented examples, not
  copies of the company's pages.
