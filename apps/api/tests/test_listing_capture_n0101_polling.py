"""N-0101 (N-0085 U1): restock, out_of_stock polled, dead-link back-off, per-site
403/429 pause, run time limit, per-site spacing, ordinary browser User-Agent.
Sites are data: spacing and the page reader come from the site config; a site without a
reader is not fetched.

No DB and no network: MagicMock session, injected http_get / clock / sleep / store / sites.
Fictional sites only.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from sqlalchemy.dialects import postgresql

from app.services.listing_capture import observation as obs_mod
from app.services.listing_capture.observation import LISTING_CAPTURE_USER_AGENT
from app.services.listing_capture.registry import (
    POLLED_LISTING_STATUSES,
    _interleave_by_marketplace,
    listing_consecutive_failures,
    listing_in_dead_link_backoff,
    poll_active_listings,
    record_observation,
)
from app.services.listing_capture.site_pause import (
    MemorySitePauseStore,
    pause_site,
    paused_until,
)
from tests.listing_site_fixtures import html_site, rest_site, unconfigured_site

SITES = {
    "shop-a": html_site("shop-a"),
    "shop-b": html_site("shop-b", rate=None),
    "market-b": rest_site("market-b"),
    "shop-c": unconfigured_site("shop-c"),
}
SITE = SITES["shop-a"]

IN_STOCK = '{"price": 999.0, "availability": "in_stock"}'
OUT_OF_STOCK = '{"price": 999.0, "availability": "out_of_stock"}'


def _listing(lid: int, marketplace: str = "shop-a", status: str = "active", **kw):
    return SimpleNamespace(
        id=lid,
        url=kw.pop("url", f"https://example.test/{marketplace}/{lid}"),
        marketplace=marketplace,
        status=status,
        status_observed_at=kw.pop("status_observed_at", None),
        meta_json=kw.pop("meta_json", None),
        product_id=kw.pop("product_id", None),
        external_id=kw.pop("external_id", None),
        customer_id=kw.pop("customer_id", 1),
    )


def _session(listings):
    session = MagicMock()
    session.scalars.return_value.all.return_value = list(listings)
    return session


class FakeClock:
    def __init__(self) -> None:
        self.t = 1000.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.sleeps.append(s)
        self.t += s


def _poll(session, http_get, *, store=None, clock=None, **kw):
    clock = clock or FakeClock()
    return poll_active_listings(
        session,
        http_get=http_get,
        pause_store=store if store is not None else MemorySitePauseStore(),
        clock=clock,
        sleep=clock.sleep,
        site_for=lambda listing: SITES.get(listing.marketplace),
        **kw,
    )


# ---------------------------------------------------------------- restock / statuses


def test_out_of_stock_seen_in_stock_returns_to_active_as_restocked() -> None:
    listing = _listing(1, status="out_of_stock")
    obs = record_observation(MagicMock(), listing, site=SITE, http_get=lambda _u: (200, IN_STOCK))
    assert listing.status == "active"
    assert obs.parse_flags["status_transition"] == {
        "from": "out_of_stock",
        "to": "active",
        "reason": "restocked",
    }
    assert listing.status_observed_at == obs.fetched_at


def test_out_of_stock_unknown_availability_is_not_a_restock() -> None:
    listing = _listing(1, status="out_of_stock")
    obs = record_observation(
        MagicMock(), listing, site=SITE, http_get=lambda _u: (200, '{"price": 999.0, "availability": "unknown"}')
    )
    assert listing.status == "out_of_stock"
    assert "status_transition" not in obs.parse_flags


def test_active_going_out_of_stock_records_transition_and_staying_active_does_not() -> None:
    listing = _listing(1)
    obs = record_observation(MagicMock(), listing, site=SITE, http_get=lambda _u: (200, OUT_OF_STOCK))
    assert listing.status == "out_of_stock"
    assert obs.parse_flags["status_transition"]["reason"] == "out_of_stock"
    listing2 = _listing(2)
    obs2 = record_observation(MagicMock(), listing2, site=SITE, http_get=lambda _u: (200, IN_STOCK))
    assert listing2.status == "active"
    assert "status_transition" not in obs2.parse_flags


def test_poller_selects_out_of_stock_and_dead_link_oldest_due_first() -> None:
    session = _session([])
    _poll(session, lambda _u: (200, IN_STOCK))
    stmt = session.scalars.call_args.args[0]
    sql = str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert set(POLLED_LISTING_STATUSES) == {"active", "out_of_stock", "dead_link"}
    for st in POLLED_LISTING_STATUSES:
        assert f"'{st}'" in sql
    assert "max(listing_observation.fetched_at)" in sql
    assert "NULLS FIRST" in sql
    assert "'skipped'" in sql  # a back-off placeholder row is not a real check


def test_poller_polls_out_of_stock_listing() -> None:
    listing = _listing(5, status="out_of_stock")
    calls: list[str] = []

    def http_get(url):
        calls.append(url)
        return 200, OUT_OF_STOCK

    out = _poll(_session([listing]), http_get)
    assert out["polled"] == 1
    assert calls == [listing.url]
    assert listing.status == "out_of_stock"


# ---------------------------------------------------------------- dead-link back-off


def test_consecutive_dead_results_drive_backoff_and_a_good_parse_resets() -> None:
    listing = _listing(7)
    for n in (1, 2, 3):
        record_observation(MagicMock(), listing, site=SITE, http_get=lambda _u: (404, ""))
        assert listing.status == "dead_link"
        assert listing_consecutive_failures(listing) == n
    now = datetime.now(timezone.utc)
    assert listing_in_dead_link_backoff(listing, now=now) is True
    assert listing_in_dead_link_backoff(listing, now=now + timedelta(hours=25)) is False

    # The poller skips it without a request or a row while in back-off.
    calls: list[str] = []
    session = _session([listing])
    out = _poll(session, lambda u: calls.append(u) or (200, IN_STOCK))
    assert out["skipped_backoff"] == 1 and out["polled"] == 0 and calls == []
    session.add.assert_not_called()

    # A day later it is checked again; a good page brings it back and clears the count.
    out = _poll(_session([listing]), lambda _u: (200, IN_STOCK), now=now + timedelta(hours=25))
    assert out["polled"] == 1
    assert listing.status == "active"
    assert listing_consecutive_failures(listing) == 0
    assert "last_failure_at" not in (listing.meta_json or {})


def test_dead_link_with_two_failures_is_still_polled() -> None:
    listing = _listing(8, status="dead_link")
    record_observation(MagicMock(), listing, site=SITE, http_get=lambda _u: (404, ""))
    record_observation(MagicMock(), listing, site=SITE, http_get=lambda _u: (404, ""))
    assert listing_in_dead_link_backoff(listing) is False
    obs = record_observation(MagicMock(), listing, site=SITE, http_get=lambda _u: (200, IN_STOCK))
    assert listing.status == "active"
    assert obs.parse_flags["status_transition"]["reason"] == "link_recovered"


# ---------------------------------------------------------------- 403 / 429 site pause


def test_429_pauses_only_that_site_and_is_recorded() -> None:
    a1, a2, a3 = (_listing(i, "shop-b") for i in (1, 2, 3))
    e1, e2 = (_listing(i, "shop-a") for i in (11, 12))
    calls: list[str] = []

    def http_get(url):
        calls.append(url)
        if "/shop-b/" in url:
            return 429, "<html>Too many requests R 12 999</html>"
        return 200, IN_STOCK

    store = MemorySitePauseStore()
    session = _session([a1, a2, a3, e1, e2])
    added: list = []
    session.add.side_effect = added.append
    out = _poll(session, http_get, store=store)

    assert sum("/shop-b/" in c for c in calls) == 1  # no more requests to shop-b this run
    assert sum("/shop-a/" in c for c in calls) == 2  # shop-a unaffected
    assert out["skipped_paused"] == {"shop-b": 2}
    assert out["paused_sites"]["shop-b"]["hours"] == 1
    assert out["paused_sites"]["shop-b"]["http_status"] == 429
    assert "shop-a" not in out["paused_sites"]
    refused_obs = [o for o in added if getattr(o, "http_status", None) == 429]
    assert len(refused_obs) == 1
    assert refused_obs[0].parse_flags["site_paused"]["hours"] == 1
    assert refused_obs[0].extracted_price is None  # never a price from a refusal page
    assert a1.status == "active"  # a refusal is not a dead link

    # Next run inside the pause: shop-b is not contacted at all.
    calls.clear()
    out2 = _poll(_session([a1, e1]), http_get, store=store)
    assert [c for c in calls if "/shop-b/" in c] == []
    assert out2["skipped_paused"] == {"shop-b": 1}
    assert out2["paused_sites"]["shop-b"]["paused_this_run"] is False


def test_403_pause_doubles_up_to_24h_and_clears_on_success() -> None:
    store = MemorySitePauseStore()
    now = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)
    hours = []
    for _ in range(7):
        rec = pause_site(store, "shop-a", http_status=403, now=now)
        hours.append(rec["hours"])
    assert hours == [1, 2, 4, 8, 16, 24, 24]
    assert paused_until(store, "shop-a", now=now) is not None
    assert paused_until(store, "shop-a", now=now + timedelta(hours=25)) is None

    # After the pause ends, a 200 from the site clears the memory (next refusal is 1 h again).
    listing = _listing(1, "shop-a")
    _poll(_session([listing]), lambda _u: (200, IN_STOCK), store=store, now=now + timedelta(hours=25))
    assert store.get("shop-a") is None
    assert pause_site(store, "shop-a", http_status=403, now=now)["hours"] == 1


def test_rest_reader_refusal_sends_no_follow_up_requests() -> None:
    session = _session([])
    session.get.return_value = SimpleNamespace(ean="6001234567890", upc=None)
    listing = _listing(
        3, "market-b", url="https://market-b.example.test/x/ID12345678", product_id=99, meta_json={}
    )
    session.scalars.return_value.all.return_value = [listing]
    calls: list[tuple[str, dict | None]] = []

    def http_get(url, headers=None):
        calls.append((url, headers))
        return 429, ""

    out = _poll(session, http_get)
    assert len(calls) == 1  # details call only; the barcode search is not sent
    assert calls[0][0] == "https://api.market-b.example.test/rest/details/ID12345678?platform=desktop"
    assert calls[0][1]["Accept"] == "application/json"  # reader headers reach the getter
    assert out["paused_sites"]["market-b"]["http_status"] == 429


def test_site_without_reader_is_not_fetched_and_takes_no_batch_slot() -> None:
    waiting = [_listing(i, "shop-c") for i in (1, 2, 3)]
    ready = _listing(4, "shop-a")
    calls: list[str] = []
    session = _session([*waiting, ready])
    out = _poll(session, lambda u: calls.append(u) or (200, IN_STOCK), limit=1)
    assert calls == [ready.url]
    assert out["polled"] == 1
    assert out["skipped_not_configured"] == {"shop-c": 3}
    assert out["considered_ids"] == [4]
    session.add.assert_called()  # the one real observation
    assert all(getattr(c.args[0], "listing_id", None) == 4 for c in session.add.call_args_list if c.args)


def test_poll_task_run_record_names_the_unconfigured_site_warns_and_keeps_polling_the_other(
    monkeypatch, caplog
) -> None:
    """W1-D: a site with no reader is loud. The run record counts its skipped listings per site,
    one WARNING names the site, the latest run is kept for capture health, and the configured
    site is still observed."""
    import logging

    from app.services.listing_capture import registry as registry_mod
    from app.services.listing_capture.site_pause import RUN_POLL, load_run_state
    from app.worker.tasks import listing_capture_poll_listings_task

    ready = _listing(21, "shop-a")
    waiting = [_listing(22, "shop-c"), _listing(23, "shop-c")]
    session = _session([ready, *waiting])
    added: list = []
    session.add.side_effect = added.append

    class _Same:
        def __enter__(self):
            return session

        def __exit__(self, *_exc):
            return False

    run_store = MemorySitePauseStore()
    real_poll = registry_mod.poll_active_listings
    clock = FakeClock()
    calls: list[str] = []

    def _with_sites(sess, **kwargs):
        kwargs.update(
            site_for=lambda listing: SITES.get(listing.marketplace),
            pause_store=MemorySitePauseStore(),
            clock=clock,
            sleep=clock.sleep,
        )
        return real_poll(sess, **kwargs)

    def http_get(url, headers=None):
        calls.append(url)
        return 200, IN_STOCK

    monkeypatch.setattr("app.db.session_sync.SessionLocal", lambda: _Same())
    monkeypatch.setattr("app.worker.celery_queues.dev_beat_disabled", lambda: False)
    gate = {"enabled": True, "listing_count": 3, "should_run": True}
    monkeypatch.setattr(registry_mod, "scheduler_should_run", lambda _s: gate)
    monkeypatch.setattr(registry_mod, "poll_active_listings", _with_sites)
    monkeypatch.setattr("app.services.listing_capture.observation.default_http_get", http_get)
    monkeypatch.setattr(
        "app.services.listing_capture.site_pause.default_run_state_store", lambda: run_store
    )
    monkeypatch.setenv("CIP_LISTING_LIVE_FETCH", "1")

    with caplog.at_level(logging.INFO):
        out = listing_capture_poll_listings_task.run()

    # Run record: per-site count of listings skipped as not configured, and why.
    assert out["skipped"] is False
    assert out["skipped_not_configured"] == {"shop-c": 2}
    assert out["not_configured_sites"] == [
        {"site_key": "shop-c", "tenant_id": "default", "listings": 2, "missing": ["adapter_key"]}
    ]
    # The configured site is still fetched and observed.
    assert out["polled"] == 1 and calls == [ready.url]
    from app.models.listing_capture import ListingObservation

    assert [o.listing_id for o in added if isinstance(o, ListingObservation)] == [21]
    # One WARNING names the site and the count; the configured site is not warned about.
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    loud = "2 listings not polled - no reader configured"
    assert any("site shop-c" in m and loud in m for m in warnings)
    assert not any("site shop-a" in m for m in warnings)
    # The latest run is kept for capture health.
    kept = load_run_state(RUN_POLL, store=run_store)
    assert kept is not None and kept["not_configured_sites"][0]["site_key"] == "shop-c"
    assert kept["finished_at"]
    assert "visited_ids" not in kept


def test_not_configured_reason_covers_missing_row_inactive_site_and_empty_columns() -> None:
    from dataclasses import replace

    from app.services.listing_capture.registry import (
        fresh_listing_poll_run,
        merge_listing_poll_batch,
    )

    no_row = _listing(31, "shop-x", customer_id=7)
    inactive = _listing(32, "shop-d")
    half = _listing(33, "market-c")
    sites = {
        "shop-d": replace(html_site("shop-d"), is_active=False),
        "market-c": replace(rest_site("market-c"), details_url_pattern=None),
    }
    out = poll_active_listings(
        _session([no_row, inactive, half]),
        http_get=lambda _u: (_ for _ in ()).throw(AssertionError("no fetch")),
        pause_store=MemorySitePauseStore(),
        clock=FakeClock(),
        sleep=lambda _s: None,
        site_for=lambda listing: sites.get(listing.marketplace),
        log_result=False,
    )
    by_key = {e["site_key"]: e for e in out["not_configured_sites"]}
    assert by_key["shop-x"] == {
        "site_key": "shop-x",
        "tenant_id": None,
        "listings": 1,
        "missing": ["site"],
    }
    assert by_key["shop-d"]["missing"] == ["is_active"]
    assert by_key["market-c"]["missing"] == ["details_url_pattern"]
    # Batches of one run keep the latest per-site list (every batch sees the same skipped listings).
    merged = merge_listing_poll_batch(fresh_listing_poll_run(), out)
    merged = merge_listing_poll_batch(merged, out)
    assert merged["not_configured_sites"] == out["not_configured_sites"]


def test_record_observation_on_unconfigured_site_writes_a_skipped_row_without_a_request() -> None:
    listing = _listing(9, "shop-c")
    calls: list[str] = []
    obs = record_observation(
        MagicMock(), listing, site=SITES["shop-c"], http_get=lambda u: calls.append(u) or (200, IN_STOCK)
    )
    assert calls == []
    assert obs.parse_status == "skipped"
    assert obs.parse_flags["reason"] == "site_not_configured"
    assert obs.parse_flags["missing"] == ["adapter_key"]


# ---------------------------------------------------------------- run limit, mix, spacing


def test_run_stops_at_time_limit() -> None:
    listings = [_listing(i, "shop-a" if i % 2 else "shop-b") for i in range(10)]
    clock = FakeClock()

    def http_get(_url):
        clock.t += 100.0
        return 200, IN_STOCK

    out = _poll(_session(listings), http_get, clock=clock, time_limit_seconds=250)
    assert out["polled"] == 3
    assert out["stopped_reason"] == "time_limit"
    assert out["duration_seconds"] >= 250


def test_default_time_limit_is_ten_minutes() -> None:
    assert obs_mod.POLL_RUN_TIME_LIMIT_SECONDS == 600


def test_interleave_mixes_retailers_keeping_oldest_due_order() -> None:
    t1, t2, t3 = (_listing(i, "market-b") for i in (1, 2, 3))
    e1, e2 = (_listing(i, "shop-a") for i in (4, 5))
    a1 = _listing(6, "shop-b")
    got = [x.id for x in _interleave_by_marketplace([t1, t2, t3, e1, e2, a1])]
    assert got == [1, 4, 6, 2, 5, 3]


def test_spacing_is_per_site() -> None:
    clock = FakeClock()
    listings = [_listing(1, "shop-a"), _listing(2, "shop-a")]

    def http_get(_url):
        clock.t += 0.5
        return 200, IN_STOCK

    _poll(_session(listings), http_get, clock=clock)
    # Spacing runs from the end of the previous request to the same site (site data: 2 s).
    assert clock.sleeps == [SITE.rate_limit_seconds]

    # A site with no spacing of its own uses the default.
    clock3 = FakeClock()

    def get3(_url):
        clock3.t += 0.5
        return 200, IN_STOCK

    _poll(_session([_listing(1, "shop-b"), _listing(2, "shop-b")]), get3, clock=clock3)
    assert clock3.sleeps == [obs_mod.DEFAULT_RATE_LIMIT_SECONDS]

    # Alternating sites that each took longer than their spacing: no sleep.
    clock2 = FakeClock()

    def slow_get(_url):
        clock2.t += 2.5
        return 200, IN_STOCK

    _poll(_session([_listing(1, "shop-a"), _listing(2, "shop-b"), _listing(3, "shop-a")]), slow_get, clock=clock2)
    assert clock2.sleeps == []


# ---------------------------------------------------------------- User-Agent (D-0063)


def test_user_agent_is_an_ordinary_browser_not_cip() -> None:
    ua = LISTING_CAPTURE_USER_AGENT
    assert ua.startswith("Mozilla/5.0 (")
    assert "Chrome/" in ua and "Safari/" in ua
    for token in ("cip", "listing-capture", "bot", "crawler", "spider", "python", "urllib"):
        assert token not in ua.lower()


def test_default_http_get_sends_browser_user_agent(monkeypatch) -> None:
    seen = {}

    class _Resp:
        status = 200

        def read(self):
            return b"ok"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(request, timeout=None):
        seen["ua"] = request.get_header("User-agent")
        seen["lang"] = request.get_header("Accept-language")
        seen["accept"] = request.get_header("Accept")
        seen["referer"] = request.get_header("Referer")
        return _Resp()

    monkeypatch.setattr(obs_mod.urllib.request, "urlopen", fake_urlopen)
    assert obs_mod.default_http_get("https://shop-a.example.test/x") == (200, "ok")
    assert seen["ua"] == LISTING_CAPTURE_USER_AGENT
    assert seen["lang"]
    assert seen["accept"].startswith("text/html")
    assert seen["referer"] is None

    # Reader headers are added; the browser User-Agent stays.
    headers = {"Accept": "application/json", "Referer": "https://market-b.example.test/"}
    assert obs_mod.default_http_get("https://api.market-b.example.test/d", headers=headers) == (200, "ok")
    assert seen["accept"] == "application/json"
    assert seen["referer"] == "https://market-b.example.test/"
    assert seen["ua"] == LISTING_CAPTURE_USER_AGENT
