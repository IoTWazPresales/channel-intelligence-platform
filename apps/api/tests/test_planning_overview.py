from app.services.planning_overview import _customer_plan_shipped, _period_caption


def test_customer_plan_shipped_groups_and_caps():
    rows = [
        {"customer_id": 1, "customer_label": "Acme", "planned_units": 10, "shipped_units": 4},
        {"customer_id": 1, "customer_label": "Acme", "planned_units": 5, "shipped_units": 6},
        {"customer_id": 2, "customer_label": "Beta", "planned_units": 100, "shipped_units": 10},
        {"customer_id": None, "customer_label": "", "planned_units": 1, "shipped_units": 0},
    ]
    out = _customer_plan_shipped(rows)
    assert out[0]["customer"] == "Beta"
    assert out[0]["plan"] == 100
    acme = next(r for r in out if r["customer"] == "Acme")
    assert acme["plan"] == 15
    assert acme["shipped"] == 10
    assert any(r["customer"] == "Unattributed" for r in out)


def test_period_caption_lists_labels():
    assert "no period_label" in _period_caption([])
    assert _period_caption(["P10", "P09"]) == "P10, P09"
