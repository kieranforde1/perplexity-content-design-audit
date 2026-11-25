"""Load a target config (targets/<name>.yaml).

A target config is everything company-specific: where its public text lives, which
surface each source belongs to, and how URLs map to stages. The code stays the same
for every company.
"""

from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True)
class StageRule:
    match: str
    stage: str


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

    def stage_for(self, url: str) -> str:
        """First rule whose `match` text appears in the URL wins. No match means 'other'."""
        for rule in self.stage_rules:
            if rule.match in url:
                return rule.stage
        return "other"

    @property
    def cache_dir(self) -> Path:
        return self.root / "cache" / self.name

    @property
    def data_dir(self) -> Path:
        return self.root / "data" / self.name


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
            )
        )

    rules = []
    for r in raw.get("stages", []):
        if r.get("stage") not in STAGES:
            raise ConfigError(f"Stage rule {r!r} has unknown stage")
        rules.append(StageRule(match=r["match"], stage=r["stage"]))

    typed = raw.get("typed_strings")
    delay = float(raw.get("delay_seconds", MIN_DELAY_SECONDS))

    return Target(
        name=raw.get("name", name),
        display_name=raw.get("display_name", name),
        sources=tuple(sources),
        stage_rules=tuple(rules),
        boilerplate=tuple(raw.get("boilerplate", [])),
        typed_strings=root / typed if typed else None,
        delay_seconds=max(delay, MIN_DELAY_SECONDS),
        root=root,
    )
