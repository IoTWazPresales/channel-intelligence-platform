"""Read-only potential-duplicate customer groups keyed by similarity-normalised name."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.derived import StockHealth, StockRisk, WeeksOfStock
from app.models.dimensions import CustomerContact, CustomerLocation, DimCustomer
from app.models.facts import FactInboundShipment
from app.services.customer_usage import _SPECS, _extra_customer_subqueries
from app.services.imports.dsi_customer_name_normalization import normalize_customer_name_for_similarity
from app.services.master_usage_batch import batch_counts_multi_table, count_subquery_for_columns

_SURVIVOR_UNVERIFIED_STATUSES = frozenset({"unverified", "needs_review"})


@dataclass(frozen=True)
class _CustomerRow:
    id: int
    code: str
    name: str
    customer_status: str
    created_at: datetime | None


def is_verified_for_survivor_hint(customer_status: str | None) -> bool:
    return (customer_status or "").strip().lower() not in _SURVIVOR_UNVERIFIED_STATUSES


def survivor_hint_sort_key(row: _CustomerRow) -> tuple[int, float, int]:
    """Verified customers first; among equals prefer oldest (earliest created_at)."""
    verified_rank = 0 if is_verified_for_survivor_hint(row.customer_status) else 1
    created_ts = row.created_at.timestamp() if row.created_at is not None else float("inf")
    return (verified_rank, created_ts, row.id)


def build_duplicate_groups(rows: list[_CustomerRow]) -> list[dict[str, Any]]:
    """Group customers by similarity key; keep only groups with 2+ members."""
    buckets: dict[str, list[_CustomerRow]] = defaultdict(list)
    for row in rows:
        key = normalize_customer_name_for_similarity(row.name)
        if not key:
            continue
        buckets[key].append(row)

    groups: list[dict[str, Any]] = []
    for similarity_key, members in buckets.items():
        if len(members) < 2:
            continue
        sorted_members = sorted(members, key=survivor_hint_sort_key)
        groups.append(
            {
                "similarity_key": similarity_key,
                "member_count": len(sorted_members),
                "members": sorted_members,
            }
        )

    groups.sort(key=lambda g: (-int(g["member_count"]), str(g["similarity_key"])))
    return groups


def paginate_groups(groups: list[dict[str, Any]], page: int, page_size: int) -> tuple[list[dict[str, Any]], int]:
    total = len(groups)
    if total == 0:
        return [], 0
    start = max(0, (page - 1) * page_size)
    end = start + page_size
    return groups[start:end], total


def _fk_reference_subqueries(customer_ids: list[int]) -> list:
    subqueries = [count_subquery_for_columns(label, [col], customer_ids) for label, col in _SPECS]
    subqueries.extend(
        [
            count_subquery_for_columns("Customer locations", [CustomerLocation.customer_id], customer_ids),
            count_subquery_for_columns("Customer contacts", [CustomerContact.customer_id], customer_ids),
            count_subquery_for_columns("Inbound shipments", [FactInboundShipment.customer_id], customer_ids),
            count_subquery_for_columns("Stock risk (derived)", [StockRisk.customer_id], customer_ids),
            count_subquery_for_columns("Weeks of stock (derived)", [WeeksOfStock.customer_id], customer_ids),
            count_subquery_for_columns("Stock health (derived)", [StockHealth.customer_id], customer_ids),
        ]
    )
    subqueries.extend(_extra_customer_subqueries(customer_ids))
    return subqueries


async def customer_fk_reference_counts_batch(
    db: AsyncSession, customer_ids: list[int]
) -> dict[int, list[dict[str, int | str]]]:
    ids = [int(i) for i in customer_ids if isinstance(i, int) and i > 0]
    if not ids:
        return {}
    subqueries = _fk_reference_subqueries(ids)
    return await batch_counts_multi_table(db, subqueries, ids)


def _member_to_api(row: _CustomerRow, *, survivor_hint: bool, reference_counts: list[dict[str, int | str]]) -> dict:
    return {
        "id": row.id,
        "customer_code": row.code,
        "customer_name": row.name,
        "customer_status": row.customer_status,
        "created_at": row.created_at.isoformat() if row.created_at is not None else None,
        "survivor_hint": survivor_hint,
        "reference_counts": sorted(reference_counts, key=lambda r: str(r.get("label", ""))),
    }


async def list_customer_duplicate_groups(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 25,
) -> dict[str, Any]:
    rows = (
        await db.execute(
            select(
                DimCustomer.id,
                DimCustomer.code,
                DimCustomer.name,
                DimCustomer.customer_status,
                DimCustomer.created_at,
            ).order_by(DimCustomer.id.asc())
        )
    ).all()

    customers = [
        _CustomerRow(
            id=int(r.id),
            code=str(r.code),
            name=str(r.name),
            customer_status=str(r.customer_status or ""),
            created_at=r.created_at,
        )
        for r in rows
    ]

    all_groups = build_duplicate_groups(customers)
    page_groups, total = paginate_groups(all_groups, page, page_size)

    member_ids: list[int] = []
    for group in page_groups:
        for member in group["members"]:
            member_ids.append(member.id)

    ref_counts = await customer_fk_reference_counts_batch(db, member_ids)

    items: list[dict[str, Any]] = []
    for group in page_groups:
        members_out: list[dict[str, Any]] = []
        for idx, member in enumerate(group["members"]):
            members_out.append(
                _member_to_api(
                    member,
                    survivor_hint=idx == 0,
                    reference_counts=ref_counts.get(member.id, []),
                )
            )
        items.append(
            {
                "similarity_key": group["similarity_key"],
                "member_count": group["member_count"],
                "members": members_out,
            }
        )

    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "customers_scanned": len(customers),
    }
