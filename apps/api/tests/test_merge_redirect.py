"""Merge-redirect guard: follow merged_into chains; never return a loser id."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.imports.distributor_sales_inventory import (
    DSIResolutionCache,
    DSIResolutionCustAliasRow,
    DSIResolutionCustomerRow,
    DSIResolutionDistributorRow,
    DSIResolutionDistAliasRow,
    _resolve_customer_from_cache,
    _resolve_distributor_from_cache,
)
from app.services.imports.provisional_entity_identity import (
    customer_source_token_alias_key,
    pick_provisional_customer_for_reuse,
)
from app.services.merge_redirect import (
    build_redirect_map,
    collapse_ids,
    follow_merge_chain,
    index_by_code_and_name,
    is_merged_customer_row,
    merged_into_customer_id,
    merged_into_distributor_id,
)


def test_follow_merge_chain_two_hop_reaches_final_survivor() -> None:
    parent = {1: 2, 2: 3, 3: None, 4: None}
    assert follow_merge_chain(1, parent) == 3
    assert follow_merge_chain(2, parent) == 3
    assert follow_merge_chain(3, parent) == 3
    assert follow_merge_chain(4, parent) == 4
    assert follow_merge_chain(None, parent) is None


def test_follow_merge_chain_cycle_does_not_hang() -> None:
    parent = {1: 2, 2: 1}
    out = follow_merge_chain(1, parent)
    assert out in (1, 2)


def test_build_redirect_map_terminals() -> None:
    redirect = build_redirect_map([(50, 788), (51, 788), (788, None), (26, 299), (299, None)])
    assert redirect[50] == 788
    assert redirect[51] == 788
    assert redirect[788] == 788
    assert redirect[26] == 299
    assert collapse_ids([50, 788, 51], redirect) == [788]


def test_token_resolving_to_merged_customer_returns_winner() -> None:
    cache = DSIResolutionCache(
        all_distributors=[],
        dist_aliases=[],
        all_customers=[
            DSIResolutionCustomerRow(id=788, code="ESQ", name="ESQUIRE TECHNOLOGIES"),
        ],
        customer_code_to_id={"tmp-cust-loser": 788},
        customer_name_to_ids={"esquire": [788]},
        customer_sim_name_to_ids={},
        cust_aliases=[
            DSIResolutionCustAliasRow(
                normalized_token="esquire",
                match_key=customer_source_token_alias_key("esquire"),
                source_definition_id=None,
                distributor_id=None,
                customer_id=50,
            )
        ],
        open_channel_cid=None,
        customer_redirect={50: 788, 788: 788},
        distributor_redirect={},
    )
    cid, diag = _resolve_customer_from_cache(
        source_id=None,
        distributor_id=None,
        customer_raw="esquire",
        dealer_group_raw=None,
        channel_raw=None,
        open_flag_raw=None,
        res_cache=cache,
    )
    assert cid == 788
    assert "customer_resolved_alias" in diag

    cid_code, diag_code = _resolve_customer_from_cache(
        source_id=None,
        distributor_id=None,
        customer_raw="TMP-CUST-LOSER",
        dealer_group_raw=None,
        channel_raw=None,
        open_flag_raw=None,
        res_cache=cache,
    )
    assert cid_code == 788
    assert "customer_resolved_code" in diag_code


def test_provisional_reuse_never_selects_merged_row() -> None:
    living = SimpleNamespace(
        id=10,
        code="TMP-CUST-LIVE",
        name="Acme Stores",
        customer_status="unverified",
        merged_into_customer_id=None,
    )
    merged = SimpleNamespace(
        id=9,
        code="TMP-CUST-DEAD",
        name="Acme Stores",
        customer_status="merged",
        merged_into_customer_id=88,
    )
    assert is_merged_customer_row(merged) is True
    assert is_merged_customer_row(living) is False
    pick = pick_provisional_customer_for_reuse([merged, living], "Acme Stores")
    assert pick is living
    assert pick_provisional_customer_for_reuse([merged], "Acme Stores") is None


def test_missing_merged_into_attr_is_not_merged() -> None:
    row = SimpleNamespace(id=1, code="X", name="X")
    assert is_merged_customer_row(row) is False
    assert merged_into_customer_id(row) is None
    assert merged_into_distributor_id(row) is None
    m = index_by_code_and_name([row], merged_into_attr="merged_into_customer_id")
    assert m["x"] is row


def test_index_by_code_and_name_points_loser_keys_at_winner() -> None:
    winner = SimpleNamespace(id=788, code="ESQ-WIN", name="ESQUIRE TECHNOLOGIES", merged_into_customer_id=None)
    loser = SimpleNamespace(id=50, code="TMP-CUST-ESQ", name="Esquire", merged_into_customer_id=788)
    m = index_by_code_and_name([winner, loser], merged_into_attr="merged_into_customer_id")
    assert m["esquire"] is winner
    assert m["tmp-cust-esq"] is winner
    assert m["esq-win"] is winner
    assert int(m["esquire"].id) == 788


def test_unique_alias_map_collapses_loser_and_winner_to_survivor() -> None:
    from app.services.imports.shipment_evidence_resolution_plan import (
        build_unique_approved_customer_alias_id_by_token,
    )

    rows = [
        ("esquire", 50, None),
        ("esquire", 788, None),
        ("amazon", 26, 1),
    ]
    redirect = {50: 788, 788: 788, 26: 299, 299: 299}
    m = build_unique_approved_customer_alias_id_by_token(rows, redirect=redirect)
    assert m["esquire"] == 788
    assert m["amazon"] == 299


def test_max_hops_cycle_does_not_hang() -> None:
    parent = {i: i + 1 for i in range(1, 40)}
    parent[40] = 1
    out = follow_merge_chain(1, parent, max_hops=32)
    assert out is not None
    assert isinstance(out, int)


def test_distributor_alias_to_merged_row_returns_winner() -> None:
    cache = DSIResolutionCache(
        all_distributors=[
            DSIResolutionDistributorRow(id=9, code="LOSER-D", name="Loser Dist"),
            DSIResolutionDistributorRow(id=2, code="WIN-D", name="Winner Dist"),
        ],
        dist_aliases=[
            DSIResolutionDistAliasRow(normalized_token="loser dist", source_definition_id=None, distributor_id=9),
        ],
        all_customers=[],
        customer_code_to_id={},
        customer_name_to_ids={},
        customer_sim_name_to_ids={},
        cust_aliases=[],
        open_channel_cid=None,
        customer_redirect={},
        distributor_redirect={9: 2, 2: 2},
    )
    did, err = _resolve_distributor_from_cache("loser dist", None, cache)
    assert err is None
    assert did == 2
