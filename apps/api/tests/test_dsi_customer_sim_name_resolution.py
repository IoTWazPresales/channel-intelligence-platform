"""DSI plan customer resolution: similarity-normalized name tier (unique match only)."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services.imports.distributor_sales_inventory import (
    DSIResolutionCache,
    DSIResolutionCustomerRow,
)
from app.services.imports.dsi_customer_name_normalization import (
    normalize_customer_name_for_similarity,
)
from app.services.imports.dsi_plan_build_context import DSIPlanBuildContext
from app.services.imports.dsi_resolution_plan import plan_dsi_candidate_sync


def _customer_plan_ctx(*, cache: DSIResolutionCache) -> DSIPlanBuildContext:
    return DSIPlanBuildContext(
        res_cache=cache,
        prod_idx=MagicMock(),
        regions_by_id={},
        channels_by_id={},
        region_code_lower={},
        region_name_lower={},
        channel_code_lower={},
        channel_name_lower={},
        region_aliases=(),
        channel_aliases=(),
        historical_customers={},
        job_customer_siblings_by_dealer_group={},
        product_staging_scopes={},
        shipment_corr_cache=None,
        global_product_identity=None,
    )


def _customer_cand(*, primary: str, dealer_group: str = "tbd") -> MagicMock:
    cand = MagicMock()
    cand.id = 1
    cand.entity_type = "customer_dealer_token"
    cand.status = "open"
    cand.normalized_key = primary.lower()
    cand.context = {
        "source_customer_name_raw_samples": [primary],
        "dealer_group_account_raw": dealer_group,
    }
    cand.row_count = 1
    cand.total_units = None
    cand.total_reported_value = None
    cand.dealer_group_token = None
    cand.source_definition_id = None
    cand.import_job_id = 99
    return cand


def test_plan_customer_similar_name_unique_match_maps_ready() -> None:
    master_name = "Acme Trading Pty Ltd"
    token = "Acme Trading"
    sim_key = normalize_customer_name_for_similarity(master_name)
    assert sim_key == normalize_customer_name_for_similarity(token)

    cache = DSIResolutionCache(
        all_distributors=[],
        dist_aliases=[],
        all_customers=[DSIResolutionCustomerRow(id=100, code="ACME", name=master_name)],
        customer_code_to_id={},
        customer_name_to_ids={master_name.strip().lower(): [100]},
        customer_sim_name_to_ids={sim_key: [100]},
        cust_aliases=[],
        open_channel_cid=None,
    )
    plan_ctx = _customer_plan_ctx(cache=cache)
    job = MagicMock()
    job.source.id = 9
    job.staged_metadata = {}

    out = plan_dsi_candidate_sync(
        MagicMock(),
        _customer_cand(primary=token),
        job,
        MagicMock(),
        default_region_id=None,
        default_channel_id=None,
        plan_ctx=plan_ctx,
    )
    assert out["suggested_action"] == "map_customer"
    assert out["plan_status"] == "ready"
    assert out["ready"] is True
    assert out["suggested_target_id"] == 100
    assert out["confidence"] == 0.9
    assert "legal-suffix/punctuation-insensitive" in out["reason"]
    assert out.get("resolution_signal") == "similar_customer_name"


def test_plan_customer_similar_name_ambiguous_falls_through_to_provisional() -> None:
    name_a = "Foo Bar Pty Ltd"
    name_b = "Foo Bar (Pty) Ltd"
    sim_key = normalize_customer_name_for_similarity(name_a)
    assert sim_key == normalize_customer_name_for_similarity(name_b)

    cache = DSIResolutionCache(
        all_distributors=[],
        dist_aliases=[],
        all_customers=[
            DSIResolutionCustomerRow(id=1, code="FB1", name=name_a),
            DSIResolutionCustomerRow(id=2, code="FB2", name=name_b),
        ],
        customer_code_to_id={},
        customer_name_to_ids={
            name_a.strip().lower(): [1],
            name_b.strip().lower(): [2],
        },
        customer_sim_name_to_ids={sim_key: [1, 2]},
        cust_aliases=[],
        open_channel_cid=None,
    )
    plan_ctx = _customer_plan_ctx(cache=cache)
    job = MagicMock()
    job.source.id = 9
    job.staged_metadata = {}

    out = plan_dsi_candidate_sync(
        MagicMock(),
        _customer_cand(primary="Foo Bar"),
        job,
        MagicMock(),
        default_region_id=None,
        default_channel_id=None,
        plan_ctx=plan_ctx,
    )
    assert out["suggested_action"] == "create_provisional_customer"
    assert out["plan_status"] == "ready"
    assert out.get("suggested_target_id") is None


def test_plan_customer_dealer_group_suffix_variant_matches_master() -> None:
    """Non-placeholder DG is resolution primary; sim tier matches legal-suffix master name."""
    master_name = "Acme Trading Pty Ltd"
    dealer_group = "Acme Trading"
    sim_key = normalize_customer_name_for_similarity(master_name)
    assert sim_key == normalize_customer_name_for_similarity(dealer_group)

    cache = DSIResolutionCache(
        all_distributors=[],
        dist_aliases=[],
        all_customers=[DSIResolutionCustomerRow(id=200, code="ACME", name=master_name)],
        customer_code_to_id={},
        customer_name_to_ids={master_name.strip().lower(): [200]},
        customer_sim_name_to_ids={sim_key: [200]},
        cust_aliases=[],
        open_channel_cid=None,
    )
    plan_ctx = _customer_plan_ctx(cache=cache)
    job = MagicMock()
    job.source.id = 9
    job.staged_metadata = {}

    cand = _customer_cand(primary="Store Branch 7", dealer_group=dealer_group)
    out = plan_dsi_candidate_sync(
        MagicMock(),
        cand,
        job,
        MagicMock(),
        default_region_id=None,
        default_channel_id=None,
        plan_ctx=plan_ctx,
    )
    assert out["suggested_action"] == "map_customer"
    assert out["ready"] is True
    assert out["suggested_target_id"] == 200
    assert out.get("resolution_signal") == "similar_customer_name"
