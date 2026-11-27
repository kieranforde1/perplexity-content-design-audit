import csv
from collections.abc import Sequence
from pathlib import Path

import pytest

from audit import config, patterns, snippets, terms
from audit.cli import main

GLOSSARY_HEADER = "term,status,use_instead,definition,basis,source_url\n"

Pages = dict[str, list[tuple[str, str]]]


def make_target(
    root: Path,
    pages: Pages,
    *,
    settings: str = "",
    glossary_rows: str = "",
    typed: Sequence[tuple[str, str, str, str]] = (),
) -> config.Target:
    """A target with invented pages, written the way `audit extract` writes them.

    `typed` rows are (text, kind, surface, stage) for app strings typed in by hand.
    """
    (root / "targets").mkdir(parents=True)
    (root / "targets" / "example.yaml").write_text(
        "name: example\n"
        "display_name: Widgetco\n"
        "sources:\n"
        "  - name: help\n"
        "    surface: help\n"
        "    index: https://help.example.com/llms.txt\n" + settings
    )
    target = config.load("example", root)
    rows, full = [], {}
    for url, pieces in pages.items():
        for kind, text in pieces:
            s = snippets.build(text, kind, url, "help", "other", "2026-11-27", "crawl")
            rows.append(s)
            full[s.id] = text
    for text, kind, surface, stage in typed:
        s = snippets.build(text, kind, f"{surface}, a screen", surface, stage, "2026-11-27",
                           "typed")
        rows.append(s)
        full[s.id] = text
    snippets.write(target.local_snippets, rows)
    with target.full_text.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "text"])
        writer.writerows(full.items())
    target.data_dir.mkdir(parents=True, exist_ok=True)
    target.glossary.write_text(GLOSSARY_HEADER + glossary_rows)
    return target


def run(target: config.Target) -> list[dict[str, str]]:
    return patterns.run(target, log=lambda _: None)


def by_reason(rows: list[dict[str, str]], reason: str) -> list[dict[str, str]]:
    return [r for r in rows if r["reason"] == reason]


# Rule 1: clean up each sentence.


def test_cleaning_lowercases_and_drops_punctuation_and_parameters() -> None:
    assert patterns.clean("Set max_results, maxResults or {name} to 1,000.") == (
        "set", "or", "to", "1000",
    )
    assert patterns.clean("It doesn't cost $1.50!") == ("it", "doesnt", "cost", "1.50")


def test_short_sentences_and_parameters_are_skipped(tmp_path: Path) -> None:
    target = make_target(tmp_path, {
        "https://help.example.com/a.md": [
            ("sentence", "Save it now. Open the widget board to start a sprint."),
            ("parameter", "widget_board_id"),
        ],
    })
    sentences, labels = patterns.collect(terms.load_texts(target))
    assert [s.words for s in sentences] == [
        ("open", "the", "widget", "board", "to", "start", "a", "sprint"),
    ]
    assert labels == {}


# Rule 2: look-alikes, chained into groups, on two or more pages.

LOOK_ALIKES: Pages = {
    "https://help.example.com/a.md": [
        ("sentence", "Open the widget board to start a new sprint with your team today."),
    ],
    "https://help.example.com/b.md": [
        ("sentence", "Open the widget board to start a new sprint with your crew today."),
    ],
    # Too different from a.md to be its look-alike, but joined to it through b.md.
    "https://help.example.com/c.md": [
        ("sentence", "Go to the widget board to start a new sprint with your crew today."),
        ("sentence", "Billing questions go to the finance team by email."),
    ],
}


def test_look_alikes_chain_into_one_group(tmp_path: Path) -> None:
    rows = run(make_target(tmp_path, LOOK_ALIKES))
    assert len(rows) == 1
    assert rows[0]["pages"] == "3"
    assert rows[0]["variants"] == "3"


def test_a_lower_overlap_than_the_setting_is_not_a_look_alike(tmp_path: Path) -> None:
    target = make_target(tmp_path, LOOK_ALIKES, settings="patterns:\n  min_overlap: 0.95\n")
    assert run(target) == []


def test_a_group_on_one_page_doesnt_count(tmp_path: Path) -> None:
    target = make_target(tmp_path, {
        "https://help.example.com/a.md": [
            ("sentence", "Open the widget board to start a new sprint today."),
            ("sentence", "Open the widget board to start a fresh sprint today."),
        ],
    })
    assert run(target) == []


def test_min_overlap_defaults_to_the_owners_choice(tmp_path: Path) -> None:
    target = make_target(tmp_path, {})
    assert target.patterns.min_overlap == 0.75


def test_min_overlap_must_be_a_share(tmp_path: Path) -> None:
    with pytest.raises(config.ConfigError, match="min_overlap"):
        make_target(tmp_path, {}, settings="patterns:\n  min_overlap: 75\n")


def test_very_common_phrases_dont_make_pairs(monkeypatch: pytest.MonkeyPatch) -> None:
    sentences = [
        patterns.Sentence(tuple(text.split()), text)
        for text in ("you can now go", "you can now stay", "you can now leave")
    ]
    assert len(patterns.look_alike_pairs(sentences, 0.5)) == 3
    monkeypatch.setattr(patterns, "COMMON_PHRASE", 2)
    assert patterns.look_alike_pairs(sentences, 0.5) == []


# Rule 3: why each group exists.


def test_one_changing_slot_is_a_template(tmp_path: Path) -> None:
    rows = run(make_target(tmp_path, {
        "https://help.example.com/chat.md": [
            ("sentence", "Admins can connect Chatterbox from the widget settings page"
             " in a few clicks."),
        ],
        "https://help.example.com/files.md": [
            ("sentence", "Admins can connect File Box from the widget settings page"
             " in a few clicks."),
        ],
    }))
    assert [r["reason"] for r in rows] == ["template"]


def test_wording_that_differs_in_two_places_is_a_message(tmp_path: Path) -> None:
    rows = run(make_target(tmp_path, LOOK_ALIKES))
    assert rows[0]["reason"] == "message"


def test_a_page_title_and_the_links_to_it_are_link_text(tmp_path: Path) -> None:
    rows = run(make_target(tmp_path, {
        "https://help.example.com/plans.md": [("title", "Which widget plan is right for you?")],
        "https://help.example.com/other.md": [
            ("sentence", "See Which widget plan is right for you?"),
        ],
    }))
    assert [r["reason"] for r in rows] == ["link_text"]


# Rule 4: rank, fact clashes, and avoided words.


def test_groups_are_ranked_by_pages_times_variants(tmp_path: Path) -> None:
    pages = dict(LOOK_ALIKES)
    pages["https://help.example.com/d.md"] = [
        ("sentence", "Export a report as a spreadsheet from the menu."),
    ]
    pages["https://help.example.com/e.md"] = [
        ("sentence", "Export a report as a table from the menu."),
    ]
    rows = run(make_target(tmp_path, pages))
    assert [r["rank"] for r in rows] == ["9", "4"]
    assert [r["group_id"] for r in rows] == ["g0001", "g0002"]


def test_different_numbers_and_periods_are_a_fact_clash(tmp_path: Path) -> None:
    rows = run(make_target(tmp_path, {
        "https://help.example.com/a.md": [
            ("sentence", "Widget reports refresh daily and keep 30 snapshots of history"
             " for every team member."),
        ],
        "https://help.example.com/b.md": [
            ("sentence", "Widget reports refresh weekly and keep 90 snapshots of history"
             " for every team member."),
        ],
    }))
    assert rows[0]["fact_clash"] == "numbers: 30 / 90; time: day / week"


def test_leaving_a_fact_out_isnt_a_clash() -> None:
    variants = [
        ("reports", "keep", "30", "days", "of", "history"),
        ("reports", "keep", "your", "history"),
    ]
    assert patterns.fact_clash(variants, {}) == ""


def test_plan_names_come_from_the_glossary(tmp_path: Path) -> None:
    target = make_target(
        tmp_path,
        {
            "https://help.example.com/a.md": [
                ("sentence", "Shared boards are included with Widgetco Plus for every team."),
            ],
            "https://help.example.com/b.md": [
                ("sentence", "Shared boards are included with Widgetco Ultra for every team."),
            ],
        },
        settings="patterns:\n  plan_names: [Widgetco Plus, Widgetco Ultra, Widgetco Mega]\n",
        glossary_rows=(
            "Widgetco Plus,use,,The middle plan.,observed,\n"
            "Widgetco Ultra,use,,The top plan.,observed,\n"
            "Plus Search,use,,A deeper search.,observed,\n"
        ),
    )
    logged: list[str] = []
    rows = patterns.run(target, log=logged.append)
    assert rows[0]["fact_clash"] == "plans: Widgetco Plus / Widgetco Ultra"
    # Not in the glossary, so it's ignored and the reader is told.
    assert any("Widgetco Mega" in line for line in logged)
    # A longer glossary term wins: "plus search" isn't the Plus plan.
    forms = patterns.plan_names(target, lambda _: None)
    assert patterns.plans_in(("try", "plus", "search", "now"), forms) == set()
    assert patterns.plans_in(("try", "plus", "now"), forms) == {"Widgetco Plus"}


def test_groups_that_only_differ_by_a_word_to_avoid_are_dropped(tmp_path: Path) -> None:
    rows = run(make_target(
        tmp_path,
        {
            "https://help.example.com/a.md": [
                ("sentence", "Create a new key in the widget portal before you start."),
            ],
            "https://help.example.com/b.md": [
                ("sentence", "Create a new key in the widget console before you start."),
            ],
        },
        glossary_rows="widget portal,avoid,widget console,Old name.,recommendation,\n",
    ))
    assert rows == []


def test_plural_avoided_words_are_swapped_too() -> None:
    swaps = patterns.avoided_words([{"term": "Space", "status": "deprecated",
                                     "use_instead": "Project"}])
    assert patterns.swap_avoided(("open", "your", "spaces"), swaps) == (
        "open", "your", "projects",
    )


# Rule 5: copied pages and short app labels.

COPIED_SENTENCES = [
    "Gadgets sync with the cloud every night automatically.",
    "Your invoices list every seat that was active this month.",
    "Teams can pin favourite dashboards to the sidebar.",
    "Removing a member frees their seat straight away.",
    "Archived boards stay readable but nobody can edit them.",
    "Keyboard shortcuts appear when you press the question mark.",
    "Exported files keep their original folder structure intact.",
    "Guests only see the boards someone shares with them.",
    "Notifications for mentions arrive within a minute or two.",
    "Owners can transfer a workspace to another administrator.",
]


def test_pages_sharing_ten_groups_are_one_copied_page_row(tmp_path: Path) -> None:
    copy = [("sentence", s) for s in COPIED_SENTENCES]
    rows = run(make_target(tmp_path, {
        "https://help.example.com/original.md": copy + [
            ("sentence", "Open the widget board to start a new sprint today."),
        ],
        "https://help.example.com/copy.md": copy + [
            ("sentence", "Open the widget board to start a fresh sprint today."),
        ],
    }))
    assert [r["reason"] for r in rows] == ["copied_page"]
    assert rows[0]["pages"] == "2"
    assert "share 11 groups" in rows[0]["example"]
    assert "copy.md" in rows[0]["source_urls"]
    assert rows[0]["fact_clash"] == ""


def test_a_fact_clash_between_copied_pages_stays_on_the_copied_row(tmp_path: Path) -> None:
    copy = [("sentence", s) for s in COPIED_SENTENCES]
    rows = run(make_target(tmp_path, {
        "https://help.example.com/original.md": copy + [
            ("sentence", "You can upload up to 10 widgets to every board."),
        ],
        "https://help.example.com/copy.md": copy + [
            ("sentence", "You can upload up to 20 widgets to every board."),
        ],
    }))
    assert [r["reason"] for r in rows] == ["copied_page"]
    assert rows[0]["fact_clash"] == "numbers: 10 / 20"


def test_short_app_labels_are_grouped_by_surface_and_stage(tmp_path: Path) -> None:
    rows = run(make_target(tmp_path, {}, typed=[
        ("Upgrade now", "button", "web-app", "upgrade"),
        ("See plans", "button", "web-app", "upgrade"),
        ("Ask anything", "label", "web-app", "answering"),
        ("Go Pro", "button", "ios-app", "upgrade"),
    ]))
    groups = by_reason(rows, "app_labels")
    assert len(groups) == 1
    assert groups[0]["surfaces"] == "web-app"
    assert groups[0]["stages"] == "upgrade"
    assert groups[0]["variants"] == "2"
    assert groups[0]["rank"] == ""


def test_longer_app_strings_are_compared_with_the_public_text(tmp_path: Path) -> None:
    rows = run(make_target(
        tmp_path,
        {"https://help.example.com/a.md": [
            ("sentence", "Something went wrong with your widget, please try again."),
        ]},
        typed=[("Something went wrong with the widget, please try again.", "error",
                "web-app", "error")],
    ))
    assert by_reason(rows, "template")[0]["surfaces"] == "help web-app"


# The command.


def test_the_command_writes_the_list_to_the_cache_only(tmp_path: Path) -> None:
    target = make_target(tmp_path, LOOK_ALIKES)
    before = sorted(target.data_dir.iterdir())
    assert main(["patterns", "--target", "example", "--root", str(tmp_path)]) == 0
    path = target.cache_dir / "pattern_candidates.csv"
    with path.open() as f:
        reader = csv.DictReader(f)
        assert tuple(reader.fieldnames or ()) == patterns.COLUMNS
        assert len(list(reader)) == 1
    # Candidates quote whole sentences, so nothing new goes in the committed folder.
    assert sorted(target.data_dir.iterdir()) == before


def test_the_command_without_the_local_table_says_what_to_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "targets").mkdir()
    (tmp_path / "targets" / "example.yaml").write_text("name: example\n")
    assert main(["patterns", "--target", "example", "--root", str(tmp_path)]) == 2
    assert "audit extract" in capsys.readouterr().err
