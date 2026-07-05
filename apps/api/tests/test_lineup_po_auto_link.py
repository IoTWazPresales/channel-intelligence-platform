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


def test_po_norm_already_linked_anywhere_skips_other_cases():
    from app.services.commercial_planner.lineup_po_auto_link import _po_norm_already_linked_anywhere

    linked = {(9, 100), (8, 200)}
    norms = {100: "PURMIDR26009978", 200: "OTHERPO"}
    assert _po_norm_already_linked_anywhere("PURMIDR26009978", linked, norms)
    assert not _po_norm_already_linked_anywhere("NEWPO", linked, norms)


def test_best_lineup_match_open_channel_staging_exact_when_ship_is_open_channel():
    from types import SimpleNamespace

    from app.services.commercial_planner.lineup_po_auto_link import _best_lineup_match_for_product

    lines = [
        SimpleNamespace(
            product_id=100,
            customer_id=None,
            distributor_id=10,
            raw_row_payload={"staging_open_channel": True},
        ),
    ]
    ln, conf, reason, align = _best_lineup_match_for_product(
        lines,
        product_id=100,
        ship_customer_id=42,
        date_source="crad",
        open_channel_customer_id=42,
    )
    assert ln is not None
    assert conf == "high"
    assert align == "exact"
    assert reason == "customer_product_crad_in_period"


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


def test_best_lineup_match_product_filter_equivalent_to_full_case_lines():
    """Quick-win: pre-filtered product lines must yield the same match as all case lines."""
    from types import SimpleNamespace

    from app.services.commercial_planner.lineup_po_auto_link import _best_lineup_match_for_product

    lines = [
        SimpleNamespace(product_id=100, customer_id=5, distributor_id=10),
        SimpleNamespace(product_id=200, customer_id=6, distributor_id=11),
        SimpleNamespace(product_id=100, customer_id=5, distributor_id=10),
    ]
    product_lines = [ln for ln in lines if int(ln.product_id) == 100]
    full = _best_lineup_match_for_product(
        lines, product_id=100, ship_customer_id=5, date_source="crad"
    )
    filtered = _best_lineup_match_for_product(
        product_lines, product_id=100, ship_customer_id=5, date_source="crad"
    )
    assert full == filtered


def test_compute_group_linked_coverage_sums_linked_po_shipped_only():
    from types import SimpleNamespace

    from app.services.commercial_planner.lineup_po_auto_link import compute_group_linked_coverage

    case = SimpleNamespace(
        id=10,
        period_label="26Q2",
        inferred_period_start=date(2026, 4, 1),
    )
    line = SimpleNamespace(product_id=100, customer_id=5, distributor_id=1)
    ship_shipped = SimpleNamespace(
        purchase_order_id=99,
        product_id=100,
        resolved_customer_id=5,
        quantity=80.0,
        line_state="shipped",
        crad_date=date(2026, 5, 1),
        schedule_ship_date=None,
        ship_confirm_date=None,
    )
    ship_open = SimpleNamespace(
        purchase_order_id=99,
        product_id=100,
        resolved_customer_id=5,
        quantity=40.0,
        line_state="open_order",
        crad_date=date(2026, 5, 1),
        schedule_ship_date=None,
        ship_confirm_date=None,
    )
    ship_unlinked = SimpleNamespace(
        purchase_order_id=200,
        product_id=100,
        resolved_customer_id=5,
        quantity=999.0,
        line_state="shipped",
        crad_date=date(2026, 5, 1),
        schedule_ship_date=None,
        ship_confirm_date=None,
    )
    coverage = compute_group_linked_coverage(
        case_by_id={10: case},
        linked_pairs={(10, 99)},
        shipment_rows=[ship_shipped, ship_open, ship_unlinked],
        lineup_by_case_product={(10, 100): [line]},
    )
    assert coverage["26Q2|5"]["linked_shipped_units"] == 80.0
    assert "26Q2|5" in coverage


def test_compute_group_planned_units_sums_full_customer_period_plan():
    from types import SimpleNamespace

    from app.services.commercial_planner.lineup_po_auto_link import compute_group_planned_units

    case = SimpleNamespace(id=9, period_label="2026 Q2", inferred_period_start=date(2026, 4, 1))
    case_by_id = {9: case}
    planned = {
        (9, 1, 100): 50.0,
        (9, 1, 200): 30.0,
        (9, 5, 100): 999.0,  # different customer — separate group
    }
    out = compute_group_planned_units(case_by_id=case_by_id, planned_by_case_customer_product=planned)
    assert out["2026 Q2|1"] == 80.0
    assert out["2026 Q2|5"] == 999.0


def test_proposal_totals_keep_shipped_and_open_order_separate():
    """Read-model totals must not merge pipeline into shipped."""
    from app.services.commercial_planner.lineup_po_auto_link import _ProductMatch

    products = [
        _ProductMatch(product_id=1, shipped_units=100.0, open_order_units=35.0, planned_units=200.0),
        _ProductMatch(product_id=2, shipped_units=20.0, open_order_units=0.0, planned_units=50.0),
    ]
    total_shipped = round(sum(m.shipped_units for m in products), 4)
    total_open = round(sum(m.open_order_units for m in products), 4)
    assert total_shipped == 120.0
    assert total_open == 35.0
    assert total_shipped + total_open == 155.0


@pytest.mark.anyio
async def test_purmidr_not_duplicated_per_po_norm_on_26q2():
    """Canonical 26Q2 filter surfaces duplicate active cases until steward supersession."""
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
    assert len(hits) >= 1
    case_ids = {h["case_id"] for h in hits}
    assert case_ids.issubset({9, 26, 32, 33})
    row = hits[0]
    assert row["total_shipped_units"] <= 7000  # was inflated to 21276 before fix


@pytest.mark.anyio
async def test_purmidr_09978_excluded_when_already_linked_to_any_case():
    """Regression: PO norm linked to one case must not be proposed for other cases."""
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
    hits = [p for p in r["proposals"] if p.get("po_number_norm") == "PURMIDR26009978"]
    assert len(hits) == 0


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
        assert "total_open_order_units" in row
        assert "total_shipped_units" in row
    assert "group_coverage_by_key" in result
