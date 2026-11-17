"""N-0088 suggested quantities: cover, forecast and this customer's history.

The old suggestion used forecast alone whenever forecast was positive, so cover
surplus and this customer's earlier quantity never changed the number.
"""

from __future__ import annotations

from sqlalchemy import text

from app.db.session_sync import SessionLocal
from app.services.cpor.promo_plan_builder import (
    blend_cip_quantity,
    cover_surplus_units,
    customer_product_history_units,
)


def _legacy_forecast_first(forecast: float, spec: float) -> float:
    """The previous rule: a positive forecast replaced every other input."""
    if forecast > 0:
        return forecast
    return spec


def test_forecast_alone_matches_the_old_number():
    pack = blend_cip_quantity(
        forecast_units=40,
        history_units=None,
        cover_surplus_units=None,
        comparable_cases=[],
        spec_units=4,
    )
    assert pack["suggested_estimate_qty"] == _legacy_forecast_first(40, 4)
    assert pack["blocks"] is False
    assert pack["signals"] == [{"source": "forecast", "units": 40.0}]


def test_cover_and_history_change_a_forecast_that_used_to_win():
    forecast = 40.0
    history = 10.0
    surplus = 90.0
    spec = 4.0
    pack = blend_cip_quantity(
        forecast_units=forecast,
        history_units=history,
        cover_surplus_units=surplus,
        comparable_cases=[{"estimate_qty": 999}],
        spec_units=spec,
    )
    old = _legacy_forecast_first(forecast, spec)
    assert old == 40
    assert pack["suggested_estimate_qty"] == round((forecast + history + surplus) / 3, 4)
    assert pack["suggested_estimate_qty"] != old
    assert pack["blocks"] is False
    assert [item["source"] for item in pack["signals"]] == ["forecast", "history", "cover"]
    assert "cip_qty_cover" in pack["flags"]


def test_cover_surplus_is_used_when_forecast_and_history_are_absent():
    pack = blend_cip_quantity(
        forecast_units=0,
        history_units=None,
        cover_surplus_units=90,
        comparable_cases=[],
        spec_units=4,
    )
    assert _legacy_forecast_first(0, 4) == 4
    assert pack["suggested_estimate_qty"] == 90
    assert pack["fallback"] is None
    assert pack["blocks"] is False


def test_zero_surplus_is_not_pulled_into_the_mean():
    assert cover_surplus_units(6, 1, 6) == 0.0
    pack = blend_cip_quantity(
        forecast_units=12,
        history_units=None,
        cover_surplus_units=0,
        comparable_cases=[],
        spec_units=1,
    )
    assert pack["suggested_estimate_qty"] == 12
    assert pack["signals"] == [{"source": "forecast", "units": 12.0}]


def test_history_query_runs_on_cip_test_and_does_not_block():
    with SessionLocal() as session:
        name = session.execute(text("SELECT current_database()")).scalar()
        print("SELECT current_database()", name)
        assert name == "cip_test"
        result = customer_product_history_units(
            session,
            customer_id=1,
            product_id=1,
            exclude_case_id=None,
        )
        session.rollback()
    assert result["blocks"] is False
    assert result["line_count"] >= 0
    assert result["mean"] is None or result["mean"] > 0


def test_apply_skips_voided_and_split_lines_before_preview_and_write(monkeypatch):
    """A retired line keeps estimate 0 even when the suggestion for it would be positive."""
    import uuid
    from datetime import date

    from sqlalchemy import select

    import app.services.cpor.promo_plan_builder as builder
    import app.services.cpor.recompute as recompute
    from app.models.cpor import CporCase, CporCaseLine
    from app.models.dimensions import DimCustomer, DimProduct

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
