"""List approved customer alias-scope conflicts (one scope → multiple customer_id values)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dimensions import DimCustomer
from app.services.customer_alias_scope_grouping import (
    group_approved_customer_alias_scope_conflicts,
    scope_from_bucket,
)
from app.services.customer_duplicate_groups import (
    _CustomerRow,
    customer_fk_reference_counts_batch,
    is_verified_for_survivor_hint,
    survivor_hint_sort_key,
)


async def list_customer_alias_scope_conflicts(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 25,
    normalized_token: str | None = None,
) -> dict[str, Any]:
    """Return conflict groups where approved aliases in one scope map to 2+ distinct customers.

    Groups by **canonical** alias key (same normalization DSI uses), not raw ``normalized_token``
    column values — e.g. ``vexall (pty) ltd`` and ``vexall (pty)ltd`` collapse to one conflict.
    """
    token_filter = (normalized_token or "").strip() or None
    rows = (
        await db.execute(
            text(
                """
                SELECT normalized_token, customer_id, source_definition_id, distributor_id
                FROM customer_source_token_alias
                WHERE status = 'approved'
                """
            )
        )
    ).fetchall()

    raw_rows = [(str(r[0]), int(r[1]), r[2], r[3]) for r in rows]
    groups = group_approved_customer_alias_scope_conflicts(
        raw_rows,
        canonical_token_filter=token_filter,
    )

    total = len(groups)
    start = max(0, (page - 1) * page_size)
    page_groups = groups[start : start + page_size]

    all_member_ids: list[int] = []
    for g in page_groups:
        all_member_ids.extend(g["customer_ids"])

    customer_rows = []
    merged_into: dict[int, int | None] = {}
    if all_member_ids:
        customer_rows = (
            await db.execute(
                select(
                    DimCustomer.id,
                    DimCustomer.code,
                    DimCustomer.name,
                    DimCustomer.customer_status,
                    DimCustomer.created_at,
                    DimCustomer.merged_into_customer_id,
                ).where(DimCustomer.id.in_(all_member_ids))
            )
        ).all()
    by_id = {
        int(r.id): _CustomerRow(
            id=int(r.id),
            code=str(r.code),
            name=str(r.name),
            customer_status=str(r.customer_status or ""),
            created_at=r.created_at,
        )
        for r in customer_rows
    }
    merged_into = {int(r.id): r.merged_into_customer_id for r in customer_rows}

    ref_counts = await customer_fk_reference_counts_batch(db, all_member_ids)

    items: list[dict[str, Any]] = []
    for g in page_groups:
        members_raw = [by_id[cid] for cid in g["customer_ids"] if cid in by_id]
        sorted_members = sorted(members_raw, key=survivor_hint_sort_key)
        members_out: list[dict[str, Any]] = []
        for idx, member in enumerate(sorted_members):
            members_out.append(
                {
                    "id": member.id,
                    "customer_code": member.code,
                    "customer_name": member.name,
                    "customer_status": member.customer_status,
                    "created_at": member.created_at.isoformat() if member.created_at else None,
                    "survivor_hint": idx == 0,
                    "verified": is_verified_for_survivor_hint(member.customer_status),
                    "merged_into_customer_id": merged_into.get(member.id),
                    "reference_counts": ref_counts.get(member.id, []),
                }
            )
        scope = scope_from_bucket(g["scope_src"], g["scope_dist"])
        scope["normalized_token"] = g["canonical_token"]
        items.append(
            {
                "conflict_key": (
                    f"{g['canonical_token']}|{scope['source_definition_id']}|{scope['distributor_id']}"
                ),
                "scope": scope,
                "token_variants": g["token_variants"],
                "member_count": len(members_out),
                "alias_rows": g["alias_rows"],
                "members": members_out,
                "default_survivor_id": sorted_members[0].id if sorted_members else None,
            }
        )

    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "scopes_scanned": len(groups),
    }
