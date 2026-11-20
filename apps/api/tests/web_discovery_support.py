"""Shared helpers for the ``test_web_discovery_*`` tests. Everything here is synthetic: invented
names, ``.test`` hosts, a made-up country. Nothing reaches the network."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.services import tenant_settings as ts
from app.services.listing_capture.site_fetch import FetchPolicy
from app.services.listing_capture.site_pause import MemorySitePauseStore
from app.services.listing_capture.web_discovery.cache import HttpCache, RobotsCache
from app.services.listing_capture.web_discovery.polite import Fetched, PoliteGetter
from app.services.listing_capture.web_discovery.settings import DiscoverySettings, settings_from_values

FIXTURES = Path(__file__).parent / "fixtures" / "web_discovery"

COUNTRY = {"code": "ZZ", "name": "Testland"}
ENDINGS = [".example.test", ".zz"]
PUBLIC_IP = "8.8.8.8"


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def settings_values(**over: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        ts.KEY_TENANT_COUNTRY: dict(COUNTRY),
        ts.KEY_TENANT_DOMAIN_ENDINGS: list(ENDINGS),
        ts.KEY_DISCOVERY_SEARCH_PROVIDERS: ["ddg_html", "ddg_lite"],
    }
    values.update(over)
    return {k: v for k, v in values.items() if v is not None}


def make_settings(**over: Any) -> DiscoverySettings:
    return settings_from_values(settings_values(**over))


class FakeWeb:
    """``raw_get`` for the polite getter: URL -> ``(status, body, location)``. Unknown URLs are 404."""

    def __init__(self, pages: dict[str, Any] | None = None) -> None:
        self.pages: dict[str, Any] = dict(pages or {})
        self.calls: list[str] = []

    def __call__(self, url: str) -> tuple[int, str, str | None]:
        self.calls.append(url)
        value = self.pages.get(url, (404, "", None))
        if isinstance(value, str):
            return 200, value, None
        status, body = value[0], value[1]
        location = value[2] if len(value) > 2 else None
        return status, body, location

    def page_calls(self) -> list[str]:
        return [u for u in self.calls if not u.endswith("/robots.txt")]


def make_getter(
    web: FakeWeb,
    *,
    resolve=None,
    time_limit: float = 600.0,
) -> PoliteGetter:
    policy = FetchPolicy(store=MemorySitePauseStore(), sleep=lambda _s: None, time_limit_seconds=time_limit)
    return PoliteGetter(
        policy,
        HttpCache(MemorySitePauseStore()),
        RobotsCache(MemorySitePauseStore()),
        raw_get=web,
        resolve=resolve or (lambda _host: [PUBLIC_IP]),
    )


@dataclass
class FakeResult:
    url: str
    host: str
    rank: int
    title: str = ""
    snippet: str = ""


@dataclass
class FakeOutcome:
    status: str = "ok"
    results: list[FakeResult] = field(default_factory=list)
    provider: str | None = "ddg_html"
    attempts: list[dict[str, Any]] = field(default_factory=list)


class FakeSearch:
    """A search function: query -> outcome. ``hosts_by_query`` maps a query substring to result hosts."""

    def __init__(self, hosts_by_query: dict[str, list[str]] | None = None, *, status: str = "ok") -> None:
        self.hosts_by_query = dict(hosts_by_query or {})
        self.status = status
        self.queries: list[str] = []

    def __call__(self, query: str) -> FakeOutcome:
        self.queries.append(query)
        hosts: list[str] = []
        for needle, found in self.hosts_by_query.items():
            if needle in query:
                hosts = found
                break
        results = [FakeResult(url=f"https://{h}/p", host=h, rank=i) for i, h in enumerate(hosts, start=1)]
        return FakeOutcome(status=self.status if results or self.status != "ok" else "empty", results=results)


class FakeGetter:
    """A getter for candidate tests: URL -> ``Fetched``. Records the gate keys it was given."""

    def __init__(self, answers: dict[str, Fetched] | None = None) -> None:
        self.answers = dict(answers or {})
        self.calls: list[tuple[str, str]] = []
        self.policy = None

    def get(self, url: str, *, gate_key: str, spacing: float | None = None) -> Fetched:
        self.calls.append((url, gate_key))
        return self.answers.get(url, Fetched(404, "", url))

    def gate_summary(self, _key: str) -> None:
        return None


def home_page(title: str = "Home", *, lang: str | None = None, country: str | None = None, org: str | None = None) -> str:
    ld = ""
    if org or country:
        address = f', "address": {{"addressCountry": "{country}"}}' if country else ""
        name = f', "name": "{org}"' if org else ""
        ld = f'<script type="application/ld+json">{{"@type": "Organization"{name}{address}}}</script>'
    html_tag = f'<html lang="{lang}">' if lang else "<html>"
    return f"<!doctype html>{html_tag}<head><title>{title}</title>{ld}</head><body>Home</body></html>"
