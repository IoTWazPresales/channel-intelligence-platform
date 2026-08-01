"""B2-02 profit/reservation + treatment split unit tests."""

from __future__ import annotations

from app.services.lineup.profit_reservation import (
    compute_profit_with_reservation,
    split_volume_treatments,
)


def test_treatment_split_5050():
    t = split_volume_treatments(100)
    assert t.normal_price_units == 50.0
    assert t.discount_units == 50.0


def test_profit_reservation_derived_q002():
    out = compute_profit_with_reservation(
        net_requirement_units=100,
        target_srp_local=1000,
        promo_srp_local=900,
        controlled_cost_amount=400,
        reserve_total_pct=0.10,
        promo_reserve_split_pct=0.5,
        fx_plan_currency_per_cost_currency=1.0,
    )
    assert out["reservation"]["source"] == "derived_from_profit"
    assert out["reservation"]["hard_enforce"] is False
    assert out["reservation"]["total"] > 0
    assert out["treatments"]["normal_price_units"] == 50.0
    assert out["pm_bottom"] == 400.0
