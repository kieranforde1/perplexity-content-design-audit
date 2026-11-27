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
3. Check the public text against the settled terms, the same way every time.
4. Group messages said in more than one place into patterns, each with one string to
   reuse.

All four steps are built. A person settles the terms in a glossary and picks the real
patterns, and `audit check` tests the public text against both. `audit skill` turns the
glossary and the patterns into the pplx-content skill that a writer, or an AI writing
tool, uses on new text. Recommendations, tone and style are paused. Their designs are
under "Later" in [ROADMAP.md](ROADMAP.md). Don't build them unless the owner asks.

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
- The viewer uses Perplexity's published brand colours from the Brand Hub. No logos, no
  brand font files, no screenshots.
- Don't publish anything (GitHub Pages, hosting, `reports/`) unless the owner asks.

**How findings are worded**
- Write findings the way an in-house content designer would write to their team: what's
  wrong, the fix, and a short question only where only the team can answer it.
- State facts as facts. Never present a guess about the reasons behind a choice as a
  fact.
- Recommendations are suggestions backed by evidence. Each one carries a question for
  the team, because outside-in work can't know the reasons behind a choice.
- A standard is only called a company rule if the company published it.

**Ask the owner before you**
- change the columns of `data/<target>/snippets.csv` (later steps and hand labels
  depend on them)
- add a source, a surface or a stage
- add a dependency
- delete or overwrite anything a person has filled in (`review`, `definition`,
  `typed_strings.csv`, `glossary.csv`, `patterns.csv`, a proposal's `decision`)
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
| `src/audit/patterns.py` | `audit patterns`: groups look-alike sentences. Writes `cache/<target>/pattern_candidates.csv` |
| `src/audit/pattern_table.py` | Rules for `patterns.csv` and `pattern_proposals.csv`, used by `audit patterns --check` |
| `src/audit/view.py`, `viewer.html` | The offline viewer |
| `src/audit/review.py` | The local review page, which saves a person's edits |
| `src/audit/typed.py` | Rules for typed app strings, used by `audit typed`, extract and review |
| `src/audit/glossary.py` | Rules for the glossary, used by `audit glossary --check` and by applying proposals |
| `src/audit/check.py` | `audit check`: tests the public text against the glossary and the patterns table |
| `src/audit/evidence.py` | Decides which excerpts are committed |
| `src/audit/skill.py`, `skill_template.md`, `skill_check_text.py` | `audit skill`: builds the pplx-content skill from the template and the check script |
| `data/<target>/` | Committed outputs: the public strings table, terms, term candidates, typed app strings, patterns, front-page headlines |
| `pplx-content/` | The generated skill, named by the config's `skill.name`. Committed, never edited by hand |
| `tests/` | One test file per step, plus checks on the committed data |

### Data contracts

Readers see each row of the snippets table as a "string": the viewer, docs and finding
text say "string". The file, its columns and the code keep the name "snippet".

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

`patterns.csv` holds the patterns a person has accepted, and is never written by code:
pattern_id, message (one sentence), shared_wording, basis (as in the glossary), variants
and pages (counts from the string IDs), surfaces (space-separated), question and
string_ids (space-separated IDs from `data/<target>/snippets.csv`). There's no status
column: every row is a real pattern, and every row asks the team a question. Shared
wording uses the glossary's `use` terms, and it's a recommendation unless the company
published it.

`pattern_proposals.csv` holds drafted patterns for a person to decide: the same columns,
plus note (how the draft was made, and where it was changed to match the glossary) and
decision (blank, accept or reject). For now a person copies accepted rows into
`patterns.csv`; a review tab will do it later. `audit patterns --check` checks both files,
including that quoted text is 20 words at most.

`typed_strings.csv` holds app text from normal use of the product, typed in by hand or
transcribed from the owner's screenshots and checked by the owner: text, kind, source_url,
surface, stage, captured_on. 20 words at most per string. `source_url` is a web address,
or a short description such as "web app, sign-up screen". `audit typed --check` checks
the file. Never add strings that didn't come from a person's own use of the product, and
leave out anything personal: usernames, account details and the person's own chats.

`headlines.csv` holds the viewer's front-page cards, written by a person: title, line (24
words at most), tab (findings, glossary or terms) and term. A card opens that tab searched
for the term, so the term must be in the glossary. Anything quoted in a line is 20 words
at most. A test checks both.

`pplx-content/` (the folder named by the config's `skill.name`) is written by `audit skill` and by nothing
else: `SKILL.md`, `references/glossary.csv` (the glossary's columns, copied),
`references/patterns.csv` (pattern_id, message, shared_wording, how_to_use, question,
where how_to_use is the first sentence of the proposal's "How to use it:" note) and
`scripts/check_text.py` (standard library only). It has no build date, so a test can
compare the committed copy with a fresh build. To change it, change the glossary, the
patterns or the template, then run `audit skill` again.

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
