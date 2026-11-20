"""S2 search contracts, saved responses only; no network and no database."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from app.services import tenant_settings as ts
from app.services.listing_capture.site_fetch import STOP_PAUSED, FetchPolicy
from app.services.listing_capture.site_pause import MemorySitePauseStore, pause_site
from app.services.listing_capture.web_discovery import candidates as cand
from app.services.listing_capture.web_discovery import preview, search
from app.services.listing_capture.web_discovery.cache import (
    SEARCH_TTL_SECONDS,
    HttpCache,
    RobotsCache,
    SearchCache,
)
from app.services.listing_capture.web_discovery.polite import SEARCH_SPACING_SECONDS, PoliteGetter
from app.services.listing_capture.web_discovery.search_parsers import (
    parse_ddg_html,
    parse_ddg_lite,
    parse_searxng,
    unwrap_result_href,
)
from app.services.listing_capture.web_discovery.settings import load_discovery_settings
from tests.web_discovery_support import (
    PUBLIC_IP,
    FakeWeb,
    fixture_text,
    make_settings,
    settings_values,
)

QUERY = '"ABC-123" Testland'
SEARXNG_URL = "https://searx.example.test/instance"
ALPHA = "alpha-shop.example.test"
GAMMA = "gamma-store.example.test"


class Clock:
    def __init__(self) -> None:
        self.elapsed = 0.0
        self.start = datetime.now(UTC)
        self.waits: list[float] = []

    def __call__(self) -> float:
        return self.elapsed

    def sleep(self, seconds: float) -> None:
        self.waits.append(seconds)
        self.elapsed += seconds

    def now(self) -> datetime:
        return self.start + timedelta(seconds=self.elapsed)


class RecordingStore(MemorySitePauseStore):
    def __init__(self) -> None:
        super().__init__()
        self.ttls: dict[str, int] = {}

    def set(self, key, record, *, ttl_seconds) -> None:
        self.ttls[key] = ttl_seconds
        super().set(key, record, ttl_seconds=ttl_seconds)


def _url(provider: str, query: str = QUERY, base: str = SEARXNG_URL) -> str:
    url = search.request_url(provider, query, base)
    assert url is not None
    return url


def _getter(pages=None, *, store=None, clock=None):
    store = store if store is not None else RecordingStore()
    clock = clock if clock is not None else Clock()
    web = FakeWeb(pages)
    getter = PoliteGetter(
        FetchPolicy(store=store, clock=clock, sleep=clock.sleep, now=clock.now),
        HttpCache(store),
        RobotsCache(store),
        raw_get=web,
        resolve=lambda _host: [PUBLIC_IP],
    )
    return getter, web, store, clock


def _run(getter, store, providers=("ddg_html",), *, query=QUERY, base=SEARXNG_URL):
    return search.web_search(
        query,
        providers=providers,
        getter=getter,
        cache=SearchCache(store),
        searxng_url=base,
    )


def test_ddg_html_fixture_unwraps_both_redirect_forms_and_skips_ads() -> None:
    parsed = parse_ddg_html(fixture_text("ddg_html_results.html"))
    assert parsed.status == "ok"
    assert [hit.url for hit in parsed.hits] == [
        "https://www.alpha-shop.example.test/products/abc-123?ref=search&v=2",
        "http://Beta.Example.test/deals",
        "https://gamma-store.example.test/p/abc-123",
        "https://duckduckgo.com/duckduckgo-help-pages/",
    ]
    assert parsed.hits[0].title == "Alpha Shop — ABC-123 Widget"
    assert parsed.hits[0].snippet == ("The ABC-123 Widget in stock at Alpha Shop, Testland.")
    results = search.build_results(parsed.hits)
    assert [result.host for result in results] == [ALPHA, "beta.example.test", GAMMA]
    assert [result.rank for result in results] == [1, 2, 3]


def test_ddg_lite_fixture_keeps_snippets_paired_when_a_result_has_none() -> None:
    parsed = parse_ddg_lite(fixture_text("ddg_lite_results.html"))
    assert parsed.status == "ok"
    assert [hit.url for hit in parsed.hits] == [
        "https://www.alpha-shop.example.test/products/abc-123",
        "https://delta-mart.example.test/",
        "https://epsilon.example.test/abc",
    ]
    assert [hit.title for hit in parsed.hits] == ["Alpha Shop ABC-123", "Delta Mart", "Epsilon"]
    assert [hit.snippet for hit in parsed.hits] == [
        "The ABC-123 Widget in stock at Alpha Shop.",
        "",
        "Epsilon sells widgets.",
    ]


@pytest.mark.parametrize("fixture", ["searxng_results.json", "searxng_results.html"])
def test_searxng_fixtures_parse_json_or_html_and_filter_the_instance(fixture) -> None:
    parsed = parse_searxng(fixture_text(fixture))
    assert parsed.status == "ok"
    results = search.build_results(
        parsed.hits, extra_engine_hosts=frozenset({"searx.example.test"})
    )
    assert [result.host for result in results] == [ALPHA, GAMMA]
    assert [result.rank for result in results] == [1, 2]
    assert results[0].title == "Alpha Shop ABC-123"
    assert results[0].snippet == "The ABC-123 Widget in stock at Alpha Shop."


@pytest.mark.parametrize(
    "href",
    [
        None,
        "",
        "javascript:alert(1)",
        "ftp://files.example.test/item",
        "https://[broken",
        "https://shop.example.test:broken/item",
        "/l/?rut=no-target",
        "//duckduckgo.com/l/?uddg=javascript%3Aalert(1)&rut=x",
        "https://duckduckgo.com/y.js?ad_domain=ads.example.test",
    ],
)
def test_unusable_result_links_do_not_raise(href) -> None:
    assert unwrap_result_href(href) is None


@pytest.mark.parametrize("parser", [parse_ddg_html, parse_ddg_lite, parse_searxng])
@pytest.mark.parametrize(
    ("fixture", "status", "reason"),
    [
        ("ddg_html_anomaly.html", 200, "anomaly_page"),
        ("ddg_html_202_empty.html", 202, "http_202"),
        ("ddg_html_no_results.html", 202, "http_202"),
    ],
)
def test_challenges_and_202_take_precedence_over_empty_results(parser, fixture, status, reason):
    parsed = parser(fixture_text(fixture), status)
    assert (parsed.status, parsed.reason, parsed.hits) == ("blocked", reason, [])


@pytest.mark.parametrize("parser", [parse_ddg_html, parse_ddg_lite, parse_searxng])
def test_explicit_no_results_is_empty_but_a_blank_200_is_unrecognised(parser) -> None:
    empty = parser(fixture_text("ddg_html_no_results.html"))
    assert (empty.status, empty.reason, empty.hits) == ("empty", "no_results", [])
    unknown = parser(fixture_text("ddg_html_202_empty.html"))
    assert unknown.status == "unrecognised"


def test_searxng_empty_json_is_a_successful_empty_answer() -> None:
    parsed = parse_searxng(fixture_text("searxng_no_results.json"))
    assert (parsed.status, parsed.reason, parsed.hits) == ("empty", "no_results", [])


def test_result_limit_and_ranks_apply_after_engine_filtering() -> None:
    parsed = parse_ddg_html(fixture_text("ddg_html_results.html"))
    organic = parsed.hits[0]
    hits = [parsed.hits[-1]] + [
        replace(organic, url=f"{organic.url}#result-{index}") for index in range(12)
    ]
    results = search.build_results(hits)
    assert len(results) == 10
    assert [result.rank for result in results] == list(range(1, 11))
    assert results[-1].url.endswith("#result-9")


@pytest.mark.parametrize(
    ("provider", "fixture", "hosts"),
    [
        ("ddg_html", "ddg_html_results.html", [ALPHA, "beta.example.test", GAMMA]),
        (
            "ddg_lite",
            "ddg_lite_results.html",
            [ALPHA, "delta-mart.example.test", "epsilon.example.test"],
        ),
        ("searxng", "searxng_results.json", [ALPHA, GAMMA]),
        ("searxng", "searxng_results.html", [ALPHA, GAMMA]),
    ],
)
def test_every_provider_fetches_via_polite_getter_with_search_spacing(provider, fixture, hosts):
    url = _url(provider)
    origin = urlsplit(url)
    robots_url = f"{origin.scheme}://{origin.netloc}/robots.txt"
    getter, web, store, clock = _getter(
        {
            url: fixture_text(fixture),
            robots_url: fixture_text("robots_crawl_delay.txt"),
        }
    )
    outcome = _run(getter, store, (provider,))
    assert (outcome.status, outcome.provider) == ("ok", provider)
    assert [result.host for result in outcome.results] == hosts
    assert web.calls == [robots_url, url]
    assert clock.waits == [SEARCH_SPACING_SECONDS]
    assert getter.gate(f"search:{origin.hostname}").spacing_seconds == SEARCH_SPACING_SECONDS


def test_fallback_uses_tenant_order_and_continues_after_blocks() -> None:
    providers = ("ddg_html", "ddg_lite", "searxng")
    getter, web, store, _clock = _getter(
        {
            _url("ddg_html"): (202, fixture_text("ddg_html_202_empty.html")),
            _url("ddg_lite"): fixture_text("ddg_html_anomaly.html"),
            _url("searxng"): fixture_text("searxng_results.json"),
        }
    )
    outcome = _run(getter, store, providers)
    assert (outcome.status, outcome.provider) == ("ok", "searxng")
    assert [attempt["provider"] for attempt in outcome.attempts] == list(providers)
    assert [attempt["status"] for attempt in outcome.attempts] == ["blocked", "blocked", "ok"]
    assert web.page_calls() == [_url(provider) for provider in providers]
    assert store.get("search:html.duckduckgo.com")["hours"] == 1
    assert store.get("search:lite.duckduckgo.com")["hours"] == 1


@pytest.mark.parametrize(
    ("provider", "fixture", "status"),
    [
        ("ddg_html", "ddg_html_anomaly.html", 200),
        ("ddg_lite", "ddg_html_anomaly.html", 200),
        ("ddg_html", "ddg_html_202_empty.html", 202),
        ("ddg_lite", "ddg_html_202_empty.html", 202),
        ("searxng", "ddg_html_anomaly.html", 200),
    ],
)
def test_a_block_pauses_the_host_is_not_cached_and_is_not_retried(provider, fixture, status):
    url = _url(provider)
    key = f"search:{urlsplit(url).hostname}"
    getter, web, store, clock = _getter({url: (status, fixture_text(fixture))})
    outcome = _run(getter, store, (provider,))
    assert outcome.status == "unavailable" and outcome.results == []
    assert outcome.attempts[0]["status"] == "blocked"
    record = store.get(key)
    assert record["http_status"] == status and record["hours"] == 1
    assert datetime.fromisoformat(record["until"]) > clock.now()
    assert getter.gate(key).stopped == STOP_PAUSED
    assert SearchCache(store).get_outcome(provider, QUERY) is None
    assert getter.cache.get_response(url) is None

    calls = list(web.calls)
    again = _run(getter, store, (provider,))
    assert again.attempts[0]["status"] == "paused"
    assert web.calls == calls and store.get(key) == record

    next_getter, next_web, _, _ = _getter({url: fixture_text(fixture)}, store=store, clock=clock)
    assert _run(next_getter, store, (provider,)).attempts[0]["status"] == "paused"
    assert next_web.calls == []


@pytest.mark.parametrize("status", [200, 202])
def test_another_challenge_after_an_expired_pause_doubles_existing_backoff(status) -> None:
    key = "search:html.duckduckgo.com"
    getter, _web, store, clock = _getter(
        {
            _url("ddg_html"): (status, fixture_text("ddg_html_anomaly.html")),
        }
    )
    pause_site(store, key, http_status=202, now=clock.now() - timedelta(hours=2))
    assert _run(getter, store).attempts[0]["status"] == "blocked"
    assert store.get(key)["hours"] == 2


@pytest.mark.parametrize("status", [403, 429])
def test_http_refusals_use_the_getters_existing_pause_once_and_fall_back(status) -> None:
    getter, web, store, _clock = _getter(
        {
            _url("ddg_html"): (status, fixture_text("ddg_html_anomaly.html")),
            _url("ddg_lite"): fixture_text("ddg_lite_results.html"),
        }
    )
    outcome = _run(getter, store, ("ddg_html", "ddg_lite"))
    assert outcome.status == "ok" and outcome.provider == "ddg_lite"
    assert outcome.attempts[0] == {
        "provider": "ddg_html",
        "status": "blocked",
        "http_status": status,
        "reason": f"http_{status}",
    }
    assert store.get("search:html.duckduckgo.com")["hours"] == 1
    assert web.page_calls() == [_url("ddg_html"), _url("ddg_lite")]


def test_robots_disallowed_provider_is_skipped_without_fetching_search_page() -> None:
    getter, web, store, _clock = _getter(
        {
            "https://html.duckduckgo.com/robots.txt": fixture_text("robots_wildcards.txt"),
            _url("ddg_html"): fixture_text("ddg_html_results.html"),
            _url("ddg_lite"): fixture_text("ddg_lite_results.html"),
        }
    )
    outcome = _run(getter, store, ("ddg_html", "ddg_lite"))
    assert outcome.provider == "ddg_lite"
    assert outcome.attempts[0]["status"] == "robots"
    assert outcome.attempts[0]["reason"] == "robots_disallowed"
    assert web.page_calls() == [_url("ddg_lite")]


@pytest.mark.parametrize("status", [0, 503])
def test_unreachable_robots_is_skipped_fail_closed(status) -> None:
    getter, web, store, _clock = _getter(
        {
            "https://html.duckduckgo.com/robots.txt": (
                status,
                fixture_text("ddg_html_202_empty.html"),
            ),
            _url("ddg_lite"): fixture_text("ddg_lite_results.html"),
        }
    )
    outcome = _run(getter, store, ("ddg_html", "ddg_lite"))
    assert outcome.provider == "ddg_lite"
    assert outcome.attempts[0]["status"] == "robots"
    assert web.page_calls() == [_url("ddg_lite")]


@pytest.mark.parametrize(
    ("provider", "fixture", "expected"),
    [
        ("ddg_html", "ddg_html_results.html", "ok"),
        ("ddg_html", "ddg_html_no_results.html", "empty"),
        ("searxng", "searxng_results.json", "ok"),
        ("searxng", "searxng_no_results.json", "empty"),
    ],
)
def test_successful_result_cache_has_spec_key_and_ttl_and_sends_no_request_on_hit(
    provider, fixture, expected
):
    url = _url(provider)
    getter, _web, store, clock = _getter({url: fixture_text(fixture)})
    first = _run(getter, store, (provider,))
    assert first.status == expected
    digest = hashlib.sha256(QUERY.encode("utf-8")).hexdigest()
    key = f"wd:search:{provider}:{digest}"
    assert store.get(key)["status"] == expected
    assert store.ttls[key] == SEARCH_TTL_SECONDS == 7 * 24 * 3600

    next_getter, next_web, _, _ = _getter(store=store, clock=clock)
    second = _run(next_getter, store, (provider,))
    assert second.results == first.results and second.status == first.status
    assert second.attempts[0]["reason"] == "cache"
    assert next_web.calls == []


def test_a_successful_empty_answer_does_not_query_the_next_provider() -> None:
    getter, web, store, _clock = _getter(
        {
            _url("ddg_html"): fixture_text("ddg_html_no_results.html"),
            _url("ddg_lite"): fixture_text("ddg_lite_results.html"),
        }
    )
    outcome = _run(getter, store, ("ddg_html", "ddg_lite"))
    assert (outcome.status, outcome.provider, outcome.results) == ("empty", "ddg_html", [])
    assert web.page_calls() == [_url("ddg_html")]


def test_searxng_cache_is_not_reused_after_the_tenant_changes_its_instance_url() -> None:
    getter, web, store, _clock = _getter(
        {
            _url("searxng"): fixture_text("searxng_results.json"),
        }
    )
    assert _run(getter, store, ("searxng",)).status == "ok"
    other_base = "https://searx.example.test/other-instance"
    other_url = _url("searxng", base=other_base)
    web.pages[other_url] = fixture_text("searxng_results.html")
    outcome = _run(getter, store, ("searxng",), base=other_base)
    assert outcome.status == "ok" and outcome.attempts[0]["reason"] != "cache"
    assert web.page_calls() == [_url("searxng"), other_url]


def test_unrecognised_200_is_not_cached_as_empty_and_can_be_tried_in_a_later_run() -> None:
    url = _url("ddg_html")
    body = fixture_text("ddg_html_202_empty.html")
    getter, _web, store, clock = _getter({url: (200, body)})
    outcome = _run(getter, store)
    assert outcome.status == "unavailable"
    assert outcome.attempts[0]["reason"] == "unrecognised_markup"
    assert SearchCache(store).get_outcome("ddg_html", QUERY) is None
    assert getter.cache.get_response(url) is None
    next_getter, next_web, _, _ = _getter(
        {url: fixture_text("ddg_html_results.html")}, store=store, clock=clock
    )
    assert _run(next_getter, store).status == "ok"
    assert next_web.page_calls() == [url]


def test_fetch_exception_falls_back_and_reports_only_the_exception_class(monkeypatch) -> None:
    getter, web, store, _clock = _getter(
        {
            _url("ddg_lite"): fixture_text("ddg_lite_results.html"),
        }
    )

    def raw_get(url):
        if urlsplit(url).hostname == "html.duckduckgo.com":
            raise OSError("private diagnostic must not appear in Preview")
        return web(url)

    monkeypatch.setattr(getter, "_raw_get", raw_get)
    outcome = _run(getter, store, ("ddg_html", "ddg_lite"))
    assert outcome.provider == "ddg_lite"
    assert outcome.attempts[0]["reason"] == "OSError"
    assert "private diagnostic" not in str(outcome)


def test_cache_failure_does_not_lose_a_successful_search(monkeypatch) -> None:
    getter, _web, store, _clock = _getter(
        {
            _url("ddg_html"): fixture_text("ddg_html_results.html"),
        }
    )
    cache = SearchCache(store)

    def broken(*_args, **_kwargs):
        raise RuntimeError("cache failed")

    monkeypatch.setattr(cache, "get_outcome", broken)
    monkeypatch.setattr(cache, "put_outcome", broken)
    outcome = search.web_search(QUERY, providers=["ddg_html"], getter=getter, cache=cache)
    assert outcome.status == "ok" and outcome.results


def test_search_off_and_missing_instance_have_no_implicit_provider_or_network() -> None:
    getter, web, store, _clock = _getter()
    assert _run(getter, store, ()).status == "off"
    assert _run(getter, store, ("searxng",), base="").status == "unavailable"
    unknown = _run(getter, store, ("unknown",))
    assert unknown.attempts[0]["reason"] == "unknown_provider"
    assert web.calls == []


def test_s1_settings_factory_injects_search_into_candidates_with_four_query_limit(monkeypatch):
    values = settings_values(
        **{
            ts.KEY_DISCOVERY_SEARCH_PROVIDERS: ["searxng", "ddg_lite"],
            ts.KEY_DISCOVERY_SEARXNG_URL: SEARXNG_URL,
        }
    )
    monkeypatch.setattr(ts, "list_settings", lambda _session, _tenant: values)
    settings = load_discovery_settings(object(), "s2-test-tenant")
    ctx = cand.CustomerContext(
        customer_id=1,
        name="Alpha Gadgets",
        products=[cand.ProductInfo(id=i, sales_model_name=f"ABC-{i}") for i in range(1, 6)],
    )
    queries = [
        cand.product_query(product, settings.country_name)
        for product in cand.choose_products(ctx.products)
    ] + [cand.name_query(ctx.name, settings.country_name)]
    getter, web, store, _clock = _getter(
        {_url("searxng", query): fixture_text("searxng_results.json") for query in queries}
    )
    fn = preview.default_search_fn(settings, getter, SearchCache(store))
    assert fn is not None
    tracker = preview.SearchTracker(fn, settings.search_providers)
    found = cand.assemble_candidates(
        ctx,
        settings,
        search=tracker,
        resolve=lambda _host: [],
        engine_hosts=preview.engine_hosts_for(settings),
    )
    assert web.page_calls() == [_url("searxng", query) for query in queries]
    assert tracker.queries == 4
    assert tracker.summary()["provider_used"] == "searxng"
    assert {item.host for item in found} == {ALPHA, GAMMA}
    assert all(item.sources == {"product_search", "name_search"} for item in found)
    assert all([hit["product_id"] for hit in item.product_hits] == [1, 2, 3] for item in found)


def test_s1_settings_with_search_unset_keep_other_candidate_sources(monkeypatch) -> None:
    values = settings_values(**{ts.KEY_DISCOVERY_SEARCH_PROVIDERS: None})
    monkeypatch.setattr(ts, "list_settings", lambda _session, _tenant: values)
    settings = load_discovery_settings(object(), "s2-test-tenant")
    getter, web, store, _clock = _getter()
    fn = preview.default_search_fn(settings, getter, SearchCache(store))
    assert fn is None
    ctx = cand.CustomerContext(customer_id=1, name="Alpha Gadgets", seed_host=ALPHA)
    found = cand.assemble_candidates(ctx, settings, search=fn, resolve=lambda _host: [])
    assert [(item.host, item.sources) for item in found] == [(ALPHA, {"on_file"})]
    assert web.calls == []


def test_all_search_providers_fail_but_preview_finishes_with_search_unavailable(monkeypatch):
    settings = make_settings()
    ctx = cand.CustomerContext(customer_id=1, name="Alpha Gadgets", seed_host=ALPHA)
    getter, _web, store, _clock = _getter(
        {
            _url("ddg_html", cand.name_query(ctx.name, settings.country_name)): (
                202,
                fixture_text("ddg_html_202_empty.html"),
            ),
            _url("ddg_lite", cand.name_query(ctx.name, settings.country_name)): (
                200,
                fixture_text("ddg_html_anomaly.html"),
            ),
            f"https://{ALPHA}/": fixture_text("home_org_jsonld.html"),
        }
    )
    customer = SimpleNamespace(id=ctx.customer_id, name=ctx.name, tenant_id="s2-test-tenant")
    monkeypatch.setattr(preview, "load_discovery_settings", lambda *_args: settings)
    monkeypatch.setattr(preview, "_load_customers", lambda *_args: [customer])
    monkeypatch.setattr(cand, "read_context", lambda *_args: ctx)
    statements: list[str] = []

    class ReadOnlySession:
        def execute(self, statement):
            statements.append(str(statement))
            assert str(statement) == "SET TRANSACTION READ ONLY"

    plan = preview.run_preview(
        ReadOnlySession(),
        tenant_id=customer.tenant_id,
        preview_id="s2-test-preview",
        request={"scope": "customer", "customer_id": customer.id},
        getter=getter,
        resolve=lambda _host: [],
        plan_store=preview.MemoryPlanStore(),
        search_factory=lambda loaded: preview.default_search_fn(loaded, getter, SearchCache(store)),
    )
    assert statements == ["SET TRANSACTION READ ONLY"]
    assert plan["status"] == "done"
    assert plan["result"]["search"]["status"] == "unavailable"
    assert [attempt["status"] for attempt in plan["result"]["search"]["attempts"]] == [
        "blocked",
        "blocked",
    ]
    assert plan["result"]["customers"][0]["candidates"][0]["domain"] == ALPHA
    assert plan["progress"] == {"done": 1, "total": 1}
