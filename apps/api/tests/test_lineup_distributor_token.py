"""Unit tests for distributor-token classifier (no DB)."""

from __future__ import annotations

from app.services.commercial_planner.lineup_distributor_token import (
    distributor_match_keys,
    match_distributor_token,
)


def test_match_keys_strips_structured_patterns():
    assert distributor_match_keys("mitsumi") == ["mitsumi"]
    assert distributor_match_keys("mitsumi distribution") == ["mitsumi distribution", "mitsumi"]
    assert distributor_match_keys("sadc - compuspeed") == ["sadc - compuspeed", "compuspeed"]
    assert distributor_match_keys("channel syntech") == ["channel syntech", "syntech"]
    assert distributor_match_keys("channel - syntech") == ["channel - syntech", "syntech"]


def test_exact_match_no_substring():
    names = {"mitsumi": 22, "compuspeed": 12, "syntech": 51, "dcc": 14}
    aliases: dict[str, int] = {}
    assert match_distributor_token("mitsumi", name_to_id=names, alias_to_id=aliases).distributor_id == 22
    assert (
        match_distributor_token("mitsumi distribution", name_to_id=names, alias_to_id=aliases).distributor_id
        == 22
    )
    assert (
        match_distributor_token("sadc - compuspeed", name_to_id=names, alias_to_id=aliases).distributor_id
        == 12
    )
    assert (
        match_distributor_token("channel syntech", name_to_id=names, alias_to_id=aliases).distributor_id
        == 51
    )
    # no fuzzy / substring: "mi" must not match Mitsumi
    assert match_distributor_token("mi", name_to_id=names, alias_to_id=aliases) is None
    assert match_distributor_token("smd", name_to_id=names, alias_to_id=aliases) is None
    assert match_distributor_token("superdisti", name_to_id=names, alias_to_id=aliases) is None


def test_preferred_target_never_preselects_ship_only():
    from app.services.commercial_planner.lineup_customer_token_stamp import _preferred_target

    assert (
        _preferred_target(
            bucket="clean",
            named_only=[299],
            all_cands={299},
            alias_cids=set(),
            ship_cids={299},
        )
        is None
    )
    assert (
        _preferred_target(
            bucket="clean",
            named_only=[299],
            all_cands={299},
            alias_cids={299},
            ship_cids={299},
        )
        == 299
    )
