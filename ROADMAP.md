# Roadmap

Every step reads the snippets table and writes its own table. Adding a step means adding
a file, not rebuilding.

```text
sources → snippets → terms → standards → findings → recommendations
                   ↘ patterns, style, tone (pass 2) ↗
```

## Phases

1. **Fetch and extract.** Done: 210 API docs and changelog pages became 20,044 snippets.
2. **`audit terms` and `audit view`.** Built: 60 terms proposed, with variants, sources and
   a question for each. Done when about 30 have been reviewed and defined.
3. **Standards, checks and recommendations.** Done when `audit recommend` produces
   recommendations that each link to their evidence, and the viewer shows them.
4. **Stubs, README and example target.** Done when someone new can clone the repo, run
   the example, and follow the steps in the README.

## Phase 3: standards, checks and recommendations

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

finding_id, standard_id, observation, count, surfaces, snippet_ids

- `observation` is a neutral sentence starting "Observed:".
- `snippet_ids` lists every snippet the finding counts, so each one can be traced.
- Tutorial and example-app pages (such as `/docs/cookbook/`) are left out of checks by a
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

Recommendations are suggested changes backed by evidence. They make no claims about how or
why the company made its decisions.

### `audit skill` → `data/<target>/skill/`

The last `system`-level recommendation: a content-standards skill that applies the audit's
standards to new text. It's filled from `templates/content-skill/SKILL.md` with the term
list, the standards register and the check results. Its gates run the same checks as
`audit check`, so the audit and the skill can't drift apart.

Rule sections stay marked "pending" until the audit has the evidence for them.

## Second pass

`audit patterns`, `audit style` and `audit tone` print "Not built yet" for now. Their
output formats will be written here in phase 4, so they fit without changing earlier
steps. Tone scoring will use the published brand principles in the standards register as
its anchor.
