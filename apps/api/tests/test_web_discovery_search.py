"""Search contracts with mocked ddgs and saved SearXNG responses; no network or database."""

from __future__ import annotations

import hashlib
import sys
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from app.services import tenant_settings as ts
from app.services.listing_capture.site_fetch import STOP_PAUSED, STOP_TIME_LIMIT, FetchPolicy
from app.services.listing_capture.site_pause import MemorySitePauseStore, pause_site
from app.services.listing_capture.web_discovery import candidates as cand
from app.services.listing_capture.web_discovery import preview, search
from app.services.listing_capture.web_discovery.cache import (
    SEARCH_TTL_SECONDS,
    HttpCache,
    RobotsCache,
    SearchCache,
)
from app.services.listing_capture.web_discovery.polite import PoliteGetter
from app.services.listing_capture.web_discovery.search_parsers import (
    ParsedHit,
    parse_searxng,
    unwrap_result_href,
)
from app.services.listing_capture.web_discovery.settings import (
    load_discovery_settings,
    settings_from_values,
)
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
DDG_KEY = "search:html.duckduckgo.com"
DDG_ROBOTS = "https://html.duckduckgo.com/robots.txt"
OPTIONS = {
    "min_interval_seconds": 23.0,
    "max_results": 10,
    "timeout_seconds": 7,
}
_UNSET = object()


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


@pytest.fixture(autouse=True)
def ddgs_stub(monkeypatch):
    state = SimpleNamespace(
        constructors=[],
        calls=[],
        rows=[
            {
                "href": f"https://www.{ALPHA}/products/abc-123",
                "title": "Alpha Shop ABC-123",
                "body": "The ABC-123 Widget in stock at Alpha Shop.",
            },
            {
                "href": f"https://{GAMMA}/p/abc-123",
                "title": "Gamma Store",
                "body": "ABC-123",
            },
        ],
        error=None,
    )

    class FakeDDGS:
        def __init__(self, **kwargs):
            state.constructors.append(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def text(self, query, **kwargs):
            state.calls.append((query, kwargs))
            if state.error is not None:
                raise state.error
            return state.rows

    monkeypatch.setitem(sys.modules, "ddgs", SimpleNamespace(DDGS=FakeDDGS))
    return state


def _url(provider="searxng", query=QUERY, base=SEARXNG_URL):
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


def _run(
    getter,
    store,
    providers=("ddg_html",),
    *,
    query=QUERY,
    base=SEARXNG_URL,
    options=_UNSET,
):
    return search.web_search(
        query,
        providers=providers,
        getter=getter,
        cache=SearchCache(store),
        searxng_url=base,
        search_options=dict(OPTIONS) if options is _UNSET else options,
    )


def test_ddgs_uses_only_supported_options_and_one_guarded_call(ddgs_stub):
    getter, web, store, clock = _getter()
    options = {**OPTIONS, "region": "zz-en", "max_results": 1}
    outcome = _run(getter, store, options=options)

    assert (outcome.status, outcome.provider) == ("ok", "ddg_html")
    assert [(result.host, result.rank) for result in outcome.results] == [(ALPHA, 1)]
    assert outcome.results[0].snippet == "The ABC-123 Widget in stock at Alpha Shop."
    assert ddgs_stub.constructors == [{"timeout": OPTIONS["timeout_seconds"]}]
    assert ddgs_stub.calls == [
        (QUERY, {"backend": "duckduckgo", "max_results": 1, "region": "zz-en"})
    ]
    assert web.calls == [DDG_ROBOTS]
    assert web.page_calls() == []
    assert clock.waits == [OPTIONS["min_interval_seconds"]]
    # One robots request and one library invocation, not an HTTP fetch followed by ddgs.
    assert getter.gate(DDG_KEY).requests == 2


def test_region_is_optional_and_no_country_is_inserted_in_ddgs_options(ddgs_stub):
    getter, _web, store, _clock = _getter()
    assert _run(getter, store).status == "ok"
    assert ddgs_stub.calls[0][1] == {
        "backend": "duckduckgo",
        "max_results": OPTIONS["max_results"],
    }


def test_repeated_queries_share_spacing_and_robots_delay_can_raise_it(ddgs_stub):
    getter, web, store, clock = _getter(
        {DDG_ROBOTS: "User-agent: *\nAllow: /\nCrawl-delay: 37\n"}
    )
    assert _run(getter, store).status == "ok"
    assert _run(getter, store, query="another query").status == "ok"
    assert len(ddgs_stub.calls) == 2
    assert web.calls == [DDG_ROBOTS]
    assert clock.waits == [37.0, 37.0]
    assert getter.gate(DDG_KEY).spacing_seconds == 37.0


def test_lite_is_explicitly_unsupported_and_never_repeats_the_html_backend(ddgs_stub):
    ddgs_stub.error = RuntimeError("private detail")
    getter, web, store, _clock = _getter(
        {_url(): fixture_text("searxng_results.json")}
    )
    outcome = _run(getter, store, ("ddg_html", "ddg_lite", "searxng"))
    assert (outcome.status, outcome.provider) == ("ok", "searxng")
    assert [attempt["provider"] for attempt in outcome.attempts] == [
        "ddg_html",
        "ddg_lite",
        "searxng",
    ]
    assert outcome.attempts[1]["reason"] == "ddgs_lite_unsupported"
    assert len(ddgs_stub.calls) == 1
    assert web.page_calls() == [_url()]


@pytest.mark.parametrize("error_type", [RuntimeError, OSError, TimeoutError, ValueError])
def test_any_ddgs_error_is_unavailable_paused_uncached_and_sanitized(ddgs_stub, error_type):
    ddgs_stub.error = error_type("secret diagnostic")
    getter, web, store, clock = _getter()
    outcome = _run(getter, store)
    assert outcome.status == "unavailable" and outcome.results == []
    assert outcome.attempts[0]["reason"] == f"ddgs_{error_type.__name__}"
    assert "secret diagnostic" not in str(outcome)
    record = store.get(DDG_KEY)
    assert record["hours"] == 1
    assert record["http_status"] == 0
    assert datetime.fromisoformat(record["until"]) > clock.now()
    assert getter.gate(DDG_KEY).stopped == STOP_PAUSED
    assert SearchCache(store).get_outcome("ddg_html", QUERY) is None

    again = _run(getter, store)
    assert again.attempts[0]["status"] == "paused"
    assert len(ddgs_stub.calls) == 1
    assert web.calls == [DDG_ROBOTS]
    assert store.get(DDG_KEY) == record

    next_getter, next_web, _, _ = _getter(store=store, clock=clock)
    assert _run(next_getter, store).attempts[0]["status"] == "paused"
    assert next_web.calls == []


@pytest.mark.parametrize("status", [202, 403, 429])
def test_exposed_http_errors_pause_once_and_fall_back(ddgs_stub, status):
    class StatusError(RuntimeError):
        status_code = status

    ddgs_stub.error = StatusError("secret")
    getter, _web, store, _clock = _getter(
        {_url(): fixture_text("searxng_results.json")}
    )
    outcome = _run(getter, store, ("ddg_html", "searxng"))
    assert (outcome.status, outcome.provider) == ("ok", "searxng")
    assert outcome.attempts[0] == {
        "provider": "ddg_html",
        "status": "blocked",
        "http_status": status,
        "reason": "ddgs_StatusError",
    }
    assert store.get(DDG_KEY)["http_status"] == status
    assert store.get(DDG_KEY)["hours"] == 1


def test_rate_limit_exception_records_429_without_exposing_message(ddgs_stub):
    class RatelimitException(Exception):
        pass

    ddgs_stub.error = RatelimitException("private")
    getter, _web, store, _clock = _getter()
    outcome = _run(getter, store)
    assert outcome.attempts[0]["http_status"] == 429
    assert outcome.attempts[0]["status"] == "blocked"
    assert store.get(DDG_KEY)["hours"] == 1


def test_expired_pause_doubles_even_if_robots_200_clears_the_old_record(ddgs_stub):
    ddgs_stub.error = RuntimeError("blocked internally")
    getter, _web, store, clock = _getter({DDG_ROBOTS: "User-agent: *\nAllow: /\n"})
    pause_site(store, DDG_KEY, http_status=429, now=clock.now() - timedelta(hours=2))
    assert _run(getter, store).status == "unavailable"
    assert store.get(DDG_KEY)["hours"] == 2


@pytest.mark.parametrize(
    "robots",
    [
        "User-agent: *\nDisallow: /html/\n",
        (0, ""),
        (503, ""),
    ],
)
def test_robots_refusal_never_constructs_ddgs_and_allows_searxng_fallback(ddgs_stub, robots):
    getter, web, store, _clock = _getter(
        {
            DDG_ROBOTS: robots,
            _url(): fixture_text("searxng_results.json"),
        }
    )
    outcome = _run(getter, store, ("ddg_html", "searxng"))
    assert outcome.provider == "searxng"
    assert outcome.attempts[0]["reason"] == "robots_disallowed"
    assert ddgs_stub.constructors == []
    assert web.page_calls() == [_url()]


@pytest.mark.parametrize("status", [403, 429])
def test_robots_http_refusal_uses_existing_gate_pause_once(ddgs_stub, status):
    getter, _web, store, _clock = _getter({DDG_ROBOTS: (status, "")})
    outcome = _run(getter, store)
    assert outcome.status == "unavailable"
    assert outcome.attempts[0]["http_status"] == status
    assert store.get(DDG_KEY)["hours"] == 1
    assert ddgs_stub.constructors == []


def test_time_budget_refuses_library_call_before_it_starts(ddgs_stub):
    getter, web, store, _clock = _getter()
    getter.policy.time_limit_seconds = OPTIONS["min_interval_seconds"]
    outcome = _run(getter, store)
    assert outcome.status == "unavailable"
    assert outcome.attempts[0]["reason"] == STOP_TIME_LIMIT
    assert web.calls == [DDG_ROBOTS]
    assert ddgs_stub.constructors == []


def test_private_backend_resolution_refuses_library_call(ddgs_stub, monkeypatch):
    getter, web, store, _clock = _getter()
    monkeypatch.setattr(getter, "_resolve", lambda _host: ["127.0.0.1"])
    outcome = _run(getter, store)
    assert outcome.attempts[0]["reason"] == "private_address"
    assert web.calls == []
    assert ddgs_stub.constructors == []


@pytest.mark.parametrize("rows", [[], None, "unexpected", [{}], [{"href": "javascript:bad"}]])
def test_empty_answer_is_distinct_from_malformed_library_results(ddgs_stub, rows):
    ddgs_stub.rows = rows
    getter, _web, store, _clock = _getter()
    outcome = _run(getter, store)
    if rows == []:
        assert (outcome.status, outcome.results) == ("empty", [])
        assert SearchCache(store).get_outcome("ddg_html", QUERY)["status"] == "empty"
        assert store.get(DDG_KEY) is None
    else:
        assert outcome.status == "unavailable"
        assert store.get(DDG_KEY)["hours"] == 1
        assert SearchCache(store).get_outcome("ddg_html", QUERY) is None


@pytest.mark.parametrize("empty", [False, True])
def test_s1_search_cache_key_ttl_and_hit_without_network(ddgs_stub, empty):
    if empty:
        ddgs_stub.rows = []
    getter, _web, store, clock = _getter()
    first = _run(getter, store)
    expected = "empty" if empty else "ok"
    assert first.status == expected
    digest = hashlib.sha256(QUERY.encode("utf-8")).hexdigest()
    key = f"wd:search:ddg_html:{digest}"
    assert store.get(key)["status"] == expected
    assert store.ttls[key] == SEARCH_TTL_SECONDS == 7 * 24 * 3600

    next_getter, next_web, _, _ = _getter(store=store, clock=clock)
    second = _run(next_getter, store)
    assert second.results == first.results
    assert second.attempts[0]["reason"] == "cache"
    assert len(ddgs_stub.calls) == 1
    assert next_web.calls == []


@pytest.mark.parametrize(
    "changes",
    [
        {"region": "zz-en"},
        {"max_results": 1},
        {"min_interval_seconds": 31.0},
        {"timeout_seconds": 9},
    ],
)
def test_changed_search_options_do_not_reuse_a_different_configuration(ddgs_stub, changes):
    getter, _web, store, _clock = _getter()
    assert _run(getter, store).status == "ok"
    second = _run(getter, store, options={**OPTIONS, **changes})
    assert second.status == "ok"
    assert second.attempts[0]["reason"] != "cache"
    assert len(ddgs_stub.calls) == 2


def test_legacy_hand_parsed_cache_cannot_bypass_the_new_adapter(ddgs_stub):
    getter, _web, store, _clock = _getter()
    SearchCache(store).put_outcome(
        "ddg_html",
        QUERY,
        {"status": "ok", "results": [{"url": "https://legacy.example.test/"}]},
    )
    outcome = _run(getter, store)
    assert [result.host for result in outcome.results] == [ALPHA, GAMMA]
    assert len(ddgs_stub.calls) == 1


def test_cache_failure_does_not_lose_successful_ddgs_results(monkeypatch):
    getter, _web, store, _clock = _getter()
    cache = SearchCache(store)

    def broken(*_args, **_kwargs):
        raise RuntimeError("private cache error")

    monkeypatch.setattr(cache, "get_outcome", broken)
    monkeypatch.setattr(cache, "put_outcome", broken)
    outcome = search.web_search(
        QUERY,
        providers=["ddg_html"],
        getter=getter,
        cache=cache,
        search_options=OPTIONS,
    )
    assert outcome.status == "ok" and outcome.results


def test_result_validation_deduplication_engine_filtering_and_rank_limit():
    hits = [
        ParsedHit("https://duckduckgo.com/help"),
        ParsedHit("https://sub.searx.example.test/help"),
        ParsedHit("https://user:password@private.example.test/"),
        ParsedHit("https://shop.example.test:broken/"),
    ]
    hits += [ParsedHit(f"https://{ALPHA}/p/{index}") for index in range(12)]
    hits.insert(5, hits[4])
    results = search.build_results(
        hits, extra_engine_hosts=frozenset({"searx.example.test"})
    )
    assert len(results) == 10
    assert [result.rank for result in results] == list(range(1, 11))
    assert results[-1].url.endswith("/9")


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
def test_unusable_result_links_do_not_raise(href):
    assert unwrap_result_href(href) is None


@pytest.mark.parametrize("fixture", ["searxng_results.json", "searxng_results.html"])
def test_searxng_fixtures_keep_json_and_html_parser_contracts(fixture):
    parsed = parse_searxng(fixture_text(fixture))
    assert parsed.status == "ok"
    results = search.build_results(
        parsed.hits, extra_engine_hosts=frozenset({"searx.example.test"})
    )
    assert [result.host for result in results] == [ALPHA, GAMMA]
    assert [result.rank for result in results] == [1, 2]
    assert results[0].title == "Alpha Shop ABC-123"
    assert results[0].snippet == "The ABC-123 Widget in stock at Alpha Shop."


@pytest.mark.parametrize("fixture", ["searxng_results.json", "searxng_results.html"])
def test_searxng_keeps_own_http_through_polite_and_tenant_spacing(ddgs_stub, fixture):
    url = _url()
    parts = urlsplit(url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    getter, web, store, clock = _getter({url: fixture_text(fixture)})
    outcome = _run(getter, store, ("searxng",))
    assert (outcome.status, outcome.provider) == ("ok", "searxng")
    assert web.calls == [robots_url, url]
    assert clock.waits == [OPTIONS["min_interval_seconds"]]
    assert ddgs_stub.calls == []


@pytest.mark.parametrize(
    ("fixture", "status", "reason"),
    [
        ("ddg_html_anomaly.html", 200, "anomaly_page"),
        ("ddg_html_202_empty.html", 202, "http_202"),
        ("ddg_html_no_results.html", 202, "http_202"),
    ],
)
def test_searxng_challenge_detection_precedes_empty_markup(fixture, status, reason):
    parsed = parse_searxng(fixture_text(fixture), status)
    assert (parsed.status, parsed.reason, parsed.hits) == ("blocked", reason, [])


@pytest.mark.parametrize("fixture", ["ddg_html_results.html", "ddg_lite_results.html"])
def test_searxng_does_not_treat_other_engines_markup_as_its_results(fixture):
    parsed = parse_searxng(fixture_text(fixture))
    assert parsed.status == "unrecognised"
    assert parsed.hits == []


def test_searxng_explicit_empty_is_distinct_from_unknown_markup():
    empty = parse_searxng(fixture_text("ddg_html_no_results.html"))
    assert (empty.status, empty.reason, empty.hits) == ("empty", "no_results", [])
    blank = parse_searxng(fixture_text("ddg_html_202_empty.html"))
    assert blank.status == "unrecognised"
    empty_json = parse_searxng(fixture_text("searxng_no_results.json"))
    assert (empty_json.status, empty_json.hits) == ("empty", [])


@pytest.mark.parametrize("status", [200, 202, 403, 429])
def test_searxng_blocks_pause_once_and_are_not_http_or_search_cached(status):
    url = _url()
    key = "search:searx.example.test"
    getter, _web, store, _clock = _getter(
        {url: (status, fixture_text("ddg_html_anomaly.html"))}
    )
    outcome = _run(getter, store, ("searxng",))
    assert outcome.status == "unavailable"
    assert store.get(key)["hours"] == 1
    assert SearchCache(store).get_outcome("searxng", QUERY) is None
    assert getter.cache.get_response(url) is None


def test_searxng_cache_does_not_cross_instance_urls():
    getter, web, store, _clock = _getter(
        {_url(): fixture_text("searxng_results.json")}
    )
    assert _run(getter, store, ("searxng",)).status == "ok"
    other_base = "https://searx.example.test/other-instance"
    other_url = _url(base=other_base)
    web.pages[other_url] = fixture_text("searxng_results.html")
    outcome = _run(getter, store, ("searxng",), base=other_base)
    assert outcome.status == "ok"
    assert outcome.attempts[0]["reason"] != "cache"
    assert web.page_calls() == [_url(), other_url]


def test_searxng_unknown_markup_is_evicted_and_can_be_retried_next_run():
    url = _url()
    getter, _web, store, clock = _getter({url: "<html><body></body></html>"})
    outcome = _run(getter, store, ("searxng",))
    assert outcome.status == "unavailable"
    assert outcome.attempts[0]["reason"] == "unrecognised_markup"
    assert getter.cache.get_response(url) is None
    next_getter, next_web, _, _ = _getter(
        {url: fixture_text("searxng_results.json")}, store=store, clock=clock
    )
    assert _run(next_getter, store, ("searxng",)).status == "ok"
    assert next_web.page_calls() == [url]


def test_search_off_missing_settings_and_unsupported_provider_have_no_network(ddgs_stub):
    getter, web, store, _clock = _getter()
    assert _run(getter, store, ()).status == "off"
    missing = _run(getter, store, options=None)
    assert missing.status == "unavailable"
    assert missing.attempts[0]["reason"] == "search_options_not_set"
    assert _run(getter, store, ("searxng",), base="").status == "unavailable"
    assert _run(getter, store, ("unknown",)).attempts[0]["reason"] == "unknown_provider"
    lite = _run(getter, store, ("ddg_lite",))
    assert lite.attempts[0]["reason"] == "ddgs_lite_unsupported"
    assert web.calls == []
    assert ddgs_stub.calls == []


@pytest.mark.parametrize(
    "changes",
    [
        {"min_interval_seconds": 0},
        {"min_interval_seconds": -1},
        {"min_interval_seconds": True},
        {"min_interval_seconds": float("nan")},
        {"min_interval_seconds": float("inf")},
        {"max_results": 0},
        {"max_results": 11},
        {"max_results": True},
        {"timeout_seconds": 0},
        {"timeout_seconds": 1.5},
        {"timeout_seconds": False},
        {"region": ""},
        {"region": "two words"},
        {"backend": "auto"},
        {"headers": {"User-Agent": "override"}},
    ],
)
def test_invalid_search_options_are_rejected_without_network(ddgs_stub, changes):
    options = {**OPTIONS, **changes}
    with pytest.raises(ValueError):
        ts.SETTING_VALIDATORS[ts.KEY_DISCOVERY_SEARCH_OPTIONS](options)
    getter, web, store, _clock = _getter()
    outcome = _run(getter, store, options=options)
    assert outcome.status == "unavailable"
    assert outcome.attempts[0]["reason"] == "search_options_invalid"
    assert web.calls == []
    assert ddgs_stub.calls == []


def test_search_options_are_loaded_fingerprinted_and_not_a_preview_prerequisite(monkeypatch):
    values = settings_values(**{ts.KEY_DISCOVERY_SEARCH_OPTIONS: dict(OPTIONS)})
    monkeypatch.setattr(ts, "list_settings", lambda _session, _tenant: values)
    settings = load_discovery_settings(object(), "s3c-test-tenant")
    assert settings.search_options == OPTIONS
    assert settings.public()["search_options"] == OPTIONS
    changed = settings_from_values(
        {**values, ts.KEY_DISCOVERY_SEARCH_OPTIONS: {**OPTIONS, "region": "zz-en"}}
    )
    assert settings.fingerprint() != changed.fingerprint()

    missing = make_settings()
    assert missing.search_options is None
    assert missing.missing_for("customer") == []


def test_settings_factory_passes_options_without_changing_candidate_call_interface(
    monkeypatch, ddgs_stub
):
    values = settings_values(
        **{
            ts.KEY_DISCOVERY_SEARCH_PROVIDERS: ["ddg_html"],
            ts.KEY_DISCOVERY_SEARCH_OPTIONS: dict(OPTIONS),
        }
    )
    monkeypatch.setattr(ts, "list_settings", lambda _session, _tenant: values)
    settings = load_discovery_settings(object(), "s3c-test-tenant")
    ctx = cand.CustomerContext(
        customer_id=1,
        name="Alpha Gadgets",
        products=[
            cand.ProductInfo(id=index, sales_model_name=f"ABC-{index}")
            for index in range(1, 6)
        ],
    )
    getter, _web, store, _clock = _getter()
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
    assert tracker.queries == 4
    assert len(ddgs_stub.calls) == 4
    assert tracker.summary()["provider_used"] == "ddg_html"
    assert {item.host for item in found} == {ALPHA, GAMMA}
    assert all(item.sources == {"product_search", "name_search"} for item in found)
    assert all(
        [hit["product_id"] for hit in item.product_hits] == [1, 2, 3] for item in found
    )


@pytest.mark.parametrize("configured", [True, False])
def test_preview_finishes_and_other_candidate_sources_survive_search_failure(
    monkeypatch, ddgs_stub, configured
):
    ddgs_stub.error = RuntimeError("private upstream failure")
    values = {
        ts.KEY_DISCOVERY_SEARCH_OPTIONS: dict(OPTIONS) if configured else None,
    }
    settings = make_settings(**values)
    ctx = cand.CustomerContext(
        customer_id=1,
        name="Alpha Gadgets",
        seed_host=ALPHA,
        contact_domains=["contact-shop.example.test"],
    )
    getter, _web, store, _clock = _getter(
        {f"https://{ALPHA}/": fixture_text("home_org_jsonld.html")}
    )
    customer = SimpleNamespace(id=1, name=ctx.name, tenant_id="s3c-test-tenant")
    monkeypatch.setattr(preview, "load_discovery_settings", lambda *_args: settings)
    monkeypatch.setattr(preview, "_load_customers", lambda *_args: [customer])
    monkeypatch.setattr(cand, "read_context", lambda *_args: ctx)
    statements = []

    class ReadOnlySession:
        def execute(self, statement):
            statements.append(str(statement))
            assert str(statement) == "SET TRANSACTION READ ONLY"

    plan = preview.run_preview(
        ReadOnlySession(),
        tenant_id=customer.tenant_id,
        preview_id="s3c-test-preview",
        request={"scope": "customer", "customer_id": customer.id},
        getter=getter,
        resolve=lambda _host: [PUBLIC_IP],
        plan_store=preview.MemoryPlanStore(),
        search_factory=lambda loaded: preview.default_search_fn(
            loaded, getter, SearchCache(store)
        ),
    )
    assert statements == ["SET TRANSACTION READ ONLY"]
    assert plan["status"] == "done"
    assert plan["result"]["search"]["status"] == "unavailable"
    assert plan["progress"] == {"done": 1, "total": 1}
    domains = {
        item["domain"] for item in plan["result"]["customers"][0]["candidates"]
    }
    assert {ALPHA, "contact-shop.example.test"} <= domains
    assert any(domain.endswith(".zz") for domain in domains)
    assert "private upstream failure" not in str(plan)
    assert len(ddgs_stub.calls) == (1 if configured else 0)


def test_ddgs_no_results_is_an_empty_search_and_does_not_pause(monkeypatch) -> None:
    import sys
    import types

    from app.services.listing_capture.web_discovery import search as search_mod

    class NoResults(Exception):
        pass

    class FakeDDGS:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def text(self, _query, **kwargs):
            assert kwargs["backend"] == "auto"
            raise NoResults("No results found.")

    monkeypatch.setitem(sys.modules, "ddgs", types.SimpleNamespace(DDGS=FakeDDGS, DDGSException=NoResults))
    status, page = search_mod._ddgs_page("q", {"max_results": 5, "timeout_seconds": 5}, "auto")
    assert status == 200 and page.status == search_mod.PARSED_EMPTY and page.hits == []

    class Limited(NoResults):
        pass

    def limited(self, _query, **_kwargs):
        raise Limited("rate")

    monkeypatch.setattr(FakeDDGS, "text", limited)
    try:
        search_mod._ddgs_page("q", {"max_results": 5, "timeout_seconds": 5}, "auto")
    except Limited:
        pass
    else:
        raise AssertionError("a subclass (rate limit) must still raise")


def test_an_empty_provider_lets_the_next_provider_try(monkeypatch):
    from types import SimpleNamespace

    from app.services.listing_capture.web_discovery import search as search_mod

    calls = []

    def run(provider, *_args):
        calls.append(provider)
        hits = [] if provider == search_mod.PROVIDER_DDG_HTML else ["hit"]
        status = search_mod.PARSED_OK if hits else search_mod.PARSED_EMPTY
        return {"provider": provider, "status": status}, SimpleNamespace(hits=hits, status=status)

    monkeypatch.setattr(search_mod, "_run_provider", run)
    monkeypatch.setattr(search_mod, "build_results", lambda hits, **_kw: list(hits))
    options = {"max_results": 5, "timeout_seconds": 5, "min_interval_seconds": 1}
    outcome = search_mod.web_search(
        "q", providers=[search_mod.PROVIDER_DDG_HTML, search_mod.PROVIDER_DDGS_AUTO],
        getter=None, search_options=options,
    )
    assert calls == [search_mod.PROVIDER_DDG_HTML, search_mod.PROVIDER_DDGS_AUTO]
    assert outcome.provider == search_mod.PROVIDER_DDGS_AUTO and outcome.results == ["hit"]

    calls.clear()
    monkeypatch.setattr(search_mod, "build_results", lambda hits, **_kw: [])
    outcome = search_mod.web_search(
        "q", providers=[search_mod.PROVIDER_DDG_HTML, search_mod.PROVIDER_DDGS_AUTO],
        getter=None, search_options=options,
    )
    assert len(calls) == 2 and outcome.status == search_mod.STATUS_EMPTY
