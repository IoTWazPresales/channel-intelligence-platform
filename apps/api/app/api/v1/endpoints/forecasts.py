from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.dimensions import DimProduct
from app.models.facts import FactForecast
from app.services.facts_upsert import get_or_create_product, resolve_customer_id

router = APIRouter()


class ForecastRowIn(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    period_start: str = Field(min_length=8, max_length=32)
    forecast_units: float
    confidence_placeholder: str | None = Field(default=None, max_length=64)
    customer_code: str | None = Field(default=None, max_length=64)
    is_override: bool = False


class ForecastBulkBody(BaseModel):
    rows: list[ForecastRowIn]


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


@router.get("")
async def list_forecasts(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(FactForecast).order_by(FactForecast.period_start.desc()))
    rows = res.scalars().all()
    out = []
    for f in rows:
        prod = await db.get(DimProduct, f.product_id)
        out.append(
            {
                "id": f.id,
                "sku": prod.sku if prod else None,
                "period_start": f.period_start.isoformat(),
                "forecast_units": float(f.forecast_units),
                "confidence_placeholder": f.confidence_placeholder,
                "is_override": f.is_override,
            }
        )
    return out


@router.post("", status_code=201)
async def create_forecast(row: ForecastRowIn, db: AsyncSession = Depends(get_db)):
    try:
        period = _parse_iso_date(row.period_start)
        prod = await get_or_create_product(db, row.sku)
        cust_id = await resolve_customer_id(db, row.customer_code, create=True)
        f = FactForecast(
            product_id=prod.id,
            customer_id=cust_id,
            period_start=period,
            forecast_units=row.forecast_units,
            confidence_placeholder=row.confidence_placeholder,
            is_override=row.is_override,
        )
        db.add(f)
        await db.commit()
        await db.refresh(f)
        return {"id": f.id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/bulk", status_code=200)
async def bulk_create_forecasts(body: ForecastBulkBody, db: AsyncSession = Depends(get_db)):
    if len(body.rows) > 5000:
        raise HTTPException(status_code=400, detail="Too many rows (max 5000)")
    n = 0
    for row in body.rows:
        try:
            period = _parse_iso_date(row.period_start)
            prod = await get_or_create_product(db, row.sku)
            cust_id = await resolve_customer_id(db, row.customer_code, create=True)
            f = FactForecast(
                product_id=prod.id,
                customer_id=cust_id,
                period_start=period,
                forecast_units=row.forecast_units,
                confidence_placeholder=row.confidence_placeholder,
                is_override=row.is_override,
            )
            db.add(f)
            n += 1
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
    await db.commit()
    return {"created": n}


@router.delete("/{forecast_id}", status_code=204)
async def delete_forecast(forecast_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(FactForecast, forecast_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        await db.delete(row)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Row is still referenced by other tables")
    return Response(status_code=204)


@router.post("/clear-all", status_code=200)
async def clear_all_forecasts(body: ClearConfirmBody, db: AsyncSession = Depends(get_db)):
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Set confirm to true to delete all forecast rows")
    try:
        res = await db.execute(delete(FactForecast))
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Cannot clear: rows are still referenced by other tables. Delete dependent rows first.")
    return {"deleted": res.rowcount or 0}
