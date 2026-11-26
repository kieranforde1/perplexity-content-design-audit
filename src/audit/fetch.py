"""`audit fetch`: download a target's public pages into cache/, politely.

Polite means: read robots.txt first and obey it, wait between requests, and say who
we are in the user agent so a site owner can get in touch. Plain HTTP GET only.
No browser, no logging in, no app automation.
"""

from __future__ import annotations

import csv
import hashlib
import http.client
import os
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from audit import REPO_URL, __version__
from audit.config import Target

BOT_NAME = "perplexity-content-design-audit"
MAX_BYTES = 5_000_000
MANIFEST_COLUMNS = ("url", "file", "surface", "fetched_on", "content_type")


class FetchError(RuntimeError):
    pass


@dataclass(frozen=True)
class Response:
    status: int
    content_type: str
    text: str
    # Why a request didn't produce a page, when the status code alone doesn't say.
    note: str = ""


# (url, user_agent) -> Response. Tests pass a fake one, so they never touch the network.
Getter = Callable[[str, str], Response]


def http_get(url: str, user_agent: str) -> Response:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "text/markdown, text/plain, text/html;q=0.9",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as r:
            # A redirect to another site would skip that site's robots.txt, so it's refused.
            if urlsplit(r.geturl()).netloc != urlsplit(url).netloc:
                return Response(0, "", "", note=f"redirected to another site ({r.geturl()})")
            charset = r.headers.get_content_charset() or "utf-8"
            body = r.read(MAX_BYTES).decode(charset, errors="replace")
            return Response(r.status, r.headers.get_content_type(), body)
    except urllib.error.HTTPError as e:
        return Response(e.code, "", "")
    except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException) as e:
        raise FetchError(f"Could not reach {url}: {e}") from e


def contact_from_env() -> str:
    contact = os.environ.get("AUDIT_CONTACT", "").strip()
    if not contact:
        raise FetchError(
            "Set AUDIT_CONTACT to an email address before fetching, for example:\n"
            "  export AUDIT_CONTACT=you@example.com\n"
            "It goes in the user agent so site owners can reach you."
        )
    return contact


def user_agent(contact: str) -> str:
    return f"{BOT_NAME}/{__version__} (+{REPO_URL}; {contact})"


class Throttle:
    """Waits so requests to the same host are at least `delay` seconds apart."""

    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._clock = clock
        self._sleep = sleep
        self._last: dict[str, float] = {}

    def wait(self, url: str, delay: float) -> None:
        host = urlsplit(url).netloc
        last = self._last.get(host)
        if last is not None:
            remaining = delay - (self._clock() - last)
            if remaining > 0:
                self._sleep(remaining)
        self._last[host] = self._clock()


class Robots:
    """One robots.txt per host, fetched once and cached for the run."""

    def __init__(self, get: Getter, agent: str, throttle: Throttle, delay: float) -> None:
        self._get = get
        self._agent = agent
        self._throttle = throttle
        self._delay = delay
        self._parsers: dict[str, RobotFileParser] = {}

    def _parser(self, url: str) -> RobotFileParser:
        parts = urlsplit(url)
        host = parts.netloc
        if host not in self._parsers:
            robots_url = f"{parts.scheme}://{host}/robots.txt"
            self._throttle.wait(robots_url, self._delay)
            response = self._get(robots_url, self._agent)
            parser = RobotFileParser()
            if response.status == 200:
                parser.parse(response.text.splitlines())
            elif 400 <= response.status < 500:
                # No robots.txt means the site sets no rules.
                parser.parse([])
            else:
                # Server error: we can't tell what's allowed, so fetch nothing from this host.
                parser.parse(["User-agent: *", "Disallow: /"])
            self._parsers[host] = parser
        return self._parsers[host]

    def allowed(self, url: str) -> bool:
        return self._parser(url).can_fetch(BOT_NAME, url)

    def delay_for(self, url: str) -> float:
        crawl_delay = self._parser(url).crawl_delay(BOT_NAME)
        return max(self._delay, float(crawl_delay or 0))


LINK_URL = re.compile(r"\]\((https?://[^)\s]+)\)")


def urls_from_index(index_text: str, index_url: str) -> list[str]:
    """Page links in an llms.txt-style index, limited to the index's own host."""
    host = urlsplit(index_url).netloc
    seen: dict[str, None] = {}
    for url in LINK_URL.findall(index_text):
        if urlsplit(url).netloc == host:
            seen.setdefault(url, None)
    return list(seen)


def cache_file_for(url: str) -> str:
    return "pages/" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:16] + ".txt"


def read_manifest(cache_dir: Path) -> dict[str, dict[str, str]]:
    path = cache_dir / "manifest.csv"
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as f:
        return {row["url"]: row for row in csv.DictReader(f)}


def write_manifest(cache_dir: Path, rows: dict[str, dict[str, str]]) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    with (cache_dir / "manifest.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_COLUMNS)
        writer.writeheader()
        for url in sorted(rows):
            writer.writerow(rows[url])


@dataclass
class FetchReport:
    planned: list[tuple[str, str]] = field(default_factory=list)
    fetched: list[str] = field(default_factory=list)
    already_cached: list[str] = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)
    failed: list[tuple[str, int]] = field(default_factory=list)


def run(
    target: Target,
    contact: str,
    *,
    get: Getter = http_get,
    throttle: Throttle | None = None,
    dry_run: bool = False,
    limit: int | None = None,
    refresh: bool = False,
    today: Callable[[], date] = date.today,
    log: Callable[[str], None] = print,
) -> FetchReport:
    agent = user_agent(contact)
    throttle = throttle or Throttle()
    robots = Robots(get, agent, throttle, target.delay_seconds)
    report = FetchReport()

    # 1. Work out which pages to fetch, and which surface each belongs to.
    # Pages named directly in the config come first, so a page that also appears in an
    # index keeps the surface its own source gives it.
    named = [(url, source.surface) for source in target.sources for url in source.urls]
    indexed: list[tuple[str, str]] = []
    for source in target.sources:
        if not source.index:
            continue
        if not robots.allowed(source.index):
            report.blocked.append(source.index)
            log(f"robots.txt disallows the index {source.index}. Skipping {source.name}.")
            continue
        throttle.wait(source.index, robots.delay_for(source.index))
        response = get(source.index, agent)
        if response.status != 200:
            report.failed.append((source.index, response.status))
            log(f"Index {source.index} returned {response.status}. Skipping {source.name}.")
            continue
        indexed += [(url, source.surface) for url in urls_from_index(response.text, source.index)]

    planned_urls: set[str] = set()
    for url, surface in named + indexed:
        if url not in planned_urls:
            planned_urls.add(url)
            report.planned.append((url, surface))

    if limit is not None:
        report.planned = report.planned[:limit]

    if dry_run:
        log(f"Dry run: would fetch up to {len(report.planned)} pages as {agent!r}")
        for url, surface in report.planned:
            log(f"  [{surface}] {url}")
        return report

    # 2. Fetch each page we don't already have, and record it in the manifest.
    manifest = read_manifest(target.cache_dir)
    for url, surface in report.planned:
        if url in manifest and not refresh:
            report.already_cached.append(url)
            # A config change can move a page to another surface without fetching it again.
            if manifest[url]["surface"] != surface:
                manifest[url]["surface"] = surface
                write_manifest(target.cache_dir, manifest)
            continue
        if not robots.allowed(url):
            report.blocked.append(url)
            log(f"blocked by robots.txt: {url}")
            continue
        throttle.wait(url, robots.delay_for(url))
        try:
            response = get(url, agent)
        except FetchError as e:
            # One dropped connection shouldn't end the whole crawl. It's retried next run.
            report.failed.append((url, 0))
            log(str(e))
            continue
        if response.status != 200:
            report.failed.append((url, response.status))
            log(f"{response.note or response.status}: {url}")
            continue
        file = cache_file_for(url)
        path = target.cache_dir / file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(response.text, encoding="utf-8")
        manifest[url] = {
            "url": url,
            "file": file,
            "surface": surface,
            "fetched_on": today().isoformat(),
            "content_type": response.content_type,
        }
        write_manifest(target.cache_dir, manifest)
        report.fetched.append(url)
        log(f"fetched [{surface}] {url}")

    log(
        f"Done. {len(report.fetched)} fetched, {len(report.already_cached)} already cached, "
        f"{len(report.blocked)} blocked by robots.txt, {len(report.failed)} failed."
    )
    return report
