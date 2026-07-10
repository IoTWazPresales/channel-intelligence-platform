"""DSI customer alias lookup uses punctuation-robust canonical keys (revalidate re-finds steward aliases)."""

from __future__ import annotations

from app.services.imports.distributor_sales_inventory import (
    DSIResolutionCache,
    DSIResolutionCustAliasRow,
    DSIResolutionDistributorRow,
    DSIResolutionDistAliasRow,
    _cust_alias_row_from_orm,
    _resolve_customer_from_cache,
    _resolve_distributor_from_cache,
)
from app.services.imports.provisional_entity_identity import (
    canonical_provisional_entity_name_key,
    customer_source_token_alias_key,
)
from app.services.imports.source_token_alias_conflicts import (
    MULTIPLE_CUSTOMER_ALIASES,
    customer_alias_conflict_reason_from_cache,
)


def _cust_alias_row(
    *,
    normalized_token: str,
    customer_id: int,
    source_definition_id: int | None = 12,
    distributor_id: int | None = None,
    match_key: str | None = None,
) -> DSIResolutionCustAliasRow:
    return DSIResolutionCustAliasRow(
        normalized_token=normalized_token,
        match_key=match_key or customer_source_token_alias_key(normalized_token),
        source_definition_id=source_definition_id,
        distributor_id=distributor_id,
        customer_id=customer_id,
    )


def _cache_with_aliases(*aliases: DSIResolutionCustAliasRow) -> DSIResolutionCache:
    return DSIResolutionCache(
        all_distributors=[],
        dist_aliases=[],
        all_customers=[],
        customer_code_to_id={},
        customer_name_to_ids={},
        customer_sim_name_to_ids={},
        cust_aliases=list(aliases),
        open_channel_cid=None,
    )


def test_canonical_key_reconciles_pty_parens_variants() -> None:
    stored = "itech administrators (pty) ltd"
    lookup = "itech administrators pty ltd"
    assert customer_source_token_alias_key(stored) == customer_source_token_alias_key(lookup)
    assert customer_source_token_alias_key(stored) == canonical_provisional_entity_name_key(lookup)


def test_legacy_stored_alias_re_found_on_dealer_group_revalidate() -> None:
    """Steward wrote alias from customer-name string; revalidate keys on dealer-group token."""
    cache = _cache_with_aliases(
        _cust_alias_row(normalized_token="itech administrators (pty) ltd", customer_id=1839),
    )
    cid, diag = _resolve_customer_from_cache(
        source_id=12,
        distributor_id=38,
        customer_raw="itech administrators pty ltd",
        dealer_group_raw="itech administrators pty ltd",
        channel_raw=None,
        open_flag_raw=None,
        res_cache=cache,
    )
    assert cid == 1839
    assert "customer_resolved_alias" in diag


def test_rand_data_parens_mismatch_re_found() -> None:
    cache = _cache_with_aliases(
        _cust_alias_row(normalized_token="rand data systems (pty) ltd", customer_id=2859),
    )
    cid, diag = _resolve_customer_from_cache(
        source_id=12,
        distributor_id=None,
        customer_raw="rand data systems pty ltd",
        dealer_group_raw="rand data systems pty ltd",
        channel_raw=None,
        open_flag_raw=None,
        res_cache=cache,
    )
    assert cid == 2859
    assert "customer_resolved_alias" in diag


def test_cust_alias_row_from_orm_canonicalizes_match_key_for_legacy_rows() -> None:
    class _Row:
        normalized_token = "itech administrators (pty) ltd"
        source_definition_id = 12
        distributor_id = None
        customer_id = 1839

    row = _cust_alias_row_from_orm(_Row())  # type: ignore[arg-type]
    assert row.match_key == "itech administrators pty ltd"
    assert row.normalized_token == "itech administrators (pty) ltd"


def test_multi_customer_canonical_collision_stays_reviewable() -> None:
    canon = "vexall pty ltd"
    cache = _cache_with_aliases(
        _cust_alias_row(normalized_token="vexall (pty) ltd", customer_id=296),
        _cust_alias_row(normalized_token="vexall pty ltd", customer_id=4521),
    )
    cid, _ = _resolve_customer_from_cache(
        source_id=12,
        distributor_id=None,
        customer_raw=canon,
        dealer_group_raw=canon,
        channel_raw=None,
        open_flag_raw=None,
        res_cache=cache,
    )
    assert cid is None
    assert (
        customer_alias_conflict_reason_from_cache(
            cache,
            source_definition_id=12,
            distributor_id=None,
            normalized_token=canon,
        )
        == MULTIPLE_CUSTOMER_ALIASES
    )


def test_distributor_resolution_unchanged_by_customer_alias_key_change() -> None:
    cache = DSIResolutionCache(
        all_distributors=[DSIResolutionDistributorRow(id=38, code="rectron", name="Rectron")],
        dist_aliases=[
            DSIResolutionDistAliasRow(normalized_token="rectron", source_definition_id=12, distributor_id=38),
        ],
        all_customers=[],
        customer_code_to_id={},
        customer_name_to_ids={},
        customer_sim_name_to_ids={},
        cust_aliases=[],
        open_channel_cid=None,
    )
    did, _ = _resolve_distributor_from_cache("rectron", 12, cache)
    assert did == 38
