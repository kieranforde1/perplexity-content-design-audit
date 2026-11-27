# Roadmap

Every step reads the strings table (`snippets.csv`) and writes its own table. Adding a
step means adding a file, not rebuilding.

The goal is to show that the tool spots terminology and pattern problems the same way
every time, suggests where content can be consolidated, and raises the right questions
for the team. It doesn't need to be perfect or ready for production.

## Built

| Step | Commands | What a person does |
| --- | --- | --- |
| 1. Collect | `fetch`, `extract`, `typed` | Types in app text from normal use |
| 2. Settle the words | `terms`, `review`, `glossary --check` | Accepts or rejects terms, writes the glossary |
| 3. Check | `check` | Nothing: the same text always gives the same result |
| 4. Find repeated messages | `patterns`, `patterns --check` | Picks the real patterns and writes one string for each |
| See the results | `view` | Writes the front-page cards in `headlines.csv` |
| Use it on new text | `skill` | Nothing: the skill is generated from the glossary and patterns |

The viewer is published from `docs/` on GitHub Pages, with a robots tag that keeps it out
of search. Its Check tab lists one rule per row, with the strings that break it. The
analysis is the front-page cards and the Patterns tab.

## Later

- **Tone and style** (`audit tone`, `audit style`). Tone is the hardest step and isn't
  needed to show the method.
- **More checks** from a standards register: heading case by surface, error messages
  that say what happened and what to do, button labels, reading level by stage.
- **Recommendations** (`audit recommend`): changes at the level of a string, a pattern or
  the system, each with reach, effort, confidence and a question for the team.
- **A review tab for pattern proposals.** The first 10 were decided in chat.
- **An example target**, so someone new can run the tool on invented data.

## Design notes

### How pattern candidates are found

A pattern is a message said in more than one place that should read the same each time.
A glossary term fixes one word. A pattern fixes one sentence.

1. Clean up each sentence: lower-case it, remove punctuation, skip parameters and anything
   under four words.
2. Two sentences are look-alikes when they share a three-word phrase and at least 75% of
   their words (`patterns.min_overlap` in the target config). Look-alikes chain into one
   group. Only groups on two or more pages count.
3. Name why each group exists: link text, template (one short slot changes, such as a
   connector name) or message (a pattern candidate).
4. Rank by pages times variants, and flag groups whose variants disagree on a number, a
   time period or a plan name. Groups whose only difference is a glossary word to avoid
   are dropped, because the check already reports them.
5. Pages that share ten or more groups are reported once, as a copied page. Short app
   labels are grouped by screen and stage instead.

The candidate list stays in `cache/`. A person decides which groups are real patterns
and writes them in `data/<target>/patterns.csv`. The shared wording is the string itself,
ready to reuse, with [brackets] for a slot, so a change made once reaches every page.
Every row carries a question for the team, because outside-in work can't know why the
wording differs.

### Standards register: `targets/<target>.standards.yaml`

For the later checks. One entry per standard: id, statement, authority, source_url,
quote (20 words at most, `published` only), applies_to, check (`automated`, `rubric` or
`manual`) and goal (`usable`, `on-brand` or `consistent`).

Authority, strongest first: **published** (the company states it publicly), **practice**
(named public guidance, such as plain-language guidance) and **majority** (the company's
own most common usage on a surface). A standard is never called a company rule unless
the company published it.

### `audit recommend` → `data/<target>/recommendations.csv`

rec_id, goal, level (`string`, `pattern` or `system`), change, finding_ids, reach, effort
(`small`, `medium` or `large`), confidence (`high`, `medium` or `low`) and question. They
state facts as facts and never present a guess about the reasons behind a choice as a
fact.

### `audit skill` → `pplx-content/`

The pplx-content skill applies the glossary and the patterns to new text. It's
generated from the committed data, so the audit and the skill can't drift apart. Its
layout follows Perplexity's public `pplx-graph` skill package (downloaded once from the
Brand Hub, read for its structure and deleted): a `SKILL.md` with its rules first, a
changelog, when to load it, routing, tracks, an operating flow, a QA report and
critique language, plus `references/` and a checking script. Perplexity's `pplx-brand`
skill needs a sign-in, so it wasn't used.
