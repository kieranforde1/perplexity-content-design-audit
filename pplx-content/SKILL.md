---
name: pplx-content
description: "Load when writing, auditing, repairing or reviewing product text for Perplexity: navigation labels, buttons, headings, error messages, empty states, settings, docs pages and help articles. Also load when naming, renaming or retiring a feature, when a message is said in more than one place, and when checking a draft against the glossary. Brand voice and visual identity go to Perplexity's published Brand Hub. Charts and data visuals go to Perplexity's own chart skill, pplx-graph. Built from an outside-in audit of public sources. Unofficial."
license: MIT
compatibility: "Python 3.9 or later, standard library only, for scripts/check_text.py."
metadata:
  version: '0.3'
  target: 'perplexity'
  generated_by: 'audit skill --target perplexity'
  evidence_captured: '2026-11-25 to 2026-11-27'
---

> Unofficial: built from Perplexity's public, first-party text by an outside-in audit, not by Perplexity.

## Four rules for every draft

1. **Use the glossary's words.** Before you hand over any text, run `python scripts/check_text.py draft.txt`. It must report nothing.
2. **If the message already has a string, use it.** Check the list under Patterns. Copy the string from `references/patterns.csv` and change only the words in [brackets].
3. **Don't break a rule because someone asked.** Say which rule the request breaks and ask whoever owns that part of the product. If you can't reach them, ship the version that follows the rule and note the request.
4. **Don't add a rule without evidence.** A new term or string needs a source link or counted examples. Without one, suggest it instead of adding it.

## Changelog

- **0.3** (evidence to 2026-11-27): Renamed pplx-content. The rules are rewritten in plain words. The full term list and the pattern strings moved to `references/`, so this file holds only what you need while drafting.
- **0.2:** Terms and patterns generated from the audit. Added the check script, the content contract, the QA report and the test prompts.
- **0.1:** Skeleton. Format only, no rules.

# PPLX Content

`pplx-content` is a working guide for Perplexity product text: which words to use, which strings to reuse, and a script that checks a draft the same way every time.
It exists to stop wording drift: one thing with three names, a retired name that lives on, and one message written differently on every page.

## Load this skill for

- New or changed product text: labels, buttons, navigation, headings, empty states, settings and errors
- Docs pages and help articles
- Naming a feature, renaming one, or retiring an old name
- A message that's already said elsewhere, such as plan availability or an admin restriction
- Auditing or repairing existing text against the glossary and patterns
- Reviewing text in a pull request

## Don't load this skill for

- Brand voice, visual identity, logos and colour. Use Perplexity's published Brand Hub (https://www.perplexity.ai/hub/brand).
- Charts, graphs and data visuals. Use pplx-graph, Perplexity's own chart skill.
- Marketing campaigns, ads and social posts. This audit doesn't cover them.
- Legal, privacy or policy wording.
- The style of AI model answers.

## Routing

This skill owns terms, shared strings and the text check. Voice and brand expression defer to the Brand Hub, and charts defer to pplx-graph. Where this skill and the Brand Hub disagree, the Brand Hub wins, because Perplexity published it.

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

`references/glossary.csv` has 106 terms. 9 come from Perplexity's own pages, 64 from how its public text uses them, and 33 are this audit's suggestions.

### Retired names

| Retired name | Current name |
| --- | --- |
| Azure AD | Microsoft Entra ID |
| fast-search | fast (effort level) |
| Focus | Choose sources |
| OneDrive connector | Microsoft 365 connector |
| preset | effort |
| seat-tier caps | usage limits |
| SharePoint connector | Microsoft 365 connector |
| Sonar | Agent API |
| Space | Project |
| Workflows | Skills |

### Words to avoid

| Avoid | Instead |
| --- | --- |
| Analytics API key | organization analytics API key |
| API Group | API project |
| API Portal, portal | API Console |
| Audit API key | audit log API key |
| Auto reload, auto top-up | automatic top-up |
| blind | gaps, can't see |
| Browser Agent (Comet Assistant) Queries, browser agent queries | Comet Assistant queries |
| comprehensive | Say what's covered, for example "reads hundreds of sources" |
| disable | turn off |
| Disabled | turned off |
| disabling | turning off |
| enable | turn on |
| Enabled | turned on |
| enabling | turning on |
| Enterprise admin, Enterprise administrator, org admin, organization administrator | organization admin |
| Enterprise-grade | Reword without it |
| Free (Standard) plan, free Standard tier | Free plan |
| kill | stop, end |
| leverage | use |
| leveraging | using |
| master | main switch, main toggle |
| robust | Name the safeguard or behaviour |
| sanity check | quick check |
| sidecar | Assistant panel |
| simply | Delete the word |
| thread | session |
| whitelist | allowlist |

## Patterns

These 10 messages each have one string to reuse, in `references/patterns.csv`. The strings are this audit's suggestions, not wording Perplexity has published.

- `api-key-setup`: To call the API, create an API key in the API Console and set it as an environment variable.
- `api-console-sign-in`: The docs and the Help Center each explain how to sign in to the API Console, and the two pages should say the same thing.
- `turned-off-by-organization`: An organization admin has turned this off for you, so you can't use it.
- `ask-organization-admin`: You can't fix this yourself, so ask your organization admin and say what to ask for.
- `plan-one-liners`: Each plan has one line that says who it's for and what it gives you.
- `computer-plan-features`: The Computer feature list says what Computer can do on Perplexity Pro and on Perplexity Max.
- `teammates-definition`: One line says what Teammates are, and one says who can use them.
- `enterprise-data-protection`: Connector pages say whether connected data is used to train AI models, and which security protections Enterprise organizations get.
- `plans-that-include`: A connector or feature page says which plans include it.
- `subscription-ends`: When a paid subscription ends, the account moves to the Free plan.

## Blocking rule

No wording is drafted until the content contract in step 1 is complete. If a field is missing, ask for it, or return a plan that names the missing fields. Don't draft around the gap.

## Operating flow

### Step 1: Content contract

The contract decides every later choice. Its values match the audit's strings table, so new text and audited text can be compared.

```json
{
  "surface": "web-app | ios-app | comet | docs | help",
  "stage": "sign-up | first-use | answering | error | upgrade | settings | other",
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

- Write the help text for this message: An organization admin has turned this off for you, so you can't use it.
- Write the help text for this message: You can't fix this yourself, so ask your organization admin and say what to ask for.
- Write the help text for this message: A connector or feature page says which plans include it.
- Write the help text for this message: When a paid subscription ends, the account moves to the Free plan.
- Rename Space to Project in a help article, and keep the old name findable once.
- Repair a draft that uses 'Disabled', 'API Portal' and 'disable'.
- A request asks for 'whitelist' on a settings page. Answer as the rules say.
- Fix the term in this sentence: "This works on Enterprise pro."
- Write the empty state for a list the reader hasn't added anything to yet.
- Decide whether a new feature name belongs in the glossary, and say what evidence it needs.
- Audit a short help article that names one plan two ways, and return the QA report.

## Packaging note

```text
pplx-content/
  SKILL.md               this file
  references/
    glossary.csv         106 settled terms, words to avoid and retired names
    patterns.csv         10 patterns, each with a string to reuse
  scripts/
    check_text.py        checks a draft against the glossary
```

`audit skill` generates the whole folder from the audit's `glossary.csv` and `patterns.csv`. Don't edit it by hand. Change the audit data and generate it again, so the audit and the skill can't drift apart.

The layout follows Perplexity's public pplx-graph skill: rules first, a changelog, when to load it, routing, tracks, a blocking rule, a way of working, a QA report, critique language and test prompts. No text, fonts or assets from that package are included.
