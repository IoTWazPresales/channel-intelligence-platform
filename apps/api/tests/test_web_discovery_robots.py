"""robots.txt matching (RFC 9309) and the polite getter's use of it. No network, no database."""

from __future__ import annotations

import pytest

from app.services.listing_capture.web_discovery import robots
from app.services.listing_capture.web_discovery.polite import (
    REFUSED_BAD_URL,
    REFUSED_PRIVATE,
    REFUSED_REDIRECTS,
    REFUSED_ROBOTS,
    is_public_address,
)
from tests.web_discovery_support import FakeWeb, fixture_text, make_getter

HOST = "https://wild.example.test"


@pytest.fixture()
def wild() -> robots.RobotsRules:
    return robots.parse_robots(fixture_text("robots_wildcards.txt"))


@pytest.mark.parametrize(
    ("path", "allowed"),
    [
        ("/", True),  # no rule matches
        ("/about", True),
        ("/private/x", False),  # plain prefix
        ("/?x=1", True),  # Disallow /*? and Allow /?* tie at 3: Allow wins
        ("/page?x=1", False),  # only Disallow /*? matches
        ("/files/a.pdf", False),  # wildcard and $ anchor
        ("/files/a.pdfx", True),  # $ means the path must end there
        ("/files/public/a.pdf", True),  # longer Allow beats the Disallow
        ("/shop/closed", False),
        ("/shop/open/item", True),  # Allow /shop/open/ is longer than Disallow /shop/
    ],
)
def test_wildcards_longest_match_and_allow_wins_a_tie(wild, path, allowed) -> None:
    assert wild.allowed(path) is allowed
    assert wild.allowed(HOST + path) is allowed


def test_only_the_star_group_applies(wild) -> None:
    # The group for another crawler says "Disallow: /"; it must not apply.
    assert wild.allowed("/")
    assert wild.sitemaps == ["https://wild.example.test/sitemap_a.xml"]


def test_an_empty_disallow_allows_everything_and_sitemaps_are_kept() -> None:
    rules = robots.parse_robots(fixture_text("robots_sitemaps.txt"))
    assert rules.allowed("/anything?x=1")
    assert rules.sitemaps == [
        "https://maps.example.test/sitemap-products.xml",
        "https://maps.example.test/sitemap-pages.xml",
    ]


def test_crawl_delay_is_read_and_capped() -> None:
    rules = robots.parse_robots(fixture_text("robots_crawl_delay.txt"))
    assert rules.crawl_delay == 7 and rules.spacing_floor() == 7
    assert not rules.allowed("/admin/users") and rules.allowed("/shop")
    capped = robots.parse_robots("User-agent: *\nCrawl-delay: 500\n")
    assert capped.spacing_floor() == robots.MAX_CRAWL_DELAY_SECONDS
    assert robots.parse_robots("User-agent: *\nDisallow:\n").spacing_floor() == 0


def test_comments_and_case_do_not_matter() -> None:
    rules = robots.parse_robots("USER-AGENT: *   # everyone\nDISALLOW: /x # no\n")
    assert not rules.allowed("/x/y") and rules.allowed("/y")


@pytest.mark.parametrize(
    ("status", "allowed_everything", "allowed_nothing"),
    [(200, False, False), (404, True, False), (403, True, False), (410, True, False),
     (500, False, True), (503, False, True), (0, False, True)],
)
def test_robots_fetch_results(status, allowed_everything, allowed_nothing) -> None:
    rules = robots.rules_from_response(status, "User-agent: *\nDisallow: /x\n")
    if allowed_everything:
        assert rules.allowed("/x") and rules.mode == robots.MODE_ALLOW_ALL
    elif allowed_nothing:
        assert not rules.allowed("/") and rules.mode == robots.MODE_DISALLOW_ALL
    else:
        assert not rules.allowed("/x") and rules.allowed("/y")


def test_rules_round_trip_through_the_cache_form(wild) -> None:
    again = robots.RobotsRules.from_dict(wild.to_dict())
    assert again.allowed("/shop/open/x") and not again.allowed("/shop/x") and again.sitemaps == wild.sitemaps


# ---------------------------------------------------------------- the polite getter


def test_a_disallowed_url_sends_no_request() -> None:
    web = FakeWeb({f"{HOST}/robots.txt": "User-agent: *\nDisallow: /private/\n", f"{HOST}/private/a": "secret"})
    getter = make_getter(web)
    out = getter.get(f"{HOST}/private/a", gate_key="host:wild.example.test")
    assert out.refused == REFUSED_ROBOTS and out.body == ""
    assert web.page_calls() == []  # only robots.txt was fetched
    assert getter.get(f"{HOST}/open", gate_key="host:wild.example.test").status == 404


def test_robots_404_allows_all_and_is_cached_per_host() -> None:
    web = FakeWeb({f"{HOST}/a": "page a", f"{HOST}/b": "page b"})
    getter = make_getter(web)
    assert getter.get(f"{HOST}/a", gate_key="host:w").body == "page a"
    assert getter.get(f"{HOST}/b", gate_key="host:w").body == "page b"
    assert web.calls.count(f"{HOST}/robots.txt") == 1
    # A second getter (a new run) reads the persisted rules and does not fetch robots again.
    web2 = FakeWeb({f"{HOST}/c": "page c"})
    getter2 = make_getter(web2)
    getter2.robots_cache = getter.robots_cache
    assert getter2.get(f"{HOST}/c", gate_key="host:w").body == "page c"
    assert web2.calls == [f"{HOST}/c"]


def test_robots_5xx_disallows_everything_for_the_run_and_is_not_persisted() -> None:
    web = FakeWeb({f"{HOST}/robots.txt": (503, "", None), f"{HOST}/a": "page a"})
    getter = make_getter(web)
    assert getter.get(f"{HOST}/a", gate_key="host:w").refused == REFUSED_ROBOTS
    assert getter.robots_cache.get_rules("wild.example.test") is None
    assert web.page_calls() == []


def test_crawl_delay_raises_the_gate_spacing_up_to_a_cap() -> None:
    web = FakeWeb({f"{HOST}/robots.txt": fixture_text("robots_crawl_delay.txt"), f"{HOST}/a": "x"})
    getter = make_getter(web)
    getter.get(f"{HOST}/a", gate_key="host:w", spacing=5.0)
    assert getter.gate("host:w").spacing_seconds == 7
    web2 = FakeWeb({f"{HOST}/robots.txt": "User-agent: *\nCrawl-delay: 500\n", f"{HOST}/a": "x"})
    getter2 = make_getter(web2)
    getter2.get(f"{HOST}/a", gate_key="host:w", spacing=5.0)
    assert getter2.gate("host:w").spacing_seconds == robots.MAX_CRAWL_DELAY_SECONDS


def test_spacing_is_never_lowered_by_robots() -> None:
    web = FakeWeb({f"{HOST}/robots.txt": "User-agent: *\nCrawl-delay: 2\n", f"{HOST}/a": "x"})
    getter = make_getter(web)
    getter.get(f"{HOST}/a", gate_key="host:w", spacing=10.0)
    assert getter.gate("host:w").spacing_seconds == 10.0


def test_a_403_pauses_the_key_and_nothing_more_is_sent() -> None:
    web = FakeWeb({f"{HOST}/a": (403, "denied", None), f"{HOST}/b": "page b"})
    getter = make_getter(web)
    first = getter.get(f"{HOST}/a", gate_key="host:w")
    assert first.status == 403 and first.refused == "site_paused" and first.body == ""
    sent = len(web.calls)
    second = getter.get(f"{HOST}/b", gate_key="host:w")
    assert second.refused == "site_paused" and len(web.calls) == sent
    assert getter.paused("host:w")


def test_a_pause_from_an_earlier_run_blocks_the_first_request() -> None:
    web = FakeWeb({f"{HOST}/a": "page"})
    getter = make_getter(web)
    from app.services.listing_capture import site_pause

    site_pause.pause_site(getter.policy.store, "host:w", http_status=429, now=getter.policy.now())
    out = getter.get(f"{HOST}/a", gate_key="host:w")
    assert out.refused == "site_paused" and web.page_calls() == []


def test_redirects_are_followed_and_each_hop_is_checked() -> None:
    web = FakeWeb(
        {
            f"{HOST}/old": (301, "", "/new"),
            f"{HOST}/new": "the page",
            f"{HOST}/robots.txt": "User-agent: *\nDisallow: /blocked\n",
            f"{HOST}/go": (302, "", "/blocked"),
        }
    )
    getter = make_getter(web)
    ok = getter.get(f"{HOST}/old", gate_key="host:w")
    assert ok.status == 200 and ok.body == "the page" and ok.final_url == f"{HOST}/new"
    denied = getter.get(f"{HOST}/go", gate_key="host:w")
    assert denied.refused == REFUSED_ROBOTS and f"{HOST}/blocked" not in web.calls


def test_a_redirect_to_another_host_uses_that_hosts_robots_and_gate() -> None:
    web = FakeWeb(
        {
            f"{HOST}/a": (301, "", "https://other.example.test/x"),
            "https://other.example.test/robots.txt": "User-agent: *\nDisallow: /x\n",
            "https://other.example.test/x": "other page",
        }
    )
    getter = make_getter(web)
    out = getter.get(f"{HOST}/a", gate_key="host:w")
    assert out.refused == REFUSED_ROBOTS and "https://other.example.test/x" not in web.calls
    assert "host:other.example.test" in getter._gates


def test_redirect_loops_stop() -> None:
    web = FakeWeb({f"{HOST}/a": (302, "", "/a")})
    out = make_getter(web).get(f"{HOST}/a", gate_key="host:w")
    assert out.refused == REFUSED_REDIRECTS


def test_200_responses_are_cached_and_a_hit_sends_nothing() -> None:
    web = FakeWeb({f"{HOST}/a": "page a"})
    getter = make_getter(web)
    getter.get(f"{HOST}/a", gate_key="host:w")
    before = len(web.calls)
    again = getter.get(f"{HOST}/a", gate_key="host:w")
    assert again.from_cache and again.body == "page a" and len(web.calls) == before


def test_non_200_and_large_bodies_are_not_cached() -> None:
    web = FakeWeb({f"{HOST}/missing": (404, "gone", None), f"{HOST}/big": "x" * 1_000_001})
    getter = make_getter(web)
    getter.get(f"{HOST}/missing", gate_key="host:w")
    getter.get(f"{HOST}/big", gate_key="host:w")
    assert getter.cache.get_response(f"{HOST}/missing") is None
    assert getter.cache.get_response(f"{HOST}/big") is None


def test_a_host_that_resolves_to_a_private_address_is_refused() -> None:
    web = FakeWeb({"https://inner.example.test/a": "internal"})
    getter = make_getter(web, resolve=lambda _h: ["10.0.0.5"])
    out = getter.get("https://inner.example.test/a", gate_key="host:inner.example.test")
    assert out.refused == REFUSED_PRIVATE and web.calls == []


def test_bad_urls_are_refused() -> None:
    getter = make_getter(FakeWeb())
    for url in ("ftp://wild.example.test/a", "https://wild.example.test:8443/a", "https:///a"):
        assert getter.get(url, gate_key="host:w").refused == REFUSED_BAD_URL


def test_address_classification() -> None:
    assert is_public_address("8.8.8.8")
    for private in ("10.1.2.3", "127.0.0.1", "192.168.0.1", "169.254.1.1", "::1", "not-an-ip"):
        assert not is_public_address(private)


def test_the_run_time_budget_stops_requests() -> None:
    web = FakeWeb({f"{HOST}/a": "page"})
    getter = make_getter(web, time_limit=0.0)
    out = getter.get(f"{HOST}/a", gate_key="host:w")
    assert out.refused == "time_limit" and web.calls == []
