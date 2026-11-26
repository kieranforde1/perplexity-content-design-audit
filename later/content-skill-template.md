---
name: content-standards
description: "Load when writing, auditing, repairing or reviewing product text for {{display_name}}: navigation labels, buttons, headings, error messages, empty states, docs pages, help articles and changelog entries. Also load for naming and renaming product features. Built from an outside-in audit of public sources. Unofficial."
license: MIT
metadata:
  version: '0.1'
  status: skeleton
  target: '{{target}}'
  generated_by: 'audit skill --target {{target}}'
  evidence_captured: '{{captured_from}} to {{captured_to}}'
---

> **Unofficial.** Built from {{display_name}}'s public, first-party text by an outside-in
> audit. It is not a company guide. Each rule says where its authority comes from.

## Gates: read first

Anyone using this skill holds these. A script checks them, so they don't depend on anyone's taste.

1. **Fill in the content contract first.** No wording is drafted until the contract in step 1 is complete.
2. **Terms come from the term list.** Use the accepted form in `references/terms.csv`. The gate is `audit check --only terms` exiting 0 on the new text.
3. **Every rule shows its authority.** `published` rules come from the company. `practice` rules come from named public guidance. `majority` rules come from the company's own most common usage. Never present a `majority` or `practice` rule as a company rule.
4. **A request that breaks a gate isn't applied silently.** Name the rule it breaks and ask the content owner for this surface (a role, not a named person). Record the decision as an exception in `references/standards.yaml`.
5. **Evidence beats preference.** A rule without a source link or counted examples doesn't belong here. Suggest it as a candidate instead.

## Changelog

- **0.1:** Skeleton. Format, contract, flow, QA and critique language are in place. Rule sections are waiting on audit data.

# Content standards

This skill exists to stop wording drift: the same thing named three ways, labels that describe the click rather than the result, and errors that leave people stuck. It turns a request into a content contract, checked wording and a QA report. It doesn't exist to make text longer or more polished.

## Load this skill for

- New or changed UI text: labels, buttons, navigation, headings, empty states, tooltips, errors
- Docs, help articles and changelog entries
- Naming a feature, renaming one, or retiring an old name
- Auditing existing text against the standards
- Reviewing text in a pull request

## Don't load this skill for

- Marketing campaigns, ads and social posts. They follow the company's own marketing guidance, which this skill doesn't cover.
- Legal, privacy or policy wording.
- The style of AI model answers. This audit doesn't cover it yet.

## Routing

Voice, visual identity and brand expression defer to {{display_name}}'s published brand guidance (`references/standards.yaml`, authority `published`). This skill owns terms, labels, content patterns and the checks.

## Tracks: decide before writing

The surface decides which rules apply.

| Surface | Track | Rules |
| --- | --- | --- |
| web-app, ios-app, comet | **product** | Labels, buttons, errors and empty states. Tightest length limits. |
| docs | **docs** | Headings, parameter names, procedures. Exact names matter most here. |
| help | **help** | Task-first articles that people find by searching. |
| changelog, blog | **announce** | Names a change, what it means for the reader, and any rename. |

## What this package bundles

```text
content-standards/
  SKILL.md                 this file
  LICENSE
  references/
    terms.csv              accepted terms, variants found, definitions (from `audit terms`)
    standards.yaml         every standard, with authority, source and check
    patterns.md            named content patterns with anatomy and examples (pass 2)
    exceptions.md          decisions that break a gate on purpose, and why
  scripts/
    check                  runs `audit check` on new text
```

## Non-negotiables

These are filled in by `audit skill` from the standards register. Each line carries its authority and source.

### Published

{{standards authority=published}}

*Pending: filled from `targets/{{target}}.standards.yaml`.*

### Practice

{{standards authority=practice}}

*Pending: each one needs a named public source before it's listed.*

### Majority

{{standards authority=majority}}

*Pending: filled from `audit check` results (phase 3). Each line shows the share of snippets that follow it, such as "Headings use sentence case (94% of 1,912 docs headings)".*

## Blocking rule

Drafting is blocked until steps 1 and 2 are complete:

1. Content contract
2. Term check

If either is incomplete, ask for the missing fields, or return a plan that names them. Don't draft wording around the gaps.

## Operating flow

### Step 1: Content contract

The contract is the source of truth for every later choice. Its values are the same ones the audit's snippets table uses, so audited text and new text can be compared directly.

```json
{
  "reader_task": "What the reader is trying to get done, in their words.",
  "must_know_or_do": "The one thing this text must get across.",
  "surface": "docs | help | pricing | blog | changelog | web-app | ios-app | comet",
  "stage": "sign-up | first-use | answering | error | upgrade | settings | other",
  "kind": "title | heading | nav | button | parameter | error | sentence",
  "state": "default | empty | loading | error | success",
  "terms": ["Product and feature names this text uses."],
  "constraints": {
    "max_words": null,
    "localised": true,
    "screen_reader_label_needed": false
  },
  "current_wording": ["Snippet IDs for any text this replaces."]
}
```

### Step 2: Term check

Look up every name in `terms` in `references/terms.csv`.

- Use the accepted form exactly, including its case.
- If a name has been retired (for example an old feature name), use the current one. Mention the old one only where readers need the link.
- If a name isn't in the list, stop and flag it as a candidate term. Don't make up a form.

### Step 3: Pattern

Choose the content pattern for this `kind` and `state` from `references/patterns.md`.

*Pending: patterns come from `audit patterns` (pass 2). Until then, follow the majority standards for the kind.*

### Step 4: Draft

Write the wording to the contract and the pattern. Keep `must_know_or_do` first.

### Step 5: Check

Run `scripts/check` on the draft. Fix anything that fails. Flagged items (such as words that overclaim) need a person to decide.

### Step 6: QA report

Every piece of shipped text comes with a QA report.

## Content QA

Each line is pass, fail or not verified. "Not verified" is never silently counted as a pass.

```md
## Content QA

- Contract complete: pass | fail | not verified
- Track: product | docs | help | announce
- Terms match terms.csv: pass | fail | not verified
- No retired names: pass | fail | not verified
- Pattern followed: pass | fail | not verified | n/a (pass 2)
- Length within constraints: pass | fail | not verified
- Buttons name the result: pass | fail | not verified | n/a
- Errors say what happened and what to do next: pass | fail | not verified | n/a
- Heading case matches the majority standard: pass | fail | not verified | n/a
- No overclaiming words, or each one reviewed: pass | fail | not verified
- Reading level within the target for this stage: pass | fail | not verified
- Screen reader label present where needed: pass | fail | not verified | n/a
- Exceptions recorded: pass | fail | n/a
```

## Critique language

Use direct, specific language in reviews. Each line points to a fix.

### Terms

- This uses two names for the same thing. Pick the one in the term list.
- This is the old name. Readers who know it need the link once, not every time.
- This term isn't in the list. Flag it before it spreads.

### Labels and buttons

- This label names the click, not the result.
- Two buttons on this screen say nearly the same thing.
- This nav label doesn't match the page title it opens.

### Errors

- This says what went wrong but not what to do.
- This blames the reader.
- This is a code, not a message.

### Claims

- This claims more than the feature does.
- This explains how it works when the reader only needs to know what it does.

### Structure

- The thing the reader came for is in the third sentence.
- This heading describes the section, not the task.

## What to return

When writing text, return:

1. Content contract
2. Term check result
3. Pattern used
4. The wording
5. QA report

When auditing text, return:

1. Verdict
2. Highest-risk issues, each with the standard it breaks
3. Required changes
4. Optional refinements
5. QA report

When repairing text, return:

1. What was wrong, with the standard it broke
2. What changed
3. Why the new version is clearer or more accurate
4. Updated QA report

## Benchmark prompts

Use these to regression-test the skill:

- Write the error for an API key that has expired.
- Rename a feature across docs, help and the changelog, and keep the old name findable.
- Audit a settings page where the nav label and page title disagree.
- Write an empty state for a list the reader hasn't added anything to yet.
- Decide whether a new feature name should go in the term list.
- Shorten a five-word button to fit a mobile layout without losing the result it names.
- Review a docs pull request that uses two forms of the same product name.
- Write a changelog entry for a change that removes an option.

## Packaging note

`SKILL.md` and `references/` are generated together by `audit skill` and versioned with each audit run. Don't edit `references/terms.csv` or `references/standards.yaml` by hand in the package. Change them in the audit, then regenerate.

The format follows the structure of the public, MIT-licensed `pplx-graph` skill on {{display_name}}'s Brand Hub: gates, contract, blocking rule, operating flow, QA report, critique language and benchmark prompts. No text, fonts or assets from that package are included.
