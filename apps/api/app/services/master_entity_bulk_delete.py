"""Bulk delete preview/confirm for master dimensions.

Performance design
------------------
* preview  — one UNION ALL reference check (1 round trip) + one batch label
             fetch (1 round trip) = 2 round trips regardless of how many tables
             are checked or how many entities are in the selection.

* confirm  — when ``deletable_ids`` is provided from a recent preview the
             expensive reference re-check is skipped entirely.  Only a single
             batch existence query is issued before proceeding to deletes.  The
             ``db.commit()`` IntegrityError handler is the data-integrity safety
             net for concurrent changes between preview and confirm.

* error path — any unhandled exception (asyncpg timeout, connection reset, etc.)
               is re-raised so the endpoint layer can map it to a structured
               HTTP response rather than a bare 500.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
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


async def _batch_entity_labels(
    db: AsyncSession, kind: MasterEntityKind, entity_ids: list[int]
) -> dict[int, str]:
    """Fetch entity labels for all IDs in a single SELECT IN query.

    Missing IDs (rows not found in the database) are absent from the returned
    dict, allowing callers to detect deletions that occurred since preview.
    """
    if not entity_ids:
        return {}
    if kind == "products":
        rows = (
            await db.execute(select(DimProduct.id, DimProduct.sku).where(DimProduct.id.in_(entity_ids)))
        ).all()
        return {row.id: row.sku for row in rows}
    if kind == "customers":
        rows = (
            await db.execute(
                select(DimCustomer.id, DimCustomer.code).where(DimCustomer.id.in_(entity_ids))
            )
        ).all()
        return {row.id: row.code for row in rows}
    if kind == "channels":
        rows = (
            await db.execute(
                select(DimChannel.id, DimChannel.code).where(DimChannel.id.in_(entity_ids))
            )
        ).all()
        return {row.id: row.code for row in rows}
    if kind == "regions":
        rows = (
            await db.execute(
                select(DimRegion.id, DimRegion.code).where(DimRegion.id.in_(entity_ids))
            )
        ).all()
        return {row.id: row.code for row in rows}
    rows = (
        await db.execute(
            select(DimDistributor.id, DimDistributor.code).where(DimDistributor.id.in_(entity_ids))
        )
    ).all()
    return {row.id: row.code for row in rows}


# Keep the single-entity helper for backward compat (used by some endpoint
# error paths and existing tests).
async def _entity_label(db: AsyncSession, kind: MasterEntityKind, entity_id: int) -> str | None:
    label_map = await _batch_entity_labels(db, kind, [entity_id])
    return label_map.get(entity_id)


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
    # Two queries: one UNION ALL reference check, one batch label fetch.
    ref_map = await _batch_refs(db, kind, ids)
    label_map = await _batch_entity_labels(db, kind, ids)
    rows: list[dict[str, Any]] = []
    for eid in ids:
        refs = ref_map.get(eid, [])
        label = label_map.get(eid)
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
        if not set(target_ids).issubset(set(ids)):
            raise ValueError("deletable_ids_not_subset")
        # Skip the full reference re-check — the preview already determined
        # these IDs are deletable.  The commit IntegrityError handler below
        # is the safety net for concurrent changes between preview and confirm.
        label_map = await _batch_entity_labels(db, kind, target_ids)
        missing = [eid for eid in target_ids if eid not in label_map]
        if missing:
            raise ValueError("not_all_entities_found")
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
    except Exception:
        await db.rollback()
        raise

    return {
        "entity_type": kind,
        "deleted_ids": deleted_ids,
        "deleted_count": len(deleted_ids),
        "skipped_blocked_count": skipped_blocked_count,
        "skipped_blocked_ids": skipped_blocked_ids,
    }
