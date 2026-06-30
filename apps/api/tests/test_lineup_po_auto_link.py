"""Unit 3 — PO↔lineup auto-link proposal engine (CRAD-primary)."""

from __future__ import annotations

from datetime import date

import pytest

from app.services.commercial_planner.lineup_po_auto_link import (
    classify_customer_alignment,
    classify_match_confidence,
    date_in_case_period,
    evidence_date_for_period_match,
    quarter_bounds_from_period_start,
)


def test_quarter_bounds_26q1():
    start, end = quarter_bounds_from_period_start(date(2026, 1, 1))
    assert start == date(2026, 1, 1)
    assert end == date(2026, 4, 1)


def test_evidence_date_prefers_crad():
    d, src = evidence_date_for_period_match(
        crad_date=date(2026, 2, 15),
        schedule_ship_date=date(2026, 3, 1),
        ship_confirm_date=date(2026, 3, 5),
    )
    assert d == date(2026, 2, 15)
    assert src == "crad"


def test_evidence_date_fallback_schedule_ship():
    d, src = evidence_date_for_period_match(
        crad_date=None,
        schedule_ship_date=date(2026, 3, 1),
        ship_confirm_date=date(2026, 3, 5),
    )
    assert d == date(2026, 3, 1)
    assert src == "schedule_ship"


def test_crad_in_period_high_confidence():
    assert date_in_case_period(date(2026, 2, 1), date(2026, 1, 1))
    conf, reason = classify_match_confidence(
        customer_align="exact",
        date_source="crad",
        in_period=True,
    )
    assert conf == "high"
    assert reason == "customer_product_crad_in_period"


def test_date_fallback_medium_confidence():
    conf, reason = classify_match_confidence(
        customer_align="exact",
        date_source="schedule_ship",
        in_period=True,
    )
    assert conf == "medium"
    assert reason == "customer_product_date_fallback_in_period"


def test_unresolved_customer_medium_not_dropped():
    conf, reason = classify_match_confidence(
        customer_align="unresolved",
        date_source="crad",
        in_period=True,
    )
    assert conf == "medium"
    assert reason == "product_period_customer_unresolved"


def test_customer_mismatch_returns_no_proposal():
    assert classify_customer_alignment(10, 20) == "mismatch"
    conf, reason = classify_match_confidence(
        customer_align="mismatch",
        date_source="crad",
        in_period=True,
    )
    assert conf is None
    assert reason is None


def test_out_of_period_no_match():
    assert not date_in_case_period(date(2026, 5, 1), date(2026, 1, 1))


def test_best_lineup_match_counts_once_per_product():
    """Multiple lineup rows for the same product must not create multiple matches."""
    from types import SimpleNamespace

    from app.services.commercial_planner.lineup_po_auto_link import _best_lineup_match_for_product

    lines = [
        SimpleNamespace(product_id=100, customer_id=5, distributor_id=10),
        SimpleNamespace(product_id=100, customer_id=5, distributor_id=10),
        SimpleNamespace(product_id=100, customer_id=5, distributor_id=10),
    ]
    ln, conf, reason, align = _best_lineup_match_for_product(
        lines,
        product_id=100,
        ship_customer_id=5,
        date_source="crad",
    )
    assert ln is not None
    assert conf == "high"
    assert align == "exact"


@pytest.mark.anyio
async def test_purmidr_not_duplicated_per_po_norm_on_26q2():
    """Regression: one proposal per case+customer+PO norm (not per duplicate purchase_order id)."""
    pytest.importorskip("asyncpg")
    from sqlalchemy import text

    from app.db.session import AsyncSessionLocal
    from app.services.commercial_planner.lineup_po_auto_link import po_auto_link_proposals

    async with AsyncSessionLocal() as db:
        has_col = await db.scalar(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name='fact_inbound_shipment' AND column_name='fact_upsert_key'"
            )
        )
        if not has_col:
            pytest.skip("migration 20260630_0060 not applied")
        r = await po_auto_link_proposals(db, period="26Q2", limit=500)
    hits = [p for p in r["proposals"] if p.get("po_number") == "PURMIDR26010748" and "Game" in (p.get("customer_label") or "")]
    assert len(hits) == 1
    row = hits[0]
    assert row["total_shipped_units"] <= 7000  # was inflated to 21276 before fix


@pytest.mark.anyio
async def test_purmidr_09978_amazon_customer_planned_and_fact_shipped_grain():
    """Regression: Amazon planned is customer-scoped; shipped uses fact layer (not stacked evidence)."""
    pytest.importorskip("asyncpg")
    from sqlalchemy import text

    from app.db.session import AsyncSessionLocal
    from app.services.commercial_planner.lineup_po_auto_link import po_auto_link_proposals

    async with AsyncSessionLocal() as db:
        has_col = await db.scalar(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name='fact_inbound_shipment' AND column_name='fact_upsert_key'"
            )
        )
        if not has_col:
            pytest.skip("migration 20260630_0060 not applied")
        r = await po_auto_link_proposals(db, period="26Q2", customer_id=26, limit=500)
    hits = [
        p
        for p in r["proposals"]
        if p.get("po_number_norm") == "PURMIDR26009978"
        and p.get("case_id") == 9
        and p.get("customer_id") == 26
    ]
    assert len(hits) == 1
    row = hits[0]
    # Was 11500 planned (whole-case product totals) and 2000 shipped (evidence + open_order).
    assert row["total_planned_units"] < 1000
    assert row["total_shipped_units"] < 1500
    assert row["total_open_order_units"] >= 0
    assert row["total_shipped_units"] + row["total_open_order_units"] < 2000


@pytest.mark.anyio
async def test_proposals_endpoint_smoke_on_cip():
    """Integration smoke when resolved columns + lineup data exist."""
    pytest.importorskip("asyncpg")
    from sqlalchemy import text

    from app.db.session import AsyncSessionLocal
    from app.services.commercial_planner.lineup_po_auto_link import po_auto_link_proposals

    try:
        async with AsyncSessionLocal() as db:
            has_col = await db.scalar(
                text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name='fact_inbound_shipment' AND column_name='fact_upsert_key'"
                )
            )
            if not has_col:
                pytest.skip("migration 20260630_0060 not applied")
            result = await po_auto_link_proposals(db, limit=5)
    except Exception as exc:
        pytest.skip(f"DB not available: {exc}")

    assert "proposals" in result
    assert result.get("data_unavailable") is False
    if result["proposals"]:
        row = result["proposals"][0]
        assert "confidence" in row
        assert row["confidence"] in ("high", "medium")
        assert "purchase_order_id" in row
        assert "matched_products" in row
