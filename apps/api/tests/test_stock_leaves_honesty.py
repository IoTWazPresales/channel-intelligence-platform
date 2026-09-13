from app.services.stock_leaves_honesty import forecast_title, sellthrough_title, week_short


def test_week_short():
    assert week_short("2026-W37") == "W37"
    assert week_short(None) == "—"


def test_sellthrough_title_when_current_week_empty():
    assert (
        sellthrough_title(current_week="W37", current_week_rows=0)
        == "Retailer sell-through for W37 not yet imported"
    )


def test_sellthrough_title_when_current_week_has_rows():
    assert sellthrough_title(current_week="W37", current_week_rows=12) == "Retailer sell-through applied in W37"


def test_forecast_title_gate():
    assert forecast_title(trailing_weeks=0) == "Forecasts need 8 weeks of applied sell-out"
    assert forecast_title(trailing_weeks=8) == "Forecast trailing window is complete"
