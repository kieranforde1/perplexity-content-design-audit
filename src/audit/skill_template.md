---
name: {{skill_name}}
description: "Load when writing, auditing, repairing or reviewing product text for {{display_name}}: navigation labels, buttons, headings, error messages, empty states, settings, docs pages and help articles. Also load when naming, renaming or retiring a feature, when a message is said in more than one place, and when checking a draft against the glossary. Brand voice and visual identity go to {{display_name}}'s published Brand Hub. Charts and data visuals go to {{display_name}}'s own chart skill, pplx-graph. Built from an outside-in audit of public sources. Unofficial."
license: MIT
compatibility: "Python 3.9 or later, standard library only, for scripts/check_text.py."
metadata:
  version: '{{version}}'
  target: '{{target}}'
  generated_by: 'audit skill --target {{target}}'
  evidence_captured: '{{captured_from}} to {{captured_to}}'
---

> Unofficial: built from {{display_name}}'s public, first-party text by an outside-in audit, not by {{display_name}}.

## Four rules for every draft

1. **Use the glossary's words.** Before you hand over any text, run `python scripts/check_text.py draft.txt`. It must report nothing.
2. **If the message already has a string, use it.** Check the list under Patterns. Copy the string from `references/patterns.csv` and change only the words in [brackets].
3. **Don't break a rule because someone asked.** Say which rule the request breaks and ask whoever owns that part of the product. If you can't reach them, ship the version that follows the rule and note the request.
4. **Don't add a rule without evidence.** A new term or string needs a source link or counted examples. Without one, suggest it instead of adding it.

## Changelog

- **0.3** (evidence to {{captured_to}}): Renamed {{skill_name}}. The rules are rewritten in plain words. The full term list and the pattern strings moved to `references/`, so this file holds only what you need while drafting.
- **0.2:** Terms and patterns generated from the audit. Added the check script, the content contract, the QA report and the test prompts.
- **0.1:** Skeleton. Format only, no rules.

# {{skill_title}}

`{{skill_name}}` is a working guide for {{display_name}} product text: which words to use, which strings to reuse, and a script that checks a draft the same way every time.
It exists to stop wording drift: one thing with three names, a retired name that lives on, and one message written differently on every page.

## Load this skill for

- New or changed product text: labels, buttons, navigation, headings, empty states, settings and errors
- Docs pages and help articles
- Naming a feature, renaming one, or retiring an old name
- A message that's already said elsewhere, such as plan availability or an admin restriction
- Auditing or repairing existing text against the glossary and patterns
- Reviewing text in a pull request

## Don't load this skill for

- Brand voice, visual identity, logos and color. Use {{display_name}}'s published Brand Hub{{brand_link}}.
- Charts, graphs and data visuals. Use pplx-graph, {{display_name}}'s own chart skill.
- Marketing campaigns, ads and social posts. This audit doesn't cover them.
- Legal, privacy or policy wording.
- The style of AI model answers.

## Routing

This skill owns terms, shared strings and the text check. Voice and brand expression defer to the Brand Hub, and charts defer to pplx-graph. Where this skill and the Brand Hub disagree, the Brand Hub wins, because {{display_name}} published it.

## Tracks: decide before writing

The surface decides the track, and the track decides what matters most.

| Surface | Track | What matters most |
| --- | --- | --- |
| web-app, ios-app, comet | product | Short labels and buttons that name the result. Errors say what happened and what to do next. |
| docs | docs | Exact names for products, endpoints and settings. Code values stay as they are, in backticks. |
| help | help | Task-first headings and steps. The same message in the same words on every article. |

## References

- `references/glossary.csv`: every term, with whether to use it, avoid it or treat it as retired, what to write instead, what it means, and where the rule comes from. Read it when a draft names a product, feature, plan, role or setting, and when the script flags a word.
- `references/patterns.csv`: every pattern, with its message, the string to reuse, how to use it, and a question the team hasn't answered yet. Read it when your message is in the list under Patterns.
- `scripts/check_text.py`: checks a draft against the glossary. Run it on every draft before the QA report.

## Terms

{{terms}}

## Patterns

{{patterns}}

## Blocking rule

No wording is drafted until the content contract in step 1 is complete. If a field is missing, ask for it, or return a plan that names the missing fields. Don't draft around the gap.

## Operating flow

### Step 1: Content contract

The contract decides every later choice. Its values match the audit's strings table, so new text and audited text can be compared.

```json
{
  "surface": "web-app | ios-app | comet | docs | help",
  "stage": "{{stages}}",
  "reader": "Who reads this, and what they're trying to get done.",
  "message": "The one thing this text must say.",
  "terms": ["Glossary terms the text needs."],
  "pattern": "A pattern_id from references/patterns.csv, or null."
}
```

### Step 2: Pick the terms

Look up every entry in `terms` in `references/glossary.csv`.

- Use the form in the glossary exactly, including its capitals.
- For a retired name, use the current one. Mention the old name once only where readers need the link.
- For a word to avoid, use its replacement.
- If a term isn't in the glossary, stop and flag it as a candidate term. Don't invent a form.

### Step 3: Reuse the pattern string

If the contract names a pattern, use its string word for word and fill in only the [slots]. Read its note on how to use it. Check any fact in a slot before using it.

### Step 4: Draft

Write to the contract, with the message first. Put each string on its own line, because the script reads each line as one string. Start a heading with #, so title case is allowed there.

### Step 5: Run the script

```bash
python scripts/check_text.py draft.txt
```

It prints `line:column: rule` for each problem and exits 1 if there are any. Fix each line and run it again until it exits 0. A flag on a code value, or on a word quoted from a screen as shown, needs a person to decide.

### Step 6: QA report

Every draft comes with the QA report below.

## QA report format

Each line is pass, fail or not verified. Not verified never counts as a pass. The script checks terms only, so the other lines need a person or a careful read.

```md
## Content QA

- Contract complete: pass | fail | not verified
- Track: product | docs | help
- check_text.py exits 0: pass | fail | not verified
- Terms missing from the glossary flagged: pass | fail | not verified
- Pattern string used word for word: pass | fail | not verified | n/a
- Facts in slots checked: pass | fail | not verified | n/a
- Message comes first: pass | fail | not verified
- Open decisions listed: pass | fail | n/a
```

## Critique language

Short, direct sentences, each pointing to a fix.

### Terms

- This uses two names for the same thing. Use the glossary form.
- This is a retired name. Use the current name, and give the old one once where readers need the link.
- This word is on the avoid list. Use its replacement.
- This term isn't in the glossary. Flag it before it spreads.

### Patterns

- This says a pattern's message in new words. Use the pattern string.
- This changes the pattern string beyond its slots.
- This slot holds a fact nobody has checked.

### Clarity

- The thing the reader came for is in the third sentence. Move it first.
- This label names the click, not the result.
- This error says what went wrong but not what to do next.
- This heading describes the section, not the task.

## Output expectations

When writing text, return:

1. The content contract
2. The terms used, and any flagged as candidates
3. The pattern used, if any
4. The wording
5. The script's output
6. The QA report

When auditing text, return:

1. A verdict
2. The problems, each with the term, pattern or rule it breaks
3. Required changes
4. Optional changes
5. The QA report

When repairing text, return:

1. What was wrong, with the rule it broke
2. The new wording
3. The script's output on the new wording
4. The updated QA report

## Benchmark prompts

Use these to test the skill. Most have an answer that the glossary or a pattern settles.

{{benchmarks}}

## Packaging note

```text
{{skill_name}}/
  SKILL.md               this file
  references/
    glossary.csv         {{term_count}} settled terms, words to avoid and retired names
    patterns.csv         {{pattern_count}} patterns, each with a string to reuse
  scripts/
    check_text.py        checks a draft against the glossary
```

`audit skill` generates the whole folder from the audit's `glossary.csv` and `patterns.csv`. Don't edit it by hand. Change the audit data and generate it again, so the audit and the skill can't drift apart.

The layout follows {{display_name}}'s public pplx-graph skill: rules first, a changelog, when to load it, routing, tracks, a blocking rule, a way of working, a QA report, critique language and test prompts. No text, fonts or assets from that package are included.
