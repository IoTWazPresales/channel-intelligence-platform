from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.api.deps import get_db
from app.models.dimensions import DimChannel, DimProduct
from app.services.product_usage import cleanup_soft_product_references, product_hard_reference_breakdown

router = APIRouter()


class ProductPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=512)
    category: str | None = Field(default=None, max_length=256)
    form_factor: str | None = Field(default=None, max_length=128)
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
async def list_products(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(DimProduct).options(joinedload(DimProduct.channel)))
    items = res.unique().scalars().all()
    out = []
    for p in items:
        out.append(
            {
                "id": p.id,
                "sku": p.sku,
                "name": p.name,
                "category": p.category,
                "form_factor": p.form_factor,
                "is_active": p.is_active,
                "channel_id": p.channel_id,
                "channel_code": p.channel.code if p.channel else None,
            }
        )
    out.sort(key=lambda x: x["sku"])
    return out


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
