"""Bulk delete preview/confirm for master dimensions."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dimensions import DimChannel, DimCustomer, DimDistributor, DimProduct, DimRegion
from app.services.channel_usage import channel_hard_reference_breakdown_batch
from app.services.customer_usage import (
    cleanup_soft_customer_references,
    customer_hard_reference_breakdown_batch,
    delete_customer_children,
)
from app.services.distributor_usage import (
    delete_distributor_children,
    distributor_hard_reference_breakdown_batch,
)
from app.services.product_usage import cleanup_soft_product_references, product_hard_reference_breakdown_batch
from app.services.region_usage import region_hard_reference_breakdown_batch

MasterEntityKind = Literal["products", "customers", "channels", "regions", "distributors"]
MAX_BULK_IDS = 200


class MasterBulkDeleteConfirmBody(BaseModel):
    entity_ids: list[int] = Field(default_factory=list, max_length=200)
    deletable_ids: list[int] | None = Field(default=None, max_length=200)
    preview_token: str | None = None


class MasterBulkDeleteIntegrityError(Exception):
    """Raised when confirm hits a DB FK the reference checks did not surface."""

    def __init__(self, message: str, references: list[dict[str, int | str]] | None = None):
        super().__init__(message)
        self.message = message
        self.references = references or []


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


async def _batch_refs(
    db: AsyncSession,
    kind: MasterEntityKind,
    entity_ids: list[int],
) -> dict[int, list[dict[str, int | str]]]:
    if kind == "products":
        return await product_hard_reference_breakdown_batch(db, entity_ids)
    if kind == "customers":
        return await customer_hard_reference_breakdown_batch(db, entity_ids)
    if kind == "channels":
        return await channel_hard_reference_breakdown_batch(db, entity_ids)
    if kind == "regions":
        return await region_hard_reference_breakdown_batch(db, entity_ids)
    return await distributor_hard_reference_breakdown_batch(db, entity_ids)


async def _entity_label(db: AsyncSession, kind: MasterEntityKind, entity_id: int) -> str | None:
    if kind == "products":
        row = await db.get(DimProduct, entity_id)
        return row.sku if row else None
    if kind == "customers":
        row = await db.get(DimCustomer, entity_id)
        return row.code if row else None
    if kind == "channels":
        row = await db.get(DimChannel, entity_id)
        return row.code if row else None
    if kind == "regions":
        row = await db.get(DimRegion, entity_id)
        return row.code if row else None
    row = await db.get(DimDistributor, entity_id)
    return row.code if row else None


def _preview_row(
    entity_id: int,
    label: str | None,
    references: list[dict[str, int | str]],
    *,
    missing: bool = False,
) -> dict[str, Any]:
    blocked = len(references) > 0
    return {
        "id": entity_id,
        "missing": missing,
        "label": label,
        "references": references,
        "blocked": blocked,
    }


async def preview_master_bulk_delete(
    db: AsyncSession,
    kind: MasterEntityKind,
    entity_ids: list[int],
) -> dict[str, Any]:
    ids = normalize_entity_ids(entity_ids)
    ref_map = await _batch_refs(db, kind, ids)
    rows: list[dict[str, Any]] = []
    for eid in ids:
        refs = ref_map.get(eid, [])
        label = await _entity_label(db, kind, eid)
        rows.append(_preview_row(eid, label, refs, missing=label is None))

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


async def _delete_one(db: AsyncSession, kind: MasterEntityKind, eid: int) -> bool:
    if kind == "products":
        row = await db.get(DimProduct, eid)
        if not row:
            return False
        await cleanup_soft_product_references(db, eid)
        await db.delete(row)
        return True
    if kind == "customers":
        row = await db.get(DimCustomer, eid)
        if not row:
            return False
        await cleanup_soft_customer_references(db, eid)
        await delete_customer_children(db, eid)
        await db.delete(row)
        return True
    if kind == "channels":
        row = await db.get(DimChannel, eid)
        if not row:
            return False
        await db.delete(row)
        return True
    if kind == "regions":
        row = await db.get(DimRegion, eid)
        if not row:
            return False
        await db.delete(row)
        return True
    row = await db.get(DimDistributor, eid)
    if not row:
        return False
    await delete_distributor_children(db, eid)
    await db.delete(row)
    return True


async def confirm_master_bulk_delete(
    db: AsyncSession,
    kind: MasterEntityKind,
    entity_ids: list[int],
    *,
    deletable_ids: list[int] | None = None,
) -> dict[str, Any]:
    ids = normalize_entity_ids(entity_ids)
    if not ids:
        raise ValueError("no_valid_entity_ids")

    if deletable_ids is not None:
        target_ids = normalize_entity_ids(deletable_ids)
        if not target_ids:
            raise ValueError("entities_still_blocked")
        id_set = set(ids)
        if not set(target_ids).issubset(id_set):
            raise ValueError("deletable_ids_not_subset")
        ref_map = await _batch_refs(db, kind, target_ids)
        blocked_at_confirm = [eid for eid in target_ids if ref_map.get(eid)]
        if blocked_at_confirm:
            merged_refs: list[dict[str, int | str]] = []
            for eid in blocked_at_confirm:
                merged_refs.extend(ref_map.get(eid, []))
            raise MasterBulkDeleteIntegrityError(
                "One or more rows are still referenced and cannot be deleted.",
                merged_refs,
            )
        preview = None
        skipped_blocked_ids = [eid for eid in ids if eid not in set(target_ids)]
        skipped_blocked_count = len(skipped_blocked_ids)
    else:
        preview = await preview_master_bulk_delete(db, kind, ids)
        if preview["missing_entity_ids"]:
            raise ValueError("not_all_entities_found")
        target_ids = preview["deletable_ids"]
        if not target_ids:
            raise ValueError("entities_still_blocked")
        skipped_blocked_ids = [r["id"] for r in preview["rows"] if r.get("blocked")]
        skipped_blocked_count = preview["blocked_count"]

    for eid in target_ids:
        row = await _entity_label(db, kind, eid)
        if row is None:
            raise ValueError("not_all_entities_found")

    deleted_ids: list[int] = []
    try:
        for eid in target_ids:
            if await _delete_one(db, kind, eid):
                deleted_ids.append(eid)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        last_refs: list[dict[str, int | str]] = []
        if deleted_ids:
            ref_map = await _batch_refs(db, kind, deleted_ids[:1])
            last_refs = ref_map.get(deleted_ids[0], [])
        raise MasterBulkDeleteIntegrityError(
            "One or more rows could not be deleted (database constraint). Dependent data may have changed.",
            last_refs
            if last_refs
            else [{"label": "Unknown referencing rows (try refresh)", "count": 1}],
        ) from None

    return {
        "entity_type": kind,
        "deleted_ids": deleted_ids,
        "deleted_count": len(deleted_ids),
        "skipped_blocked_count": skipped_blocked_count,
        "skipped_blocked_ids": skipped_blocked_ids,
    }
