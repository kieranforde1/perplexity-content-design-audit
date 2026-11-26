from pathlib import Path

import pytest

from audit import REPO_URL, config, fetch
from audit.fetch import Response

ROBOTS = "User-agent: *\nDisallow: /private/\n"
INDEX = (
    "# Example\n"
    "- [A](https://docs.example.com/a.md): first\n"
    "- [B](https://docs.example.com/private/b.md): blocked\n"
    "- [Elsewhere](https://other.example.org/c.md): another host\n"
    "- [A again](https://docs.example.com/a.md): duplicate\n"
)


class FakeWeb:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str]] = []

    def __call__(self, url: str, agent: str) -> Response:
        self.requests.append((url, agent))
        pages = {
            "https://docs.example.com/robots.txt": ROBOTS,
            "https://docs.example.com/llms.txt": INDEX,
            "https://docs.example.com/a.md": "# A\n\nPage A says hello to everyone.",
            "https://docs.example.com/changelog.md": "# Changelog\n\nNew things shipped today.",
        }
        if url in pages:
            return Response(200, "text/markdown", pages[url])
        return Response(404, "", "")


def target(tmp_path: Path) -> config.Target:
    (tmp_path / "targets").mkdir()
    (tmp_path / "targets" / "example.yaml").write_text(
        "name: example\n"
        "delay_seconds: 0.2\n"
        "sources:\n"
        "  - name: docs\n"
        "    surface: docs\n"
        "    index: https://docs.example.com/llms.txt\n"
        "  - name: changelog\n"
        "    surface: changelog\n"
        "    urls: [https://docs.example.com/changelog.md]\n"
    )
    return config.load("example", tmp_path)


class NoWait(fetch.Throttle):
    def __init__(self) -> None:
        self.waits: list[tuple[str, float]] = []
        super().__init__(clock=lambda: 0.0, sleep=lambda _: None)

    def wait(self, url: str, delay: float) -> None:
        self.waits.append((url, delay))


def quiet(_: str) -> None:
    pass


def test_fetch_obeys_robots_and_stays_on_host(tmp_path: Path) -> None:
    web = FakeWeb()
    report = fetch.run(target(tmp_path), "me@example.com", get=web, throttle=NoWait(), log=quiet)
    assert report.planned == [
        ("https://docs.example.com/changelog.md", "changelog"),
        ("https://docs.example.com/a.md", "docs"),
        ("https://docs.example.com/private/b.md", "docs"),
    ]
    assert report.blocked == ["https://docs.example.com/private/b.md"]
    assert "https://docs.example.com/private/b.md" not in [u for u, _ in web.requests]
    assert not any("other.example.org" in u for u, _ in web.requests)


def test_fetch_sends_contact_and_waits_before_every_request(tmp_path: Path) -> None:
    web = FakeWeb()
    throttle = NoWait()
    fetch.run(target(tmp_path), "me@example.com", get=web, throttle=throttle, log=quiet)
    assert all("me@example.com" in agent for _, agent in web.requests)
    assert all(REPO_URL in agent for _, agent in web.requests)
    assert len(throttle.waits) == len(web.requests)
    # The config asks for 0.2 seconds, but the floor is 1 second.
    assert {delay for _, delay in throttle.waits} == {config.MIN_DELAY_SECONDS}


def test_fetch_caches_and_skips_on_second_run(tmp_path: Path) -> None:
    t = target(tmp_path)
    fetch.run(t, "me@example.com", get=FakeWeb(), throttle=NoWait(), log=quiet)
    manifest = fetch.read_manifest(t.cache_dir)
    assert set(manifest) == {
        "https://docs.example.com/a.md",
        "https://docs.example.com/changelog.md",
    }
    assert manifest["https://docs.example.com/changelog.md"]["surface"] == "changelog"
    page = t.cache_dir / manifest["https://docs.example.com/a.md"]["file"]
    assert "Page A" in page.read_text()

    second = fetch.run(t, "me@example.com", get=FakeWeb(), throttle=NoWait(), log=quiet)
    assert second.fetched == []
    assert len(second.already_cached) == 2


def test_named_page_keeps_its_surface_when_an_index_lists_it_too(tmp_path: Path) -> None:
    t = target(tmp_path)
    web = FakeWeb()
    original = web.__call__

    def index_lists_changelog(url: str, agent: str) -> Response:
        if url.endswith("llms.txt"):
            return Response(200, "text/plain", INDEX + "- [C](https://docs.example.com/changelog.md)\n")
        return original(url, agent)

    report = fetch.run(t, "me@example.com", get=index_lists_changelog, throttle=NoWait(), log=quiet)
    assert ("https://docs.example.com/changelog.md", "changelog") in report.planned
    assert ("https://docs.example.com/changelog.md", "docs") not in report.planned


def test_cached_page_takes_new_surface_without_refetching(tmp_path: Path) -> None:
    t = target(tmp_path)
    fetch.run(t, "me@example.com", get=FakeWeb(), throttle=NoWait(), log=quiet)
    manifest = fetch.read_manifest(t.cache_dir)
    manifest["https://docs.example.com/changelog.md"]["surface"] = "docs"
    fetch.write_manifest(t.cache_dir, manifest)

    web = FakeWeb()
    fetch.run(t, "me@example.com", get=web, throttle=NoWait(), log=quiet)
    surface = fetch.read_manifest(t.cache_dir)["https://docs.example.com/changelog.md"]["surface"]
    assert surface == "changelog"
    assert "https://docs.example.com/changelog.md" not in [u for u, _ in web.requests]


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    t = target(tmp_path)
    web = FakeWeb()
    report = fetch.run(t, "me@example.com", get=web, throttle=NoWait(), dry_run=True, log=quiet)
    assert len(report.planned) == 3
    assert not t.cache_dir.exists()
    assert {u for u, _ in web.requests} == {
        "https://docs.example.com/robots.txt",
        "https://docs.example.com/llms.txt",
    }


def test_robots_server_error_blocks_everything(tmp_path: Path) -> None:
    def broken(url: str, agent: str) -> Response:
        return Response(503, "", "")

    report = fetch.run(target(tmp_path), "me@example.com", get=broken, throttle=NoWait(), log=quiet)
    assert report.fetched == []
    assert "https://docs.example.com/changelog.md" in report.blocked


def test_a_dropped_connection_skips_the_page_not_the_crawl(tmp_path: Path) -> None:
    web = FakeWeb()

    def flaky(url: str, agent: str) -> Response:
        if url.endswith("a.md"):
            raise fetch.FetchError("Could not reach a.md: connection reset")
        return web(url, agent)

    report = fetch.run(target(tmp_path), "me@example.com", get=flaky, throttle=NoWait(), log=quiet)
    assert ("https://docs.example.com/a.md", 0) in report.failed
    assert "https://docs.example.com/changelog.md" in report.fetched


def test_robots_crawl_delay_raises_the_wait(tmp_path: Path) -> None:
    web = FakeWeb()

    def slow_robots(url: str, agent: str) -> Response:
        if url.endswith("robots.txt"):
            return Response(200, "text/plain", "User-agent: *\nCrawl-delay: 5\n")
        return web(url, agent)

    throttle = NoWait()
    fetch.run(target(tmp_path), "me@example.com", get=slow_robots, throttle=throttle, log=quiet)
    page_waits = [d for u, d in throttle.waits if not u.endswith("robots.txt")]
    assert page_waits and set(page_waits) == {5.0}


def test_contact_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUDIT_CONTACT", raising=False)
    with pytest.raises(fetch.FetchError, match="AUDIT_CONTACT"):
        fetch.contact_from_env()


def test_throttle_spaces_requests_per_host() -> None:
    now = [0.0]
    slept: list[float] = []

    def sleep(seconds: float) -> None:
        slept.append(seconds)
        now[0] += seconds

    throttle = fetch.Throttle(clock=lambda: now[0], sleep=sleep)
    throttle.wait("https://a.example.com/1", 1.5)
    throttle.wait("https://a.example.com/2", 1.5)
    throttle.wait("https://b.example.com/1", 1.5)
    assert slept == [1.5]
