"""Unit tests for related-master customer groups (anchored containment)."""

from __future__ import annotations

from datetime import datetime, timezone

from app.services.customer_duplicate_groups import _CustomerRow
from app.services.customer_related_master_groups import build_related_master_groups
from app.services.imports.dsi_customer_name_normalization import (
    anchor_is_eligible,
    containment_score,
    is_token_prefix_containment,
    normalize_customer_name_for_similarity,
)


def _row(
    id: int,
    name: str,
    *,
    code: str | None = None,
    status: str = "active",
    created_at: datetime | None = None,
) -> _CustomerRow:
    return _CustomerRow(
        id=id,
        code=code or f"CUST-{id}",
        name=name,
        customer_status=status,
        created_at=created_at,
    )


def test_token_prefix_containment_helpers():
    assert is_token_prefix_containment("amazon", "amazon commercial se") is True
    assert is_token_prefix_containment("computer mania", "computer mania centl") is True
    assert is_token_prefix_containment("amazon", "amazon") is False
    assert is_token_prefix_containment("amazon commercial", "amazon") is False
    assert containment_score("amazon", "amazon commercial se") == round(
        len("amazon") / len("amazon commercial se"), 4
    )


def test_anchor_eligibility_guards():
    assert anchor_is_eligible("amazon") is True
    assert anchor_is_eligible("computer mania") is True
    assert anchor_is_eligible("trading") is False
    assert anchor_is_eligible("computers") is False
    assert anchor_is_eligible("sa") is False
    assert anchor_is_eligible("tb") is False


def test_amazon_and_computer_mania_contained_prefix_groups():
    rows = [
        _row(1, "Amazon"),
        _row(2, "AMAZON COMMERCIAL SE"),
        _row(3, "Computer Mania"),
        _row(4, "COMPUTER MANIA CENTL"),
        _row(5, "Unique Solo"),
    ]
    groups = build_related_master_groups(rows)
    by_key = {g["anchor_similarity_key"]: g for g in groups}

    amazon_key = normalize_customer_name_for_similarity("Amazon")
    mania_key = normalize_customer_name_for_similarity("Computer Mania")
    assert amazon_key in by_key
    assert mania_key in by_key

    amazon = by_key[amazon_key]
    assert amazon["member_count"] == 2
    assert amazon["members"][0].id == 1
    assert amazon["member_meta"][2]["match_basis"] == "contained_prefix"

    mania = by_key[mania_key]
    assert mania["member_count"] == 2
    assert mania["members"][0].id == 3
    assert mania["member_meta"][4]["match_basis"] == "contained_prefix"


def test_tb_computers_vs_tb_solutions_no_group():
    rows = [
        _row(1, "TB Computers"),
        _row(2, "TB Solutions"),
    ]
    assert build_related_master_groups(rows) == []


def test_generic_and_short_anchors_do_not_group():
    rows = [
        _row(1, "Trading"),
        _row(2, "Trading Extra Name"),
        _row(3, "SA"),
        _row(4, "SA Retail Branch"),
        _row(5, "Computers"),
        _row(6, "Computers Extra"),
    ]
    groups = build_related_master_groups(rows)
    forbidden_anchors = {"sa", "trading", "computers", "tb"}
    assert all(g["anchor_similarity_key"] not in forbidden_anchors for g in groups)
    # Short/generic singles must not appear as related members either.
    member_names = {m.name for g in groups for m in g["members"]}
    assert "SA" not in member_names
    assert "Trading" not in member_names
    assert "Computers" not in member_names
    assert groups == []


def test_exact_normalized_dupes_not_related_members():
    rows = [
        _row(1, "Acme Corp Pty Ltd"),
        _row(2, "ACME CORP (PTY) LTD"),
    ]
    # Same similarity key — belongs on name-similarity tab, not related.
    assert build_related_master_groups(rows) == []


def test_survivor_hint_order_on_related_members():
    older = datetime(2020, 1, 1, tzinfo=timezone.utc)
    newer = datetime(2024, 1, 1, tzinfo=timezone.utc)
    rows = [
        _row(1, "Amazon", status="unverified", created_at=newer),
        _row(2, "AMAZON COMMERCIAL SE", status="active", created_at=older),
        _row(3, "AMAZON RETAIL SE", status="unverified", created_at=newer),
    ]
    groups = build_related_master_groups(rows)
    amazon = next(g for g in groups if g["anchor_similarity_key"] == "amazon")
    assert amazon["members"][0].id == 1  # anchor pinned first
    related_ids = [m.id for m in amazon["members"][1:]]
    assert related_ids[0] == 2  # verified/oldest among related
