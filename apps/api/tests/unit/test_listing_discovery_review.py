"""PR #95 regressions; in-memory models, mocked sessions and HTTP only."""

import re
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.endpoints import listing_capture as endpoint
from app.core.security import Role
from app.models.cst_listing_seed import CstListingSeed
from app.models.customer_report_config import CustomerReportConfig
from app.models.dimensions import DimCustomer, DimProduct
from app.models.listing_site import ListingSite, ListingSiteSeller
from app.services.listing_capture import autoconfig, discovery, observation, site_pause, sites
from app.services.listing_capture.site_pause import MemorySitePauseStore
from app.worker import celery_queues, tasks


HOST = "https://catalogue.example.test"
TENANT = "unit-tenant"


def _site(**fields):
    return ListingSite(**{
        "id": 7, "tenant_id": TENANT, "site_key": "review-catalogue", "display_name": "Catalogue",
        "adapter_key": "html_page", "is_active": True, "first_party_seller": "Counter",
        "search_url_pattern": f"{HOST}/search?q={{query}}", "sellers": [], **fields,
    })


def _product(pid=1, model="GLIDE14"):
    return DimProduct(id=pid, tenant_id=TENANT, sku=f"sku-{pid}", name=model, model_name=model)


def _page(model="GLIDE14"):
    return (
        '<script type="application/ld+json">'
        f'{{"model":"{model}","offers":{{"priceCurrency":"ZAR","price":199,'
        '"availability":"https://schema.org/InStock","seller":{"name":"Counter"}}}}'
        '</script>'
    )


def _mock_catalogue(monkeypatch, products, *, proposal=None, row=None):
    row = row if row is not None else _site()
    session = MagicMock()
    session.scalar.return_value = None
    session.get.side_effect = lambda model, pid: products.get(pid)
    customer = DimCustomer(id=11, tenant_id=TENANT, name="Counter")
    config = CustomerReportConfig(customer_id=11, reports_expected=True,
                                  feed_profile_json={"listing_seed": {"marketplace": row.site_key}})
    monkeypatch.setattr(discovery, "_reporting_customers", lambda *args: [(config, customer)])
    monkeypatch.setattr(discovery, "_load_site", lambda *args: row)
    monkeypatch.setattr(discovery, "_catalogue_product_ids", lambda *args, **kwargs: list(products))
    monkeypatch.setattr(discovery, "_has_listing", lambda *args, **kwargs: False)
    monkeypatch.setattr(discovery, "_queue_exists", lambda *args, **kwargs: False)
    monkeypatch.setattr(discovery, "_proposed_seed", lambda *args, **kwargs: proposal)
    monkeypatch.setattr(discovery, "confirmed_link", lambda *args: None)
    monkeypatch.setattr(discovery, "_rejected_urls", lambda *args: set())
    monkeypatch.setattr(discovery, "remember_link", MagicMock())
    return session


@pytest.mark.parametrize("trigger", ["scheduled", "endpoint"])
@pytest.mark.parametrize("live", [True, False])
def test_autoconfigure_entry_points_run_discovery(monkeypatch, trigger, live):
    """Exercise the real shared service from the task and an HTTP POST."""
    row = _site()
    session = _mock_catalogue(monkeypatch, {1: _product()}, row=row)
    store = MemorySitePauseStore()
    monkeypatch.setattr(site_pause, "default_run_state_store", lambda: store)
    monkeypatch.setattr(observation, "listing_live_fetch_enabled", lambda: live)
    monkeypatch.setattr(celery_queues, "dev_beat_disabled", lambda: False)
    monkeypatch.setattr(autoconfig, "_advisory_lock", MagicMock())
    monkeypatch.setattr(autoconfig, "_tenant_ids", lambda *args: [TENANT])
    monkeypatch.setattr(autoconfig, "_configure_tenant", lambda *args, **kwargs: [])
    monkeypatch.setattr(autoconfig, "_site_run_summary", lambda *args: [])
    http = MagicMock(side_effect=lambda url: (200, '<a href="/p/glide">view</a>')
                     if "/search?" in url else (200, _page()))
    monkeypatch.setattr(observation, "default_http_get", http)
    factory = MagicMock()
    factory.return_value.__enter__.return_value = session
    if trigger == "scheduled":
        from app.db import session_sync

        monkeypatch.setattr(session_sync, "SessionLocal", factory)
        report = tasks.listing_capture_autoconfigure_sites_task.run(tenant_id=TENANT)
        assert report["skipped"] is False
    else:
        monkeypatch.setattr(endpoint, "SessionLocal", factory)
        app = FastAPI()
        app.include_router(endpoint.router)
        route = next(r for r in endpoint.router.routes if r.path == "/sites/autoconfigure")
        app.dependency_overrides[route.dependant.dependencies[0].call] = lambda: {
            "tenant_id": TENANT, "role": Role.STEWARD, "id": "unit-steward",
        }
        with TestClient(app) as client:
            response = client.post("/sites/autoconfigure")
        assert response.status_code == 200
        report = response.json()
        assert report["data_unavailable"] is False
    customer = report["discovery"]["customers"][0]
    assert customer["tenant_id"] == TENANT
    assert customer["proposed_created"] == int(live)
    proposals = [call.args[0] for call in session.add.call_args_list if isinstance(call.args[0], CstListingSeed)]
    assert len(proposals) == int(live)
    if live:
        assert proposals[0].raw_json["url"] == f"{HOST}/p/glide"
        assert proposals[0].status == "proposed"
    else:
        http.assert_not_called()
        assert customer["reason"] == discovery.REASON_NO_FETCH
    session.commit.assert_called_once()


@pytest.mark.parametrize("resolver", [discovery._site_keys, autoconfig._site_keys])
@pytest.mark.parametrize("existing", ["unrelated", "matching_listing", "matching_site"])
def test_domain_only_seed_targets_its_domain(resolver, existing):
    session = MagicMock()
    listings = [("review-market", "https://unrelated.example.test/p/old")]
    sites = [_site(site_key="review-market", search_url_pattern="https://unrelated.example.test/search?q={query}")]
    if existing == "matching_listing":
        listings.append(("own-shop", f"{HOST}/p/existing"))
    if existing == "matching_site":
        sites.append(_site(site_key="own-shop"))
    session.execute.return_value.all.return_value = listings
    session.scalars.return_value.all.return_value = sites
    keys = resolver(session, tenant_id=TENANT, customer_id=11,
                    seed={"domain": "www.catalogue.example.test"})
    assert keys == (["catalogue-example-test"] if existing == "unrelated" else ["own-shop"])
    assert "review-market" not in keys
    # Both reads constrain ownership before inspecting the domain.
    statements = [session.execute.call_args.args[0], session.scalars.call_args.args[0]]
    assert all(TENANT in stmt.compile().params.values() for stmt in statements)


def test_explicit_marketplace_keeps_its_seed_target():
    session = MagicMock()
    assert discovery._site_keys(session, tenant_id=TENANT, customer_id=11,
                                seed={"marketplace": " Review-Market ", "domain": HOST}) == ["review-market"]
    session.execute.assert_not_called()


@pytest.mark.parametrize("raw", [None, {}, {"url": "  ", "feed_column": "original"}])
def test_feed_proposal_without_url_is_enriched_in_place(monkeypatch, raw):
    proposal = CstListingSeed(id=20, customer_id=11, marketplace="review-catalogue", product_id=1,
                             external_id="feed-id", import_job_id=55, status="proposed", raw_json=raw)
    session = _mock_catalogue(monkeypatch, {1: _product()}, proposal=proposal)
    http = lambda url: (200, '<a href="/p/glide">view</a>') if "/search?" in url else (200, _page())
    report = discovery.discover_reporting_customers(session, tenant_id=TENANT, http_get=http,
                                                     run_store=MemorySitePauseStore())
    assert report["customers"][0]["proposed_listings"] == 1
    added = [call.args[0] for call in session.add.call_args_list]
    assert added == [proposal]
    assert proposal.external_id == "feed-id"
    assert proposal.import_job_id == 55
    assert proposal.status == "proposed"
    assert proposal.raw_json["url"] == f"{HOST}/p/glide"
    assert proposal.raw_json["price"] == 199
    if raw and "feed_column" in raw:
        assert proposal.raw_json["feed_column"] == "original"


def test_existing_proposal_with_url_is_not_searched_again(monkeypatch):
    proposal = CstListingSeed(raw_json={"url": f"{HOST}/p/glide"})
    session = _mock_catalogue(monkeypatch, {1: _product()}, proposal=proposal)
    http = MagicMock()
    report = discovery.discover_reporting_customers(session, tenant_id=TENANT, http_get=http,
                                                     run_store=MemorySitePauseStore())
    assert report["customers"][0]["proposed_listings"] == 1
    http.assert_not_called()
    session.add.assert_not_called()


def test_feed_proposal_without_a_match_surfaces_the_failure(monkeypatch):
    proposal = CstListingSeed(id=20, product_id=1, status="proposed", raw_json={"feed": "kept"})
    session = _mock_catalogue(monkeypatch, {1: _product()}, proposal=proposal)
    http = MagicMock(return_value=(200, "no matches"))
    report = discovery.discover_reporting_customers(session, tenant_id=TENANT, http_get=http,
                                                     run_store=MemorySitePauseStore())
    assert report["customers"][0]["reason"] == discovery.REASON_NOT_FOUND
    assert report["customers"][0]["proposed_listings"] == 0
    assert http.called
    assert proposal.raw_json == {"feed": "kept"}
    session.add.assert_not_called()


def test_models_with_same_digits_have_distinct_idempotent_external_ids(monkeypatch):
    """GLIDE14 and SWIFT14 used to share external_id='14'."""
    session = _mock_catalogue(monkeypatch, {1: _product(), 2: _product(2, "SWIFT14")})
    stored = {}

    def scalar(stmt):
        values = stmt.compile().params.values()
        key = next((value for value in values if isinstance(value, str) and value.startswith("discovery:")), None)
        return stored.get(key)

    def add(row):
        if isinstance(row, CstListingSeed):
            assert row.external_id not in stored
            stored[row.external_id] = row

    session.scalar.side_effect = scalar
    session.add.side_effect = add
    # Include long shared URL prefixes so truncating the URL cannot solve this either.
    prefix = f"{HOST}/p/" + "shared-" * 25

    def http(url):
        if "/search?" in url:
            model = url.split("q=")[-1]
            return 200, f'<a href="{prefix}{model}">view</a>'
        return 200, _page("SWIFT14" if url.endswith("SWIFT14") else "GLIDE14")

    for _ in range(2):
        report = discovery.discover_reporting_customers(session, tenant_id=TENANT, http_get=http,
                                                         run_store=MemorySitePauseStore())
        assert report["customers"][0]["proposed_listings"] == 2
    assert len(stored) == 2
    assert {row.product_id for row in stored.values()} == {1, 2}
    assert all(len(key) <= 128 for key in stored)


@pytest.mark.parametrize("pattern,path", [
    (None, "/products/opaque-123"),
    (r"/catalogue/([^/?]+)", "/catalogue/opaque-123"),
    (None, "/opaque-123.html"),
])
def test_product_links_survive_navigation_before_them(monkeypatch, pattern, path):
    session = _mock_catalogue(monkeypatch, {1: _product()}, row=_site(page_id_pattern=pattern))
    seen = []

    def http(url):
        seen.append(url)
        if "/search?" in url:
            return 200, (
                '<header><nav><a href="/">Home</a><a href="/login">Login</a><a href="/cart">Cart</a>'
                '<a href="/category/GLIDE14">Category</a></nav></header>'
                f'<a href="{path}">Product</a>'
            )
        return (200, _page()) if url.endswith(path) else (200, "navigation")

    report = discovery.discover_reporting_customers(session, tenant_id=TENANT, http_get=http,
                                                     run_store=MemorySitePauseStore())
    assert report["customers"][0]["proposed_created"] == 1
    assert seen[1] == HOST + path


def test_discovery_cursor_reaches_product_26_after_empty_results(monkeypatch):
    products = {pid: _product(pid, f"MODEL{pid:03}") for pid in range(30, 0, -1)}
    session = _mock_catalogue(monkeypatch, products)
    store = MemorySitePauseStore()
    searched = []

    def http(url):
        if "/search?" in url:
            searched.append(int(url.split("MODEL")[-1]))
        return 200, "no matches"

    def run(**kwargs):
        return discovery.discover_reporting_customers(session, tenant_id=TENANT, http_get=http,
                                                       run_store=store, **kwargs)["customers"][0]["sites"][0]

    first = run()
    assert searched == list(range(1, 26))
    assert first["next_after_product_id"] == 25
    # Dry runs may inspect the next page, but never advance the stored cursor.
    run(apply=False)
    searched.clear()
    second = run()
    assert searched == list(range(26, 31))
    assert second["next_after_product_id"] is None
    searched.clear()
    run()
    assert searched == list(range(1, 26))


def test_no_live_fetch_does_not_advance_cursor(monkeypatch):
    session = _mock_catalogue(monkeypatch, {1: _product()})
    store = MemorySitePauseStore()
    key = f"discovery:{TENANT}:11:7"
    store.set(key, {"after_product_id": 17}, ttl_seconds=600)
    discovery.discover_reporting_customers(session, tenant_id=TENANT, http_get=None, run_store=store)
    assert store.get(key) == {"after_product_id": 17}


@pytest.mark.parametrize("other_key", ["discovery:other-tenant:11:7", "discovery:unit-tenant:12:7",
                                        "discovery:unit-tenant:11:8"])
def test_discovery_cursor_is_scoped_to_tenant_customer_and_site(monkeypatch, other_key):
    session = _mock_catalogue(monkeypatch, {1: _product(), 2: _product(2, "SWIFT14")})
    store = MemorySitePauseStore()
    store.set(other_key, {"after_product_id": 1}, ttl_seconds=600)
    http = MagicMock(return_value=(200, "no matches"))
    discovery.discover_reporting_customers(session, tenant_id=TENANT, http_get=http,
                                           run_store=store, product_limit=1)
    assert "GLIDE14" in http.call_args_list[0].args[0]
    assert store.get(other_key) == {"after_product_id": 1}


def test_cursor_recovers_when_catalogue_products_have_changed(monkeypatch):
    session = _mock_catalogue(monkeypatch, {1: _product()})
    store = MemorySitePauseStore()
    store.set(f"discovery:{TENANT}:11:7", {"after_product_id": 999}, ttl_seconds=600)
    http = MagicMock(return_value=(200, "no matches"))
    discovery.discover_reporting_customers(session, tenant_id=TENANT, http_get=http, run_store=store)
    assert "GLIDE14" in http.call_args_list[0].args[0]


def test_unit_guard_refuses_database_connections():
    from sqlalchemy import create_engine

    engine = create_engine("sqlite://")
    with pytest.raises(pytest.fail.Exception, match="connections are forbidden"):
        engine.connect()


@pytest.mark.parametrize("bad_fields", [
    {"seller_names": {"bad": True}},
    {"seller_ids": 42},
    {"seller": {"names": ["valid", 42]}},
    {"seller": {"ids": {"bad": True}}},
    {"site": {"seller_names": {"bad": True}}},
    {"site": {"seller_ids": [False]}},
])
def test_bad_seller_seed_cannot_leave_a_discovered_site(monkeypatch, bad_fields):
    """Run both phases with real writers and in-memory reads/savepoint rollback."""
    rows = {}
    session = MagicMock()
    session.scalar.return_value = None

    def add(row):
        if isinstance(row, ListingSite):
            if row.id is None:
                row.id = len(rows) + 1
                row.is_active = True
            rows[row.site_key] = row

    @contextmanager
    def savepoint():
        before = dict(rows)
        try:
            yield
        except Exception:
            rows.clear()
            rows.update(before)
            raise

    session.add.side_effect = add
    session.begin_nested.side_effect = savepoint
    seeds = [
        bad_fields,
        {"seller_names": "   ", "seller_ids": "  "},
        {"seller_names": [" ", ""]},
        {"seller_names": "  Counter  ", "seller_ids": "  sid-9 "},
        {"seller_names": ["Good Seller"]},
    ]
    customers = []
    for cid, fields in enumerate(seeds, 1):
        seed = {**fields, "marketplace": f"review-seller-{cid}",
                "site": {"adapter_key": "html_page", **fields.get("site", {})}}
        customers.append((
            CustomerReportConfig(customer_id=cid, reports_expected=True,
                                 feed_profile_json={"listing_seed": seed}),
            DimCustomer(id=cid, tenant_id=TENANT, name=f"Customer {cid}"),
        ))
    for module in (discovery, autoconfig):
        monkeypatch.setattr(module, "_reporting_customers", lambda *args: customers)
        monkeypatch.setattr(module, "_load_site", lambda session, tenant, key: rows.get(key))
    monkeypatch.setattr(discovery, "_catalogue_product_ids", lambda *args, **kwargs: [])
    monkeypatch.setattr(autoconfig, "_listings", lambda *args, **kwargs: [])
    monkeypatch.setattr(autoconfig, "_advisory_lock", MagicMock())
    monkeypatch.setattr(autoconfig, "_site_run_summary", lambda *args: [])
    monkeypatch.setattr(sites, "customer_tenant", lambda *args: TENANT)
    monkeypatch.setattr(observation, "listing_live_fetch_enabled", lambda: False)

    report = autoconfig.autoconfigure_sites(session, tenant_id=TENANT, run_store=MemorySitePauseStore())

    assert report["excluded"][0]["customer_id"] == 1
    assert report["excluded"][0]["reason"] == "seller_seed_invalid"
    assert {entry["customer_id"] for entry in report["configured"]} == {2, 3, 4, 5}
    assert "review-seller-1" not in rows
    assert set(rows) == {f"review-seller-{cid}" for cid in range(2, 6)}
    assert rows["review-seller-2"].sellers[0].seller_names == ["Customer 2"]
    assert rows["review-seller-3"].sellers[0].seller_names == ["Customer 3"]
    assert rows["review-seller-4"].sellers[0].seller_names == ["Counter"]
    assert rows["review-seller-4"].sellers[0].seller_ids == ["sid-9"]
    assert rows["review-seller-5"].sellers[0].seller_names == ["Good Seller"]
    assert report["discovery"]["customers"][0]["detail"] == "SellerSeedError"


def test_discovery_preserves_a_stored_seller_with_a_bad_seed(monkeypatch):
    row = _site(sellers=[ListingSiteSeller(customer_id=11, seller_names=["Stored Seller"], seller_ids=[])])
    session = _mock_catalogue(monkeypatch, {}, row=row)
    config, customer = discovery._reporting_customers(session, TENANT)[0]
    config.feed_profile_json["listing_seed"]["seller_names"] = {"bad": True}

    report = discovery.discover_reporting_customers(session, tenant_id=TENANT)

    assert report["customers"][0]["reason"] == discovery.REASON_NO_CATALOGUE
    assert row.sellers[0].seller_names == ["Stored Seller"]
    session.add.assert_not_called()


def test_application_has_no_declared_site_literals():
    """Use the existing integration test's fixture/config keys without querying a DB."""
    from tests.test_listing_site_autoconfig import _declared_site_keys

    patterns = [
        (key, re.compile(r"(?<![A-Za-z0-9])" + re.escape(key) + r"(?![A-Za-z0-9])", re.I))
        for key in sorted(_declared_site_keys())
    ]
    assert patterns
    api_root = Path(__file__).resolve().parents[2]
    hits = []
    for root in (api_root / "app", api_root / "alembic"):
        for path in root.rglob("*"):
            if "__pycache__" in path.parts or path.suffix.lower() not in {".py", ".sql", ".mako"}:
                continue
            for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                hits.extend(f"{path.relative_to(api_root)}:{line_no}: {key}"
                            for key, pattern in patterns if pattern.search(line))
    assert hits == []
