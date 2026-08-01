from app.semantics.registry import default_catalog, validate_metric_grain


def test_catalog_loads_governed_metrics():
    cat = default_catalog()
    assert cat.version == 1
    keys = {m.key for m in cat.metrics}
    assert "fill_rate" in keys
    assert "weeks_of_cover" in keys
    assert "channel_stock" in keys
    assert "claim_rate" in keys
    dims = {d.id for d in cat.dimensions}
    assert {"period", "distributor", "product", "bu", "site_label"} <= dims


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
