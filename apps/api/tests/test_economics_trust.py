from app.services.commercial_planner.economics_trust import (
    classify_line_economics_trust,
    plan_trust_from_line_tiers,
    summarize_recalculate_trust,
)


def test_classify_blocked_when_missing_sku():
    tier, reasons = classify_line_economics_trust(["missing_sku_assumption", "missing_customer_term"])
    assert tier == "blocked"
    assert "missing_sku_assumption" in reasons


def test_classify_blocked_when_invalid_fx_plan_currency_per_cost_currency():
    tier, reasons = classify_line_economics_trust(["invalid_fx_plan_currency_per_cost_currency"])
    assert tier == "blocked"
    assert "invalid_fx_plan_currency_per_cost_currency" in reasons


def test_classify_warning_when_only_missing_terms():
    tier, reasons = classify_line_economics_trust(["missing_customer_term", "missing_distributor_term"])
    assert tier == "warning"
    assert "missing_customer_term" in reasons


def test_plan_trust_from_line_tiers():
    assert plan_trust_from_line_tiers(["ok", "warning", "ok"]) == "warning"
    assert plan_trust_from_line_tiers(["ok", "blocked"]) == "blocked"


def test_summarize_recalculate_trust():
    rows = [
        (1, ["missing_sku_assumption"], "blocked"),
        (2, ["missing_customer_term"], "warning"),
        (3, [], "ok"),
    ]
    s = summarize_recalculate_trust(rows)
    assert s["lines_blocked"] == 1
    assert s["lines_warning"] == 1
    assert s["lines_trusted_ok"] == 1
    assert "missing_sku_assumption" in s["top_blocker_flags"]
