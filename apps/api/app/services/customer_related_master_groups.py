"""Related-master customer groups (anchored token-prefix containment only)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.dimensions import DimCustomer
from app.services.customer_duplicate_groups import (
    _CustomerRow,
    customer_fk_reference_counts_batch,
    paginate_groups,
    survivor_hint_sort_key,
)
from app.services.imports.dsi_customer_name_normalization import (
    anchor_is_eligible,
    containment_score,
    is_token_prefix_containment,
    normalize_customer_name_for_similarity,
)

RELATED_SIMILARITY_KEY_PREFIX = "related:"


def _first_token(normalized: str) -> str:
    tokens = [t for t in (normalized or "").split() if t]
    return tokens[0] if tokens else ""


def build_related_master_groups(rows: list[_CustomerRow]) -> list[dict[str, Any]]:
    """Build anchored related groups via token-prefix containment only.

    Root-similarity was removed from this worklist: shared short roots like
    ``computer`` / ``destiny`` produced high-confidence false groups
    (Computer Connection vs Computer World, Destiny Group vs Destiny Global, …).
    Exact-key duplicates stay on the name-similarity tab.
    """
    normalized: dict[int, str] = {}
    for row in rows:
        key = normalize_customer_name_for_similarity(row.name)
        if key:
            normalized[row.id] = key

    by_id = {row.id: row for row in rows}
    blocks: dict[str, list[int]] = defaultdict(list)
    for cid, norm in normalized.items():
        lead = _first_token(norm)
        if lead:
            blocks[lead].append(cid)

    groups: list[dict[str, Any]] = []
    for _lead, block_ids in blocks.items():
        if len(block_ids) < 2:
            continue
        for anchor_id in block_ids:
            anchor_norm = normalized[anchor_id]
            if not anchor_is_eligible(anchor_norm):
                continue
            anchor_row = by_id[anchor_id]
            members: list[_CustomerRow] = [anchor_row]
            meta: dict[int, dict[str, Any]] = {
                anchor_id: {"match_basis": "anchor", "score": 1.0},
            }
            for other_id in block_ids:
                if other_id == anchor_id:
                    continue
                other_norm = normalized[other_id]
                if other_norm == anchor_norm:
                    # Exact-key duplicates belong on the name-similarity tab.
                    continue
                if not is_token_prefix_containment(anchor_norm, other_norm):
                    continue
                members.append(by_id[other_id])
                meta[other_id] = {
                    "match_basis": "contained_prefix",
                    "score": containment_score(anchor_norm, other_norm),
                }

            if len(members) < 2:
                continue
            related = [m for m in members if m.id != anchor_id]
            related_sorted = sorted(related, key=survivor_hint_sort_key)
            ordered = [anchor_row, *related_sorted]
            groups.append(
                {
                    "anchor_similarity_key": anchor_norm,
                    "member_count": len(ordered),
                    "members": ordered,
                    "member_meta": meta,
                }
            )

    groups.sort(key=lambda g: (-int(g["member_count"]), str(g["anchor_similarity_key"])))
    return groups


def _load_unmerged_customer_rows_sync(db: Session) -> list[_CustomerRow]:
    rows = db.execute(
        select(
            DimCustomer.id,
            DimCustomer.code,
            DimCustomer.name,
            DimCustomer.customer_status,
            DimCustomer.created_at,
        )
        .where(DimCustomer.merged_into_customer_id.is_(None))
        .order_by(DimCustomer.id.asc())
    ).all()
    return [
        _CustomerRow(
            id=int(r.id),
            code=str(r.code),
            name=str(r.name),
            customer_status=str(r.customer_status or ""),
            created_at=r.created_at,
        )
        for r in rows
    ]


def related_group_members_for_key(db: Session, anchor_similarity_key: str) -> list[_CustomerRow]:
    """Resolve related-group members for merge (sync). Empty list when no group."""
    key = (anchor_similarity_key or "").strip()
    if not key:
        return []
    for group in build_related_master_groups(_load_unmerged_customer_rows_sync(db)):
        if group["anchor_similarity_key"] == key:
            return list(group["members"])
    return []


def _member_to_api(
    row: _CustomerRow,
    *,
    survivor_hint: bool,
    reference_counts: list[dict[str, int | str]],
    match_basis: str,
    score: float,
) -> dict[str, Any]:
    return {
        "id": row.id,
        "customer_code": row.code,
        "customer_name": row.name,
        "customer_status": row.customer_status,
        "created_at": row.created_at.isoformat() if row.created_at is not None else None,
        "survivor_hint": survivor_hint,
        "reference_counts": sorted(reference_counts, key=lambda r: str(r.get("label", ""))),
        "match_basis": match_basis,
        "score": score,
    }


async def list_customer_related_master_groups(
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
            )
            .where(DimCustomer.merged_into_customer_id.is_(None))
            .order_by(DimCustomer.id.asc())
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

    all_groups = build_related_master_groups(customers)
    page_groups, total = paginate_groups(all_groups, page, page_size)

    member_ids: list[int] = []
    for group in page_groups:
        for member in group["members"]:
            member_ids.append(member.id)

    ref_counts = await customer_fk_reference_counts_batch(db, member_ids)

    items: list[dict[str, Any]] = []
    for group in page_groups:
        meta: dict[int, dict[str, Any]] = group["member_meta"]
        members_out: list[dict[str, Any]] = []
        for idx, member in enumerate(group["members"]):
            m = meta.get(member.id, {"match_basis": "anchor", "score": 1.0})
            members_out.append(
                _member_to_api(
                    member,
                    survivor_hint=idx == 0,
                    reference_counts=ref_counts.get(member.id, []),
                    match_basis=str(m["match_basis"]),
                    score=float(m["score"]),
                )
            )
        items.append(
            {
                "anchor_similarity_key": group["anchor_similarity_key"],
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
