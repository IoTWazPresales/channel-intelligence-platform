"""Listing-site autoconfigure on cip_test only. No live HTTP.

Customer ``code`` is unique across the whole database, so two tenants cannot share a
customer code. The shared code under test is the site key.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.models.cst_listing_seed import CstListingSeed
from app.models.customer_report_config import CustomerReportConfig
from app.models.dimensions import DimCustomer, DimProduct
from app.models.listing_capture import CustomerListing
from app.models.listing_site import ListingSite
from app.services.imports.cst_d1 import apply_listing_seed_fields
from app.services.listing_capture.autoconfig import autoconfigure_sites, capture_health
from app.services.listing_capture.registry import poll_active_listings
from app.services.listing_capture.site_pause import MemorySitePauseStore
from app.worker.celery_app import build_beat_schedule
from app.worker.celery_queues import dev_beat_disabled

_PAGE = (
    '{"gtin13":"4006381333931"}\n'
    '"priceCurrency": "ZAR", "price": 199.00'
)
_EAN = "4006381333931"
_KEPT_PRODUCT = "https://shop-a.example.test/kept/{page_id}"
_KEPT_PAGE_ID = r"^https://shop-a\.example\.test/kept/([^/]+)$"


def _sync_url() -> str:
    """Point the sync URL at cip_test when settings still name cip. Never print the URL."""
    from sqlalchemy.engine import make_url

    from app.core.config import get_settings

    get_settings.cache_clear()
    url = get_settings().database_url_sync
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    parsed = make_url(url)
    if (parsed.database or "").casefold() == "cip":
        parsed = parsed.set(database="cip_test")
    return parsed.render_as_string(hide_password=False)


@pytest.fixture()
def db_session():
    url = _sync_url()
    eng = create_engine(url)
    try:
        conn = eng.connect()
    except Exception as exc:  # pragma: no cover - environment
        pytest.skip(f"no database: {type(exc).__name__}")
    db = conn.execute(text("select current_database()")).scalar_one()
    print("current_database()", db)
    if db != "cip_test":
        conn.close()
        eng.dispose()
        pytest.skip(f"listing autoconfigure tests run on cip_test only (current_database()={db})")
    conn.rollback()
    tx = conn.begin()
    session = Session(bind=conn)
    try:
        yield session
    finally:
        session.close()
        tx.rollback()
        conn.close()
        eng.dispose()


def _customer(session: Session, tenant: str, label: str) -> DimCustomer:
    tag = uuid.uuid4().hex[:8]
    row = DimCustomer(
        code=f"{label}-{tag}",
        name=f"{label} {tag}",
        customer_status="active",
        is_key_account=False,
        tenant_id=tenant,
    )
    session.add(row)
    session.flush()
    return row


def _report(session: Session, customer: DimCustomer, seed: dict | None, *, expected: bool = True) -> None:
    profile = {"listing_seed": seed} if seed is not None else {}
    session.add(
        CustomerReportConfig(
            customer_id=int(customer.id),
            reports_expected=expected,
            feed_profile_json=profile or None,
        )
    )
    session.flush()


def _product(session: Session, tenant: str) -> DimProduct:
    tag = uuid.uuid4().hex[:8]
    row = DimProduct(tenant_id=tenant, sku=f"sku-{tag}", name=f"Item {tag}", ean=_EAN, is_active=True)
    session.add(row)
    session.flush()
    return row


def _listing(
    session: Session,
    customer: DimCustomer,
    *,
    site_key: str,
    url: str,
    product: DimProduct | None = None,
) -> CustomerListing:
    row = CustomerListing(
        customer_id=int(customer.id),
        product_id=int(product.id) if product is not None else None,
        url=url,
        marketplace=site_key,
        status="active",
        source="manual",
    )
    session.add(row)
    session.flush()
    return row


def _site(session: Session, tenant: str, site_key: str) -> ListingSite:
    row = session.scalar(
        text("select id from listing_site where tenant_id = :t and site_key = :k"),
        {"t": tenant, "k": site_key},
    )
    assert row is not None
    found = session.get(ListingSite, int(row))
    assert found is not None
    return found


def test_autoconfigure_runs_daily_at_0520_and_poll_runs_every_30_minutes() -> None:
    schedule = build_beat_schedule()
    auto = schedule["listing-capture-autoconfigure"]
    poll = schedule["listing-capture-poll"]
    assert auto["task"] == "listing_capture.autoconfigure_sites"
    assert poll["task"] == "listing_capture.poll_listings"
    assert auto["schedule"].hour == {5}
    assert auto["schedule"].minute == {20}
    assert set(poll["schedule"].minute) == {0, 30}
    assert len(set(poll["schedule"].hour)) > 1
    if dev_beat_disabled():
        from app.worker.tasks import listing_capture_autoconfigure_sites_task

        skipped = listing_capture_autoconfigure_sites_task.run()
        assert skipped == {"skipped": True, "reason": "dev_beat_disabled"}


def test_autoconfigure_task_does_not_pass_http_when_live_fetch_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CIP_LISTING_LIVE_FETCH", raising=False)
    seen: dict[str, object] = {}

    def fake_auto(session, *, tenant_id=None, http_get=None):
        seen["http_get"] = http_get
        return {"configured": [], "excluded": [], "needs_pattern": [], "live_fetch_disabled": True}

    class _Session:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def commit(self):
            seen["committed"] = True

    monkeypatch.setattr("app.services.listing_capture.autoconfig.autoconfigure_sites", fake_auto)
    monkeypatch.setattr("app.db.session_sync.SessionLocal", lambda: _Session())
    from app.worker.tasks import listing_capture_autoconfigure_sites_task

    result = listing_capture_autoconfigure_sites_task.run(on_demand=True)
    assert seen["http_get"] is None
    assert result["live_fetch_disabled"] is True
    assert seen["committed"] is True


def test_seed_configures_a_site_and_a_second_run_does_not_change_it(db_session: Session) -> None:
    tenant = f"t-seed-{uuid.uuid4().hex[:6]}"
    customer = _customer(db_session, tenant, "seed")
    _report(
        db_session,
        customer,
        {
            "marketplace": "shop-a",
            "seller_names": ["Seed Seller"],
            "site": {"adapter_key": "html_page", "display_name": "Shop A", "rate_limit_seconds": 0},
        },
    )
    _listing(db_session, customer, site_key="shop-a", url="https://shop-a.example.test/p/111")
    _listing(db_session, customer, site_key="shop-a", url="https://shop-a.example.test/p/222")

    def boom(url, headers=None):
        raise AssertionError(f"unexpected fetch {url}")

    first = autoconfigure_sites(db_session, tenant_id=tenant, http_get=boom)
    assert [row["customer_id"] for row in first["configured"]] == [customer.id]
    assert first["excluded"] == [] and first["needs_pattern"] == []
    site = _site(db_session, tenant, "shop-a")
    assert site.display_name == "Shop A"
    assert site.adapter_key == "html_page"
    assert site.product_url_pattern == "https://shop-a.example.test/p/{page_id}"
    assert site.page_id_pattern
    assert site.updated_by == "listing-autoconfigure"
    seller = site.sellers[0]
    snapshot = (
        site.adapter_key,
        site.product_url_pattern,
        site.page_id_pattern,
        site.display_name,
        site.updated_by,
        list(seller.seller_names),
        seller.updated_by,
    )

    second = autoconfigure_sites(db_session, tenant_id=tenant, http_get=boom)
    db_session.refresh(site)
    db_session.refresh(seller)
    assert [row["outcome"] for row in second["configured"]] == ["configured"]
    assert (
        site.adapter_key,
        site.product_url_pattern,
        site.page_id_pattern,
        site.display_name,
        site.updated_by,
        list(seller.seller_names),
        seller.updated_by,
    ) == snapshot
    count = db_session.execute(
        text("select count(*) from listing_site where tenant_id = :t and site_key = 'shop-a'"),
        {"t": tenant},
    ).scalar_one()
    assert count == 1


def test_steward_fields_are_not_overwritten(db_session: Session) -> None:
    from app.services.listing_capture import sites as site_service

    tenant = f"t-keep-{uuid.uuid4().hex[:6]}"
    customer = _customer(db_session, tenant, "keep")
    row = site_service.create_site(
        db_session,
        tenant_id=tenant,
        site_key="shop-a",
        fields={
            "display_name": "Kept",
            "adapter_key": "rest_buybox_json",
            "product_url_pattern": _KEPT_PRODUCT,
            "page_id_pattern": _KEPT_PAGE_ID,
            "details_url_pattern": "https://shop-a.example.test/api/{page_id}",
            "search_url_pattern": "https://shop-a.example.test/search?q={query}",
            "first_party_seller": "Kept Counter",
            "rate_limit_seconds": "1.5",
        },
        actor="steward@x",
    )
    site_service.set_site_seller(
        db_session,
        row,
        customer_id=int(customer.id),
        seller_names=["Kept Seller"],
        seller_ids=["kept-1"],
        actor="steward@x",
    )
    _report(
        db_session,
        customer,
        {
            "marketplace": "shop-a",
            "seller_names": ["Other Seller"],
            "seller_ids": ["other-9"],
            "site": {
                "adapter_key": "html_page",
                "display_name": "Replaced",
                "product_url_pattern": "https://shop-a.example.test/other/{page_id}",
                "page_id_pattern": r"^https://shop-a\.example\.test/other/(\d+)$",
                "details_url_pattern": "https://shop-a.example.test/other-api/{page_id}",
                "search_url_pattern": "https://shop-a.example.test/other-search?q={query}",
                "first_party_seller": "Other Counter",
                "rate_limit_seconds": 9,
            },
        },
    )
    _listing(db_session, customer, site_key="shop-a", url="https://shop-a.example.test/p/111")

    def boom(url, headers=None):
        raise AssertionError(url)

    report = autoconfigure_sites(db_session, tenant_id=tenant, http_get=boom)
    assert report["configured"][0]["customer_id"] == customer.id
    db_session.refresh(row)
    assert row.adapter_key == "rest_buybox_json"
    assert row.product_url_pattern == _KEPT_PRODUCT
    assert row.page_id_pattern == _KEPT_PAGE_ID
    assert row.details_url_pattern == "https://shop-a.example.test/api/{page_id}"
    assert row.search_url_pattern == "https://shop-a.example.test/search?q={query}"
    assert row.first_party_seller == "Kept Counter"
    assert float(row.rate_limit_seconds) == 1.5
    assert row.display_name == "Kept"
    assert row.updated_by == "steward@x"
    assert [(s.customer_id, s.seller_names, s.seller_ids, s.updated_by) for s in row.sellers] == [
        (customer.id, ["Kept Seller"], ["kept-1"], "steward@x")
    ]


def test_html_probe_configures_and_mixed_urls_need_a_pattern(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CIP_LISTING_LIVE_FETCH", "1")
    tenant = f"t-html-{uuid.uuid4().hex[:6]}"
    product = _product(db_session, tenant)
    html_customer = _customer(db_session, tenant, "html")
    mixed_customer = _customer(db_session, tenant, "mixed")
    _report(db_session, html_customer, {"marketplace": "shop-a", "seller_names": ["Html Seller"], "site": {"rate_limit_seconds": 0}})
    _report(db_session, mixed_customer, {"marketplace": "shop-b", "seller_names": ["Mixed Seller"]})
    _listing(
        db_session,
        html_customer,
        site_key="shop-a",
        url="https://shop-a.example.test/p/111",
        product=product,
    )
    _listing(
        db_session,
        html_customer,
        site_key="shop-a",
        url="https://shop-a.example.test/p/222",
        product=product,
    )
    # A second marketplace on the same customer is ignored when the seed names one site.
    _listing(db_session, html_customer, site_key="shop-z", url="https://shop-z.example.test/p/1", product=product)
    _listing(db_session, mixed_customer, site_key="shop-b", url="https://shop-b.example.test/p/111", product=product)
    _listing(db_session, mixed_customer, site_key="shop-b", url="https://other.example.test/p/222", product=product)
    calls: list[str] = []

    def http_get(url, headers=None):
        calls.append(url)
        if "shop-a" in url:
            return 200, _PAGE
        return 200, "<html><title>no identity</title></html>"

    report = autoconfigure_sites(db_session, tenant_id=tenant, http_get=http_get)
    by_customer = {row["customer_id"]: row for row in report["configured"] + report["needs_pattern"] + report["excluded"]}
    assert by_customer[html_customer.id]["outcome"] == "configured"
    assert by_customer[html_customer.id]["pattern_status"] == "derived"
    assert by_customer[mixed_customer.id]["outcome"] == "needs_pattern"
    assert by_customer[mixed_customer.id]["reason"] == "needs_details_pattern"
    assert by_customer[mixed_customer.id]["pattern_status"] == "mixed"
    assert "shop-z" not in {row["site_key"] for row in by_customer.values()}
    html_site = _site(db_session, tenant, "shop-a")
    mixed_site = _site(db_session, tenant, "shop-b")
    assert html_site.adapter_key == "html_page"
    assert html_site.product_url_pattern == "https://shop-a.example.test/p/{page_id}"
    assert mixed_site.adapter_key is None
    assert mixed_site.product_url_pattern is None
    assert mixed_site.page_id_pattern is None
    assert any("shop-a" in url for url in calls)
    assert any("shop-b" in url for url in calls)

    def poll_get(url, headers=None):
        return 200, _PAGE

    polled = poll_active_listings(
        db_session,
        marketplaces=["shop-a"],
        http_get=poll_get,
        pause_store=MemorySitePauseStore(),
        sleep=lambda _seconds: None,
        log_result=False,
    )
    assert polled["skipped_not_configured"] == {}
    assert polled["polled"] >= 1
    health = capture_health(db_session, tenant_id=tenant)
    shop_a = next(row for row in health["sites"] if row["site_key"] == "shop-a")
    assert shop_a["configured"] is True
    assert shop_a["skipped_not_configured"] == 0
    assert shop_a["listings_due"] >= 1
    assert shop_a["newest_observation"]["status"] == "ok"
    assert shop_a["newest_observation"]["price"] == 199.0
    assert health["skipped_not_configured"].get("shop-a", 0) == 0


def test_excluded_customers_keep_their_reason(db_session: Session) -> None:
    tenant = f"t-ex-{uuid.uuid4().hex[:6]}"
    no_key = _customer(db_session, tenant, "nokey")
    no_seller = _customer(db_session, tenant, "noseller")
    silent = _customer(db_session, tenant, "silent")
    _report(db_session, no_key, None)
    _report(
        db_session,
        no_seller,
        {"marketplace": "shop-a", "site": {"adapter_key": "html_page"}},
    )
    _report(db_session, silent, {"marketplace": "shop-b", "seller_names": ["Silent"], "site": {"adapter_key": "html_page"}}, expected=False)

    report = autoconfigure_sites(db_session, tenant_id=tenant, http_get=lambda url, headers=None: (_ for _ in ()).throw(AssertionError(url)))
    reasons = {row["customer_id"]: row["reason"] for row in report["excluded"]}
    assert reasons[no_key.id] == "no_site_key"
    assert no_seller.id not in reasons
    assert no_seller.id in {row["customer_id"] for row in report["configured"]}
    buckets = [value for value in report.values() if isinstance(value, list)]
    assert silent.id not in {row["customer_id"] for bucket in buckets for row in bucket}
    seller_site = _site(db_session, tenant, "shop-a")
    db_session.refresh(seller_site)
    assert seller_site.adapter_key == "html_page"
    assert seller_site.first_party_seller == no_seller.name
    assert seller_site.sellers[0].seller_names == [no_seller.name]
    assert seller_site.sellers[0].seller_ids == []
    health = capture_health(db_session, tenant_id=tenant)
    health_reasons = {(row["customer_id"], row["reason"]) for row in health["exclusions"]}
    assert (no_key.id, "no_site_key") in health_reasons
    assert all(row["customer_id"] != no_seller.id for row in health["exclusions"])
    assert isinstance(health["coverage"], dict)


def test_missing_adapter_and_seller_reports_both_reasons(db_session: Session) -> None:
    tenant = f"t-both-{uuid.uuid4().hex[:6]}"
    customer = _customer(db_session, tenant, "both")
    _report(db_session, customer, {"marketplace": "shop-b"})
    _listing(db_session, customer, site_key="shop-b", url="https://shop-b.example.test/only")
    report = autoconfigure_sites(db_session, tenant_id=tenant)
    needs = [row for row in report["needs_pattern"] if row["customer_id"] == customer.id]
    excluded = [row for row in report["excluded"] if row["customer_id"] == customer.id]
    assert len(needs) == 1 and len(excluded) == 1
    assert needs[0] is excluded[0]
    assert needs[0]["reasons"] == ["needs_details_pattern", "no_seller_data"]
    assert needs[0]["reason"] is None
    assert all(row["customer_id"] != customer.id for row in report["configured"])
    health = capture_health(db_session, tenant_id=tenant)
    health_rows = [row for row in health["exclusions"] if row["customer_id"] == customer.id]
    assert len(health_rows) == 1
    assert health_rows[0]["reasons"] == ["needs_details_pattern", "no_seller_data"]


def test_live_fetch_off_does_not_call_http(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CIP_LISTING_LIVE_FETCH", raising=False)
    tenant = f"t-off-{uuid.uuid4().hex[:6]}"
    product = _product(db_session, tenant)
    customer = _customer(db_session, tenant, "off")
    _report(db_session, customer, {"marketplace": "shop-a", "seller_names": ["Seller"]})
    _listing(db_session, customer, site_key="shop-a", url="https://shop-a.example.test/p/111", product=product)
    calls: list[str] = []

    def http_get(url, headers=None):
        calls.append(url)
        return 200, _PAGE

    report = autoconfigure_sites(db_session, tenant_id=tenant, http_get=http_get)
    assert calls == []
    assert report["live_fetch_disabled"] is True
    assert _site(db_session, tenant, "shop-a").adapter_key is None


def test_probe_refused_with_403_is_recorded_warned_and_shown_in_health(
    db_session: Session, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """W1-D: the probe outcome is kept per site, a site left without a reader is logged at
    WARNING with its unpolled count, and capture health shows it (with the last poll run cut
    to this tenant)."""
    import logging

    from app.services.listing_capture.site_pause import RUN_POLL, save_run_state

    monkeypatch.setenv("CIP_LISTING_LIVE_FETCH", "1")
    tenant = f"t-403-{uuid.uuid4().hex[:6]}"
    product = _product(db_session, tenant)
    customer = _customer(db_session, tenant, "refused")
    _report(db_session, customer, {"marketplace": "shop-a", "seller_names": ["Refused Seller"]})
    url = "https://shop-a.example.test/p/403"
    listing = _listing(db_session, customer, site_key="shop-a", url=url, product=product)
    calls: list[str] = []

    def http_get(url, headers=None):
        calls.append(url)
        return 403, "<html>forbidden</html>"

    store = MemorySitePauseStore()
    with caplog.at_level(logging.WARNING):
        report = autoconfigure_sites(
            db_session, tenant_id=tenant, http_get=http_get, run_store=store
        )

    assert calls == [listing.url]
    entry = next(row for row in report["needs_pattern"] if row["customer_id"] == customer.id)
    assert entry["probe"] == {
        "corroborated": False,
        "reason": "http_status_not_200",
        "status": 403,
        "listing_id": listing.id,
    }
    site = next(row for row in report["run"]["sites"] if row["site_key"] == "shop-a")
    assert site["tenant_id"] == tenant
    assert site["configured"] is False
    assert site["skipped_not_configured"] == 1
    assert site["missing_fields"] == ["adapter_key"]
    assert [(p["customer_id"], p["status"], p["reason"]) for p in site["probes"]] == [
        (customer.id, 403, "http_status_not_200")
    ]
    assert _site(db_session, tenant, "shop-a").adapter_key is None
    warned = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    loud = f"site shop-a (tenant {tenant}) still has no reader: 1 listings not polled"
    assert any(loud in m and "HTTP 403" in m for m in warned)

    # The poll's latest run covers every tenant; health shows only this tenant's sites.
    mine = {"site_key": "shop-a", "tenant_id": tenant, "listings": 1, "missing": ["adapter_key"]}
    theirs = {**mine, "tenant_id": "another-tenant", "listings": 9}
    save_run_state(
        RUN_POLL,
        {
            "finished_at": "2026-11-13T08:00:00+00:00",
            "stopped_reason": None,
            "not_configured_sites": [mine, theirs],
        },
        store=store,
    )
    health = capture_health(db_session, tenant_id=tenant, run_store=store)
    assert health["not_polled"] == [
        {
            "site_key": "shop-a",
            "site_id": site["site_id"],
            "listings": 1,
            "reason": "no_reader_configured",
            "missing_fields": ["adapter_key"],
            "last_probes": site["probes"],
        }
    ]
    assert health["last_poll_run"] == {
        "finished_at": "2026-11-13T08:00:00+00:00",
        "stopped_reason": None,
        "not_configured_sites": [mine],
        "listings_not_polled": 1,
    }
    assert health["last_autoconfigure_run"]["tenant_id"] == tenant
    assert health["last_autoconfigure_run"]["sites"][0]["probes"][0]["status"] == 403
    # Another tenant sees neither this tenant's autoconfigure run nor its poll entries.
    other = capture_health(db_session, tenant_id=f"t-none-{uuid.uuid4().hex[:6]}", run_store=store)
    assert other["last_autoconfigure_run"] is None
    assert other["last_poll_run"]["not_configured_sites"] == []


def test_bad_seller_seed_shapes_leave_the_other_customers_configured(db_session: Session) -> None:
    tenant = f"t-seller-{uuid.uuid4().hex[:6]}"
    broken = _customer(db_session, tenant, "broken")
    blank = _customer(db_session, tenant, "blank")
    blanks = _customer(db_session, tenant, "blanks")
    named = _customer(db_session, tenant, "named")
    good = _customer(db_session, tenant, "good")
    _report(
        db_session,
        broken,
        {"marketplace": "shop-z", "seller_names": {"bad": True}, "site": {"adapter_key": "html_page"}},
    )
    _report(
        db_session,
        blank,
        {"marketplace": "shop-a", "seller_names": "   ", "seller_ids": "  ", "site": {"adapter_key": "html_page"}},
    )
    _report(
        db_session,
        blanks,
        {"marketplace": "shop-b", "seller_names": [" ", ""], "site": {"adapter_key": "html_page"}},
    )
    _report(
        db_session,
        named,
        {
            "marketplace": "shop-c",
            "seller_names": "  Counter  ",
            "seller_ids": "  sid-9 ",
            "site": {"adapter_key": "html_page"},
        },
    )
    _report(
        db_session,
        good,
        {"marketplace": "shop-w", "seller_names": ["Good Seller"], "site": {"adapter_key": "html_page"}},
    )
    report = autoconfigure_sites(db_session, tenant_id=tenant)
    reasons = {row["customer_id"]: row["reason"] for row in report["excluded"]}
    assert reasons[broken.id] == "seller_seed_invalid"
    assert blank.id not in reasons
    assert blanks.id not in reasons
    assert {row["customer_id"] for row in report["configured"]} >= {named.id, good.id, blank.id, blanks.id}
    assert _site(db_session, tenant, "shop-c").sellers[0].seller_names == ["Counter"]
    assert _site(db_session, tenant, "shop-c").sellers[0].seller_ids == ["sid-9"]
    assert _site(db_session, tenant, "shop-w").sellers[0].seller_names == ["Good Seller"]
    shop_a = _site(db_session, tenant, "shop-a")
    db_session.refresh(shop_a)
    assert shop_a.first_party_seller == blank.name
    assert shop_a.sellers[0].seller_names == [blank.name]
    shop_b = _site(db_session, tenant, "shop-b")
    db_session.refresh(shop_b)
    assert shop_b.first_party_seller == blanks.name
    assert shop_b.sellers[0].seller_names == [blanks.name]
    assert db_session.scalar(text("select id from listing_site where tenant_id = :t and site_key = 'shop-z'"), {"t": tenant}) is None


def test_buy_box_site_does_not_take_the_customer_name(db_session: Session) -> None:
    """A marketplace reader keeps an empty seller. Discovery must not stamp the customer name."""
    tenant = f"t-bb-{uuid.uuid4().hex[:6]}"
    customer = _customer(db_session, tenant, "box")
    _report(
        db_session,
        customer,
        {
            "marketplace": "market-b",
            "site": {
                "adapter_key": "rest_buybox_json",
                "product_url_pattern": "https://market-b.example.test/x/ID{page_id}",
                "page_id_pattern": r"ID(\d{5,12})",
                "details_url_pattern": "https://api.market-b.example.test/rest/details/ID{page_id}?platform=desktop",
            },
        },
    )
    report = autoconfigure_sites(db_session, tenant_id=tenant)
    reasons = {row["customer_id"]: row["reason"] for row in report["excluded"]}
    assert reasons[customer.id] == "no_seller_data"
    assert all(row["customer_id"] != customer.id for row in report["configured"])
    site = _site(db_session, tenant, "market-b")
    db_session.refresh(site)
    assert site.adapter_key == "rest_buybox_json"
    assert not (site.first_party_seller or "").strip()
    assert site.sellers == []
    assert customer.name not in (site.first_party_seller or "")


def test_existing_first_party_seller_is_kept_when_discovery_infers_the_customer(db_session: Session) -> None:
    """An existing first-party name stays the seller identity. The customer name must not relabel it."""
    from app.services.listing_capture.adapters import seller_role_label
    from app.services.listing_capture.sites import create_site, site_config_from_row

    tenant = f"t-keep-fp-{uuid.uuid4().hex[:6]}"
    customer = _customer(db_session, tenant, "keepown")
    row = create_site(
        db_session,
        tenant_id=tenant,
        site_key="shop-a",
        fields={
            "display_name": "Kept",
            "adapter_key": "html_page",
            "first_party_seller": "Kept Counter",
        },
        actor="steward@x",
    )
    _report(db_session, customer, {"marketplace": "shop-a", "site": {"adapter_key": "html_page"}})
    report = autoconfigure_sites(db_session, tenant_id=tenant)
    assert [item["customer_id"] for item in report["configured"]] == [customer.id]
    db_session.refresh(row)
    assert row.first_party_seller == "Kept Counter"
    assert [seller.seller_names for seller in row.sellers] == [["Kept Counter"]]
    assert customer.name not in row.sellers[0].seller_names
    config = site_config_from_row(row)
    assert seller_role_label(config.is_own_seller(int(customer.id), name="Kept Counter")) == "Own"
    assert seller_role_label(config.is_own_seller(int(customer.id), name=customer.name)) == "Competition"


_OWN_SITE_SEED = {"marketplace": "shop-a", "site": {"adapter_key": "html_page"}}


def _own_site(session: Session, tenant: str, *, first_party: str | None = None) -> ListingSite:
    from app.services.listing_capture.sites import create_site

    fields = {"display_name": "Own", "adapter_key": "html_page"}
    if first_party:
        fields["first_party_seller"] = first_party
    return create_site(
        session, tenant_id=tenant, site_key="shop-a", fields=fields, actor="steward@x"
    )


def _names_by_customer(row: ListingSite) -> dict[int, list[str]]:
    return {int(seller.customer_id): list(seller.seller_names) for seller in row.sellers}


def test_r2_1_stored_seller_skips_an_invalid_seed_seller(db_session: Session) -> None:
    """A stored seller identity is kept; a bad seed seller field must not roll the site back."""
    from app.services.listing_capture.sites import set_site_seller

    tenant = f"t-r21-{uuid.uuid4().hex[:6]}"
    customer = _customer(db_session, tenant, "stored")
    row = _own_site(db_session, tenant)
    set_site_seller(
        db_session,
        row,
        customer_id=int(customer.id),
        seller_names=["North Counter"],
        seller_ids=[],
        actor="steward@x",
    )
    _report(db_session, customer, {**_OWN_SITE_SEED, "seller_names": 17})
    report = autoconfigure_sites(db_session, tenant_id=tenant)
    reasons = {item["customer_id"]: item["reason"] for item in report["excluded"]}
    assert customer.id not in reasons
    assert [item["customer_id"] for item in report["configured"]] == [customer.id]
    db_session.refresh(row)
    assert _names_by_customer(row) == {int(customer.id): ["North Counter"]}


def test_r2_2_each_customer_keeps_its_own_seller_on_a_shared_site(db_session: Session) -> None:
    """A first-party name filled from one customer never becomes another customer's seller."""
    tenant = f"t-r22-{uuid.uuid4().hex[:6]}"
    first = _customer(db_session, tenant, "north")
    second = _customer(db_session, tenant, "harbour")
    _report(db_session, first, dict(_OWN_SITE_SEED))
    _report(db_session, second, dict(_OWN_SITE_SEED))
    autoconfigure_sites(db_session, tenant_id=tenant)
    row = _site(db_session, tenant, "shop-a")
    db_session.refresh(row)
    assert _names_by_customer(row) == {
        int(first.id): [first.name],
        int(second.id): [second.name],
    }
    assert row.first_party_seller == first.name


def test_r2_3_stored_seller_blocks_the_inferred_first_party_fill(db_session: Session) -> None:
    """A steward-saved seller: discovery must not write the customer name as first party."""
    from app.services.listing_capture.sites import set_site_seller

    tenant = f"t-r23-{uuid.uuid4().hex[:6]}"
    customer = _customer(db_session, tenant, "online")
    row = _own_site(db_session, tenant)
    set_site_seller(
        db_session,
        row,
        customer_id=int(customer.id),
        seller_names=["North Counter Online"],
        seller_ids=[],
        actor="steward@x",
    )
    _report(db_session, customer, dict(_OWN_SITE_SEED))
    autoconfigure_sites(db_session, tenant_id=tenant)
    db_session.refresh(row)
    assert not (row.first_party_seller or "").strip()
    assert _names_by_customer(row) == {int(customer.id): ["North Counter Online"]}


def test_r2_4_inferred_seller_keeps_first_party_offers_own(db_session: Session) -> None:
    """A seller inferred from the customer name does not let a page-named seller decide."""
    from app.services.listing_capture.adapters import seller_role_label
    from app.services.listing_capture.adapters.html_page import parse
    from app.services.listing_capture.sites import set_site_seller, site_config_from_row

    tenant = f"t-r24-{uuid.uuid4().hex[:6]}"
    customer = DimCustomer(
        code=f"nc-{uuid.uuid4().hex[:8]}",
        name=f"North Counter (Pty) Ltd {uuid.uuid4().hex[:4]}",
        customer_status="active",
        is_key_account=False,
        tenant_id=tenant,
    )
    db_session.add(customer)
    db_session.flush()
    _report(db_session, customer, dict(_OWN_SITE_SEED))
    autoconfigure_sites(db_session, tenant_id=tenant)
    row = _site(db_session, tenant, "shop-a")
    db_session.refresh(row)
    assert row.first_party_seller == customer.name
    page = (
        '{"@type":"Offer","priceCurrency":"ZAR","price":1299.00,'
        '"seller":{"name":"North Counter"}}'
    )

    def label() -> str | None:
        config = site_config_from_row(row)
        offer = parse(page, site=config, parser_version="test").offers[0]
        return seller_role_label(config.is_own_seller(int(customer.id), name=offer["seller_name"]))

    assert label() == "Own"
    set_site_seller(
        db_session,
        row,
        customer_id=int(customer.id),
        seller_names=[customer.name],
        seller_ids=[],
        actor="steward@x",
    )
    db_session.refresh(row)
    assert label() == "Competition"


def test_r3_shared_site_reads_the_page_seller_per_customer(db_session: Session) -> None:
    """Shared site, one configured and one inferred seller: each listing follows its customer."""
    from app.services.listing_capture.registry import record_observation
    from app.services.listing_capture.sites import INFERRED_SELLER_ACTOR, set_site_seller

    tenant = f"t-r3-{uuid.uuid4().hex[:6]}"
    configured = _customer(db_session, tenant, "north")
    inferred = _customer(db_session, tenant, "harbour")
    row = _own_site(db_session, tenant, first_party="North Counter")
    set_site_seller(
        db_session,
        row,
        customer_id=int(configured.id),
        seller_names=["North Counter"],
        seller_ids=[],
        actor="steward@x",
    )
    set_site_seller(
        db_session,
        row,
        customer_id=int(inferred.id),
        seller_names=[inferred.name],
        seller_ids=[],
        actor=INFERRED_SELLER_ACTOR,
    )

    def read(customer: DimCustomer, seller: str):
        page = (
            '{"@type":"Offer","priceCurrency":"ZAR","price":1299.00,'
            f'"seller":{{"name":"{seller}"}}}}'
        )
        url = f"https://shop-a.example.test/p/{uuid.uuid4().hex[:8]}"
        listing = _listing(db_session, customer, site_key="shop-a", url=url)
        return record_observation(db_session, listing, http_get=lambda _u: (200, page))

    competitor = read(configured, "Harbour Stall")
    assert competitor.buy_box_seller == "Harbour Stall"
    assert competitor.buy_box_own is False
    own = read(configured, "North Counter")
    assert own.buy_box_seller == "North Counter"
    assert own.buy_box_own is True
    fallback = read(inferred, "Harbour Stall")
    assert fallback.buy_box_seller == "North Counter"
    assert fallback.buy_box_own is False


def test_absent_compact_flag_follows_stored_external_ids(db_session: Session) -> None:
    tenant = f"t-compact-{uuid.uuid4().hex[:6]}"
    compacted = _customer(db_session, tenant, "compacted")
    spaced = _customer(db_session, tenant, "spaced")
    db_session.add(
        CstListingSeed(
            customer_id=int(compacted.id),
            marketplace="shop-a",
            external_id="222547542",
            status="proposed",
        )
    )
    listing = _listing(db_session, spaced, site_key="shop-a", url="https://shop-a.example.test/p/1")
    listing.external_id = "111 222 333"
    db_session.flush()

    compact_row = {"listing_external_id": "333 444 555", "listing_marketplace": "shop-a"}
    apply_listing_seed_fields(
        compact_row,
        {"listing_seed": {"marketplace": "shop-a"}},
        session=db_session,
        customer_id=int(compacted.id),
    )
    assert compact_row["listing_external_id"] == "333444555"

    spaced_row = {"listing_external_id": "333 444 555", "listing_marketplace": "shop-a"}
    apply_listing_seed_fields(
        spaced_row,
        {"listing_seed": {"marketplace": "shop-a"}},
        session=db_session,
        customer_id=int(spaced.id),
    )
    assert spaced_row["listing_external_id"] == "333 444 555"


def test_second_tenant_with_the_same_site_key_does_not_collide_or_leak(db_session: Session) -> None:
    tag = uuid.uuid4().hex[:6]
    tenant_a, tenant_b = f"t-a-{tag}", f"t-b-{tag}"
    customer_a = _customer(db_session, tenant_a, "alpha")
    customer_b = _customer(db_session, tenant_b, "beta")
    _report(
        db_session,
        customer_a,
        {
            "marketplace": "shop-a",
            "seller_names": ["Seller A"],
            "site": {
                "adapter_key": "html_page",
                "product_url_pattern": "https://shop-a.example.test/a/{page_id}",
                "page_id_pattern": r"^https://shop-a\.example\.test/a/(\d+)$",
            },
        },
    )
    _report(
        db_session,
        customer_b,
        {
            "marketplace": "shop-a",
            "seller_names": ["Seller B"],
            "site": {
                "adapter_key": "html_page",
                "product_url_pattern": "https://shop-a.example.test/b/{page_id}",
                "page_id_pattern": r"^https://shop-a\.example\.test/b/(\d+)$",
            },
        },
    )
    product = _product(db_session, tenant_a)
    _listing(db_session, customer_a, site_key="shop-a", url="https://shop-a.example.test/a/7", product=product)

    only_a = autoconfigure_sites(db_session, tenant_id=tenant_a, http_get=lambda url, headers=None: (200, _PAGE))
    assert [row["tenant_id"] for row in only_a["configured"]] == [tenant_a]
    assert _count_sites(db_session, tenant_b, "shop-a") == 0

    both = autoconfigure_sites(db_session, tenant_id=tenant_b, http_get=lambda url, headers=None: (200, _PAGE))
    assert [row["tenant_id"] for row in both["configured"]] == [tenant_b]
    site_a = _site(db_session, tenant_a, "shop-a")
    site_b = _site(db_session, tenant_b, "shop-a")
    assert site_a.id != site_b.id
    assert site_a.product_url_pattern == "https://shop-a.example.test/a/{page_id}"
    assert site_b.product_url_pattern == "https://shop-a.example.test/b/{page_id}"
    assert [s.customer_id for s in site_a.sellers] == [customer_a.id]
    assert [s.seller_names for s in site_b.sellers] == [["Seller B"]]
    assert all(int(s.customer_id) != int(customer_b.id) for s in site_a.sellers)

    health_a = capture_health(db_session, tenant_id=tenant_a)
    health_b = capture_health(db_session, tenant_id=tenant_b)
    assert {row["site_key"] for row in health_a["sites"]} == {"shop-a"}
    assert {row["customer_id"] for row in health_a["configured"]} == {customer_a.id}
    assert all(row["customer_id"] != customer_b.id for row in health_a["configured"] + health_a["exclusions"])
    assert {row["customer_id"] for row in health_b["configured"]} == {customer_b.id}
    assert health_b["sites"][0]["site_id"] == site_b.id
    assert health_a["sites"][0]["site_id"] == site_a.id


# Fixture rows use marketplace="test" as a placeholder word. It is not a site key;
# scanning it would match the word "test" across the API. Every other marketplace
# value is taken from listing_seed / customer_listing fixtures and from data files.
_PLACEHOLDER_MARKETPLACES = frozenset({"test"})
_CONFIG_SKIP_DIRS = frozenset({".git", "node_modules", ".worktrees", ".venv", "venv", "__pycache__", ".next", "dist"})


def _declared_site_keys() -> set[str]:
    """Site keys named by fixtures and config. Not a hand-maintained retailer list."""
    keys: set[str] = set()
    marketplace_re = re.compile(
        r"""(?:["']marketplace["']\s*:|marketplace\s*=)\s*["']([^"']+)["']"""
    )
    tests_dir = Path(__file__).resolve().parent
    for path in tests_dir.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        source = path.read_text(encoding="utf-8", errors="replace")
        keys.update(match.group(1).strip().lower() for match in marketplace_re.finditer(source))
    repo = Path(__file__).resolve().parents[3]
    field_re = re.compile(
        r"""["'](?:site_key|marketplace)["']\s*:\s*["']([^"']+)["']"""
    )
    yaml_re = re.compile(r"""^(?:site_key|marketplace)\s*:\s*["']?([A-Za-z0-9][\w.-]*)["']?\s*$""", re.M)
    for root in (repo / "scripts", repo / "apps" / "api" / "scripts", repo / "docs"):
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or any(part in _CONFIG_SKIP_DIRS for part in path.parts):
                continue
            if path.suffix.lower() not in {".json", ".yaml", ".yml"}:
                continue
            source = path.read_text(encoding="utf-8", errors="replace")
            keys.update(match.group(1).strip().lower() for match in field_re.finditer(source))
            if path.suffix.lower() in {".yaml", ".yml"}:
                keys.update(match.group(1).strip().lower() for match in yaml_re.finditer(source))
    keys -= _PLACEHOLDER_MARKETPLACES
    return {key for key in keys if len(key) >= 4}


def test_no_site_literals(db_session: Session) -> None:
    db = db_session.execute(text("select current_database()")).scalar_one()
    print("current_database()", db)
    assert db == "cip_test"
    keys = _declared_site_keys()
    for key in db_session.execute(
        text("select distinct site_key from listing_site where site_key <> ''")
    ).scalars().all():
        text_key = str(key).strip().lower()
        if len(text_key) >= 4 and text_key not in _PLACEHOLDER_MARKETPLACES:
            keys.add(text_key)
    assert keys, "forbidden set must come from fixtures, config, or cip_test site keys"
    api_root = Path(__file__).resolve().parents[1]
    hits: list[str] = []
    patterns = [
        # Underscore is not a boundary: prefix_key and key_suffix still name the key.
        (key, re.compile(r"(?<![A-Za-z0-9])" + re.escape(key) + r"(?![A-Za-z0-9])", re.IGNORECASE))
        for key in sorted(keys)
    ]
    for root in (api_root / "app", api_root / "alembic"):
        for path in root.rglob("*"):
            if "__pycache__" in path.parts or path.suffix.lower() not in {".py", ".sql", ".mako"}:
                continue
            source = path.read_text(encoding="utf-8", errors="replace")
            for line_no, line in enumerate(source.splitlines(), start=1):
                for key, pattern in patterns:
                    if pattern.search(line):
                        hits.append(f"{path.relative_to(api_root)}:{line_no}: {key}")
    assert hits == [], (
        "site keys from fixtures, config, and cip_test must not be literals in app/ or alembic/:\n"
        + "\n".join(hits)
    )


def _count_sites(session: Session, tenant: str, site_key: str) -> int:
    return int(
        session.execute(
            text("select count(*) from listing_site where tenant_id = :t and site_key = :k"),
            {"t": tenant, "k": site_key},
        ).scalar_one()
    )
