"""Capture-health counts follow the caller's product-line scope. cip_test only.

GET /listing-capture/capture-health opens SessionLocal, the same factory as the other
listing reads. The router binds cip.product_lines for a numeric app_user, and the
session listener applies it. customer_listing is under product-line row security, so
listings_due and the newest price for a site count only the caller's lines.

NOT RUN (cloud): this file needs cip_test. Do not point it at cip.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.session_sync import SessionLocal
from app.main import app
from app.models.dimensions import DimCustomer, DimProduct
from app.models.iam import AppUser, Tenant
from app.models.listing_capture import CustomerListing, ListingObservation
from app.models.product_line_access import UserProductLineAccess

# Stub auth resolves the user by id and does not check this column. It is not a credential.
_UNUSED_AUTH_COLUMN = "unused"


def _database_name() -> str:
    with SessionLocal() as session:
        return str(session.execute(text("select current_database()")).scalar_one())


def test_capture_health_counts_honour_the_callers_product_line() -> None:
    try:
        db_name = _database_name()
    except Exception as exc:  # pragma: no cover - environment
        pytest.skip(f"no database: {type(exc).__name__}")
    if db_name != "cip_test":
        pytest.skip(f"capture-health product-line test runs on cip_test only (current_database()={db_name})")

    tag = uuid.uuid4().hex[:10]
    tenant_id = f"health-{tag}"
    line_in = f"line-in-{tag}"
    line_out = f"line-out-{tag}"
    marketplace = f"shop-{tag}"
    viewer_id = admin_id = customer_id = None
    listing_ids: list[int] = []
    product_ids: list[int] = []

    with SessionLocal() as session:
        session.add(Tenant(id=tenant_id, name=f"Health {tag}"))
        session.flush()
        viewer = AppUser(
            tenant_id=tenant_id,
            email=f"viewer-{tag}@example.invalid",
            password_hash=_UNUSED_AUTH_COLUMN,
            display_name=f"Viewer {tag}",
            role="viewer",
        )
        admin = AppUser(
            tenant_id=tenant_id,
            email=f"admin-{tag}@example.invalid",
            password_hash=_UNUSED_AUTH_COLUMN,
            display_name=f"Admin {tag}",
            role="admin",
        )
        session.add_all([viewer, admin])
        session.flush()
        viewer_id, admin_id = int(viewer.id), int(admin.id)
        session.add(
            UserProductLineAccess(
                tenant_id=tenant_id, user_id=viewer_id, product_line=line_in, can_edit=False
            )
        )
        customer = DimCustomer(
            code=f"hc-{tag}",
            name=f"Health customer {tag}",
            customer_status="active",
            is_key_account=False,
            tenant_id=tenant_id,
        )
        in_scope = DimProduct(
            tenant_id=tenant_id,
            sku=f"in-{tag}",
            name=f"In scope {tag}",
            product_line=line_in,
            is_active=True,
        )
        out_scope = DimProduct(
            tenant_id=tenant_id,
            sku=f"out-{tag}",
            name=f"Out of scope {tag}",
            product_line=line_out,
            is_active=True,
        )
        session.add_all([customer, in_scope, out_scope])
        session.flush()
        customer_id = int(customer.id)
        product_ids = [int(in_scope.id), int(out_scope.id)]
        older = datetime.now(UTC) - timedelta(days=2)
        newer = datetime.now(UTC) - timedelta(hours=1)
        in_listing = CustomerListing(
            customer_id=customer_id,
            product_id=in_scope.id,
            url=f"https://shop.example.test/{tag}/in",
            marketplace=marketplace,
            status="active",
            source="manual",
        )
        out_listing = CustomerListing(
            customer_id=customer_id,
            product_id=out_scope.id,
            url=f"https://shop.example.test/{tag}/out",
            marketplace=marketplace,
            status="active",
            source="manual",
        )
        session.add_all([in_listing, out_listing])
        session.flush()
        listing_ids = [int(in_listing.id), int(out_listing.id)]
        session.add_all(
            [
                ListingObservation(
                    listing_id=in_listing.id,
                    fetched_at=older,
                    extracted_price=111,
                    parser_version="t",
                    parse_status="ok",
                ),
                ListingObservation(
                    listing_id=out_listing.id,
                    fetched_at=newer,
                    extracted_price=222,
                    parser_version="t",
                    parse_status="ok",
                ),
            ]
        )
        session.commit()

    try:
        client = TestClient(app)
        scoped = client.get(
            "/api/v1/listing-capture/capture-health",
            headers={"X-User-Id": str(viewer_id)},
        )
        assert scoped.status_code == 200, scoped.text
        scoped_body = scoped.json()
        assert scoped_body.get("data_unavailable") is not True
        assert scoped_body["listings_due"] == 1
        scoped_site = next(row for row in scoped_body["sites"] if row["site_key"] == marketplace)
        assert scoped_site["listings_due"] == 1
        assert scoped_site["newest_observation"]["price"] == 111

        wide = client.get(
            "/api/v1/listing-capture/capture-health",
            headers={"X-User-Id": str(admin_id)},
        )
        assert wide.status_code == 200, wide.text
        wide_body = wide.json()
        assert wide_body["listings_due"] == 2
        wide_site = next(row for row in wide_body["sites"] if row["site_key"] == marketplace)
        assert wide_site["listings_due"] == 2
        # The newer reading belongs to the other product line, so only the admin sees it.
        assert wide_site["newest_observation"]["price"] == 222
    finally:
        with SessionLocal() as session:
            if listing_ids:
                session.execute(
                    text("delete from listing_observation where listing_id = any(:ids)"),
                    {"ids": listing_ids},
                )
                session.execute(
                    text("delete from customer_listing where id = any(:ids)"),
                    {"ids": listing_ids},
                )
            if product_ids:
                session.execute(text("delete from dim_product where id = any(:ids)"), {"ids": product_ids})
            if customer_id is not None:
                session.execute(text("delete from dim_customer where id = :id"), {"id": customer_id})
            session.execute(
                text("delete from user_product_line_access where tenant_id = :tid"),
                {"tid": tenant_id},
            )
            session.execute(text("delete from app_user where tenant_id = :tid"), {"tid": tenant_id})
            session.execute(text("delete from tenant where id = :tid"), {"tid": tenant_id})
            session.commit()
