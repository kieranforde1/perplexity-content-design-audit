"""The viewer's "Test a line of copy" box (viewer_check.js) must give the same answers as
the skill's check script (skill_check_text.py). Every sentence here is invented."""

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

SRC = Path(__file__).resolve().parent.parent / "src" / "audit"
COMPANY = "Example"
ENTRIES = [
    {"term": "Help Panel", "status": "use", "use_instead": ""},
    {"term": "Deep Dive", "status": "use", "use_instead": ""},
    {"term": "AI assistants", "status": "use", "use_instead": ""},
    {"term": "Pro Search", "status": "use", "use_instead": ""},
    {"term": "Gadget", "status": "deprecated", "use_instead": "Tool"},
    {"term": "disabled", "status": "avoid", "use_instead": "turned off"},
    {"term": "Admin Portal", "status": "avoid", "use_instead": "Admin Console"},
    {"term": "portal", "status": "avoid", "use_instead": "Admin Console"},
    {"term": "simply", "status": "avoid", "use_instead": ""},
]
TEXT = """Turn on the Help Panel to see tips.
Turn on the help Panel from settings.
The help panel opens on the right.
# Using the Help Panel
# Using The help panel
Open the Example Help Panel. Then try the Help-Panel.
Ask the AI Assistant. Ask the AI assistants. Ask the AI Assistants.
Run a Pro Searches job, then a pro-search, then ProSearch.
The Gadget is old. A gadget is a general word. Two Gadgets.
This is disabled. It was Disabled. Simply do it.
The Admin Portal has a portal. See admin-portal.png and a portal/page.
Use `Help panel` in code, then the help Panel.
- list item with the Deep dive
1. numbered item: Deep Dive and DEEP DIVE
"""


def load_python_checker() -> ModuleType:
    path = SRC / "skill_check_text.py"
    spec = importlib.util.spec_from_file_location("check_text", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    vars(module)["COMPANY"] = COMPANY
    return module


@pytest.mark.skipif(shutil.which("node") is None, reason="node isn't installed")
def test_javascript_matches_the_skill_script() -> None:
    python = load_python_checker()
    expected = [
        [line, column, rule]
        for line, column, _term, rule in python.problems(TEXT.splitlines(), ENTRIES)
    ]
    assert expected, "the sample text should break some rules"
    script = (
        "const {checkText} = require(process.argv[1]);"
        "const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
        "const out = checkText(input.text, input.entries, input.company);"
        "console.log(JSON.stringify(out.problems.map(p => [p.line, p.column, p.rule])));"
    )
    result = subprocess.run(
        ["node", "-e", script, str(SRC / "viewer_check.js")],
        input=json.dumps({"text": TEXT, "entries": ENTRIES, "company": COMPANY}),
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout) == expected


def rule(kind: str, term: str, texts: list[str]) -> dict[str, object]:
    """A Check tab rule row, shaped the way `audit view` builds it."""
    return {
        "standard_id": f"glossary:{term}",
        "kind": kind,
        "term": term,
        "strings": [{"parts": [[t, False]]} for t in texts],
    }


@pytest.mark.skipif(shutil.which("node") is None, reason="node isn't installed")
def test_samples_are_flagged_strings_from_the_rules() -> None:
    """Each sample is a string from a rule that the box flags, one per kind of rule, the
    shortest in its rule that reads as copy, and never more than three. Patterns don't
    give samples."""
    rules = [
        rule("replace", "disabled", ["This is fine.", "It was disabled here, sadly.", "Disabled."]),
        rule("replace", "simply", ["Simply do it."]),
        rule("retired", "Gadget", ["A gadget is a general word.", "The Gadget is old."]),
        {"standard_id": "pattern:p1", "kind": "pattern", "term": "p1",
         "strings": [{"parts": [["Ask the AI Assistant.", False]]}]},
        rule("write", "Help Panel", ["Turn on the help Panel."]),
        rule("write", "Pro Search", ["Run a ProSearch."]),
        rule("avoid", "Admin Portal", ["The Admin Portal opens."]),
    ]
    script = (
        "const {sampleLines} = require(process.argv[1]);"
        "const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
        "console.log(JSON.stringify(sampleLines(input.rules, input.entries, input.company)));"
    )
    result = subprocess.run(
        ["node", "-e", script, str(SRC / "viewer_check.js")],
        input=json.dumps({"rules": rules, "entries": ENTRIES, "company": COMPANY}),
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout) == [
        "It was disabled here, sadly.",
        "The Gadget is old.",
        "Turn on the help Panel.",
    ]
