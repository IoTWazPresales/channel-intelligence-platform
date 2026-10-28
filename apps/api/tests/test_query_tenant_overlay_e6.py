"""E6: tenant overlay reaches v2 counterparts, spec keys, and avg/min/max."""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.query.cache import cache_key_v2
from app.query.model.catalog import catalog_v2
from app.query.model.compiler import compile_plan
from app.query.model.execute import catalog_version_for
from app.query.model.graph import V2Request, plan_request
from app.query.model.loader import clear_model_cache, default_model
from app.query.model.tenant_restrictions import normalize_spec_keys
from app.semantics.registry import SemanticCatalog, load_catalog


@pytest.fixture(autouse=True)
def _fresh_model():
    clear_model_cache()
    yield
    clear_model_cache()


def _catalog(**metric_changes) -> SemanticCatalog:
    cat = load_catalog()
    metrics = []
    for metric in cat.metrics:
        if metric.key == "sellout_units" and metric_changes:
            metrics.append(replace(metric, **metric_changes))
        else:
            metrics.append(metric)
    return replace(cat, metrics=tuple(metrics), tenant_id="fictional-review", overlay_applied=True)


def _plan(catalog, measures, breakdowns):
    return plan_request(
        default_model(),
        V2Request(measures=measures, breakdowns=breakdowns),
        v1_catalog=catalog,
    )


def test_hidden_legacy_measure_blocks_the_v2_counterpart_and_line_aggregates():
    catalog = _catalog(hidden=True, label="Fictional restricted metric")
    refused = _plan(catalog, ["dsi_sellout.units"], ["customer"])
    assert refused.ok is False
    assert refused.refusals[0].reason == (
        "Metric Fictional restricted metric (sellout_units) is hidden for this tenant and cannot be queried."
    )
    for measure in ("dsi_sellout.units_avg", "dsi_sellout.units_min", "dsi_sellout.units_max", "dsi_sellout.units_prior_period"):
        again = _plan(catalog, [measure], ["product"])
        assert again.ok is False
        assert "hidden for this tenant" in again.refusals[0].reason
    lines = _plan(catalog, ["dsi_sellout.lines"], ["customer"])
    assert lines.ok is True


def test_narrowed_grains_refuse_other_breakdowns_and_the_catalog_matches():
    catalog = _catalog(
        label="Fictional restricted metric",
        allowed_grains=(frozenset({"product"}),),
    )
    refused = _plan(catalog, ["dsi_sellout.units"], ["customer"])
    assert refused.ok is False
    assert "Requested {customer}" in refused.refusals[0].reason
    allowed = _plan(catalog, ["dsi_sellout.units"], ["product"])
    assert allowed.ok is True

    dm = default_model()
    public = catalog_v2(dm, catalog, is_admin=False)
    entry = next(m for m in public["measures"] if m["id"] == "dsi_sellout.units")
    assert entry["label"] == "Fictional restricted metric"
    assert entry["breakdowns"] == ["product"]
    assert "customer" not in entry["breakdowns"]


def test_hidden_measure_is_omitted_for_non_admins_and_flagged_for_admins():
    catalog = _catalog(hidden=True, label="Fictional restricted metric")
    dm = default_model()
    public = catalog_v2(dm, catalog, is_admin=False)
    assert all(m["id"] != "dsi_sellout.units" for m in public["measures"])
    admin = catalog_v2(dm, catalog, is_admin=True)
    entry = next(m for m in admin["measures"] if m["id"] == "dsi_sellout.units")
    assert entry["hidden"] is True
    assert entry["label"] == "Fictional restricted metric"


def test_spec_keys_reject_cycles_injection_duplicates_and_nulls():
    assert normalize_spec_keys(None, strict=True) == []
    assert normalize_spec_keys(["GPU"], strict=True) == ["gpu"]
    with pytest.raises(ValueError, match="nested path"):
        normalize_spec_keys(["gpu.vram", "vram.gpu"], strict=True)
    with pytest.raises(ValueError, match="not an allowed spec key"):
        normalize_spec_keys(["gpu'; drop table dim_product --"], strict=True)
    with pytest.raises(ValueError, match="duplicate"):
        normalize_spec_keys(["gpu", "gpu"], strict=True)
    with pytest.raises(ValueError, match="null"):
        normalize_spec_keys(["gpu", None], strict=True)
    assert normalize_spec_keys("not-a-list", strict=False) == []


def test_unknown_spec_key_is_refused_and_an_allowed_key_compiles_as_a_bound_extract():
    platform = load_catalog()
    unknown = _plan(platform, ["dsi_sellout.units"], ["spec_gpu"])
    assert unknown.ok is False
    assert "spec key" in unknown.refusals[0].reason

    allowed_catalog = replace(platform, spec_keys=("gpu",))
    planned = _plan(allowed_catalog, ["dsi_sellout.units"], ["spec_gpu"])
    assert planned.ok is True
    compiled = compile_plan(default_model(), planned, tenant_id="fictional-review")
    sql = str(compiled.rows.compile(compile_kwargs={"literal_binds": False}))
    assert "->>" in sql
    assert "spec_key_gpu" in sql
    assert "drop table" not in sql.lower()

    listed = catalog_v2(default_model(), allowed_catalog, is_admin=False)
    assert any(b["id"] == "spec_gpu" and b["kind"] == "spec" for b in listed["breakdowns"])


def test_catalog_version_and_cache_key_change_with_tenant_and_spec_keys():
    dm = default_model()
    base = load_catalog()
    with_gpu = replace(base, version=base.version + 1, spec_keys=("gpu",))
    assert catalog_version_for(dm, base) != catalog_version_for(dm, with_gpu)
    one = cache_key_v2(tenant_id="tenant-a", request={"measures": ["dsi_sellout.units"]}, catalog_version=catalog_version_for(dm, base))
    two = cache_key_v2(tenant_id="tenant-b", request={"measures": ["dsi_sellout.units"]}, catalog_version=catalog_version_for(dm, base))
    three = cache_key_v2(tenant_id="tenant-a", request={"measures": ["dsi_sellout.units"]}, catalog_version=catalog_version_for(dm, with_gpu))
    assert len({one, two, three}) == 3


def test_avg_min_max_are_registered_on_the_unit_columns():
    dm = default_model()
    assert dm.measures["dsi_sellout.units_avg"].column == "units"
    assert dm.measures["dsi_sellout.units_min"].agg == "min"
    assert dm.measures["dsi_sellout.units_max"].agg == "max"
    assert dm.measures["cst_sellthrough.units_avg"].column == "units_sold"
    assert dm.measures["dsi_sellout.units"].agg == "sum"
