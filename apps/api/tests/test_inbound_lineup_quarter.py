"""Unit tests for inbound lineup-plan-quarter attribution (derived-on-read)."""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from app.services.commercial_planner.inbound_lineup_quarter import (
    AttributionContext,
    _CaseAttribution,
    awaiting_pod_days,
    compute_slipped,
    enrich_fact_lineup_fields,
    is_slipped_in,
    is_slipped_out,
    lifecycle_bucket,
    resolve_plan_quarter,
)


def _ctx(
    *,
    po_to_cases: dict | None = None,
    line_match: dict | None = None,
) -> AttributionContext:
    return AttributionContext(
        open_channel_customer_id=None,
        open_channel_alias_ids=frozenset(),
        po_to_cases=po_to_cases or {},
        line_match=line_match or {},
    )


def test_lifecycle_bucket_taxonomy():
    assert lifecycle_bucket("open_order", None) == "pipeline"
    assert lifecycle_bucket("shipped", None) == "shipped"
    assert lifecycle_bucket("shipped", date(2026, 6, 1)) == "landed"


def test_awaiting_pod_days_shipped_without_pod():
    days = awaiting_pod_days(
        line_state="shipped",
        pod_date=None,
        ship_confirm_date=date(2026, 6, 1),
        schedule_ship_date=None,
        reference=date(2026, 6, 10),
    )
    assert days == 9


def test_awaiting_pod_days_null_when_landed():
    assert (
        awaiting_pod_days(
            line_state="shipped",
            pod_date=date(2026, 6, 5),
            ship_confirm_date=date(2026, 6, 1),
            schedule_ship_date=None,
        )
        is None
    )


def test_slip_computation():
    assert compute_slipped("26Q2", "26Q3", None) is True
    assert compute_slipped("26Q2", "26Q2", "26Q2") is False
    assert compute_slipped(None, "26Q3", None) is False


def test_slipped_out_and_in():
    assert is_slipped_out("26Q2", "26Q3", None, "26Q2") is True
    assert is_slipped_in("26Q1", "26Q2", "26Q2") is True
    assert is_slipped_in("26Q2", "26Q2", "26Q2") is False


def test_resolve_plan_quarter_no_po():
    ctx = _ctx()
    pq, _label, note = resolve_plan_quarter(
        purchase_order_id=None,
        customer_id=1,
        product_id=2,
        product_line="NB",
        business_unit=None,
        ctx=ctx,
    )
    assert pq is None
    assert note == "no_po"


def test_resolve_plan_quarter_unattributed_po():
    ctx = _ctx()
    pq, _label, note = resolve_plan_quarter(
        purchase_order_id=99,
        customer_id=1,
        product_id=2,
        product_line="NB",
        business_unit=None,
        ctx=ctx,
    )
    assert pq is None
    assert note == "unattributed"


def test_resolve_plan_quarter_line_match():
    ctx = _ctx(
        po_to_cases={
            10: [
                _CaseAttribution(1, "26Q2", "2026 Q2", "NB"),
                _CaseAttribution(2, "26Q3", "2026 Q3", "NB"),
            ]
        },
        line_match={(10, 5, 100): 1},
    )
    pq, label, note = resolve_plan_quarter(
        purchase_order_id=10,
        customer_id=5,
        product_id=100,
        product_line="NB",
        business_unit=None,
        ctx=ctx,
    )
    assert pq == "26Q2"
    assert label == "2026 Q2"
    assert note == "line_match"


def test_resolve_plan_quarter_single_case_fallback():
    ctx = _ctx(
        po_to_cases={10: [_CaseAttribution(1, "26Q2", "2026 Q2", "NB")]},
    )
    pq, _label, note = resolve_plan_quarter(
        purchase_order_id=10,
        customer_id=5,
        product_id=999,
        product_line="NB",
        business_unit=None,
        ctx=ctx,
    )
    assert pq == "26Q2"
    assert note == "single_case"


def test_resolve_plan_quarter_multi_case_ambiguous():
    ctx = _ctx(
        po_to_cases={
            10: [
                _CaseAttribution(1, "26Q2", "2026 Q2", "NB"),
                _CaseAttribution(2, "26Q3", "2026 Q3", "NR"),
            ]
        },
    )
    pq, _label, note = resolve_plan_quarter(
        purchase_order_id=10,
        customer_id=5,
        product_id=999,
        product_line="NX",
        business_unit=None,
        ctx=ctx,
    )
    assert pq is None
    assert note == "ambiguous_multi_case"


def test_enrich_fact_lineup_fields():
    row = SimpleNamespace(
        purchase_order_id=10,
        customer_id=5,
        product_id=100,
        line_state="shipped",
        pod_date=None,
        ship_confirm_date=date(2026, 4, 15),
        schedule_ship_date=None,
        quantity=10,
    )
    ctx = _ctx(
        po_to_cases={10: [_CaseAttribution(1, "26Q2", "2026 Q2", "NB")]},
        line_match={(10, 5, 100): 1},
    )
    out = enrich_fact_lineup_fields(row, ctx=ctx, product_line="NB", business_unit="NB")
    assert out["plan_quarter"] == "26Q2"
    assert out["ship_quarter"] == "26Q2"
    assert out["lifecycle_bucket"] == "shipped"
    assert out["slipped"] is False
    assert out["awaiting_pod_days"] is not None
