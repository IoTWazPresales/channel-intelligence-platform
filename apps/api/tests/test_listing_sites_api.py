"""Sites & sellers API: steward-only writes, data-driven /meta. cip_test only; rows are removed after.

Fictional site keys and customer. Skips on any database other than cip_test.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.session_sync import SessionLocal
from app.main import app

STEWARD = {"X-User-Role": "steward"}
VIEWER = {"X-User-Role": "viewer"}


@pytest.fixture()
def fixture_ids():
    with SessionLocal() as session:
        db = session.execute(text("select current_database()")).scalar_one()
        if db != "cip_test":
            pytest.skip(f"listing sites API test runs on cip_test only (current_database()={db})")
        tag = uuid.uuid4().hex[:6]
        customer_id = session.execute(
            text(
                "insert into dim_customer (code, name, customer_status, is_key_account, tenant_id) "
                "values (:c, :n, 'active', false, 'default') returning id"
            ),
            {"c": f"API-{tag}", "n": f"Api Customer {tag}"},
        ).scalar_one()
        session.commit()
    key = f"api-{tag}"
    try:
        yield {"customer_id": int(customer_id), "key": key}
    finally:
        with SessionLocal() as session:
            session.execute(text("delete from listing_site where site_key = :k"), {"k": key})
            session.execute(text("delete from dim_customer where id = :i"), {"i": customer_id})
            session.commit()


def test_steward_manages_sites_and_sellers_viewer_cannot(fixture_ids) -> None:
    client = TestClient(app)
    key, customer_id = fixture_ids["key"], fixture_ids["customer_id"]

    denied = client.post("/api/v1/listing-capture/sites", json={"site_key": key}, headers=VIEWER)
    assert denied.status_code == 403

    created = client.post("/api/v1/listing-capture/sites", json={"site_key": key, "display_name": "Api Shop"}, headers=STEWARD)
    assert created.status_code == 200, created.text
    site = created.json()
    assert site["site_key"] == key and site["configured"] is False and site["missing_fields"] == ["adapter_key"]

    meta = client.get("/api/v1/listing-capture/meta", headers=VIEWER).json()
    assert key in meta["marketplaces"]
    assert {"site_key": key, "display_name": "Api Shop", "configured": False} in meta["sites"]
    assert "html_page" in meta["adapter_keys"] and "rest_buybox_json" in meta["adapter_keys"]

    bad = client.patch(f"/api/v1/listing-capture/sites/{site['id']}", json={"page_id_pattern": "x"}, headers=STEWARD)
    assert bad.status_code == 422 and "capture group" in bad.json()["detail"]

    patched = client.patch(
        f"/api/v1/listing-capture/sites/{site['id']}",
        json={"adapter_key": "html_page", "first_party_seller": "Api Shop Retail", "rate_limit_seconds": 3},
        headers=STEWARD,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["configured"] is True

    seller = client.put(
        f"/api/v1/listing-capture/sites/{site['id']}/sellers/{customer_id}",
        json={"seller_names": ["Api Shop Retail"], "seller_ids": []},
        headers=STEWARD,
    )
    assert seller.status_code == 200, seller.text
    sellers = seller.json()["sellers"]
    assert sellers[0]["customer_id"] == customer_id and sellers[0]["seller_names"] == ["Api Shop Retail"]
    assert sellers[0]["customer_name"].startswith("Api Customer")

    listed = client.get("/api/v1/listing-capture/sites", headers=VIEWER).json()
    assert any(r["site_key"] == key and r["sellers"] for r in listed["items"])

    removed = client.delete(f"/api/v1/listing-capture/sites/{site['id']}/sellers/{customer_id}", headers=STEWARD)
    assert removed.status_code == 200 and removed.json()["sellers"] == []
    assert client.delete(f"/api/v1/listing-capture/sites/{site['id']}/sellers/{customer_id}", headers=STEWARD).status_code == 404

    listing = client.post(
        "/api/v1/listing-capture/listings",
        json={"customer_id": customer_id, "url": f"https://{key}.example.test/p/1", "marketplace": key},
        headers=STEWARD,
    )
    assert listing.status_code == 200, listing.text
    assert listing.json()["site_name"] == "Api Shop" and listing.json()["site_configured"] is True
    unknown = client.post(
        "/api/v1/listing-capture/listings",
        json={"customer_id": customer_id, "url": "https://x.example.test/p", "marketplace": f"{key}-none"},
        headers=STEWARD,
    )
    assert unknown.status_code == 422 and "unknown site" in unknown.json()["detail"]
    with SessionLocal() as session:
        session.execute(text("delete from customer_listing where customer_id = :i"), {"i": customer_id})
        session.commit()
