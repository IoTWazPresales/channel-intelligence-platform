"""GOV-008 M7: period-start facts refuse day and week; the catalog offers only what the planner accepts; pending measures say why."""

from __future__ import annotations

import pytest

from app.query.model.catalog import catalog_v2
from app.query.model.graph import V2Request, plan_request
from app.query.model.loader import clear_model_cache, default_model
from app.semantics.registry import load_catalog


@pytest.fixture(autouse=True)
def _fresh_model():
    clear_model_cache()
    yield
    clear_model_cache()


def _plan(measure, grain, breakdowns=("period",)):
    return plan_request(default_model(), V2Request(measures=[measure], breakdowns=list(breakdowns), period_grain=grain),
                        v1_catalog=load_catalog())


@pytest.mark.parametrize("measure", ["lineup.units", "lineup.lines", "sellin.units"])
@pytest.mark.parametrize("grain", ["day", "week"])
def test_period_start_facts_refuse_day_and_week(measure, grain):
    plan = _plan(measure, grain)
    assert not plan.measures and plan.refusals, f"{measure} by {grain} must be refused"
    assert "start of a planning period" in plan.refusals[0].reason
    assert "month, quarter or year" in plan.refusals[0].reason


@pytest.mark.parametrize("measure", ["lineup.units", "lineup.lines", "sellin.units"])
@pytest.mark.parametrize("grain", ["month", "quarter", "year"])
def test_period_start_facts_still_accept_month_quarter_year(measure, grain):
    plan = _plan(measure, grain)
    assert plan.measures and not plan.refusals


def test_day_floored_facts_keep_day_and_week():
    for measure in ("dsi_sellout.units", "returns.units", "cpor.estimate_units"):
        for grain in ("day", "week"):
            plan = _plan(measure, grain)
            assert plan.measures, (measure, grain, plan.refusals and plan.refusals[0].reason)


def test_every_period_grain_the_catalog_offers_plans_and_every_grain_it_omits_is_refused():
    dm, cat = default_model(), load_catalog()
    listed = catalog_v2(dm, cat, is_admin=False)["measures"]
    checked = 0
    for entry in listed:
        if entry["kind"] not in ("base", "calculated"):
            continue
        offered = set(entry["period_grains"])
        for grain in dm.period.grains:
            plan = _plan(entry["id"], grain)
            if grain in offered:
                assert plan.measures, f"{entry['id']} offers {grain} but the planner refuses: {plan.refusals[0].reason}"
            else:
                assert not plan.measures, f"{entry['id']} omits {grain} but the planner accepts it"
            checked += 1
    assert checked > 150


def test_catalog_offers_no_period_breakdown_the_planner_refuses():
    dm, cat = default_model(), load_catalog()
    bad = []
    for entry in catalog_v2(dm, cat, is_admin=False)["measures"]:
        if entry["kind"] not in ("base", "calculated"):
            continue
        for b in entry["breakdowns"]:
            plan = _plan(entry["id"], "month", (b,))
            if plan.measures:
                continue
            reason = plan.refusals[0].reason if plan.refusals else "<no refusal>"
            if "needs period" in reason and any("period" in r for r in entry["requires"]):
                continue  # advertised through requires: the builder must add period
            bad.append((entry["id"], b, reason[:80]))
    assert not bad, bad[:10]


def test_open_shipment_measures_do_not_offer_period():
    listed = {m["id"]: m for m in catalog_v2(default_model(), load_catalog(), is_admin=False)["measures"]}
    for mid in ("shipments.open_quantity", "shipments.open_lines"):
        assert "period" not in listed[mid]["breakdowns"] and listed[mid]["period_grains"] == []


def test_cst_does_not_offer_day_and_prior_year_says_it_needs_period():
    listed = {m["id"]: m for m in catalog_v2(default_model(), load_catalog(), is_admin=False)["measures"]}
    assert "day" not in listed["cst_sellthrough.units"]["period_grains"]
    assert "week" in listed["cst_sellthrough.units"]["period_grains"]
    assert listed["dsi_sellout.units_prior_year"]["requires"] == ["period"]
    assert listed["dsi_sellout.units_running_total"]["requires"] == ["period"]


def test_every_pending_measure_is_refused_with_its_reason_not_unknown_measure():
    dm = default_model()
    assert dm.pending
    for item in dm.pending:
        plan = plan_request(dm, V2Request(measures=[item["id"]], breakdowns=[]), v1_catalog=load_catalog())
        assert not plan.measures and plan.refusals
        reason = plan.refusals[0].reason
        assert "Unknown measure" not in reason, item["id"]
        assert item["reason"] in reason, item["id"]
        assert "not available yet" in reason
    unknown = plan_request(dm, V2Request(measures=["no_such.measure"], breakdowns=[]), v1_catalog=load_catalog())
    assert "Unknown measure" in unknown.refusals[0].reason
