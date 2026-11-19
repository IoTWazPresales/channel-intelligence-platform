"""Suggested quantities from customer sell-through only (N-0088, then Warren 2026-11-19).

The suggestion is the mean of the positive signals: expected units (the customer's sell-through
run rate over the horizon) and units of customer stock above the cover target. This customer's
earlier cases and the line-up/forecast comparables are not planner sources any more, and a missing
figure is ``None``, not a zero.
"""

from __future__ import annotations

from app.db.session_sync import SessionLocal
from app.services.cpor.promo_plan_builder import (
    blend_cip_quantity,
    cover_surplus_units,
)
from sqlalchemy import text


def test_run_rate_units_alone_are_the_suggestion():
    pack = blend_cip_quantity(forecast_units=40, cover_surplus_units=None, spec_units=4)
    assert pack["suggested_estimate_qty"] == 40
    assert pack["blocks"] is False
    assert pack["signals"] == [{"source": "forecast", "units": 40.0}]


def test_cover_surplus_changes_a_run_rate_that_would_otherwise_win():
    pack = blend_cip_quantity(forecast_units=40.0, cover_surplus_units=90.0, spec_units=4.0)
    assert pack["suggested_estimate_qty"] == round((40.0 + 90.0) / 2, 4)
    assert pack["blocks"] is False
    assert [item["source"] for item in pack["signals"]] == ["forecast", "cover"]
    assert "cip_qty_cover" in pack["flags"]
    assert pack["history_units"] is None  # earlier cases are not a planner source


def test_cover_surplus_is_used_when_the_run_rate_is_zero():
    pack = blend_cip_quantity(forecast_units=0, cover_surplus_units=90, spec_units=4)
    assert pack["suggested_estimate_qty"] == 90
    assert pack["fallback"] is None
    assert pack["blocks"] is False


def test_zero_surplus_is_not_pulled_into_the_mean():
    assert cover_surplus_units(6, 1, 6) == 0.0
    pack = blend_cip_quantity(forecast_units=12, cover_surplus_units=0, spec_units=1)
    assert pack["suggested_estimate_qty"] == 12
    assert pack["signals"] == [{"source": "forecast", "units": 12.0}]


def test_no_sellthrough_units_is_missing_even_with_a_line_estimate():
    own = blend_cip_quantity(forecast_units=None, cover_surplus_units=None, spec_units=4)
    assert own["suggested_estimate_qty"] is None and own["fallback"] is None
    missing = blend_cip_quantity(forecast_units=None, cover_surplus_units=None, spec_units=0)
    assert missing["suggested_estimate_qty"] is None
    assert missing["unavailable_reason"] == "no_sellthrough_units"
    assert missing["blocks"] is False


def test_apply_skips_voided_and_split_lines_before_preview_and_write(monkeypatch):
    """A retired line keeps estimate 0 even when the suggestion for it would be positive."""
    import uuid
    from datetime import date

    import app.services.cpor.promo_plan_builder as builder
    import app.services.cpor.recompute as recompute
    from app.models.cpor import CporCase, CporCaseLine
    from app.models.dimensions import DimCustomer, DimProduct
    from sqlalchemy import select

    def fake_draft(session, **kwargs):
        return {
            "lines": [
                {
                    "seed_line_id": spec["seed_line_id"],
                    "product_id": spec["product_id"],
                    "suggested_estimate_qty": 40,
                    "quantity_evidence": {"blocks": False},
                    "flags": [],
                }
                for spec in (kwargs.get("line_specs") or [])
            ]
        }

    monkeypatch.setattr(builder, "build_promo_plan_draft", fake_draft)
    monkeypatch.setattr(recompute, "recompute_case_line", lambda *args, **kwargs: None)

    with SessionLocal() as session:
        name = session.execute(text("SELECT current_database()")).scalar()
        print("SELECT current_database()", name)
        assert name == "cip_test"
        customer_id = session.scalar(select(DimCustomer.id).limit(1))
        product_ids = list(session.scalars(select(DimProduct.id).limit(3)))
        assert customer_id is not None
        assert len(product_ids) >= 3
        case = CporCase(
            case_code=f"W1C-VOID-{uuid.uuid4().hex[:8]}",
            customer_id=int(customer_id),
            promotion_type="Sell out PP",
            window_start=date(2026, 10, 5),
            window_end=date(2026, 10, 11),
            status="draft",
            channel="reseller",
        )
        session.add(case)
        session.flush()

        def make_line(product_id: int, qty: float, remark: str | None) -> CporCaseLine:
            return CporCaseLine(
                case_id=case.id,
                product_id=int(product_id),
                window_start=case.window_start,
                window_end=case.window_end,
                srp=100,
                vat_rate=0.15,
                dealer_margin_pct=0.1,
                estimate_qty=qty,
                remark=remark,
            )

        live = make_line(product_ids[0], 4, None)
        voided = make_line(product_ids[1], 0, "[voided] retired")
        split = make_line(product_ids[2], 0, "[split into layers]")
        session.add_all([live, voided, split])
        session.flush()
        preview = builder.preview_cip_quantities(session, case_id=int(case.id))
        preview_ids = {int(row["line_id"]) for row in preview["lines"]}
        assert int(live.id) in preview_ids
        assert int(voided.id) not in preview_ids
        assert int(split.id) not in preview_ids
        written = builder.apply_cip_quantities(session, case)
        written_ids = {int(row["line_id"]) for row in written["lines"]}
        assert float(voided.estimate_qty or 0) == 0.0
        assert float(split.estimate_qty or 0) == 0.0
        assert float(live.estimate_qty or 0) == 40.0
        assert int(voided.id) not in written_ids
        assert int(split.id) not in written_ids
        session.rollback()


def test_apply_leaves_a_line_estimate_alone_when_sellthrough_gives_no_units(monkeypatch):
    """No sell-through units: the stored estimate stays and the response says why."""
    import uuid
    from datetime import date

    import app.services.cpor.promo_plan_builder as builder
    import app.services.cpor.recompute as recompute
    from app.models.cpor import CporCase, CporCaseLine
    from app.models.dimensions import DimCustomer, DimProduct
    from sqlalchemy import select

    def fake_draft(session, **kwargs):
        return {
            "lines": [
                {
                    "seed_line_id": spec["seed_line_id"],
                    "product_id": spec["product_id"],
                    "suggested_estimate_qty": None,
                    "quantity_evidence": {
                        "blocks": False,
                        "unavailable_reason": "no_sellthrough_units",
                    },
                    "flags": [],
                }
                for spec in (kwargs.get("line_specs") or [])
            ]
        }

    monkeypatch.setattr(builder, "build_promo_plan_draft", fake_draft)
    monkeypatch.setattr(recompute, "recompute_case_line", lambda *args, **kwargs: None)

    with SessionLocal() as session:
        name = session.execute(text("SELECT current_database()")).scalar()
        assert name == "cip_test"
        customer_id = session.scalar(select(DimCustomer.id).limit(1))
        product_id = session.scalar(select(DimProduct.id).limit(1))
        assert customer_id is not None and product_id is not None
        case = CporCase(
            case_code=f"W1C-NOUNITS-{uuid.uuid4().hex[:8]}",
            customer_id=int(customer_id),
            promotion_type="Sell out PP",
            window_start=date(2026, 10, 5),
            window_end=date(2026, 10, 11),
            status="draft",
            channel="reseller",
        )
        session.add(case)
        session.flush()
        line = CporCaseLine(
            case_id=case.id,
            product_id=int(product_id),
            window_start=case.window_start,
            window_end=case.window_end,
            srp=100,
            vat_rate=0.15,
            dealer_margin_pct=0.1,
            estimate_qty=7,
        )
        session.add(line)
        session.flush()
        written = builder.apply_cip_quantities(session, case)
        assert float(line.estimate_qty) == 7.0
        assert written["lines"] == []
        assert written["unavailable"] == [
            {"line_id": int(line.id), "reason": "no_sellthrough_units"}
        ]
        session.rollback()
