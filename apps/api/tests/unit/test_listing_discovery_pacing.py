"""Discovery shares the poll's per-site spacing and 403/429 pause (alignment D5, finding 2).

In-memory models, mocked sessions and HTTP only.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from app.models.customer_report_config import CustomerReportConfig
from app.models.dimensions import DimCustomer, DimProduct
from app.models.listing_site import ListingSite
from app.services.listing_capture import discovery, site_pause
from app.services.listing_capture.site_fetch import FetchPolicy, SiteFetchGate, site_spacing_seconds
from app.services.listing_capture.site_pause import MemorySitePauseStore

HOST = "https://catalogue.example.test"
TENANT = "unit-tenant"
SITE_KEY = "pace-catalogue"


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(round(seconds, 3))
        self.t += seconds


def _policy(store=None, clock=None, limit=600.0):
    clock = clock or FakeClock()
    return clock, FetchPolicy(
        store=store if store is not None else MemorySitePauseStore(),
        clock=clock,
        sleep=clock.sleep,
        time_limit_seconds=limit,
    )


def _site(**fields):
    return ListingSite(
        **{
            "id": 7,
            "tenant_id": TENANT,
            "site_key": SITE_KEY,
            "display_name": "Catalogue",
            "adapter_key": "html_page",
            "is_active": True,
            "first_party_seller": "Counter",
            "search_url_pattern": f"{HOST}/search?q={{query}}",
            "sellers": [],
            **fields,
        }
    )


def _products(n):
    return {
        pid: DimProduct(
            id=pid,
            tenant_id=TENANT,
            sku=f"sku-{pid}",
            name=f"MODEL{pid}X",
            model_name=f"MODEL{pid}X",
        )
        for pid in range(1, n + 1)
    }


def _mock(monkeypatch, products, row):
    session = MagicMock()
    session.scalar.return_value = None
    session.get.side_effect = lambda model, pid: products.get(pid)
    customer = DimCustomer(id=11, tenant_id=TENANT, name="Counter")
    config = CustomerReportConfig(
        customer_id=11,
        reports_expected=True,
        feed_profile_json={"listing_seed": {"marketplace": row.site_key}},
    )
    monkeypatch.setattr(discovery, "_reporting_customers", lambda *args: [(config, customer)])
    monkeypatch.setattr(discovery, "_load_site", lambda *args: row)
    monkeypatch.setattr(discovery, "_catalogue_product_ids", lambda *args, **kwargs: list(products))
    monkeypatch.setattr(discovery, "_has_listing", lambda *args, **kwargs: False)
    monkeypatch.setattr(discovery, "_queue_exists", lambda *args, **kwargs: False)
    monkeypatch.setattr(discovery, "_proposed_seed", lambda *args, **kwargs: None)
    monkeypatch.setattr(discovery, "confirmed_link", lambda *args: None)
    monkeypatch.setattr(discovery, "_rejected_urls", lambda *args: set())
    monkeypatch.setattr(discovery, "remember_link", MagicMock())
    queue = MagicMock()
    monkeypatch.setattr(discovery, "queue_case", queue)
    return session, queue


def _site_row(report):
    return report["customers"][0]["sites"][0]


def test_spacing_default_and_configured():
    assert site_spacing_seconds(None) == 5.0
    assert site_spacing_seconds(2) == 2.0
    assert site_spacing_seconds(-1) == 0.0


def test_discovery_waits_site_spacing_between_requests(monkeypatch):
    row = _site(rate_limit_seconds=3)
    session, _queue = _mock(monkeypatch, _products(2), row)
    clock, policy = _policy()
    calls: list[float] = []

    def http(url, headers=None):
        calls.append(clock.t)
        return 200, "no matches"

    discovery.discover_reporting_customers(
        session,
        tenant_id=TENANT,
        http_get=http,
        run_store=MemorySitePauseStore(),
        fetch_policy=policy,
    )
    assert len(calls) >= 2
    gaps = [b - a for a, b in zip(calls, calls[1:], strict=False)]
    assert all(gap >= 3 for gap in gaps), gaps
    assert clock.sleeps and all(s <= 3 for s in clock.sleeps)


def test_paused_site_gets_no_request(monkeypatch):
    row = _site()
    session, _queue = _mock(monkeypatch, _products(2), row)
    store = MemorySitePauseStore()
    site_pause.pause_site(store, SITE_KEY, http_status=429, now=datetime.now(UTC))
    _clock, policy = _policy(store)
    http = MagicMock(return_value=(200, "no matches"))
    run_store = MemorySitePauseStore()
    run_store.set(f"discovery:{TENANT}:11:7", {"after_product_id": 1}, ttl_seconds=600)
    report = discovery.discover_reporting_customers(
        session, tenant_id=TENANT, http_get=http, run_store=run_store, fetch_policy=policy
    )
    http.assert_not_called()
    entry = _site_row(report)
    assert entry["reason"] == discovery.REASON_PAUSED
    assert entry["fetch"]["stopped"] == "site_paused"
    assert run_store.get(f"discovery:{TENANT}:11:7") == {"after_product_id": 1}


@pytest.mark.parametrize("refusal", [403, 429])
def test_refusal_pauses_site_stops_run_and_writes_nothing(monkeypatch, refusal):
    row = _site()
    products = _products(3)
    session, queue = _mock(monkeypatch, products, row)
    store = MemorySitePauseStore()
    _clock, policy = _policy(store)
    urls: list[str] = []

    def http(url, headers=None):
        urls.append(url)
        if "MODEL2X" in url:
            return refusal, "<html>blocked</html>"
        return 200, "no matches"

    run_store = MemorySitePauseStore()
    report = discovery.discover_reporting_customers(
        session, tenant_id=TENANT, http_get=http, run_store=run_store, fetch_policy=policy
    )
    # Nothing after the refusal: product 3 is never searched.
    assert not any("MODEL3X" in u for u in urls)
    assert sum(1 for u in urls if "MODEL2X" in u) == 1
    record = store.get(SITE_KEY)
    assert record and record["http_status"] == refusal and record["hours"] == 1
    entry = _site_row(report)
    assert entry["reason"] == discovery.REASON_PAUSED
    assert entry["fetch"]["pause"]["http_status"] == refusal
    # The interrupted product is searched again next run.
    assert run_store.get(f"discovery:{TENANT}:11:7") == {"after_product_id": 1}
    queue.assert_not_called()


def test_refused_search_is_rolled_back(monkeypatch):
    row = _site()
    session, _queue = _mock(monkeypatch, _products(1), row)
    savepoint = MagicMock()
    savepoint.is_active = True
    session.begin_nested.return_value = savepoint
    _clock, policy = _policy()
    discovery.discover_reporting_customers(
        session,
        tenant_id=TENANT,
        http_get=lambda url, headers=None: (403, ""),
        run_store=MemorySitePauseStore(),
        fetch_policy=policy,
    )
    savepoint.rollback.assert_called()
    savepoint.commit.assert_not_called()


def test_pause_set_by_discovery_holds_back_the_poll_key():
    store = MemorySitePauseStore()
    _clock, policy = _policy(store)
    gate = SiteFetchGate(site_key="Pace-Catalogue", spacing_seconds=0, policy=policy)
    assert gate.get(lambda url: (429, "x"), f"{HOST}/a") == (429, "")
    assert gate.get(lambda url: (200, "ok"), f"{HOST}/b") == (429, "")
    # Same key the poll checks (lower-cased marketplace).
    assert site_pause.paused_until(store, "pace-catalogue", now=datetime.now(UTC)) is not None


def test_good_response_clears_an_expired_pause_record():
    store = MemorySitePauseStore()
    past = datetime.now(UTC) - timedelta(hours=2)
    site_pause.pause_site(store, SITE_KEY, http_status=403, now=past)
    _clock, policy = _policy(store)
    gate = SiteFetchGate(site_key=SITE_KEY, spacing_seconds=0, policy=policy)
    assert gate.get(lambda url: (200, "ok"), f"{HOST}/a") == (200, "ok")
    assert store.get(SITE_KEY) is None


def test_time_budget_stops_new_requests_and_keeps_cursor(monkeypatch):
    # 5 s spacing and a 7 s budget: a request at t=0, one at t=5, and the third would
    # have to wait past the budget, so it is never sent and nothing sleeps past 7 s.
    row = _site(rate_limit_seconds=5)
    session, _queue = _mock(monkeypatch, _products(4), row)
    clock, policy = _policy(limit=7.0)
    http = MagicMock(return_value=(200, "no matches"))
    run_store = MemorySitePauseStore()
    report = discovery.discover_reporting_customers(
        session, tenant_id=TENANT, http_get=http, run_store=run_store, fetch_policy=policy
    )
    assert http.call_count == 2
    assert clock.sleeps == [5.0]
    assert clock.t == 5.0
    entry = _site_row(report)
    assert entry["fetch"] == {"stopped": "time_limit", "requests": 2}
    after = (run_store.get(f"discovery:{TENANT}:11:7") or {}).get("after_product_id")
    # Product 1 finished; product 2 was cut short, rolled back, and is not past the cursor.
    assert after == 1
    assert entry["reason"] == discovery.REASON_NOT_FOUND
    # The next run starts with product 2 again.
    _clock2, policy2 = _policy(limit=7.0)
    http2 = MagicMock(return_value=(200, "no matches"))
    discovery.discover_reporting_customers(
        session, tenant_id=TENANT, http_get=http2, run_store=run_store, fetch_policy=policy2
    )
    assert "MODEL2X" in http2.call_args_list[0].args[0]


def test_spacing_is_shared_by_every_gate_on_one_site():
    clock, policy = _policy()
    first = SiteFetchGate(site_key="Shared-Site", spacing_seconds=3, policy=policy)
    second = SiteFetchGate(site_key="shared-site", spacing_seconds=3, policy=policy)
    other = SiteFetchGate(site_key="other-site", spacing_seconds=3, policy=policy)
    assert first.get(lambda url: (200, "a"), f"{HOST}/a") == (200, "a")
    assert other.get(lambda url: (200, "b"), f"{HOST}/b") == (200, "b")
    assert clock.sleeps == []  # another site does not wait
    assert second.get(lambda url: (200, "c"), f"{HOST}/c") == (200, "c")
    assert clock.sleeps == [3.0]  # a new gate on the same site still waits the spacing


def test_two_customers_on_one_site_are_spaced_in_one_run(monkeypatch):
    row = _site(rate_limit_seconds=4)
    session, _queue = _mock(monkeypatch, _products(1), row)
    first = DimCustomer(id=11, tenant_id=TENANT, name="Counter")
    second = DimCustomer(id=12, tenant_id=TENANT, name="Counter Two")
    seed = {"listing_seed": {"marketplace": row.site_key}}
    monkeypatch.setattr(
        discovery,
        "_reporting_customers",
        lambda *args: [
            (
                CustomerReportConfig(customer_id=11, reports_expected=True, feed_profile_json=seed),
                first,
            ),
            (
                CustomerReportConfig(customer_id=12, reports_expected=True, feed_profile_json=seed),
                second,
            ),
        ],
    )
    clock, policy = _policy()
    calls: list[float] = []

    def http(url, headers=None):
        calls.append(clock.t)
        return 200, "no matches"

    discovery.discover_reporting_customers(
        session,
        tenant_id=TENANT,
        http_get=http,
        run_store=MemorySitePauseStore(),
        fetch_policy=policy,
    )
    assert len(calls) >= 2
    gaps = [b - a for a, b in zip(calls, calls[1:], strict=False)]
    assert all(gap >= 4 for gap in gaps), gaps


def _probe_inputs():
    from app.models.listing_capture import CustomerListing

    row = _site(adapter_key=None, rate_limit_seconds=2)
    listing = CustomerListing(
        id=31, customer_id=11, product_id=1, marketplace=SITE_KEY, url=f"{HOST}/p/1"
    )
    session = MagicMock()
    session.scalar.return_value = _products(1)[1]
    return row, [listing], session


def test_autoconfigure_probe_sends_nothing_to_a_paused_site(monkeypatch):
    from app.services.listing_capture import autoconfig

    monkeypatch.setattr(
        "app.services.listing_capture.observation.listing_live_fetch_enabled", lambda: True
    )
    row, listings, session = _probe_inputs()
    store = MemorySitePauseStore()
    site_pause.pause_site(store, SITE_KEY, http_status=429, now=datetime.now(UTC))
    _clock, policy = _policy(store)
    http = MagicMock(return_value=(200, "<html></html>"))
    probe = autoconfig._gated_probe(
        session,
        tenant_id=TENANT,
        site_key=SITE_KEY,
        row=row,
        listings=listings,
        http_get=http,
        policy=policy,
    )
    http.assert_not_called()
    assert probe["reason"] == autoconfig.PROBE_SITE_PAUSED
    assert probe["corroborated"] is False


@pytest.mark.parametrize("refusal", [403, 429])
def test_autoconfigure_probe_refusal_pauses_the_site(monkeypatch, refusal):
    from app.services.listing_capture import autoconfig

    monkeypatch.setattr(
        "app.services.listing_capture.observation.listing_live_fetch_enabled", lambda: True
    )
    row, listings, session = _probe_inputs()
    store = MemorySitePauseStore()
    _clock, policy = _policy(store)
    http = MagicMock(return_value=(refusal, "<html>blocked</html>"))
    probe = autoconfig._gated_probe(
        session,
        tenant_id=TENANT,
        site_key=SITE_KEY,
        row=row,
        listings=listings,
        http_get=http,
        policy=policy,
    )
    assert http.call_count == 1
    # Reported as the HTTP status it got (capture health shows it), and the site is paused
    # for the poll and discovery too.
    assert probe["reason"] == autoconfig.PROBE_HTTP_STATUS
    assert probe["status"] == refusal
    assert store.get(SITE_KEY)["http_status"] == refusal


def test_autoconfigure_probe_waits_the_site_spacing_after_discovery(monkeypatch):
    from app.services.listing_capture import autoconfig

    monkeypatch.setattr(
        "app.services.listing_capture.observation.listing_live_fetch_enabled", lambda: True
    )
    row, listings, session = _probe_inputs()
    clock, policy = _policy()
    gate = SiteFetchGate(site_key=SITE_KEY, spacing_seconds=2, policy=policy)
    gate.get(lambda url: (200, "x"), f"{HOST}/search")  # discovery's last request
    autoconfig._gated_probe(
        session,
        tenant_id=TENANT,
        site_key=SITE_KEY,
        row=row,
        listings=listings,
        http_get=lambda url, headers=None: (200, "<html></html>"),
        policy=policy.fork(),
    )
    assert clock.sleeps == [2.0]


def test_autoconfigure_probe_stops_when_the_budget_is_spent(monkeypatch):
    from app.services.listing_capture import autoconfig

    monkeypatch.setattr(
        "app.services.listing_capture.observation.listing_live_fetch_enabled", lambda: True
    )
    row, listings, session = _probe_inputs()
    clock, policy = _policy(limit=1.0)
    clock.t = 5.0
    http = MagicMock(return_value=(200, "<html></html>"))
    probe = autoconfig._gated_probe(
        session,
        tenant_id=TENANT,
        site_key=SITE_KEY,
        row=row,
        listings=listings,
        http_get=http,
        policy=policy,
    )
    http.assert_not_called()
    assert probe["reason"] == autoconfig.PROBE_TIME_LIMIT


def test_steward_autoconfigure_uses_the_short_budget(monkeypatch):
    from contextlib import nullcontext

    from app.api.v1.endpoints import listing_capture as endpoint
    from app.services.listing_capture.site_fetch import STEWARD_RUN_TIME_LIMIT_SECONDS

    seen: dict = {}

    def fake_autoconfigure(_session, **kwargs):
        seen.update(kwargs)
        return {"configured": [], "excluded": [], "needs_pattern": []}

    monkeypatch.setattr(
        "app.services.listing_capture.autoconfig.autoconfigure_sites", fake_autoconfigure
    )
    monkeypatch.setattr(endpoint, "SessionLocal", lambda: nullcontext(MagicMock()))
    monkeypatch.setattr(endpoint, "tenant_id_from_user", lambda _user: TENANT)
    out = endpoint.post_autoconfigure_sites(user={"id": 1})
    assert seen["time_limit_seconds"] == STEWARD_RUN_TIME_LIMIT_SECONDS
    assert STEWARD_RUN_TIME_LIMIT_SECONDS <= 60
    assert out["data_unavailable"] is False


def test_autoconfigure_gives_discovery_and_probes_the_budget(monkeypatch):
    from app.services.listing_capture import autoconfig

    monkeypatch.setattr(
        "app.services.listing_capture.observation.listing_live_fetch_enabled", lambda: True
    )
    monkeypatch.setattr(autoconfig, "_advisory_lock", lambda *_a: None)
    monkeypatch.setattr(autoconfig, "_tenant_ids", lambda *_a: [TENANT])
    monkeypatch.setattr(autoconfig, "_site_run_summary", lambda *_a: [])
    policies: dict = {}

    def fake_discover(_session, **kwargs):
        policies["discovery"] = kwargs["fetch_policy"]
        return {"customers": []}

    def fake_configure(_session, _tid, **kwargs):
        policies["probe"] = kwargs["policy"]
        return []

    monkeypatch.setattr(discovery, "discover_reporting_customers", fake_discover)
    monkeypatch.setattr(autoconfig, "_configure_tenant", fake_configure)
    autoconfig.autoconfigure_sites(
        MagicMock(),
        tenant_id=TENANT,
        http_get=lambda url: (200, ""),
        run_store=MemorySitePauseStore(),
        time_limit_seconds=30,
    )
    assert policies["discovery"].time_limit_seconds == 30
    assert policies["probe"].time_limit_seconds == 30
    assert policies["probe"] is not policies["discovery"]
    # Same pause store and per-site spacing, so a probe is spaced from discovery's requests.
    assert policies["probe"].store is policies["discovery"].store
    assert policies["probe"].last_request_at is policies["discovery"].last_request_at
