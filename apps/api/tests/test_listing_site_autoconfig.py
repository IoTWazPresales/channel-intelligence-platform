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

from app.models.customer_report_config import CustomerReportConfig
from app.models.dimensions import DimCustomer, DimProduct
from app.models.listing_capture import CustomerListing
from app.models.listing_site import ListingSite
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


@pytest.fixture()
def db_session():
    from app.core.config import get_settings

    get_settings.cache_clear()
    url = get_settings().database_url_sync
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
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


def test_autoconfigure_task_is_scheduled_before_the_half_hour_poll() -> None:
    schedule = build_beat_schedule()
    auto = schedule["listing-capture-autoconfigure"]
    poll = schedule["listing-capture-poll"]
    assert auto["task"] == "listing_capture.autoconfigure_sites"
    assert poll["task"] == "listing_capture.poll_listings"
    assert auto["schedule"].hour == {5}
    assert auto["schedule"].minute == {20}
    assert 30 in poll["schedule"].minute
    if dev_beat_disabled():
        from app.worker.tasks import listing_capture_autoconfigure_sites_task

        skipped = listing_capture_autoconfigure_sites_task.run()
        assert skipped == {"skipped": True, "reason": "dev_beat_disabled"}


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


def test_html_probe_configures_and_mixed_urls_need_a_pattern(db_session: Session) -> None:
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
    assert reasons[no_seller.id] == "no_seller_data"
    assert silent.id not in {row["customer_id"] for bucket in report.values() for row in bucket}
    seller_site = _site(db_session, tenant, "shop-a")
    assert seller_site.adapter_key == "html_page"
    assert seller_site.sellers == []
    health = capture_health(db_session, tenant_id=tenant)
    health_reasons = {(row["customer_id"], row["reason"]) for row in health["exclusions"]}
    assert (no_key.id, "no_site_key") in health_reasons
    assert (no_seller.id, "no_seller_data") in health_reasons


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


def test_no_site_literals(db_session: Session) -> None:
    db = db_session.execute(text("select current_database()")).scalar_one()
    print("current_database()", db)
    assert db == "cip_test"
    keys = [
        str(key)
        for key in db_session.execute(text("select distinct site_key from listing_site where site_key <> ''")).scalars().all()
        if key and len(str(key)) >= 2
    ]
    api_root = Path(__file__).resolve().parents[1]
    hits: list[str] = []
    for root in (api_root / "app", api_root / "alembic"):
        for path in root.rglob("*"):
            if "__pycache__" in path.parts or path.suffix.lower() not in {".py", ".sql", ".mako"}:
                continue
            source = path.read_text(encoding="utf-8", errors="replace")
            for key in keys:
                pattern = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(key) + r"(?![A-Za-z0-9_])")
                for line_no, line in enumerate(source.splitlines(), start=1):
                    if pattern.search(line):
                        hits.append(f"{path.relative_to(api_root)}:{line_no}: {key}")
    assert hits == [], "listing_site keys from cip_test must not be literals in app/ or alembic/:\n" + "\n".join(hits)


def _count_sites(session: Session, tenant: str, site_key: str) -> int:
    return int(
        session.execute(
            text("select count(*) from listing_site where tenant_id = :t and site_key = :k"),
            {"t": tenant, "k": site_key},
        ).scalar_one()
    )
