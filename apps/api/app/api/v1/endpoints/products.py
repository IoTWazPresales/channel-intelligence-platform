from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import Date, and_, asc, desc, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db
from app.models.dimensions import DimChannel, DimProduct
from app.models.ingestion import ImportJob
from app.models.product_catalog import CatalogProduct
from app.services.commercial_planner.read_model import specs_json_flat_string_map
from app.services.product_dsi_maintenance import (
    CLEAR_DISTRIBUTOR_INVENTORY_FOR_PRODUCT,
    clear_dsi_facts_for_product,
    dsi_dependency_detail_payload,
)
from app.api.v1.master_bulk_delete_http import raise_bulk_delete_http_error
from app.services.master_entity_bulk_delete import (
    MasterBulkDeleteConfirmBody,
    MasterBulkDeleteIntegrityError,
    confirm_master_bulk_delete,
    preview_master_bulk_delete,
)
from app.services.product_usage import cleanup_soft_product_references, product_hard_reference_breakdown

router = APIRouter()


class MasterBulkIdsBody(BaseModel):
    entity_ids: list[int] = Field(default_factory=list, max_length=200)


def _compact_specs_preview(
    specs: dict | None, *, max_keys: int = 8, max_val_len: int = 56
) -> dict[str, str]:
    """Small string map for list/search UIs — not a full specs_json dump."""
    if not isinstance(specs, dict) or not specs:
        return {}

    def _one(v: object) -> str:
        if v is None:
            return ''
        if isinstance(v, bool):
            return 'true' if v else 'false'
        if isinstance(v, (int, float)):
            return str(v)
        if isinstance(v, str):
            s = v.strip().replace('\n', ' ')
        else:
            s = str(v).strip().replace('\n', ' ')
        if len(s) > max_val_len:
            return f'{s[: max_val_len - 1]}…'
        return s

    # Nested containers (raw file columns) are surfaced via specs_flat, not the preview.
    skip = {"import_staging", "importStaging", "attribute_candidates"}
    out: dict[str, str] = {}
    for k in sorted(str(x) for x in specs.keys() if str(x) not in skip)[:max_keys]:
        out[str(k)] = _one(specs.get(k))
    return out


class ProductPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=512)
    category: str | None = Field(default=None, max_length=256)
    form_factor: str | None = Field(default=None, max_length=128)
    lifecycle_status: str | None = Field(default=None, max_length=64)
    launch_date: date | None = None
    retired_date: date | None = None
    is_active: bool | None = None
    channel_id: int | None = None


class ProductBulkRow(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=512)
    category: str | None = Field(default=None, max_length=256)
    channel_code: str | None = Field(default=None, max_length=32)


class ProductBulkBody(BaseModel):
    rows: list[ProductBulkRow]


@router.get("")
async def list_products(
    db: AsyncSession = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    q: str | None = Query(default=None, description="Global search over product identity fields"),
    is_active: bool | None = Query(default=None),
    category: str | None = Query(default=None),
    lifecycle_status: str | None = Query(default=None),
    channel_code: str | None = Query(default=None),
    launch_date_from: date | None = Query(default=None),
    launch_date_to: date | None = Query(default=None),
    retired_date_from: date | None = Query(default=None),
    retired_date_to: date | None = Query(default=None),
    sort_by: str = Query(default="sku"),
    sort_dir: str = Query(default="asc", pattern="^(asc|desc)$"),
):
    allowed_sort = {
        "sku": DimProduct.sku,
        "name": DimProduct.name,
        "category": DimProduct.category,
        "lifecycle_status": DimProduct.lifecycle_status,
        "launch_date": DimProduct.launch_date,
        "retired_date": DimProduct.retired_date,
        "is_active": DimProduct.is_active,
        "updated_at": DimProduct.updated_at,
    }
    sort_col = allowed_sort.get(sort_by, DimProduct.sku)
    sort_fn = asc if sort_dir == "asc" else desc

    last_import_subq = (
        select(
            DimProduct.id.label("product_id"),
            func.max(func.cast(ImportJob.completed_at, Date)).label("last_import_date"),
        )
        .select_from(DimProduct)
        .join(CatalogProduct, CatalogProduct.canonical_product_id == DimProduct.id, isouter=True)
        .join(ImportJob, ImportJob.id == CatalogProduct.last_import_job_id, isouter=True)
        .group_by(DimProduct.id)
        .subquery()
    )

    base = (
        select(DimProduct, DimChannel.code.label("channel_code"), last_import_subq.c.last_import_date)
        .join(DimChannel, DimChannel.id == DimProduct.channel_id, isouter=True)
        .join(last_import_subq, last_import_subq.c.product_id == DimProduct.id, isouter=True)
    )
    count_stmt = select(func.count()).select_from(DimProduct)
    filters = []

    if q and q.strip():
        needle = f"%{q.strip()}%"
        filters.append(
            or_(
                DimProduct.sku.ilike(needle),
                DimProduct.name.ilike(needle),
                DimProduct.category.ilike(needle),
                DimProduct.model_name.ilike(needle),
                DimProduct.sales_model_name.ilike(needle),
                DimProduct.part_number.ilike(needle),
                DimProduct.product_line.ilike(needle),
                DimProduct.series_name.ilike(needle),
            )
        )
    if is_active is not None:
        filters.append(DimProduct.is_active.is_(is_active))
    if category and category.strip():
        filters.append(DimProduct.category == category.strip())
    if lifecycle_status and lifecycle_status.strip():
        filters.append(DimProduct.lifecycle_status == lifecycle_status.strip())
    if channel_code and channel_code.strip():
        base = base.where(DimChannel.code == channel_code.strip())
        count_stmt = count_stmt.join(DimChannel, DimChannel.id == DimProduct.channel_id)
    if launch_date_from is not None:
        filters.append(DimProduct.launch_date >= launch_date_from)
    if launch_date_to is not None:
        filters.append(DimProduct.launch_date <= launch_date_to)
    if retired_date_from is not None:
        filters.append(DimProduct.retired_date >= retired_date_from)
    if retired_date_to is not None:
        filters.append(DimProduct.retired_date <= retired_date_to)

    if filters:
        base = base.where(and_(*filters))
        count_stmt = count_stmt.where(and_(*filters))

    total = int((await db.execute(count_stmt)).scalar_one())
    offset = (page - 1) * page_size
    rows = (
        await db.execute(
            base.order_by(sort_fn(sort_col), asc(DimProduct.id)).offset(offset).limit(page_size)
        )
    ).all()

    items = []
    specs_field_keys: set[str] = set()
    for p, channel_code_out, last_import_date in rows:
        missing_required = []
        if not (p.sku or "").strip():
            missing_required.append("sku")
        if not (p.name or "").strip():
            missing_required.append("name")
        if not (p.category or "").strip():
            missing_required.append("category")
        if not (p.lifecycle_status or "").strip():
            missing_required.append("lifecycle_status")
        if p.channel_id is None:
            missing_required.append("channel")
        specs_flat = specs_json_flat_string_map(p.specs_json if isinstance(p.specs_json, dict) else None, max_keys=48)
        specs_field_keys.update(specs_flat.keys())
        items.append(
            {
                "id": p.id,
                "sku": p.sku,
                "part_number": p.part_number,
                "name": p.name,
                "sales_model_name": p.sales_model_name,
                "model_name": p.model_name,
                "series_name": p.series_name,
                "product_line": p.product_line,
                "business_unit": p.business_unit,
                "category": p.category,
                "form_factor": p.form_factor,
                "country_code": p.country_code,
                "ean": p.ean,
                "upc": p.upc,
                "lifecycle_status": p.lifecycle_status,
                "launch_date": p.launch_date.isoformat() if p.launch_date else None,
                "retired_date": p.retired_date.isoformat() if p.retired_date else None,
                "is_active": p.is_active,
                "channel_id": p.channel_id,
                "channel_code": channel_code_out,
                "missing_required_fields": missing_required,
                "last_import_date": last_import_date.isoformat() if last_import_date else None,
                "specs_preview": _compact_specs_preview(p.specs_json),
                "specs_flat": specs_flat,
            }
        )
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "sort_by": sort_by if sort_by in allowed_sort else "sku",
        "sort_dir": sort_dir,
        "specs_field_keys": sorted(specs_field_keys),
    }


async def _product_references_bundle(db: AsyncSession, product_id: int) -> dict:
    row = await db.get(DimProduct, product_id)
    if not row:
        raise HTTPException(status_code=404, detail={"error": "product_not_found", "product_id": product_id})
    refs = await product_hard_reference_breakdown(db, product_id)
    return {"sku": row.sku, "references": refs, "blocked": len(refs) > 0}


@router.get("/references")
async def get_product_references_by_query(
    product_id: int = Query(..., ge=1, description="dim_product.id"),
    db: AsyncSession = Depends(get_db),
):
    """Stable path for delete UX (`?product_id=`) — avoids any ambiguity with `/{product_id}/...` routes."""
    return await _product_references_bundle(db, product_id)


@router.get("/id/{product_id}/refs")
async def get_product_refs_for_delete_ux(product_id: int, db: AsyncSession = Depends(get_db)):
    """Where this SKU is still referenced (for delete UX). Uses `/id/.../refs` so the path is never a single
    dynamic segment under `/products` (that collides with `PATCH /{product_id}` → GET returns 405)."""
    return await _product_references_bundle(db, product_id)


def _require_admin_role(x_user_role: str | None = Header(default=None, alias="X-User-Role")) -> None:
    if (x_user_role or "").strip().lower() != "admin":
        raise HTTPException(
            status_code=403,
            detail={"error": "admin_required", "message": "Admin maintenance requires X-User-Role: admin"},
        )


@router.get("/id/{product_id}/dependencies/distributor-inventory")
async def get_dsi_dependency_detail_for_product(
    product_id: int,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_require_admin_role),
):
    """Small sample + counts for DSI facts that block product delete (inventory snapshot + sell-out)."""
    payload = await dsi_dependency_detail_payload(db, product_id)
    if payload.get("error") == "product_not_found":
        raise HTTPException(status_code=404, detail=payload)
    return payload


class ClearDistributorInventoryFactsBody(BaseModel):
    confirm: str = Field(
        ...,
        description=f'Must be exactly "{CLEAR_DISTRIBUTOR_INVENTORY_FOR_PRODUCT}"',
    )


@router.delete("/id/{product_id}/dependencies/distributor-inventory")
async def clear_dsi_dependency_facts_for_product(
    product_id: int,
    body: ClearDistributorInventoryFactsBody,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_require_admin_role),
):
    """Admin maintenance: remove DSI ``fact_inventory_distributor`` + ``fact_sales_sellout`` rows for this product.

    Does not delete ``dim_product``. Requires explicit confirm token (see GET detail response).
    """
    if body.confirm != CLEAR_DISTRIBUTOR_INVENTORY_FOR_PRODUCT:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "confirm_required",
                "message": "Refusing delete without explicit maintenance confirm token.",
                "expected_confirm": CLEAR_DISTRIBUTOR_INVENTORY_FOR_PRODUCT,
            },
        )
    row = await db.get(DimProduct, product_id)
    if not row:
        raise HTTPException(status_code=404, detail={"error": "product_not_found", "product_id": product_id})
    try:
        out = await clear_dsi_facts_for_product(db, product_id)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return {
        "ok": True,
        "product_id": product_id,
        "sku": row.sku,
        "deleted": out,
    }


@router.patch("/{product_id}")
async def patch_product(product_id: int, body: ProductPatch, db: AsyncSession = Depends(get_db)):
    row = await db.get(DimProduct, product_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    data = body.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        row.name = data["name"].strip()
    if "category" in data:
        row.category = (data["category"] or "").strip() or None
    if "form_factor" in data:
        row.form_factor = (data["form_factor"] or "").strip() or None
    if "lifecycle_status" in data:
        row.lifecycle_status = (data["lifecycle_status"] or "").strip() or None
    if "launch_date" in data:
        row.launch_date = data["launch_date"]
    if "retired_date" in data:
        row.retired_date = data["retired_date"]
    if "is_active" in data:
        row.is_active = bool(data["is_active"])
    if "channel_id" in data:
        cid = data["channel_id"]
        if cid is not None:
            ch = await db.get(DimChannel, cid)
            if not ch:
                raise HTTPException(status_code=400, detail="Invalid channel_id")
        row.channel_id = cid
    await db.commit()
    await db.refresh(row)
    return {
        "id": row.id,
        "sku": row.sku,
        "name": row.name,
        "category": row.category,
        "form_factor": row.form_factor,
        "lifecycle_status": row.lifecycle_status,
        "launch_date": row.launch_date.isoformat() if row.launch_date else None,
        "retired_date": row.retired_date.isoformat() if row.retired_date else None,
        "is_active": row.is_active,
        "channel_id": row.channel_id,
    }


@router.post("/bulk", status_code=200)
async def bulk_upsert_products(body: ProductBulkBody, db: AsyncSession = Depends(get_db)):
    if len(body.rows) > 5000:
        raise HTTPException(status_code=400, detail="Too many rows (max 5000)")
    ch_res = await db.execute(select(DimChannel))
    channels = {c.code: c.id for c in ch_res.scalars().all()}
    created = 0
    updated = 0
    for r in body.rows:
        sku = r.sku.strip()
        name = r.name.strip()
        cat = r.category.strip() if r.category else None
        channel_id = None
        if r.channel_code and r.channel_code.strip():
            channel_id = channels.get(r.channel_code.strip())
            if channel_id is None:
                raise HTTPException(status_code=400, detail=f"Unknown channel_code for SKU {sku!r}")
        existing = await db.execute(select(DimProduct).where(DimProduct.sku == sku))
        row = existing.scalar_one_or_none()
        if row:
            row.name = name
            row.category = cat
            row.channel_id = channel_id
            updated += 1
        else:
            db.add(DimProduct(sku=sku, name=name, category=cat, channel_id=channel_id))
            created += 1
    await db.commit()
    return {"created": created, "updated": updated, "total": len(body.rows)}


@router.get("/{product_id}/references")
async def get_product_references(product_id: int, db: AsyncSession = Depends(get_db)):
    """List user-facing areas that still reference this product (for delete UX)."""
    return await _product_references_bundle(db, product_id)


@router.post("/bulk-delete-preview")
async def post_products_bulk_delete_preview(body: MasterBulkIdsBody, db: AsyncSession = Depends(get_db)):
    if not body.entity_ids:
        raise HTTPException(
            status_code=400,
            detail={"error": "no_valid_entity_ids", "message": "Provide at least one valid product id."},
        )
    return await preview_master_bulk_delete(db, "products", body.entity_ids)


@router.post("/bulk-delete-confirm")
async def post_products_bulk_delete_confirm(
    body: MasterBulkDeleteConfirmBody, db: AsyncSession = Depends(get_db)
):
    if not body.entity_ids:
        raise HTTPException(
            status_code=400,
            detail={"error": "no_valid_entity_ids", "message": "Provide at least one valid product id."},
        )
    try:
        return await confirm_master_bulk_delete(
            db,
            "products",
            body.entity_ids,
            deletable_ids=body.deletable_ids,
        )
    except Exception as exc:
        raise_bulk_delete_http_error(exc, entity_label="product")


async def _delete_dim_product(product_id: int, db: AsyncSession) -> Response:
    row = await db.get(DimProduct, product_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    refs = await product_hard_reference_breakdown(db, product_id)
    if refs:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Product is still referenced; remove or clear dependent rows first.",
                "references": refs,
            },
        )
    await cleanup_soft_product_references(db, product_id)
    await db.delete(row)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        refs2 = await product_hard_reference_breakdown(db, product_id)
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Product could not be deleted (database constraint). Dependent data may have changed.",
                "references": refs2
                if refs2
                else [{"label": "Unknown referencing rows (try refresh)", "count": 1}],
            },
        ) from None
    return Response(status_code=204)


@router.delete("/id/{product_id}", status_code=204)
async def delete_product_by_path_id(product_id: int, db: AsyncSession = Depends(get_db)):
    """Explicit path; same behavior as `DELETE /{product_id}`."""
    return await _delete_dim_product(product_id, db)


@router.delete("/{product_id}", status_code=204)
async def delete_product(product_id: int, db: AsyncSession = Depends(get_db)):
    """Registered after `GET /{product_id}/references` so two-segment paths are not mistaken for delete."""
    return await _delete_dim_product(product_id, db)
