---
name: content-standards
description: "Load when writing, auditing, repairing or reviewing product text for Perplexity: navigation labels, buttons, headings, error messages, empty states, settings, docs pages and help articles. Also load when naming, renaming or retiring a feature, when a message is said in more than one place, and when checking a draft against the glossary. Brand voice and visual identity go to Perplexity's published Brand Hub. Charts and data visuals go to Perplexity's own chart skill, pplx-graph. Built from an outside-in audit of public sources. Unofficial."
license: MIT
compatibility: "Python 3.9 or later, standard library only, for scripts/check_text.py."
metadata:
  version: '0.2'
  target: 'perplexity'
  generated_by: 'audit skill --target perplexity'
  evidence_captured: '2026-11-25 to 2026-11-27'
---

> Unofficial: built from Perplexity's public, first-party text by an outside-in audit, not by Perplexity.

## Gates: read first

These hold for every piece of text. A script or a file settles each one, not taste.

1. **Terms come from `references/glossary.csv`.** The gate is `python scripts/check_text.py <file>` exiting 0 on the draft.
2. **A message that matches a pattern uses its string** from `references/patterns.csv`, word for word, with only the [slots] filled in.
3. **A request that breaks a gate isn't applied silently.** Name the rule it breaks and ask the content owner for that surface, a role and not a named person. If they can't be reached, ship the version that follows the rule and list the request as an open decision.
4. **A rule needs a source or counted evidence.** Without one, suggest it as a candidate for the glossary or the patterns. Don't add it here.

## Changelog

- **0.2** (evidence to 2026-11-27): Terms and patterns are generated from the audit's glossary and patterns table. Added the text check script, the content contract, the QA report and benchmark prompts. Read `references/glossary.csv` and `references/patterns.csv`.
- **0.1:** Skeleton. Format only, no rules.

# Content standards

This skill helps a writer, or an AI writing tool, use Perplexity's settled terms and shared strings in new text, and check a draft the same way every time.
It exists to prevent wording drift: one thing named three ways, a retired name that lives on, and one message said differently on every page.

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

- `references/glossary.csv`: every settled term, with its status (use, avoid or deprecated), the replacement, a definition, its basis and a source link. Read it when a draft names a product, feature, plan, role or setting, and when the script flags a word.
- `references/patterns.csv`: every pattern, with its message, the shared wording to reuse, how to use it and an open question for the team. Read it when the contract's message matches a pattern below.
- `scripts/check_text.py`: checks a draft against the glossary. Run it on every draft before the QA report.

## Terms

106 glossary rows: 9 published by Perplexity, 64 observed in its public text and 33 recommended by this audit. Only published rows are Perplexity's own rules. Each row's basis and source are in `references/glossary.csv`.

### Use

Write these as shown, including capitals. A plural, or Perplexity in front, is the same term.

Agent API, Agent API models, AI assistants, AI models, AI-powered, API Console, API key, API project, API reference, App Connectors, Assistant panel, audit log API key, automatic top-up, Brain, Chat Completions, Comet, Comet Assistant, Comet Browser, Computer, Computer credits, Connectors, Content Generation, Credits, Deep Research, Discover, Enterprise, Enterprise Max, Enterprise Pro, Enterprise users, Fast Search, File Connectors, File Uploads, Free plan, Health, Help Center, Home, Incognito, Incognito mode, MCP server, Model Council, Monitor API, My organization, Orchestrator API, organization admin, organization analytics API key, Organization settings, OS, People Search, Perplexity API Platform, Perplexity Enterprise organizations, Perplexity Max, Perplexity Pro, Portable Computer, Pro Search, Project, Role-based, Search API, Session, Sessions page, Skills, Teammate, Trust Center.

### Retired names

| Retired name | Current name |
| --- | --- |
| Space | Project |
| Sonar | Agent API |
| Focus | Choose sources |
| preset | effort |
| fast-search | fast (effort level) |
| SharePoint connector | Microsoft 365 connector |
| OneDrive connector | Microsoft 365 connector |
| Azure AD | Microsoft Entra ID |
| Workflows | Skills |
| seat-tier caps | usage limits |

### Words to avoid

| Avoid | Instead |
| --- | --- |
| Disabled | turned off |
| API Portal, portal | API Console |
| Enterprise-grade | Reword without it |
| disable | turn off |
| whitelist | allowlist |
| master | main switch, main toggle |
| sanity check | quick check |
| blind | gaps, can't see |
| kill | stop, end |
| comprehensive | Say what's covered, for example "reads hundreds of sources" |
| leverage | use |
| robust | Name the safeguard or behaviour |
| simply | Delete the word |
| thread | session |
| Enterprise admin, Enterprise administrator, organization administrator, org admin | organization admin |
| API Group | API project |
| Audit API key | audit log API key |
| Analytics API key | organization analytics API key |
| sidecar | Assistant panel |
| Browser Agent (Comet Assistant) Queries, browser agent queries | Comet Assistant queries |
| Auto reload, auto top-up | automatic top-up |
| Free (Standard) plan, free Standard tier | Free plan |
| disabling | turning off |
| enable | turn on |
| Enabled | turned on |
| enabling | turning on |
| leveraging | using |

## Patterns

10 messages are said in more than one place. Each one gives the message, then the string to reuse, then how to use it where the audit has a note. Words in [brackets] are slots to fill in each time. The strings are this audit's suggestions, not wording Perplexity has published. Each pattern's open question for the team is in `references/patterns.csv`.

### api-key-setup

To call the API, create an API key in the API Console and set it as an environment variable.

> Create an API key on the API Keys page of the API Console. Set it as the PERPLEXITY_API_KEY environment variable.

### api-console-sign-in

The docs and the Help Center each explain how to sign in to the API Console, and the two pages should say the same thing.

> Signing in creates a Perplexity account. It doesn't give you an API project or API access on its own.

Keep one of the two pages as the source and link to it from the other.

### turned-off-by-organization

An organization admin has turned this off for you, so you can't use it.

> Turned off by your organization: an organization admin has turned this off.

Use this status for connectors, local file access and custom connectors alike, in one status set shown in a fixed order: Connected, Connect, Upgrade required, Unavailable, Turned off by your organization.

### ask-organization-admin

You can't fix this yourself, so ask your organization admin and say what to ask for.

> Ask your organization admin to [the specific action].

Example: Ask your organization admin to turn on desktop tools.

### plan-one-liners

Each plan has one line that says who it's for and what it gives you.

> Free plan: Cited answers from the web, with [daily or weekly] limits. Perplexity Pro: Higher limits, top AI models and Computer, for serious work. Perplexity Max: The highest limits and newest models, for heavy, sustained work.

Use the same line on the pricing card, the pricing FAQ, the Help Center and the app.

### computer-plan-features

The Computer feature list says what Computer can do on Perplexity Pro and on Perplexity Max.

> Both plans: Create and edit documents, slides and spreadsheets. Both plans: Connect 400+ apps. Perplexity Pro: Deep Research. Perplexity Max: Expert-level research and data analysis.

One feature list: a row both plans have reads the same on both, and a Perplexity Max row only says what's more.

### teammates-definition

One line says what Teammates are, and one says who can use them.

> Teammates are AI agents that own ongoing work. They keep working while you're away, using your tools and context. Research preview on Perplexity Max, Enterprise Pro and Enterprise Max.

The second sentence is optional where space is short.

### enterprise-data-protection

Connector pages say whether connected data is used to train AI models, and which security protections Enterprise organizations get.

> Will my [Connector] data be used to train AI models? No. [Connector] data, like all Enterprise data, is never used to train AI models. Perplexity Enterprise organizations get SOC 2 Type II certification, end-to-end encryption, strict data privacy measures and granular user access controls.

One fixed block on every connector page, with one slot for the connector name.

### plans-that-include

A connector or feature page says which plans include it.

> Available on Perplexity Pro, Perplexity Max, Enterprise Pro and Enterprise Max.

Always list the plans in that order, and leave out any plan that doesn't apply.

### subscription-ends

When a paid subscription ends, the account moves to the Free plan.

> Your account moves to the Free plan when your current billing period ends.

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
2. The problems, each with the term, pattern or gate it breaks
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
- A request asks for 'whitelist' on a settings page. Answer as the gates say.
- Fix the term in this sentence: "This works on Enterprise pro."
- Write the empty state for a list the reader hasn't added anything to yet.
- Decide whether a new feature name belongs in the glossary, and say what evidence it needs.
- Audit a short help article that names one plan two ways, and return the QA report.

## Packaging note

```text
content-standards/
  SKILL.md               this file
  references/
    glossary.csv         106 settled terms, words to avoid and retired names
    patterns.csv         10 patterns, each with a string to reuse
  scripts/
    check_text.py        checks a draft against the glossary
```

`audit skill` generates the whole folder from the audit's `glossary.csv` and `patterns.csv`. Don't edit it by hand. Change the audit data and generate it again, so the audit and the skill can't drift apart.

The layout follows the structure of Perplexity's public, MIT-licensed pplx-graph skill: gates first, a changelog, when to load it, routing, tracks, a blocking rule, an operating flow, a QA report, critique language and benchmark prompts. No text, fonts or assets from that package are included.
