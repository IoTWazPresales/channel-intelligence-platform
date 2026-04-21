from app.services.planning.wos import WosInputs, classify_stock_risk, compute_wos


def test_compute_wos_basic():
    w = compute_wos(WosInputs(on_hand=180, avg_weekly_demand=90, target_wos=6))
    assert abs(w - 2.0) < 1e-6


def test_stockout_risk():
    r = classify_stock_risk(WosInputs(on_hand=50, avg_weekly_demand=100, target_wos=6))
    assert r.kind == "stockout_risk"


def test_overstock_risk():
    r = classify_stock_risk(WosInputs(on_hand=900, avg_weekly_demand=100, target_wos=6))
    assert r.kind == "overstock_risk"
