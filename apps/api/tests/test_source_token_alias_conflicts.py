"""Tests for alias conflict diagnostics (INT-03 surfacing, resolution unchanged)."""

from __future__ import annotations

from app.services.imports.provisional_entity_identity import customer_source_token_alias_key
from app.services.imports.distributor_sales_inventory import (
    DSIResolutionCache,
    DSIResolutionCustAliasRow,
    DSIResolutionDistAliasRow,
)
from app.services.imports.source_token_alias_conflicts import (
    MULTIPLE_CUSTOMER_ALIASES,
    MULTIPLE_DISTRIBUTOR_ALIASES,
    customer_alias_conflict_reason_from_cache,
    distributor_alias_conflict_reason_from_cache,
)


def _dist_cache(*aliases) -> DSIResolutionCache:
    return DSIResolutionCache(
        all_distributors=[],
        dist_aliases=list(aliases),
        all_customers=[],
        customer_code_to_id={},
        customer_name_to_ids={},
        customer_sim_name_to_ids={},
        cust_aliases=[],
        open_channel_cid=None,
    )


def test_distributor_multi_alias_conflict_detected() -> None:
    cache = _dist_cache(
        DSIResolutionDistAliasRow(normalized_token="acme", source_definition_id=None, distributor_id=1),
        DSIResolutionDistAliasRow(normalized_token="acme", source_definition_id=None, distributor_id=2),
    )
    assert (
        distributor_alias_conflict_reason_from_cache(cache, source_definition_id=10, normalized_token="acme")
        == MULTIPLE_DISTRIBUTOR_ALIASES
    )


def test_distributor_single_alias_no_conflict() -> None:
    cache = _dist_cache(
        DSIResolutionDistAliasRow(normalized_token="acme", source_definition_id=None, distributor_id=1),
    )
    assert distributor_alias_conflict_reason_from_cache(cache, source_definition_id=10, normalized_token="acme") is None


def test_customer_multi_alias_conflict_detected() -> None:
    cache = DSIResolutionCache(
        all_distributors=[],
        dist_aliases=[],
        all_customers=[],
        customer_code_to_id={},
        customer_name_to_ids={},
        customer_sim_name_to_ids={},
        cust_aliases=[
            DSIResolutionCustAliasRow(
                normalized_token="dealer1",
                match_key=customer_source_token_alias_key("dealer1"),
                source_definition_id=None,
                distributor_id=5,
                customer_id=100,
            ),
            DSIResolutionCustAliasRow(
                normalized_token="dealer1",
                match_key=customer_source_token_alias_key("dealer1"),
                source_definition_id=None,
                distributor_id=5,
                customer_id=101,
            ),
        ],
        open_channel_cid=None,
    )
    assert (
        customer_alias_conflict_reason_from_cache(
            cache, source_definition_id=1, distributor_id=5, normalized_token="dealer1"
        )
        == MULTIPLE_CUSTOMER_ALIASES
    )
