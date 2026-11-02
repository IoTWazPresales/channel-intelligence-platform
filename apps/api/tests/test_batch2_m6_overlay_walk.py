"""GOV-008 M6: hiding or narrowing a legacy metric restricts EVERY measure that reads its column.

``dsi_sellout.priced_units`` is the same ``units`` column as ``sellout_units`` with a price filter; it stayed queryable and
listed when ``sellout_units`` was hidden. The walk below goes over the whole model catalog, so a measure added later on a
restricted column (or a calculated measure over one) cannot slip through.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.query.model.catalog import catalog_v2
from app.query.model.graph import V2Request, plan_request
from app.query.model.loader import Calculated, clear_model_cache, default_model
from app.query.model.tenant_restrictions import counterpart_policy
from app.semantics.registry import load_catalog


@pytest.fixture(autouse=True)
def _fresh_model():
    clear_model_cache()
    yield
    clear_model_cache()


def _catalog(key: str, **changes):
    cat = load_catalog()
    metrics = tuple(replace(m, **changes) if m.key == key else m for m in cat.metrics)
    return replace(cat, metrics=metrics, tenant_id="fictional-m6", overlay_applied=True)


def _restricted_by(dm, anchor) -> set[str]:
    """Independent of the production code: base measures on the anchor's column, and calculated measures over them."""
    ids = {m.id for m in dm.models[anchor.model].measures.values() if m.column and m.column == anchor.column}
    changed = True
    while changed:
        changed = False
        for c in dm.calculated.values():
            if c.id not in ids and any(i in ids for i in c.inputs):
                ids.add(c.id)
                changed = True
    return ids


def _legacy_anchors(dm):
    return [m for m in dm.measures.values() if m.legacy_key]


def test_every_measure_on_a_hidden_legacy_column_is_hidden_and_nothing_else():
    dm = default_model()
    anchors = _legacy_anchors(dm)
    assert anchors, "the model must still declare legacy-keyed measures"
    for anchor in anchors:
        catalog = _catalog(anchor.legacy_key, hidden=True, label="Fictional restricted")
        expected = _restricted_by(dm, anchor)
        every = {**dm.measures, **dm.calculated}
        hidden = {mid for mid, m in every.items() if (p := counterpart_policy(dm, m, catalog)) is not None and p.hidden}
        # Another legacy-keyed measure on a different column of the same model is unaffected by this one.
        assert expected <= hidden, f"{anchor.id} hidden but still reachable: {sorted(expected - hidden)}"
        assert not (hidden - expected), f"{anchor.id} hidden over-reaches: {sorted(hidden - expected)}"
        public = {m["id"] for m in catalog_v2(dm, catalog, is_admin=False)["measures"]}
        assert not (expected & public), f"{anchor.id} hidden but still listed: {sorted(expected & public)}"


def test_priced_units_refuses_when_sellout_units_is_hidden_and_keeps_its_own_label():
    catalog = _catalog("sellout_units", hidden=True, label="Fictional restricted")
    plan = plan_request(default_model(), V2Request(measures=["dsi_sellout.priced_units"], breakdowns=["customer"]), v1_catalog=catalog)
    assert plan.ok is False and "hidden for this tenant" in plan.refusals[0].reason
    admin = {m["id"]: m for m in catalog_v2(default_model(), catalog, is_admin=True)["measures"]}
    assert admin["dsi_sellout.priced_units"]["hidden"] is True
    assert admin["dsi_sellout.priced_units"]["label"] == "Sell-out units with a price"  # not the restricted metric's name
    assert admin["dsi_sellout.units"]["label"] == "Fictional restricted"
    # A measure on another column of the same model keeps working.
    ok = plan_request(default_model(), V2Request(measures=["dsi_sellout.lines"], breakdowns=["customer"]), v1_catalog=catalog)
    assert ok.ok is True


def test_narrowed_grains_reach_priced_units_and_every_calculated_measure_over_the_column():
    dm = default_model()
    catalog = _catalog("sellout_units", allowed_grains=(frozenset({"product"}),))
    for mid in ("dsi_sellout.priced_units", "dsi_sellout.units_avg", "dsi_sellout.units_per_week", "dsi_sellout.units_change"):
        m = dm.measure(mid)
        policy = counterpart_policy(dm, m, catalog)
        assert policy is not None and policy.grains == (frozenset({"product"}),), mid
    refused = plan_request(dm, V2Request(measures=["dsi_sellout.priced_units"], breakdowns=["customer"]), v1_catalog=catalog)
    assert refused.ok is False and "Requested {customer}" in refused.refusals[0].reason
    assert plan_request(dm, V2Request(measures=["dsi_sellout.priced_units"], breakdowns=["product"]), v1_catalog=catalog).ok


def test_calculated_measure_over_two_anchors_takes_the_hidden_one():
    """cpor.delivery_rate has no legacy anchor; a calculated measure over two anchors is hidden if either is."""
    dm = default_model()
    two = Calculated(**{**dm.calculated["dsi_sellout.units_change"].__dict__,
                        "inputs": ("cst_sellthrough.units", "dsi_sellout.units")})
    catalog = _catalog("sellout_units", hidden=True, label="Fictional restricted")
    assert counterpart_policy(dm, two, catalog).hidden is True
