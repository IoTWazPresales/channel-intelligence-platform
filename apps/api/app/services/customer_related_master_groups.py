"""Related-name customer worklist (BACKLOG-083).

Name-similarity groups only catch names that normalise to the same key. A related-name group is
anchored on one customer and lists the customers whose name starts with the anchor's whole name
("Amazon" -> "Amazon Commercial Services (South Africa)") or shares its root identity. The steward
picks a subset (2 or more) and merges it through the same full-merge path, which seals aliases.

Test-fixture customers are left out of the worklist (and counted), never edited.
"""

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
from app.services.customer_test_fixtures import is_test_fixture_customer
from app.services.imports.dsi_customer_name_normalization import (
    anchor_is_eligible,
    compare_root_identities_from_raw,
    containment_score,
    is_token_prefix_containment,
    normalize_customer_name_for_similarity,
    split_distinctive_and_generic_tokens,
)

RELATED_SIMILARITY_KEY_PREFIX = "related:"


def _match(anchor: _CustomerRow, anchor_norm: str, other: _CustomerRow, other_norm: str) -> tuple[str, float] | None:
    if is_token_prefix_containment(anchor_norm, other_norm):
        return "contained_prefix", containment_score(anchor_norm, other_norm)
    tokens = [t for t in other_norm.split() if t]
    distinctive, _ = split_distinctive_and_generic_tokens(other_norm)
    if not distinctive or (len(tokens) == 1 and len(tokens[0]) <= 3):
        return None
    score = compare_root_identities_from_raw(anchor.name, other.name)
    return ("root_similarity", float(score)) if score is not None else None


def build_related_master_groups(rows: list[_CustomerRow]) -> list[dict[str, Any]]:
    """Anchored groups with at least one related member. Same-key duplicates stay on the other tab."""
    normalized = {r.id: k for r in rows if (k := normalize_customer_name_for_similarity(r.name))}
    by_id = {r.id: r for r in rows}
    blocks: dict[str, list[int]] = defaultdict(list)
    for cid, norm in normalized.items():
        blocks[norm.split()[0]].append(cid)

    groups: list[dict[str, Any]] = []
    seen_sets: set[frozenset[int]] = set()
    for block_ids in blocks.values():
        if len(block_ids) < 2:
            continue
        for anchor_id in block_ids:
            anchor_norm = normalized[anchor_id]
            if not anchor_is_eligible(anchor_norm):
                continue
            anchor = by_id[anchor_id]
            meta: dict[int, dict[str, Any]] = {anchor_id: {"match_basis": "anchor", "score": 1.0}}
            for other_id in block_ids:
                other_norm = normalized[other_id]
                if other_id == anchor_id or other_norm == anchor_norm:
                    continue
                hit = _match(anchor, anchor_norm, by_id[other_id], other_norm)
                if hit is not None:
                    meta[other_id] = {"match_basis": hit[0], "score": hit[1]}
            if len(meta) < 2:
                continue
            member_set = frozenset(meta)
            if member_set in seen_sets:
                continue
            seen_sets.add(member_set)
            related = sorted((by_id[i] for i in meta if i != anchor_id), key=survivor_hint_sort_key)
            groups.append(
                {
                    "anchor_similarity_key": anchor_norm,
                    "member_count": len(meta),
                    "members": [anchor, *related],
                    "member_meta": meta,
                }
            )

    groups.sort(key=lambda g: (-int(g["member_count"]), str(g["anchor_similarity_key"])))
    return groups


def _row(r: Any) -> _CustomerRow:
    return _CustomerRow(
        id=int(r.id),
        code=str(r.code),
        name=str(r.name),
        customer_status=str(r.customer_status or ""),
        created_at=r.created_at,
    )


def _living_rows_query():
    return (
        select(DimCustomer.id, DimCustomer.code, DimCustomer.name, DimCustomer.customer_status, DimCustomer.created_at)
        .where(DimCustomer.merged_into_customer_id.is_(None))
        .order_by(DimCustomer.id.asc())
    )


def _split_fixtures(rows: list[_CustomerRow]) -> tuple[list[_CustomerRow], int]:
    real = [r for r in rows if not is_test_fixture_customer(r.code, r.name)]
    return real, len(rows) - len(real)


def related_group_members_for_key(db: Session, anchor_similarity_key: str) -> list[_CustomerRow]:
    """Members of the related group anchored on this key (sync). Empty when there is none."""
    key = (anchor_similarity_key or "").strip()
    if not key:
        return []
    real, _ = _split_fixtures([_row(r) for r in db.execute(_living_rows_query()).all()])
    for group in build_related_master_groups(real):
        if group["anchor_similarity_key"] == key:
            return list(group["members"])
    return []


async def list_customer_related_master_groups(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 25,
    q: str | None = None,
) -> dict[str, Any]:
    rows = [_row(r) for r in (await db.execute(_living_rows_query())).all()]
    real, fixtures = _split_fixtures(rows)
    all_groups = build_related_master_groups(real)
    needle = (q or "").strip().lower()
    if needle:
        all_groups = [g for g in all_groups if any(needle in m.name.lower() for m in g["members"])]
    page_groups, total = paginate_groups(all_groups, page, page_size)

    member_ids = [m.id for g in page_groups for m in g["members"]]
    ref_counts = await customer_fk_reference_counts_batch(db, member_ids)

    items: list[dict[str, Any]] = []
    for group in page_groups:
        meta: dict[int, dict[str, Any]] = group["member_meta"]
        hint_id = sorted(group["members"], key=survivor_hint_sort_key)[0].id
        items.append(
            {
                "similarity_key": f"{RELATED_SIMILARITY_KEY_PREFIX}{group['anchor_similarity_key']}",
                "anchor_similarity_key": group["anchor_similarity_key"],
                "member_count": group["member_count"],
                "members": [
                    {
                        "id": m.id,
                        "customer_code": m.code,
                        "customer_name": m.name,
                        "customer_status": m.customer_status,
                        "created_at": m.created_at.isoformat() if m.created_at is not None else None,
                        "survivor_hint": m.id == hint_id,
                        "reference_counts": sorted(ref_counts.get(m.id, []), key=lambda r: str(r.get("label", ""))),
                        "match_basis": str(meta[m.id]["match_basis"]),
                        "score": float(meta[m.id]["score"]),
                    }
                    for m in group["members"]
                ],
            }
        )

    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "customers_scanned": len(real),
        "test_fixture_customers_excluded": fixtures,
    }
