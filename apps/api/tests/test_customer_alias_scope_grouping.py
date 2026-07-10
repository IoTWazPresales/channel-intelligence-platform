"""Tests for canonical customer alias-scope conflict grouping."""

from __future__ import annotations

from app.services.customer_alias_scope_grouping import (
    canonical_customer_alias_token,
    customer_ids_for_canonical_scope_conflict,
    group_approved_customer_alias_scope_conflicts,
)


def test_canonical_key_unifies_pty_ltd_variants() -> None:
    assert canonical_customer_alias_token("vexall (pty) ltd") == "vexall pty ltd"
    assert canonical_customer_alias_token("vexall (pty)ltd") == "vexall pty ltd"
    assert canonical_customer_alias_token("vexall") == "vexall"


def test_group_conflicts_by_canonical_token_not_raw_column() -> None:
    rows = [
        ("vexall (pty) ltd", 296, 12, None),
        ("vexall (pty)ltd", 4521, 12, None),
        ("vexall", 296, 12, None),
        ("unique dealer only", 1, 12, None),
    ]
    groups = group_approved_customer_alias_scope_conflicts(rows)
    assert len(groups) == 1
    g = groups[0]
    assert g["canonical_token"] == "vexall pty ltd"
    assert set(g["customer_ids"]) == {296, 4521}
    assert "vexall (pty)ltd" in g["token_variants"]


def test_customer_ids_for_canonical_scope_conflict() -> None:
    rows = [
        ("vexall (pty) ltd", 296, 12, None),
        ("vexall (pty)ltd", 4521, 12, None),
    ]
    ids = customer_ids_for_canonical_scope_conflict(
        rows,
        normalized_token="vexall (pty)ltd",
        source_definition_id=12,
        distributor_id=None,
    )
    assert ids == [296, 4521]
