"""Load a target config (targets/<name>.yaml).

A target config is everything company-specific: where its public text lives, which
surface each source belongs to, and how URLs map to stages. The code stays the same
for every company.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from audit.snippets import STAGES, SURFACES

# Never fetch faster than this, whatever a config says.
MIN_DELAY_SECONDS = 1.0


@dataclass(frozen=True)
class Source:
    name: str
    surface: str
    # A page that lists other pages as Markdown links, like llms.txt.
    index: str | None
    # Pages to fetch directly.
    urls: tuple[str, ...]
    # Keep only index links whose URL contains this text, such as one language's pages
    # from an index that lists every language.
    include: str | None = None


@dataclass(frozen=True)
class StageRule:
    match: str
    stage: str


@dataclass(frozen=True)
class LegacyName:
    old: str
    current: str
    source: str


@dataclass(frozen=True)
class TermSettings:
    seeds: tuple[str, ...] = ()
    legacy_names: tuple[LegacyName, ...] = ()
    not_terms: tuple[str, ...] = ()
    third_party: tuple[str, ...] = ()
    repeated_text: tuple[str, ...] = ()
    max_proposed: int = 60
    consistent_min_pages: int = 3


@dataclass(frozen=True)
class CheckSettings:
    """Company-specific exceptions for `audit check`."""

    # Surfaces that record the past, such as a changelog. A retired or avoided name
    # there was correct on the day it was written, so it isn't reported.
    history_surfaces: tuple[str, ...] = ()
    # Pages about moving off an old name. They have to say the old name to explain the move.
    rename_pages: tuple[str, ...] = ()
    # Glossary term -> phrases that contain it but name something else. A match inside one
    # of these phrases isn't a use of the term.
    other_things: dict[str, tuple[str, ...]] = field(default_factory=dict)
    # Glossary term -> pages (parts of the URL) that list it as a value shown on screen,
    # such as a policy table of Enabled and Disabled. The help text has to match the screen,
    # so the fix belongs in the product, not on these pages.
    screen_value_pages: dict[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class PatternSettings:
    """Settings for `audit patterns`."""

    # Two sentences are look-alikes when they share at least this share of their words.
    # Groups chain, so a looser setting pulls unrelated sentences into one group. The owner
    # chose 0.75 on 2026-11-27 (about 690 groups, against about 1,180 at 0.6).
    min_overlap: float = 0.75
    # Plan names from the glossary. Variants that name different plans disagree on a fact.
    plan_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class Target:
    name: str
    display_name: str
    sources: tuple[Source, ...]
    stage_rules: tuple[StageRule, ...]
    boilerplate: tuple[str, ...]
    typed_strings: Path | None
    delay_seconds: float
    root: Path
    analysis_exclude: tuple[str, ...] = ()
    terms: TermSettings = TermSettings()
    check: CheckSettings = CheckSettings()
    patterns: PatternSettings = PatternSettings()
    max_committed_excerpts: int = 500
    evidence_per_finding: int = 5
    # The skill's folder name (at the top of the repo) and its title.
    skill_name: str = "content-standards"
    skill_title: str = "Content standards"

    def stage_for(self, url: str) -> str:
        """First rule whose `match` text appears in the URL wins. No match means 'other'."""
        for rule in self.stage_rules:
            if rule.match in url:
                return rule.stage
        return "other"

    def analysed(self, url: str) -> bool:
        """False for pages that are collected but left out of analysis."""
        return not any(pattern in url for pattern in self.analysis_exclude)

    @property
    def cache_dir(self) -> Path:
        return self.root / "cache" / self.name

    @property
    def data_dir(self) -> Path:
        return self.root / "data" / self.name

    @property
    def local_snippets(self) -> Path:
        """The full snippets table, every excerpt filled in. Gitignored."""
        return self.cache_dir / "snippets.csv"

    @property
    def public_snippets(self) -> Path:
        """The committed snippets table. Excerpts only for evidence rows."""
        return self.data_dir / "snippets.csv"

    @property
    def glossary(self) -> Path:
        """Settled terms and words to avoid. Written by a person, never by code."""
        return self.data_dir / "glossary.csv"

    @property
    def pattern_table(self) -> Path:
        """Patterns a person has accepted. Written by a person, never by code."""
        return self.data_dir / "patterns.csv"

    @property
    def pattern_proposals(self) -> Path:
        """Drafted patterns for a person to accept or reject."""
        return self.data_dir / "pattern_proposals.csv"

    @property
    def full_text(self) -> Path:
        """Each snippet's full text by ID, for counting. Gitignored."""
        return self.cache_dir / "full_text.csv"


class ConfigError(ValueError):
    pass


def load(name: str, root: Path = Path(".")) -> Target:
    path = root / "targets" / f"{name}.yaml"
    if not path.exists():
        raise ConfigError(f"No target config at {path}")
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    sources = []
    for s in raw.get("sources", []):
        surface = s.get("surface")
        if surface not in SURFACES:
            raise ConfigError(f"Source {s.get('name')!r} has unknown surface {surface!r}")
        if not s.get("index") and not s.get("urls"):
            raise ConfigError(f"Source {s.get('name')!r} needs an index or a list of urls")
        sources.append(
            Source(
                name=s["name"],
                surface=surface,
                index=s.get("index"),
                urls=tuple(s.get("urls", [])),
                include=s.get("include"),
            )
        )

    rules = []
    for r in raw.get("stages", []):
        if r.get("stage") not in STAGES:
            raise ConfigError(f"Stage rule {r!r} has unknown stage")
        rules.append(StageRule(match=r["match"], stage=r["stage"]))

    typed = raw.get("typed_strings")
    delay = float(raw.get("delay_seconds", MIN_DELAY_SECONDS))

    raw_terms: dict[str, Any] = raw.get("terms", {}) or {}
    legacy = []
    for entry in raw_terms.get("legacy_names", []):
        if not entry.get("source"):
            raise ConfigError(f"Legacy name {entry.get('old')!r} needs a first-party source")
        legacy.append(
            LegacyName(old=entry["old"], current=entry["current"], source=entry["source"])
        )
    term_settings = TermSettings(
        seeds=tuple(raw_terms.get("seeds", [])),
        legacy_names=tuple(legacy),
        not_terms=tuple(raw_terms.get("not_terms", [])),
        third_party=tuple(raw_terms.get("third_party", [])),
        repeated_text=tuple(raw_terms.get("repeated_text", [])),
        max_proposed=int(raw_terms.get("max_proposed", 60)),
        consistent_min_pages=int(raw_terms.get("consistent_min_pages", 3)),
    )

    raw_check: dict[str, Any] = raw.get("check", {}) or {}
    history = tuple(raw_check.get("history_surfaces", []))
    for surface in history:
        if surface not in SURFACES:
            raise ConfigError(f"check.history_surfaces has unknown surface {surface!r}")
    check_settings = CheckSettings(
        history_surfaces=history,
        rename_pages=tuple(raw_check.get("rename_pages", [])),
        other_things={
            term: tuple(phrases)
            for term, phrases in (raw_check.get("other_things", {}) or {}).items()
        },
        screen_value_pages={
            term: tuple(pages)
            for term, pages in (raw_check.get("screen_value_pages", {}) or {}).items()
        },
    )

    raw_patterns: dict[str, Any] = raw.get("patterns", {}) or {}
    min_overlap = float(raw_patterns.get("min_overlap", PatternSettings.min_overlap))
    if not 0 < min_overlap <= 1:
        raise ConfigError(f"patterns.min_overlap must be above 0 and at most 1, not {min_overlap}")
    pattern_settings = PatternSettings(
        min_overlap=min_overlap,
        plan_names=tuple(raw_patterns.get("plan_names", [])),
    )

    return Target(
        name=raw.get("name", name),
        display_name=raw.get("display_name", name),
        sources=tuple(sources),
        stage_rules=tuple(rules),
        boilerplate=tuple(raw.get("boilerplate", [])),
        typed_strings=root / typed if typed else None,
        delay_seconds=max(delay, MIN_DELAY_SECONDS),
        root=root,
        analysis_exclude=tuple(raw.get("analysis_exclude", [])),
        terms=term_settings,
        check=check_settings,
        patterns=pattern_settings,
        max_committed_excerpts=int(raw.get("max_committed_excerpts", 500)),
        evidence_per_finding=int(raw.get("evidence_per_finding", 5)),
        skill_name=str((raw.get("skill") or {}).get("name", Target.skill_name)),
        skill_title=str((raw.get("skill") or {}).get("title", Target.skill_title)),
    )
