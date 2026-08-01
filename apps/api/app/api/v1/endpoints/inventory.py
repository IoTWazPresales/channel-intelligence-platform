from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.security import get_optional_current_user
from app.core.tenant_scope import tenant_id_from_user, where_tenant
from app.models.dimensions import DimCustomer, DimProduct
from app.models.facts import FactInventoryCustomer
from app.services.facts_upsert import get_or_create_customer, get_or_create_product

router = APIRouter()


class InventoryCustomerRowIn(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    customer_code: str = Field(min_length=1, max_length=64)
    as_of_date: str = Field(min_length=8, max_length=32)
    on_hand_units: float
    on_order_units: float = 0


class InventoryCustomerBulkBody(BaseModel):
    rows: list[InventoryCustomerRowIn]


class ClearConfirmBody(BaseModel):
    confirm: bool = False


def _parse_iso_date(s: str) -> date:
    s = s.strip()
    if "T" in s:
        s = s.split("T", 1)[0]
    try:
        y, m, d = (int(x) for x in s.split("-", 2))
        return date(y, m, d)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Invalid date {s!r}") from exc


@router.get("/customer")
async def inventory_customer(
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
):
    res = await db.execute(
        select(FactInventoryCustomer)
        .where(where_tenant(FactInventoryCustomer.tenant_id, user))
        .order_by(FactInventoryCustomer.as_of_date.desc())
    )
    rows = res.scalars().all()
    out = []
    for inv in rows:
        prod = await db.get(DimProduct, inv.product_id)
        cust = await db.get(DimCustomer, inv.customer_id)
        out.append(
            {
                "id": inv.id,
                "product_sku": prod.sku if prod else None,
                "product_name": prod.name if prod else None,
                "customer_code": cust.code if cust else None,
                "as_of_date": inv.as_of_date.isoformat(),
                "on_hand_units": float(inv.on_hand_units),
                "on_order_units": float(inv.on_order_units),
            }
        )
    return out


@router.post("/customer", status_code=201)
async def create_inventory_customer(
    row: InventoryCustomerRowIn,
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
):
    try:
        as_of = _parse_iso_date(row.as_of_date)
        prod = await get_or_create_product(db, row.sku)
        cust = await get_or_create_customer(db, row.customer_code)
        inv = FactInventoryCustomer(
            product_id=prod.id,
            customer_id=cust.id,
            as_of_date=as_of,
            on_hand_units=row.on_hand_units,
            on_order_units=row.on_order_units,
            tenant_id=tenant_id_from_user(user),
        )
        db.add(inv)
        await db.commit()
        await db.refresh(inv)
        return {"id": inv.id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/customer/bulk", status_code=200)
async def bulk_create_inventory_customer(body: InventoryCustomerBulkBody, db: AsyncSession = Depends(get_db)):
    if len(body.rows) > 5000:
        raise HTTPException(status_code=400, detail="Too many rows (max 5000)")
    n = 0
    for row in body.rows:
        try:
            as_of = _parse_iso_date(row.as_of_date)
            prod = await get_or_create_product(db, row.sku)
            cust = await get_or_create_customer(db, row.customer_code)
            inv = FactInventoryCustomer(
                product_id=prod.id,
                customer_id=cust.id,
                as_of_date=as_of,
                on_hand_units=row.on_hand_units,
                on_order_units=row.on_order_units,
            )
            db.add(inv)
            n += 1
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
    await db.commit()
    return {"created": n}


@router.delete("/customer/{row_id}", status_code=204)
async def delete_inventory_customer(row_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(FactInventoryCustomer, row_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        await db.delete(row)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Row is still referenced by other tables")
    return Response(status_code=204)


@router.post("/customer/clear-all", status_code=200)
async def clear_inventory_customer(body: ClearConfirmBody, db: AsyncSession = Depends(get_db)):
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Set confirm to true to delete all inventory rows")
    try:
        res = await db.execute(delete(FactInventoryCustomer))
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Cannot clear: rows are still referenced by other tables. Delete dependent rows first.")
    return {"deleted": res.rowcount or 0}
