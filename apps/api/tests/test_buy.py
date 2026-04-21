from datetime import date

from app.services.planning.buy import BuyInputs, build_buy_plan


def test_buy_recommendation_positive_gap():
    plan = build_buy_plan(
        BuyInputs(
            forecast_weekly_demand=100,
            on_hand=100,
            inbound=0,
            target_wos=6,
            lead_time_weeks=4,
        ),
        today=date(2026, 4, 1),
    )
    assert plan.recommended_qty > 0
