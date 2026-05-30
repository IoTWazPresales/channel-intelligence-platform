"""Bulk delete preview/confirm for master dimensions (products, customers)."""

from __future__ import annotations

from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dimensions import DimChannel, DimCustomer, DimDistributor, DimProduct, DimRegion
from app.services.channel_usage import channel_hard_reference_breakdown
from app.services.customer_usage import (
    cleanup_soft_customer_references,
    customer_hard_reference_breakdown,
    delete_customer_children,
)
from app.services.distributor_usage import delete_distributor_children, distributor_hard_reference_breakdown
from app.services.product_usage import cleanup_soft_product_references, product_hard_reference_breakdown
from app.services.region_usage import region_hard_reference_breakdown

MasterEntityKind = Literal["products", "customers", "channels", "regions", "distributors"]
MAX_BULK_IDS = 200


def normalize_entity_ids(entity_ids: list[int]) -> list[int]:
    out: list[int] = []
    seen: set[int] = set()
    for raw in entity_ids:
        if not isinstance(raw, int) or raw < 1:
            continue
        if raw in seen:
            continue
        seen.add(raw)
        out.append(raw)
        if len(out) >= MAX_BULK_IDS:
            break
    return out


async def _preview_one(
    db: AsyncSession,
    kind: MasterEntityKind,
    entity_id: int,
) -> dict[str, Any]:
    if kind == "products":
        row = await db.get(DimProduct, entity_id)
        if not row:
            return {"id": entity_id, "missing": True, "label": None, "references": [], "blocked": False}
        refs = await product_hard_reference_breakdown(db, entity_id)
        return {
            "id": entity_id,
            "missing": False,
            "label": row.sku,
            "references": refs,
            "blocked": len(refs) > 0,
        }
    if kind == "customers":
        row = await db.get(DimCustomer, entity_id)
        if not row:
            return {"id": entity_id, "missing": True, "label": None, "references": [], "blocked": False}
        refs = await customer_hard_reference_breakdown(db, entity_id)
        return {
            "id": entity_id,
            "missing": False,
            "label": row.code,
            "references": refs,
            "blocked": len(refs) > 0,
        }
    if kind == "channels":
        row = await db.get(DimChannel, entity_id)
        if not row:
            return {"id": entity_id, "missing": True, "label": None, "references": [], "blocked": False}
        refs = await channel_hard_reference_breakdown(db, entity_id)
        return {
            "id": entity_id,
            "missing": False,
            "label": row.code,
            "references": refs,
            "blocked": len(refs) > 0,
        }
    if kind == "regions":
        row = await db.get(DimRegion, entity_id)
        if not row:
            return {"id": entity_id, "missing": True, "label": None, "references": [], "blocked": False}
        refs = await region_hard_reference_breakdown(db, entity_id)
        return {
            "id": entity_id,
            "missing": False,
            "label": row.code,
            "references": refs,
            "blocked": len(refs) > 0,
        }
    row = await db.get(DimDistributor, entity_id)
    if not row:
        return {"id": entity_id, "missing": True, "label": None, "references": [], "blocked": False}
    refs = await distributor_hard_reference_breakdown(db, entity_id)
    return {
        "id": entity_id,
        "missing": False,
        "label": row.code,
        "references": refs,
        "blocked": len(refs) > 0,
    }


async def preview_master_bulk_delete(
    db: AsyncSession,
    kind: MasterEntityKind,
    entity_ids: list[int],
) -> dict[str, Any]:
    ids = normalize_entity_ids(entity_ids)
    rows = [await _preview_one(db, kind, eid) for eid in ids]
    missing_ids = [r["id"] for r in rows if r.get("missing")]
    blocked_rows = [r for r in rows if not r.get("missing") and r.get("blocked")]
    deletable_ids = [r["id"] for r in rows if not r.get("missing") and not r.get("blocked")]
    return {
        "entity_type": kind,
        "entity_ids": ids,
        "missing_entity_ids": missing_ids,
        "rows": rows,
        "blocked_count": len(blocked_rows),
        "deletable_count": len(deletable_ids),
        "deletable_ids": deletable_ids,
    }


async def confirm_master_bulk_delete(
    db: AsyncSession,
    kind: MasterEntityKind,
    entity_ids: list[int],
) -> dict[str, Any]:
    preview = await preview_master_bulk_delete(db, kind, entity_ids)
    if preview["missing_entity_ids"]:
        raise ValueError("not_all_entities_found")
    if not preview["deletable_ids"]:
        raise ValueError("entities_still_blocked")
    deleted_ids: list[int] = []
    for eid in preview["deletable_ids"]:
        if kind == "products":
            row = await db.get(DimProduct, eid)
            if not row:
                continue
            await cleanup_soft_product_references(db, eid)
            await db.delete(row)
        elif kind == "customers":
            row = await db.get(DimCustomer, eid)
            if not row:
                continue
            await cleanup_soft_customer_references(db, eid)
            await delete_customer_children(db, eid)
            await db.delete(row)
        elif kind == "channels":
            row = await db.get(DimChannel, eid)
            if not row:
                continue
            await db.delete(row)
        elif kind == "regions":
            row = await db.get(DimRegion, eid)
            if not row:
                continue
            await db.delete(row)
        else:
            row = await db.get(DimDistributor, eid)
            if not row:
                continue
            await delete_distributor_children(db, eid)
            await db.delete(row)
        deleted_ids.append(eid)
    await db.commit()
    return {
        "entity_type": kind,
        "deleted_ids": deleted_ids,
        "deleted_count": len(deleted_ids),
        "skipped_blocked_count": preview["blocked_count"],
        "skipped_blocked_ids": [r["id"] for r in preview["rows"] if r.get("blocked")],
    }
