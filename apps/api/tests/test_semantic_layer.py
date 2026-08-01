from pathlib import Path

import yaml

from app.semantics.registry import (
    _TENANT_DIR,
    catalog_for_tenant,
    clear_catalog_cache,
    default_catalog,
    validate_metric_grain,
)


def test_catalog_covers_implemented_core_metrics():
    cat = default_catalog()
    keys = {m.key for m in cat.metrics}
    required = {
        "fill_rate",
        "line_hit_rate",
        "over_plan_intake_rate",
        "short_exposure",
        "unplanned_intake",
        "no_po_blind_spot",
        "pipeline_inbound",
        "volume_bias",
        "slip",
        "support_spend",
        "delivery_rate",
        "support_norms",
        "comparable_cases",
        "support_cost_per_unit_sold",
        "claim_rate",
        "channel_stock",
        "weeks_of_cover",
        "replenishment_flag",
        "forecast_units",
        "forecast_confidence",
        "forecast_band",
        "forecast_method",
        "analogue_provenance",
        "lifecycle_buckets",
        "commercial_cohorts",
    }
    missing = required - keys
    assert not missing, f"Catalog missing metrics: {sorted(missing)}"
    dims = {d.id for d in cat.dimensions}
    assert {"period", "distributor", "product", "bu", "site_label", "promo_type"} <= dims


def test_weeks_of_cover_valid_at_dist_product():
    r = validate_metric_grain("weeks_of_cover", ["distributor", "product"])
    assert r.ok is True
    assert r.metric_id == "A3-02"


def test_weeks_of_cover_refuses_period_bu():
    r = validate_metric_grain("A3-02", ["period", "bu"])
    assert r.ok is False
    assert "distributor" in r.message.lower() or "not allowed" in r.message.lower()


def test_channel_stock_refuses_lineup_quarter():
    r = validate_metric_grain("channel_stock", ["lineup_quarter"])
    assert r.ok is False
    assert "lineup" in r.message.lower() or "refused" in r.message.lower() or "distributor" in r.message.lower()


def test_claim_rate_always_refused():
    r = validate_metric_grain("claim_rate", ["customer"])
    assert r.ok is False
    assert "non-computable" in r.message.lower() or "not queryable" in r.message.lower()


def test_unknown_metric_refused():
    r = validate_metric_grain("made_up_margin", ["product"])
    assert r.ok is False
    assert "unknown metric" in r.message.lower()


def test_fill_rate_valid_period_bu():
    r = validate_metric_grain("fill_rate", ["period", "bu"])
    assert r.ok is True


def test_support_spend_valid_customer_bu():
    r = validate_metric_grain("support_spend", ["customer", "bu"])
    assert r.ok is True
    assert r.metric_id == "A2-01"


def test_incremental_cost_refused():
    r = validate_metric_grain("cost_per_incremental_unit", ["customer"])
    assert r.ok is False


def test_tenant_overlay_merges_metric(tmp_path=None):
    clear_catalog_cache()
    overlay = {
        "version": 1,
        "metrics": [
            {
                "id": "T-DEMO",
                "key": "tenant_demo_metric",
                "label": "Tenant demo",
                "status": "implemented",
                "owner_surface": "custom",
                "formula": "1",
                "source_facts": [],
                "allowed_grains": [["period"]],
            }
        ],
        "dimensions": [],
    }
    _TENANT_DIR.mkdir(parents=True, exist_ok=True)
    path = _TENANT_DIR / "acme.yaml"
    try:
        path.write_text(yaml.safe_dump(overlay), encoding="utf-8")
        clear_catalog_cache()
        cat = catalog_for_tenant("acme")
        assert cat.overlay_applied is True
        assert cat.metric_by_key("tenant_demo_metric") is not None
        r = validate_metric_grain("tenant_demo_metric", ["period"], tenant_id="acme")
        assert r.ok is True
        # default tenant must not see overlay metric
        r2 = validate_metric_grain("tenant_demo_metric", ["period"], tenant_id="default")
        assert r2.ok is False
    finally:
        if path.exists():
            path.unlink()
        clear_catalog_cache()
