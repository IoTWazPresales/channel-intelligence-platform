"""Stock-based listing scope (24 Nov 2026). Pure tier rules, the setting, and a cip_test DB case.

DB fixtures are inserted in a fresh tenant on cip_test and always rolled back. No network.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.services import tenant_settings as ts
from app.services.listing_capture import stock_scope as sc

ON = sc.ScopeSettings(enabled=True, recent_window_days=180, recent_interval_days=7, absent_days=14)
REF = date(2026, 11, 20)


def test_tiers_follow_stock_evidence_with_hysteresis():
    assert sc.tier_for(REF, None, REF, ON) == sc.TIER_ACTIVE
    # one zero in a feed: still active until absent longer than absent_days
    assert sc.tier_for(REF - timedelta(days=14), None, REF, ON) == sc.TIER_ACTIVE
    assert sc.tier_for(REF - timedelta(days=15), None, REF, ON) == sc.TIER_RECENT
    assert sc.tier_for(REF - timedelta(days=180), None, REF, ON) == sc.TIER_RECENT
    assert sc.tier_for(REF - timedelta(days=181), None, REF, ON) == sc.TIER_HISTORICAL
    assert sc.tier_for(None, None, REF, ON) == sc.TIER_HISTORICAL
    # inbound keeps a product active; end of life does not
    assert sc.tier_for(None, None, REF, ON, inbound_open=True) == sc.TIER_ACTIVE
    assert sc.tier_for(REF, REF - timedelta(days=3), REF, ON) == sc.TIER_RECENT
    assert sc.tier_for(None, REF - timedelta(days=30), REF, ON) == sc.TIER_RECENT
    assert sc.tier_for(None, REF - timedelta(days=400), REF, ON) == sc.TIER_HISTORICAL
    # a retired date in the future is not end of life yet
    assert sc.tier_for(REF, REF + timedelta(days=30), REF, ON) == sc.TIER_ACTIVE


def test_scope_setting_needs_every_field_and_sane_days():
    check = ts.SETTING_VALIDATORS[ts.KEY_LISTING_SCOPE]
    good = {"enabled": True, "recent_window_days": 180, "recent_interval_days": 7, "absent_days": 14}
    assert check(good) == good
    for bad in (
        {"enabled": True},
        {**good, "absent_days": 180},
        {**good, "recent_interval_days": 0},
        {**good, "recent_window_days": 1.5},
        {**good, "extra": 1},
        "on",
    ):
        with pytest.raises(ValueError):
            check(bad)


@pytest.fixture()
def db_session():
    from app.core.config import get_settings

    get_settings.cache_clear()
    url = get_settings().database_url_sync.replace("postgresql://", "postgresql+psycopg://", 1)
    eng = create_engine(url)
    try:
        conn = eng.connect()
    except Exception as exc:  # pragma: no cover - environment
        pytest.skip(f"no database: {type(exc).__name__}")
    db = conn.execute(text("select current_database()")).scalar_one()
    if db != "cip_test":
        conn.close()
        eng.dispose()
        pytest.skip(f"stock scope DB test runs on cip_test only (current_database()={db})")
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


def test_scope_filters_due_listings_on_cip_test(db_session: Session):
    from app.models.dimensions import DimCustomer, DimProduct
    from app.models.facts import FactInventoryCustomer

    tag = uuid.uuid4().hex[:8]
    tenant = f"t-scope-{tag}"
    customer = DimCustomer(code=f"SC-{tag}", name=f"Scope {tag}", customer_status="active",
                           is_key_account=False, tenant_id=tenant)
    products = [DimProduct(tenant_id=tenant, sku=f"SC-{tag}-{i}", name=f"P{i}") for i in range(3)]
    db_session.add_all([customer, *products])
    db_session.flush()
    live, gone, old = (int(p.id) for p in products)
    for pid, day in ((live, REF), (gone, REF - timedelta(days=60)), (old, REF - timedelta(days=400))):
        db_session.add(FactInventoryCustomer(tenant_id=tenant, product_id=pid, customer_id=int(customer.id),
                                             as_of_date=day, on_hand_units=3, on_order_units=0))
    db_session.flush()

    # off (no row): not scoped
    assert sc.product_tiers(db_session, tenant, [live, gone, old]) is None

    ts.set_setting(db_session, tenant, ts.KEY_LISTING_SCOPE,
                   {"enabled": True, "recent_window_days": 180, "recent_interval_days": 7, "absent_days": 14},
                   actor="test")
    tiers = sc.product_tiers(db_session, tenant, [live, gone, old])
    assert tiers == {live: sc.TIER_ACTIVE, gone: sc.TIER_RECENT, old: sc.TIER_HISTORICAL}

    now = datetime(2026, 11, 24, tzinfo=timezone.utc)
    rows = [SimpleNamespace(id=i + 1, customer_id=int(customer.id), product_id=pid)
            for i, pid in enumerate((live, gone, old, None))]
    rows.append(SimpleNamespace(id=9, customer_id=int(customer.id), product_id=gone))
    seen = {2: now - timedelta(days=2), 9: now - timedelta(days=8)}
    kept, skipped = sc.scope_due_listings(db_session, rows, now=now, last_seen=seen)
    # active, unlinked and the recently-gone listing last checked 8 days ago are polled
    assert [r.id for r in kept] == [1, 4, 9]
    assert skipped == {sc.TIER_RECENT: 1, sc.TIER_HISTORICAL: 1}
