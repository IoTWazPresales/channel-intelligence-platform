"""CRUD for retailer listings following distributors.py pattern."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.customer_sales import DimRetailerListing
from app.models.dimensions import DimCustomer, DimProduct

router = APIRouter()


class RetailerListingCreate(BaseModel):
    product_id: int = Field(ge=1)
    customer_id: int = Field(ge=1)
    listing_url: str = Field(min_length=1, max_length=1024)
    retailer_sku: str | None = Field(default=None, max_length=256)
    expected_price: float | None = None
    listing_status: str = Field(default="active", max_length=32)
    notes: str | None = Field(default=None, max_length=1024)


class RetailerListingPatch(BaseModel):
    listing_url: str | None = Field(default=None, min_length=1, max_length=1024)
    retailer_sku: str | None = Field(default=None, max_length=256)
    expected_price: float | None = None
    listing_status: str | None = Field(default=None, max_length=32)
    last_price_seen: float | None = None
    last_availability_seen: str | None = Field(default=None, max_length=32)
    notes: str | None = Field(default=None, max_length=1024)


def _listing_to_dict(r: DimRetailerListing) -> dict[str, Any]:
    return {
        "id": r.id,
        "product_id": r.product_id,
        "customer_id": r.customer_id,
        "listing_url": r.listing_url,
        "retailer_sku": r.retailer_sku,
        "expected_price": float(r.expected_price) if r.expected_price is not None else None,
        "listing_status": r.listing_status,
        "last_checked_at": r.last_checked_at.isoformat() if r.last_checked_at else None,
        "last_price_seen": float(r.last_price_seen) if r.last_price_seen is not None else None,
        "last_availability_seen": r.last_availability_seen,
        "notes": r.notes,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


@router.get("")
async def list_retailer_listings(
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    product_id: int | None = None,
    customer_id: int | None = None,
    listing_status: str | None = None,
    search: str | None = None,
) -> dict[str, Any]:
    try:
        q = select(DimRetailerListing)

        if product_id is not None:
            q = q.where(DimRetailerListing.product_id == int(product_id))
        if customer_id is not None:
            q = q.where(DimRetailerListing.customer_id == int(customer_id))
        if listing_status:
            q = q.where(DimRetailerListing.listing_status == listing_status)
        if search and search.strip():
            term = f"%{search.strip()}%"
            q = q.where(
                DimRetailerListing.listing_url.ilike(term)
                | DimRetailerListing.retailer_sku.ilike(term)
            )

        count_q = select(func.count()).select_from(q.subquery())
        total = int((await db.scalar(count_q)) or 0)

        rows = (await db.execute(q.order_by(DimRetailerListing.id.desc()).offset(skip).limit(limit))).scalars().all()
        items = [_listing_to_dict(r) for r in rows]

    except Exception:
        return {"data_unavailable": True, "reason": "dim_retailer_listing table not yet created", "total": 0, "items": []}

    return {"total": total, "skip": skip, "limit": limit, "items": items}


@router.get("/{listing_id}")
async def get_retailer_listing(
    listing_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        row = await db.get(DimRetailerListing, listing_id)
    except Exception:
        raise HTTPException(status_code=500, detail="dim_retailer_listing table not yet created")
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    return _listing_to_dict(row)


@router.post("", status_code=201)
async def create_retailer_listing(
    body: RetailerListingCreate,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    product = await db.get(DimProduct, body.product_id)
    if not product:
        raise HTTPException(status_code=400, detail="Invalid product_id")
    customer = await db.get(DimCustomer, body.customer_id)
    if not customer:
        raise HTTPException(status_code=400, detail="Invalid customer_id")

    row = DimRetailerListing(
        product_id=body.product_id,
        customer_id=body.customer_id,
        listing_url=body.listing_url.strip(),
        retailer_sku=body.retailer_sku.strip() if body.retailer_sku else None,
        expected_price=body.expected_price,
        listing_status=body.listing_status.strip(),
        notes=body.notes.strip() if body.notes else None,
    )
    db.add(row)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Listing already exists for this product/customer/URL combination")
    await db.refresh(row)
    return _listing_to_dict(row)


@router.patch("/{listing_id}")
async def patch_retailer_listing(
    listing_id: int,
    body: RetailerListingPatch,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await db.get(DimRetailerListing, listing_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    data = body.model_dump(exclude_unset=True)
    if "listing_url" in data and data["listing_url"] is not None:
        row.listing_url = data["listing_url"].strip()
    if "retailer_sku" in data:
        row.retailer_sku = data["retailer_sku"].strip() if data["retailer_sku"] else None
    if "expected_price" in data:
        row.expected_price = data["expected_price"]
    if "listing_status" in data and data["listing_status"] is not None:
        row.listing_status = data["listing_status"].strip()
    if "last_price_seen" in data:
        row.last_price_seen = data["last_price_seen"]
    if "last_availability_seen" in data:
        row.last_availability_seen = data["last_availability_seen"]
    if "notes" in data:
        row.notes = data["notes"].strip() if data["notes"] else None
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Listing already exists for this product/customer/URL combination")
    await db.refresh(row)
    return _listing_to_dict(row)


@router.delete("/{listing_id}", status_code=204)
async def delete_retailer_listing(
    listing_id: int,
    db: AsyncSession = Depends(get_db),
) -> Response:
    row = await db.get(DimRetailerListing, listing_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    await db.delete(row)
    await db.commit()
    return Response(status_code=204)
