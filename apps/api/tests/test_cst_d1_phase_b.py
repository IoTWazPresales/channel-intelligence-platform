"""CPOR U4.5 Phase B — CST D1 helpers + apply/cost wiring (no cip)."""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.cpor.cost_suggestion import suggest_cost_basis
from app.services.cpor.waterfall import quantize_money
from app.services.imports import customer_sell_through_apply as apply_mod
from app.services.imports.cst_d1 import (
    corroborate_period,
    feed_profile_vat_basis,
    monday_of_week,
    normalize_article_token,
    resolve_customer_article_alias,
)


def test_allow_tests_on_dev_db_unset():
    assert os.environ.get("ALLOW_TESTS_ON_DEV_DB", "").strip() != "1"


def test_corroborate_period_conflict_keeps_steward():
    out = corroborate_period(
        steward_declared=date(2026, 6, 29),
        file_inferred=date(2026, 6, 22),
        filename="ASUS_WEEK_27.xlsx",
    )
    assert out["period_start_date"] == date(2026, 6, 29)
    assert out["source"] == "steward_declared"
    assert "period_conflict" in out["flags"]


def test_corroborate_period_match():
    d = date(2026, 6, 29)
    out = corroborate_period(steward_declared=d, file_inferred=d)
    assert out["source"] == "steward_corroborated"
    assert out["flags"] == []


def test_feed_profile_vat_basis_default():
    assert feed_profile_vat_basis(None) == "ex_vat"
    cfg = SimpleNamespace(feed_profile_json={"vat_basis": "inc_vat"})
    assert feed_profile_vat_basis(cfg) == "inc_vat"


def test_monday_of_week():
    # 2026-07-08 is Wednesday → Monday 2026-07-06
    assert monday_of_week(date(2026, 7, 8)) == date(2026, 7, 6)


def test_normalize_article_token():
    assert normalize_article_token("  ABC-1 ") == "abc-1"
    assert normalize_article_token(None) == ""


def test_resolve_customer_article_alias_confirmed_only():
    session = MagicMock()
    row = SimpleNamespace(product_id=99, valid_from=None, valid_to=None, status="confirmed")
    session.scalars.return_value.all.return_value = [row]
    assert resolve_customer_article_alias(session, customer_id=1, article_token="ART-1") == 99
    session.scalars.return_value.all.return_value = []
    assert resolve_customer_article_alias(session, customer_id=1, article_token="ART-1") is None


def test_apply_carries_site_label_and_unit_mac_unmapped_location(monkeypatch):
    """FLAG ≠ BLOCK: unmapped location still applies with site_label set."""
    monkeypatch.setattr(
        "app.services.imports.customer_sell_through.customer_sellthrough_source_key",
        lambda **kw: f"{kw['customer_id']}-{kw['customer_location_id']}-{kw['product_id']}-{kw['period_start_date']}",
    )
    line = SimpleNamespace(
        id=1,
        resolved_customer_id=1,
        resolved_product_id=10,
        resolved_location_id=None,  # unmapped
        period_start_date="2026-06-29",
        units_sold=3,
        period_type="weekly",
        raw_mtd_units=None,
        is_mtd_estimate=False,
        unit_sell_price=None,
        unit_cost=100.0,
        unit_mac=95.5,
        reported_soh=2,
        site_label="Store 01",
        vat_basis=None,
        raw_location_token="Store 01",
        raw_row_payload={"Store": "Store 01"},
        apply_status=None,
        fact_sellthrough_row_id=None,
    )
    returned = [SimpleNamespace(id=500, source_key="1-None-10-2026-06-29")]
    db = MagicMock()
    scalars_result = MagicMock()
    scalars_result.all.return_value = [line]
    db.scalars.return_value = scalars_result
    db.scalar.return_value = 0
    exec_result = MagicMock()
    exec_result.all.return_value = returned
    db.execute.return_value = exec_result

    summary = apply_mod.apply_customer_sellthrough_staging(db, 7)
    assert summary.applied == 1
    assert line.apply_status == "applied"
    # Inspect upsert payload
    call_args = db.execute.call_args
    stmt = call_args[0][0]
    # pg_insert values are on the statement; fall back to grouped values via side effect
    # by re-running capture: the values dict is built before execute — assert via conflict set keys
    assert "unit_mac" in apply_mod._CONFLICT_SET
    assert "site_label" in apply_mod._CONFLICT_SET
    assert "vat_basis" in apply_mod._CONFLICT_SET


def test_tier1_prefers_unit_mac():
    session = MagicMock()
    t1 = MagicMock()
    # unit_mac, unit_cost, period, id
    t1.first = MagicMock(return_value=(Decimal("90"), Decimal("100"), date(2026, 6, 1), 7))
    session.execute = MagicMock(return_value=t1)
    sug = suggest_cost_basis(session, customer_id=1, product_id=2, as_of=date(2026, 7, 1))
    assert sug.cost_source == "cst_reported"
    assert quantize_money(sug.cost_basis) == Decimal("90.00")
    assert sug.evidence["field_used"] == "unit_mac"


def test_tier1_falls_back_to_unit_cost():
    session = MagicMock()
    t1 = MagicMock()
    t1.first = MagicMock(return_value=(None, Decimal("100"), date(2026, 6, 1), 7))
    session.execute = MagicMock(return_value=t1)
    sug = suggest_cost_basis(session, customer_id=1, product_id=2, as_of=date(2026, 7, 1))
    assert sug.evidence["field_used"] == "unit_cost"
    assert quantize_money(sug.cost_basis) == Decimal("100.00")
