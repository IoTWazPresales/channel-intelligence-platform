"""Ops upsert of listing_seed into feed_profile_json. cip_test only. Never cip."""

from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.models.customer_report_config import CustomerReportConfig
from app.models.dimensions import DimCustomer

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ops" / "upsert_listing_seed_profile.py"


def _ops():
    spec = importlib.util.spec_from_file_location("upsert_listing_seed_profile", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
        pytest.skip(f"listing seed ops tests run on cip_test only (current_database()={db})")
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


def test_refuses_cip_unless_allowed() -> None:
    ops = _ops()
    with pytest.raises(ops.DatabaseRefused):
        ops.ensure_database_allowed("cip", allow_cip=False)
    ops.ensure_database_allowed("cip", allow_cip=True)
    ops.ensure_database_allowed("cip_test", allow_cip=False)


def test_merge_pins_compact_flag_and_keeps_a_string_seller_whole() -> None:
    ops = _ops()
    merged = ops.merge_listing_seed(
        {},
        {"seller_names": "  Counter  ", "compact_spaced_numeric_external_id": False},
    )
    assert merged["listing_seed"]["seller_names"] == ["Counter"]
    assert merged["listing_seed"]["compact_spaced_numeric_external_id"] is False
    pinned = ops.merge_listing_seed(merged, {"compact_spaced_numeric_external_id": True})
    assert pinned["listing_seed"]["compact_spaced_numeric_external_id"] is True
    with pytest.raises(ops.DatabaseRefused):
        ops.merge_listing_seed({}, {"compact_spaced_numeric_external_id": "yes"})


def test_merge_keeps_unrelated_profile_keys() -> None:
    ops = _ops()
    merged = ops.merge_listing_seed(
        {"vat_basis": "inc_vat", "listing_seed": {"marketplace": "shop-a", "external_id_from": "raw_product_token"}},
        {
            "seller_names": ["Seller"],
            "seller_ids": ["s1"],
            "site": {"adapter_key": "html_page", "ignored_extra": "no"},
        },
    )
    assert merged["vat_basis"] == "inc_vat"
    seed = merged["listing_seed"]
    assert seed["marketplace"] == "shop-a"
    assert seed["external_id_from"] == "raw_product_token"
    assert seed["seller_names"] == ["Seller"]
    assert seed["seller_ids"] == ["s1"]
    assert seed["site"] == {"adapter_key": "html_page"}
    again = ops.merge_listing_seed(merged, {"seller_names": ["Seller"], "seller_ids": ["s1"], "site": {"adapter_key": "html_page"}})
    assert again == merged


def test_dry_run_does_not_write_and_apply_is_idempotent(db_session: Session) -> None:
    ops = _ops()
    tag = uuid.uuid4().hex[:8]
    customer = DimCustomer(
        code=f"seed-{tag}",
        name=f"Seed {tag}",
        customer_status="active",
        is_key_account=False,
        tenant_id=f"t-seed-{tag}",
    )
    db_session.add(customer)
    db_session.flush()
    payload = {
        "customers": [
            {
                "customer_id": int(customer.id),
                "marketplace": "shop-a",
                "seller_names": ["Seller"],
                "seller_ids": ["s1"],
                "site": {
                    "adapter_key": "html_page",
                    "product_url_pattern": "https://shop-a.example.test/p/{page_id}",
                    "page_id_pattern": "/p/([^/]+)",
                },
            }
        ]
    }
    dry = ops.apply_listing_seed_config(db_session, payload, apply=False, allow_cip=False)
    assert dry == [{"customer_id": int(customer.id), "changed": True, "applied": False}]
    stored = db_session.scalar(select(CustomerReportConfig).where(CustomerReportConfig.customer_id == customer.id))
    assert stored is None

    applied = ops.apply_listing_seed_config(db_session, payload, apply=True, allow_cip=False)
    assert applied[0]["applied"] is True
    stored = db_session.scalar(select(CustomerReportConfig).where(CustomerReportConfig.customer_id == customer.id))
    assert stored is not None
    assert stored.reports_expected is False
    seed = stored.feed_profile_json["listing_seed"]
    assert seed["seller_names"] == ["Seller"]
    assert seed["seller_ids"] == ["s1"]
    assert seed["site"]["adapter_key"] == "html_page"
    assert seed["site"]["product_url_pattern"] == "https://shop-a.example.test/p/{page_id}"

    second = ops.apply_listing_seed_config(db_session, payload, apply=True, allow_cip=False)
    assert second == [{"customer_id": int(customer.id), "changed": False, "applied": False}]
    db_session.refresh(stored)
    assert stored.feed_profile_json["listing_seed"] == seed
