"""N-0115 model file, derived breakdowns, walls and request validation (no database).

- the model file loads; every table / column / id resolves; tenant path is structural;
- every v1 refuse_example is kept verbatim, refused with its own text by v2 (where the measure
  exists in v2) and still by v1 (validate_metric_grain) unchanged;
- derived breakdowns per model; one model per query; walls on breakdowns and filters;
- ids only from the model file; values only as bound parameters; limits refused, not clamped;
- the v2 cache key separates request, tenant, catalog version, scope and role.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.core.product_line_scope import request_product_lines, request_role
from app.query.cache import cache_key_v2
from app.query.model.compiler import compile_plan
from app.query.model.graph import (
    DAILY_REFUSAL,
    MAX_LIMIT,
    V2Request,
    derived_breakdowns,
    plan_request,
)
from app.query.model.loader import MODEL_PATH, ModelLoadError, load_model
from app.semantics.registry import load_catalog, validate_metric_grain


@pytest.fixture(scope="module")
def dm():
    return load_model()


@pytest.fixture(scope="module")
def v1():
    return load_catalog()


def _plan(dm, v1, **kw):
    return plan_request(dm, V2Request(**kw), v1_catalog=v1)


def _reasons(plan):
    return [r.reason for r in plan.refusals]


# ----------------------------------------------------------------------------- loader


def test_model_file_loads_with_three_models_and_tenant_paths(dm):
    assert set(dm.models) == {"dsi_sellout", "cst_sellthrough", "cpor"}
    assert dm.models["dsi_sellout"].tenant_via is None and dm.models["dsi_sellout"].tenant_column == "tenant_id"
    assert dm.models["cst_sellthrough"].tenant_via is None
    assert dm.models["cpor"].tenant_via == "case"  # cpor_case_line has no tenant_id
    assert dm.measures["dsi_sellout.units"].legacy_key == "sellout_units"
    assert dm.measures["cst_sellthrough.units"].legacy_key == "cst_sellthrough_units"
    assert {c.kind for c in dm.calculated.values()} == {"ratio", "difference", "prior_period", "pct_change", "per_week_rate"}


def _write(tmp_path: Path, mutate) -> Path:
    data = yaml.safe_load(MODEL_PATH.read_text(encoding="utf-8"))
    mutate(data)
    p = tmp_path / "model.yaml"
    p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return p


def test_loader_refuses_a_model_with_no_tenant_path(tmp_path):
    def drop(d):
        d["models"]["dsi_sellout"].pop("tenant_column")

    with pytest.raises(ModelLoadError, match="no tenant path"):
        load_model(_write(tmp_path, drop))


def test_loader_refuses_unknown_table_column_and_rule(tmp_path):
    def bad_col(d):
        d["models"]["dsi_sellout"]["measures"]["units"]["column"] = "units; drop table x"

    with pytest.raises(ModelLoadError, match="has no column"):
        load_model(_write(tmp_path, bad_col))

    def bad_table(d):
        d["models"]["dsi_sellout"]["table"] = "pg_shadow"

    with pytest.raises(ModelLoadError, match="unknown table"):
        load_model(_write(tmp_path, bad_table))

    def bad_rule(d):
        d["models"]["cpor"]["rules"] = ["select 1"]

    with pytest.raises(ModelLoadError, match="unknown rule"):
        load_model(_write(tmp_path, bad_rule))


def test_loader_refuses_a_wall_text_that_drifts_from_v1(tmp_path):
    def drift(d):
        d["walls"][0]["keeps"][0]["text"] = "site_label is CST-only."

    with pytest.raises(ModelLoadError, match="differs from the v1 refuse_example"):
        load_model(_write(tmp_path, drift))


def test_loader_accepts_tenant_via_dim_product(tmp_path):
    def add_returns(d):
        d["models"]["returns_test"] = {
            "label": "Returns (test)",
            "table": "fact_returns",
            "tenant_via": "dim_product",
            "time": {"column": "transaction_date", "floor": "day"},
            "joins": {"product": {"fk": "product_id"}, "distributor": {"fk": "distributor_id"}},
            "measures": {"units": {"label": "Return units", "unit": "units", "agg": "sum", "column": "return_quantity"}},
        }

    m = load_model(_write(tmp_path, add_returns))
    assert m.models["returns_test"].tenant_via == "dim_product"

    def no_path(d):
        add_returns(d)
        d["models"]["returns_test"].pop("tenant_via")

    with pytest.raises(ModelLoadError, match="no tenant path"):
        load_model(_write(tmp_path, no_path))


def test_every_v1_refuse_example_is_kept_verbatim_by_a_wall(dm, v1):
    kept = {(k.metric, k.grains, k.text) for w in dm.walls for k in w.keeps}
    examples = [(m.key, ex.grains, ex.reason) for m in v1.metrics for ex in m.refuse_examples]
    assert len(examples) == 11
    for ex in examples:
        assert ex in kept, ex


# ----------------------------------------------------------------------------- derived breakdowns


def test_derived_breakdowns_per_model(dm):
    dsi = derived_breakdowns(dm, dm.models["dsi_sellout"])
    cst = derived_breakdowns(dm, dm.models["cst_sellthrough"])
    cpor = derived_breakdowns(dm, dm.models["cpor"])
    for b in ("period", "product", "bu", "category", "customer", "region", "channel", "distributor"):
        assert b in dsi
    assert "site_label" not in dsi
    assert "site_label" in cst and "distributor" not in cst
    assert "region" in cst and "bu" in cst
    for b in ("period", "customer", "product", "distributor", "bu", "promo_type", "status", "workflow_status"):
        assert b in cpor
    assert "site_label" not in cpor


def test_cpor_named_case_breakdown_uses_the_existing_tenant_join(dm, v1):
    p = _plan(dm, v1, measures=["cpor.cases"], breakdowns=["case"], filters={"case": [17]})
    assert p.ok and not p.refusals
    compiled = compile_plan(dm, p, tenant_id="example")
    assert compiled.columns[0].fields == ["case_id", "case_name"]
    sql = compiled.sql_text()
    assert "b_case.case_name" in sql and "b_case.id AS case_id" in sql
    assert "b_case.tenant_id = %(tenant_id)s" in sql
    assert "filter_case" in sql and "17" not in sql
    assert p.filters[0].values == [17]
    numeric = _plan(dm, v1, measures=["cpor.cases"], filters={"case": ["17"]})
    assert numeric.ok and numeric.filters[0].values == [17]
    for value in [True, None, "not-an-id", 1.5, 2**40]:
        refused = _plan(dm, v1, measures=["cpor.cases"], filters={"case": [value]})
        assert not refused.ok and "Filter 'case'" in _reasons(refused)[0]


def test_named_local_breakdown_refuses_an_unknown_name_column(tmp_path):
    def invalid(d):
        d["models"]["cpor"]["local"]["case"] = {
            "column": "id", "via": "case", "name_column": "missing_case_name", "label": "Case",
        }

    with pytest.raises(ModelLoadError, match="has no column.*missing_case_name"):
        load_model(_write(tmp_path, invalid))


def test_any_three_derived_breakdowns_are_valid(dm, v1):
    p = _plan(dm, v1, measures=["dsi_sellout.units"], breakdowns=["period", "region", "bu"], period_grain="month")
    assert p.refusals == [] and p.measures
    p = _plan(dm, v1, measures=["dsi_sellout.units"], breakdowns=["period", "region", "bu", "customer"])
    assert _reasons(p) == ["At most 3 breakdowns at once."]


# ----------------------------------------------------------------------------- walls


MODEL_LEGACY = {"sellout_units": "dsi_sellout.units", "cst_sellthrough_units": "cst_sellthrough.units"}


def test_old_refuse_examples_refused_with_their_exact_text_in_v2_and_v1(dm, v1):
    for metric in v1.metrics:
        for ex in metric.refuse_examples:
            # v1 unchanged
            v = validate_metric_grain(metric.key, sorted(ex.grains), catalog=v1)
            assert not v.ok and v.message == ex.reason, (metric.key, ex.grains)
            # v2: model measure for the two legacy metrics, governed otherwise
            mid = MODEL_LEGACY.get(metric.key, metric.key)
            p = _plan(dm, v1, measures=[mid], breakdowns=sorted(ex.grains))
            assert not p.ok, (mid, ex.grains)
            assert [r.reason for r in p.refusals if r.measure == mid] == [ex.reason], (mid, ex.grains, p.refusals)
            assert p.refusals[0].wall and p.refusals[0].wall.startswith("W-")


def test_wall_reasons_for_measures_without_a_v1_example(dm, v1):
    p = _plan(dm, v1, measures=["dsi_sellout.lines"], breakdowns=["site_label"])
    assert p.refusals[0].wall == "W-SITE-CST-ONLY"
    assert p.refusals[0].reason == dm.wall("W-SITE-CST-ONLY").reason
    p = _plan(dm, v1, measures=["cst_sellthrough.lines"], breakdowns=["distributor"])
    assert p.refusals[0].wall == "W-CST-NO-DISTRIBUTOR"
    p = _plan(dm, v1, measures=["dsi_sellout.units"], breakdowns=["lineup_quarter"])
    assert p.refusals[0].wall == "W-LINEUP-QUARTER"
    # A wall applies to a filter as to a breakdown.
    p = _plan(dm, v1, measures=["cst_sellthrough.units"], filters={"distributor": 3})
    assert p.refusals[0].wall == "W-CST-NO-DISTRIBUTOR" and not p.measures


def test_one_model_per_query_holds_the_customer_role_wall(dm, v1):
    p = _plan(dm, v1, measures=["dsi_sellout.units", "cst_sellthrough.units"], breakdowns=["customer"])
    assert not p.ok
    assert p.refusals[0].wall == "W-CUSTOMER-ROLE"
    assert dm.wall("W-CUSTOMER-ROLE").reason in p.refusals[0].reason


def test_stock_is_never_summed_across_periods(dm, v1):
    p = _plan(dm, v1, measures=["cst_sellthrough.reported_soh", "cst_sellthrough.units"], breakdowns=["period"])
    assert [m.id for m in p.measures] == ["cst_sellthrough.units"]
    assert p.refusals[0].measure == "cst_sellthrough.reported_soh" and p.refusals[0].wall == "W-SNAPSHOT-NOT-SUMMED"


def test_governed_refuse_all_keeps_its_reason(dm, v1):
    p = _plan(dm, v1, measures=["claim_rate"], breakdowns=["customer"])
    assert p.refusals[0].reason == v1.metric_by_key("claim_rate").refuse_reason
    assert p.refusals[0].wall == "W-NOT-COMPUTABLE"


def test_governed_metric_is_answered_alone_at_its_v1_grains(dm, v1):
    p = _plan(dm, v1, measures=["weeks_of_cover"], breakdowns=["distributor", "product"])
    assert p.governed is not None and p.refusals == []
    p = _plan(dm, v1, measures=["weeks_of_cover", "dsi_sellout.units"], breakdowns=["distributor", "product"])
    assert not p.ok and "on its own" in p.refusals[0].reason
    p = _plan(dm, v1, measures=["sellout_units"], breakdowns=["period"])
    assert p.refusals[0].reason == "Use dsi_sellout.units for sellout_units in v2 queries."


# ----------------------------------------------------------------------------- period and calculated


def test_day_grain_refused_with_the_v1_text(dm, v1):
    p = _plan(dm, v1, measures=["dsi_sellout.units"], breakdowns=["period"], period_grain="day")
    assert _reasons(p) == [DAILY_REFUSAL]
    v = validate_metric_grain("sellout_units", ["period"], catalog=v1, period_grain="day")
    assert v.message == DAILY_REFUSAL


def test_calculated_measures_state_their_needs(dm, v1):
    p = _plan(dm, v1, measures=["dsi_sellout.units_pct_change"], breakdowns=["customer"])
    assert "needs period" in p.refusals[0].reason
    p = _plan(dm, v1, measures=["dsi_sellout.units_change"], breakdowns=["customer"])
    assert "needs period" in p.refusals[0].reason
    p = _plan(dm, v1, measures=["dsi_sellout.units_per_week"], breakdowns=["customer"])
    assert "period.from and period.to" in p.refusals[0].reason
    p = _plan(
        dm, v1, measures=["dsi_sellout.units_per_week"], breakdowns=["customer"], period_from="2026-01-01", period_to="2026-03-31"
    )
    assert p.refusals == [] and p.base_measures[0].id == "dsi_sellout.units"
    p = _plan(dm, v1, measures=["dsi_sellout.units_pct_change"], breakdowns=["period"], period_grain="week")
    assert p.needs_prev and p.refusals == []


# ----------------------------------------------------------------------------- injection and limits


@pytest.mark.parametrize(
    "bad",
    ["dsi_sellout.units; drop table dim_customer", "dsi_sellout.units' or '1'='1", "f.units", "../../etc", "DSI_SELLOUT.UNITS "],
)
def test_unknown_measure_ids_are_refused(dm, v1, bad):
    p = _plan(dm, v1, measures=[bad])
    assert not p.ok and p.refusals[0].measure == bad.strip()


def test_unknown_breakdown_sort_and_filter_ids_are_refused(dm, v1):
    p = _plan(dm, v1, measures=["dsi_sellout.units"], breakdowns=["customer) or (1=1"])
    assert "Unknown breakdown" in p.refusals[0].reason and not p.measures
    p = _plan(dm, v1, measures=["dsi_sellout.units"], breakdowns=["customer"], sort_by="units desc; --")
    assert "Sort by" in p.refusals[0].reason and not p.measures
    p = _plan(dm, v1, measures=["dsi_sellout.units"], sort_dir="sideways")
    assert not p.measures
    p = _plan(dm, v1, measures=["dsi_sellout.units"], filters={"tenant_id": "other"})
    assert "Unknown breakdown" in p.refusals[0].reason and not p.measures
    p = _plan(dm, v1, measures=["dsi_sellout.units"], filters={"period": "2026-01-01"})
    assert not p.measures


def test_filter_values_are_coerced_capped_and_bound(dm, v1):
    p = _plan(dm, v1, measures=["dsi_sellout.units"], filters={"customer": "1 or 1=1"})
    assert "takes ids" in p.refusals[0].reason and not p.measures
    p = _plan(dm, v1, measures=["dsi_sellout.units"], filters={"customer": list(range(1001))})
    assert "at most 1000" in p.refusals[0].reason
    p = _plan(dm, v1, measures=["dsi_sellout.units"], filters={"customer": []})
    assert "empty list" in p.refusals[0].reason
    evil = "NB' OR '1'='1"
    p = _plan(dm, v1, measures=["dsi_sellout.units"], breakdowns=["bu"], filters={"bu": [evil, "NR"], "customer": "42"})
    assert p.refusals == []
    assert p.filters[1].values == [42]
    sql = compile_plan(dm, p, tenant_id="t-evil' --").sql_text()
    assert evil not in sql and "t-evil" not in sql and "42" not in sql
    assert "filter_bu" in sql and "tenant_id" in sql


def test_limit_above_max_is_refused_not_clamped(dm, v1):
    assert _plan(dm, v1, measures=["dsi_sellout.units"], limit=MAX_LIMIT).limit == MAX_LIMIT
    p = _plan(dm, v1, measures=["dsi_sellout.units"], limit=MAX_LIMIT + 1)
    assert not p.measures and "refused, not clamped" in p.refusals[0].reason
    p = _plan(dm, v1, measures=["dsi_sellout.units"], limit=0)
    assert not p.measures
    assert _plan(dm, v1, measures=["dsi_sellout.units"]).limit == 500


def test_governed_metrics_check_limit_and_sort_like_model_measures(dm, v1):
    """Verification D1: the governed path returned before the limit and sort checks."""
    grains = ["distributor", "product"]
    ok = _plan(dm, v1, measures=["weeks_of_cover"], breakdowns=grains, limit=25, sort_by="weeks_of_cover", sort_dir="asc")
    assert ok.refusals == [] and ok.governed is not None and ok.limit == 25 and ok.sort_dir == "asc"
    big = _plan(dm, v1, measures=["weeks_of_cover"], breakdowns=grains, limit=999_999)
    assert big.governed is None and "refused, not clamped" in big.refusals[0].reason
    bad_sort = _plan(dm, v1, measures=["support_spend"], breakdowns=["customer"], sort_by="nonsense")
    assert bad_sort.governed is None and "Sort by" in bad_sort.refusals[0].reason
    bad_dir = _plan(dm, v1, measures=["support_spend"], breakdowns=["customer"], sort_dir="sideways")
    assert bad_dir.governed is None


def test_governed_metrics_refuse_filters_their_handler_never_reads(dm, v1):
    """A filter the v1 handler ignores is refused in plain words, never accepted and dropped."""
    grains = ["distributor", "product"]
    p = _plan(dm, v1, measures=["weeks_of_cover"], breakdowns=grains, filters={"customer": "18"})
    assert p.governed is None and "cannot be filtered by customer" in p.refusals[0].reason
    p = _plan(dm, v1, measures=["weeks_of_cover"], breakdowns=grains, filters={"distributor": "3"})
    assert p.refusals == [] and p.governed_filters == {"distributor_id": "3"}
    p = _plan(dm, v1, measures=["weeks_of_cover"], breakdowns=grains, period_from="2026-01-01")
    assert p.governed is None and "cannot be filtered by dates" in p.refusals[0].reason
    p = _plan(dm, v1, measures=["pipeline_inbound"], breakdowns=["period"], filters={"customer": "18"})
    assert p.governed is None and "cannot be filtered by customer" in p.refusals[0].reason
    p = _plan(dm, v1, measures=["support_spend"], breakdowns=["customer"], filters={"customer": "18"})
    assert p.refusals == [] and p.governed_filters == {"customer_id": "18"}
    p = _plan(dm, v1, measures=["support_spend"], breakdowns=["customer"], filters={"promo_type": "x"})
    assert p.governed is None


def test_cpor_compiles_the_portfolio_rules_and_case_tenant(dm, v1):
    p = _plan(dm, v1, measures=["cpor.support_usd", "cpor.cases"], breakdowns=["status"])
    sql = compile_plan(dm, p, tenant_id="default").sql_text()
    assert "b_case.tenant_id = %(tenant_id)s" in sql
    assert "superseded_by_case_id IS NULL" in sql and "intelligence_exclude IS false" in sql
    assert "'[voided]'" in sql and "'[split into layers]'" in sql


def test_attribute_joins_are_left_joins_with_unassigned(dm, v1):
    p = _plan(dm, v1, measures=["dsi_sellout.units"], breakdowns=["bu", "region"])
    sql = compile_plan(dm, p, tenant_id="default").sql_text()
    assert "LEFT OUTER JOIN dim_product AS d_product" in sql and "d_product.tenant_id = %(tenant_id)s" in sql
    assert "LEFT OUTER JOIN dim_region AS r_region" in sql
    assert "coalesce(d_product.product_line, 'Unassigned')" in sql
    assert "preferred_distributor" not in sql


# ----------------------------------------------------------------------------- cache key


def test_v2_cache_key_hashes_request_tenant_version_scope_and_role():
    req = V2Request(measures=["dsi_sellout.units"], breakdowns=["customer"]).canonical()
    base = cache_key_v2(tenant_id="default", request=req, catalog_version="1.a.2")
    assert base.startswith("cip:query:model:v1:")
    assert cache_key_v2(tenant_id="other", request=req, catalog_version="1.a.2") != base
    assert cache_key_v2(tenant_id="default", request=req, catalog_version="1.b.2") != base
    req2 = V2Request(measures=["dsi_sellout.units"], breakdowns=["customer"], limit=10).canonical()
    assert cache_key_v2(tenant_id="default", request=req2, catalog_version="1.a.2") != base
    t1 = request_product_lines.set(frozenset({"NB"}))
    t2 = request_role.set("viewer")
    try:
        scoped = cache_key_v2(tenant_id="default", request=req, catalog_version="1.a.2")
    finally:
        request_product_lines.reset(t1)
        request_role.reset(t2)
    assert scoped != base
