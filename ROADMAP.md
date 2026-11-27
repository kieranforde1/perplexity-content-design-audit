# Roadmap

Every step reads the strings table (`snippets.csv`) and writes its own table. Adding a
step means adding a file, not rebuilding.

## Phases

1. **Fetch and extract.** Done when fetch and extract run on the docs index. Done.
2. **`audit terms` and `audit view`.** Done when the viewer shows about 30 reviewed terms
   with sources. Built, and waiting on review.
3. **Stubs, README and example target.** Done when someone new can clone the repo, run
   the example, and follow the steps in the README.

## Second pass

`audit style` and `audit tone` print "Not built yet" for now. Their output formats will be
written here, so they fit without changing earlier steps. `audit patterns` is designed
below. The owner agreed it on 2026-11-27.

**Order agreed on 2026-11-27:** finish patterns steps 2 and 4, then a design pass, then
patterns step 3. The design pass simplifies both the screens (the viewer and the review
page) and how the tool works (its commands, files and steps), so the Patterns tabs are
built once, in the new design. Tone waits until after that. It's the hardest step and
isn't needed to show the method.

### `audit patterns`: the same message in different words

A pattern is a message said in more than one place that should read the same each time:
an instruction, a notice, a status, a plan description. A glossary term fixes one word.
A pattern fixes one sentence. The audit's question is the same as for terms: where does
the wording vary, and what should it be?

**Two tables, like terms and the glossary**

| File | Written by | What it holds |
| --- | --- | --- |
| `cache/<target>/pattern_candidates.csv` | `audit patterns` (local, gitignored) | Groups of look-alike sentences, with their string IDs. A list to work from, not a finding. |
| `data/<target>/patterns.csv` | A person (drafts can be proposed first, as for the glossary) | The patterns that are real: message, shared wording, the variants found, and a question for the team. |

**How candidates are found** (five rules a content designer can explain)
1. Clean up each sentence: lower-case it, remove punctuation, skip parameters and anything
   under four words.
2. Two sentences are look-alikes when they share a three-word phrase and at least 75% of
   their words. Look-alikes chain into one group. Only groups on two or more pages count.
3. Name why each group exists: link text (send it to terms), template (one slot changes,
   such as a connector name; record it, usually fine) or message (the wording differs in
   more than one place; a pattern candidate).
4. Rank by pages times variants. Raise groups where the variants disagree on a fact, such
   as different numbers, plan names or "daily" against "weekly". If the only difference is
   a glossary word to avoid, `audit check` already covers it.
5. Report pages that share ten or more groups once, as a copied page, not as dozens of
   findings. Short app labels are too short for word overlap, so they're grouped by screen
   and stage instead.

**What a person decides:** which candidates are real patterns, what the message is, and
the shared wording. The tool never writes `patterns.csv` rows as final.

**`patterns.csv` columns:** pattern_id, message (one plain sentence), shared_wording,
basis (`published`, `observed` or `recommendation`, as in the glossary), variants (count),
pages (count), surfaces, question, string_ids. The shared wording is a recommendation
unless the company published it. Every row carries a question for the team, because
outside-in work can't know why the wording differs.

**What it connects to**
- `audit check` reads every pattern and reports pages that say the message
  another way, as findings in a new "same message, different words" category.
- The viewer gets a Patterns tab, and the review page gets a tab to accept or reject
  proposed patterns, built the same way as Glossary proposals.
- Text that exists only in the app (statuses, labels) can't be fixed by changing the help
  page alone. Those rows say so.

**Build order, each step its own pull request**
1. `audit patterns` writes the candidate list, with tests on invented fixtures. Done.
2. `patterns.csv`, its check (`audit patterns --check`) and the draft rows from the
   research notes (10 candidates).
3. The viewer tab and review tab. Built after the design pass.
4. The `audit check` link.

**Decided by the owner on 2026-11-27:**
- Look-alikes share at least 75% of their words, not 60%. Groups chain, so a looser
  setting pulls unrelated sentences into one group (about 690 groups against about
  1,180). It's a setting in the target config, not a fixed number.
- Patterns don't wait any longer: the glossary review is finished, and rule 4 already
  drops groups whose only difference is a glossary word to avoid.
- The first release includes the viewer and review tabs (steps 1 to 3).
- Every row in `patterns.csv` is a real pattern, because only a person writes it. There's
  no status column, and `audit check` reads every row.

## Later

These are paused. They're kept here so they can be picked up without starting again.
`audit recommend` and `audit skill` print "Not built yet" until then. The first part of
`audit check` is built: it checks the public text against `glossary.csv` (words to avoid,
retired names and other spellings). The other checks below are still to come.

### Standards register: `targets/<target>.standards.yaml`

Each standard is something the content can be checked against. One entry per standard:

| Field | What it holds |
| --- | --- |
| id | Short name, such as `heading-case` |
| statement | The standard in one plain sentence |
| authority | `published`, `practice` or `majority` (see below) |
| source_url | Where it comes from. Required for `published` and `practice` |
| quote | The source's own words, 20 words at most. `published` only |
| applies_to | Which surfaces, kinds and stages it covers |
| check | `automated`, `rubric` or `manual` |
| goal | `usable`, `on-brand` or `consistent` |

Authority, strongest first:

1. **published**: something the company states publicly about its own content or brand.
2. **practice**: named, public general guidance, such as plain-language or accessibility
   guidance.
3. **majority**: the company's own most common usage. If most headings on a surface use
   sentence case, that becomes the standard for that surface, and the rest are the
   exceptions. The standard comes from the content itself, not outside taste.

A standard never claims to be a company rule unless the company published it.

### `audit check` → `data/<target>/findings.csv`

finding_id, standard_id, category, term, written, count, surfaces, issue, fix, question,
snippet_ids

- `category` is the kind of mismatch: capitalisation, spelling or spacing, deprecated
  name, avoided term or other variant.
- `issue` says what's wrong, `fix` says what to write instead, and `question` is filled
  in only where only the team can answer.
- `snippet_ids` lists every string the finding counts, so each one can be traced.
- Tutorial and example-app pages are left out of checks by the `analysis_exclude`
  config setting, because they aren't product language.

First checks:

| Goal | Check |
| --- | --- |
| consistent | Term variants: case, plurals, hyphenation, legacy against current names |
| consistent | Heading case by surface |
| usable | Error messages: does each say what happened and what to do next? |
| usable | Button labels: length and whether they start with a verb |
| usable | Reading level by stage |
| on-brand | Words that overclaim or explain the machinery, flagged for a person to review |

### `audit recommend` → `data/<target>/recommendations.csv`

rec_id, goal, level, change, finding_ids, reach, effort, confidence, question

- `level` is one of:
  - `string`: fix these specific strings.
  - `pattern`: change how a type of content is written.
  - `system`: change the process or tooling so the problem doesn't come back, such as a
    term check at build time.
- `reach` is how many strings and surfaces the change would touch.
- `effort` is `small`, `medium` or `large`.
- `confidence` is `high`, `medium` or `low`. Automated counts start high and anything
  needing a person's judgement starts lower.
- `question` is what to ask the team, because outside-in work can't know why something
  was written the way it was.

Recommendations are suggested changes backed by evidence. They state facts as facts and
never present a guess about the reasons behind a choice as a fact.

### `audit skill` → `data/<target>/skill/`

A content-standards skill that applies the audit's standards to new text. It would be
filled from `later/content-skill-template.md` with the term list, the standards register
and the check results. Its gates would run the same checks as `audit check`, so the audit
and the skill can't drift apart.
