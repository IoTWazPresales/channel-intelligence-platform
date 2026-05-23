"""DSI customer token vs dim_distributor name collision hints (no database)."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.imports.dsi_customer_intelligence import annotate_dsi_customer_distributor_name_collisions


def test_customer_token_matching_distributor_name_gets_collision_hint() -> None:
    dist = SimpleNamespace(id=42, name="Harbor Wholesale", code="DIST-02")
    agg = {
        ("customer_dealer_token", "harbor wholesale"): {
            "dealer_group_raw": "Harbor Wholesale",
            "source_customer_raw_samples": [],
            "sellout_distributor_ids": {1},
            "row_count": 3,
        },
        ("customer_dealer_token", "acme dealer"): {
            "dealer_group_raw": "Acme Dealer",
            "source_customer_raw_samples": [],
            "sellout_distributor_ids": {1},
            "row_count": 1,
        },
    }
    annotate_dsi_customer_distributor_name_collisions(agg, [dist])
    hit = agg[("customer_dealer_token", "harbor wholesale")].get("distributor_master_collision")
    assert hit is not None
    assert hit["distributor_id"] == 42
    assert hit["distributor_name"] == "Harbor Wholesale"
    assert "distributor_master_collision" not in agg[("customer_dealer_token", "acme dealer")]
