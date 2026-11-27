# Roadmap

Every step reads the snippets table and writes its own table. Adding a step means adding
a file, not rebuilding.

## Phases

1. **Fetch and extract.** Done when fetch and extract run on the docs index. Done.
2. **`audit terms` and `audit view`.** Done when the viewer shows about 30 reviewed terms
   with sources. Built, and waiting on review.
3. **Stubs, README and example target.** Done when someone new can clone the repo, run
   the example, and follow the steps in the README.

## Second pass

`audit patterns`, `audit style` and `audit tone` print "Not built yet" for now. Their
output formats will be written here, so they fit without changing earlier steps.

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
- `snippet_ids` lists every snippet the finding counts, so each one can be traced.
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
- `reach` is how many snippets and surfaces the change would touch.
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
