from datetime import datetime, timezone

from app.services.customer_duplicate_groups import (
    _CustomerRow,
    build_duplicate_groups,
    is_verified_for_survivor_hint,
    paginate_groups,
    survivor_hint_sort_key,
)
from app.services.imports.dsi_customer_name_normalization import normalize_customer_name_for_similarity


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


def test_build_duplicate_groups_filters_singletons_and_empty_keys():
    rows = [
        _row(1, "Acme Corp Pty Ltd"),
        _row(2, "ACME CORP (PTY) LTD"),
        _row(3, "Unique Retailer"),
        _row(4, "   "),
    ]
    groups = build_duplicate_groups(rows)
    assert len(groups) == 1
    assert groups[0]["member_count"] == 2
    assert groups[0]["similarity_key"] == normalize_customer_name_for_similarity("Acme Corp Pty Ltd")


def test_survivor_hint_prefers_verified_then_oldest():
    older = datetime(2020, 1, 1, tzinfo=timezone.utc)
    newer = datetime(2024, 1, 1, tzinfo=timezone.utc)
    members = [
        _row(2, "Acme Corp Pty Ltd", status="unverified", created_at=older),
        _row(3, "ACME CORP (PTY) LTD", status="active", created_at=newer),
        _row(1, "Acme Corp Limited", status="active", created_at=older),
    ]
    groups = build_duplicate_groups(members)
    sorted_ids = [m.id for m in groups[0]["members"]]
    assert sorted_ids[0] == 1
    assert is_verified_for_survivor_hint("active") is True
    assert is_verified_for_survivor_hint("unverified") is False


def test_survivor_hint_sort_key_orders_verified_before_unverified():
    verified = _row(1, "A", status="active", created_at=datetime(2024, 1, 1, tzinfo=timezone.utc))
    unverified = _row(2, "B", status="unverified", created_at=datetime(2020, 1, 1, tzinfo=timezone.utc))
    assert survivor_hint_sort_key(verified) < survivor_hint_sort_key(unverified)


def test_paginate_groups():
    groups = [{"similarity_key": f"k{i}", "member_count": 2, "members": []} for i in range(5)]
    page, total = paginate_groups(groups, page=2, page_size=2)
    assert total == 5
    assert len(page) == 2
    assert page[0]["similarity_key"] == "k2"
