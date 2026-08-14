from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.security import get_optional_current_user
from app.core.tenant_scope import tenant_id_from_user, where_tenant
from app.db.session_sync import SessionLocal
from app.models.dimensions import DimCustomer, DimDistributor, DimProduct
from app.models.fact_demand_forecast import FactDemandForecast
from app.services.commercial_planner.open_channel_customer import OPEN_CHANNEL_CUSTOMER_CODE
from app.services.commercial_planner.unassigned_distributor import UNASSIGNED_DISTRIBUTOR_CODE
from app.services.demand_forecast.analogue_compute import generate_analogue_demand_forecasts
from app.services.demand_forecast.compute_from_history import compute_from_history
from app.services.demand_forecast.velocity_compute import (
    generate_velocity_demand_forecasts,
    sum_rollup,
)

router = APIRouter()


class ForecastRowIn(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    period_start: str = Field(min_length=8, max_length=32)
    forecast_units: float
    confidence_placeholder: str | None = Field(default=None, max_length=64)
    customer_code: str | None = Field(default=None, max_length=64)
    distributor_code: str | None = Field(default=None, max_length=64)
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


def _confidence_for_manual(*, is_override: bool, placeholder: str | None) -> str:
    if is_override:
        return "override"
    if placeholder and placeholder.lower() in {"low", "medium", "high", "override"}:
        return placeholder.lower()
    return "medium"


async def _require_product(db: AsyncSession, sku: str) -> DimProduct:
    row = (
        await db.execute(select(DimProduct).where(DimProduct.sku == sku.strip()))
    ).scalar_one_or_none()
    if row is None:
        raise ValueError(f"Unknown SKU {sku!r} — create/resolve in Product Master first")
    return row


async def _resolve_customer_id(db: AsyncSession, customer_code: str | None) -> int:
    if customer_code and customer_code.strip():
        row = (
            await db.execute(
                select(DimCustomer).where(DimCustomer.code == customer_code.strip())
            )
        ).scalar_one_or_none()
        if row is None:
            raise ValueError(
                f"Unknown customer_code {customer_code!r} — resolve in Customer Master first"
            )
        return int(row.id)
    oc = (
        await db.execute(
            select(DimCustomer).where(DimCustomer.code == OPEN_CHANNEL_CUSTOMER_CODE)
        )
    ).scalar_one_or_none()
    if oc is None:
        raise ValueError("System reference OPEN_CHANNEL customer missing")
    return int(oc.id)


async def _resolve_distributor_id(db: AsyncSession, distributor_code: str | None) -> int:
    if distributor_code and distributor_code.strip():
        row = (
            await db.execute(
                select(DimDistributor).where(DimDistributor.code == distributor_code.strip())
            )
        ).scalar_one_or_none()
        if row is None:
            raise ValueError(
                f"Unknown distributor_code {distributor_code!r} — resolve in Distributor Master first"
            )
        return int(row.id)
    un = (
        await db.execute(
            select(DimDistributor).where(DimDistributor.code == UNASSIGNED_DISTRIBUTOR_CODE)
        )
    ).scalar_one_or_none()
    if un is None:
        raise ValueError("System reference UNASSIGNED distributor missing")
    return int(un.id)


def _serialize(f: FactDemandForecast, prod: DimProduct | None) -> dict:
    return {
        "id": f.id,
        "sku": prod.sku if prod else None,
        "period_start": f.period_start.isoformat(),
        "forecast_units": float(f.forecast_units),
        "confidence_placeholder": f.confidence_level,
        "confidence_level": f.confidence_level,
        "method": f.method,
        "is_override": f.is_override,
        "distributor_id": f.distributor_id,
        "customer_id": f.customer_id,
        "lower_band": float(f.lower_band) if f.lower_band is not None else None,
        "upper_band": float(f.upper_band) if f.upper_band is not None else None,
        "analogue_product_id": f.analogue_product_id,
        "analogue_basis": f.analogue_basis,
        "velocity_basis": f.velocity_basis,
        "seasonal_index": float(f.seasonal_index) if f.seasonal_index is not None else None,
    }


@router.get("")
async def list_forecasts(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=500, ge=1, le=5000),
    method: str | None = Query(default=None),
    user: dict | None = Depends(get_optional_current_user),
):
    q = (
        select(FactDemandForecast)
        .where(where_tenant(FactDemandForecast.tenant_id, user))
        .order_by(FactDemandForecast.period_start.desc())
    )
    if method:
        q = q.where(FactDemandForecast.method == method)
    q = q.limit(limit)
    res = await db.execute(q)
    rows = res.scalars().all()
    out = []
    for f in rows:
        prod = await db.get(DimProduct, f.product_id)
        out.append(_serialize(f, prod))
    return out


class VelocityComputeBody(BaseModel):
    distributor_id: int | None = None
    weeks_ahead: int = Field(default=13, ge=1, le=52)
    confirm: bool = False


class AnalogueComputeBody(BaseModel):
    product_ids: list[int] | None = None
    weeks_ahead: int = Field(default=13, ge=1, le=52)
    max_products: int = Field(default=50, ge=1, le=500)
    confirm: bool = False


class ComputeFromHistoryBody(BaseModel):
    distributor_id: int | None = None
    weeks_ahead: int = Field(default=13, ge=1, le=52)
    max_analogue_products: int = Field(default=50, ge=1, le=500)
    confirm: bool = False


@router.post("/compute-from-history", status_code=200)
async def compute_from_history_forecasts(
    body: ComputeFromHistoryBody,
    user: dict | None = Depends(get_optional_current_user),
):
    """Primary B1 CTA: velocity then analogue into fact_demand_forecast. Overrides kept."""
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Set confirm=true to compute from history")
    tid = tenant_id_from_user(user)
    with SessionLocal() as db:
        try:
            result = compute_from_history(
                db,
                tenant_id=tid,
                distributor_id=body.distributor_id,
                weeks_ahead=body.weeks_ahead,
                max_analogue_products=body.max_analogue_products,
            )
            db.commit()
            return result
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/compute-velocity", status_code=200)
async def compute_velocity_forecasts(
    body: VelocityComputeBody,
    user: dict | None = Depends(get_optional_current_user),
):
    """Project fact_customer_velocity → fact_demand_forecast at full grain (sync)."""
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Set confirm=true to run velocity compute")
    tid = tenant_id_from_user(user)
    with SessionLocal() as db:
        try:
            result = generate_velocity_demand_forecasts(
                db,
                distributor_id=body.distributor_id,
                weeks_ahead=body.weeks_ahead,
                tenant_id=tid,
            )
            db.commit()
            return result
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/compute-analogue", status_code=200)
async def compute_analogue_forecasts(
    body: AnalogueComputeBody,
    user: dict | None = Depends(get_optional_current_user),
):
    """Forecast no-history products from analogue SKUs (confidence capped low)."""
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Set confirm=true to run analogue compute")
    tid = tenant_id_from_user(user)
    with SessionLocal() as db:
        try:
            result = generate_analogue_demand_forecasts(
                db,
                product_ids=body.product_ids,
                weeks_ahead=body.weeks_ahead,
                max_products=body.max_products,
                tenant_id=tid,
            )
            db.commit()
            return result
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/rollups")
async def forecast_rollups(
    group_by: str = Query(..., pattern="^(product|distributor|customer|period)$"),
    period_start: str | None = None,
    user: dict | None = Depends(get_optional_current_user),
):
    """Sum-rollup proof endpoint — Σ(atomic) by axis."""
    period: date | None = None
    if period_start:
        try:
            period = _parse_iso_date(period_start)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
    tid = tenant_id_from_user(user)
    with SessionLocal() as db:
        rows = sum_rollup(db, group_by=group_by, period_start=period, tenant_id=tid)
        atomic_total = float(
            db.execute(
                select(func.coalesce(func.sum(FactDemandForecast.forecast_units), 0)).where(
                    FactDemandForecast.tenant_id == tid
                )
            ).scalar()
            or 0
        )
        rollup_total = sum(r["forecast_units"] for r in rows)
        return {
            "group_by": group_by,
            "rows": rows,
            "atomic_total": atomic_total,
            "rollup_total": rollup_total,
            "reconciles": abs(atomic_total - rollup_total) < 1e-6,
        }


async def _upsert_manual_row(
    db: AsyncSession, row: ForecastRowIn, *, tenant_id: str = "default"
) -> FactDemandForecast:
    period = _parse_iso_date(row.period_start)
    prod = await _require_product(db, row.sku)
    cust_id = await _resolve_customer_id(db, row.customer_code)
    dist_id = await _resolve_distributor_id(db, row.distributor_code)
    conf = _confidence_for_manual(is_override=row.is_override, placeholder=row.confidence_placeholder)
    units = float(row.forecast_units)
    tid = (tenant_id or "default").strip() or "default"
    existing = (
        await db.execute(
            select(FactDemandForecast).where(
                FactDemandForecast.distributor_id == dist_id,
                FactDemandForecast.product_id == prod.id,
                FactDemandForecast.customer_id == cust_id,
                FactDemandForecast.period_start == period,
                FactDemandForecast.tenant_id == tid,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        f = FactDemandForecast(
            distributor_id=dist_id,
            product_id=prod.id,
            customer_id=cust_id,
            period_start=period,
            forecast_units=units,
            lower_band=units if row.is_override else None,
            upper_band=units if row.is_override else None,
            method="manual",
            confidence_level=conf,
            is_override=row.is_override,
            tenant_id=tid,
        )
        db.add(f)
        return f
    existing.forecast_units = units
    existing.method = "manual"
    existing.confidence_level = conf
    existing.is_override = row.is_override or existing.is_override
    if existing.is_override:
        existing.lower_band = units
        existing.upper_band = units
    return existing


@router.post("", status_code=201)
async def create_forecast(
    row: ForecastRowIn,
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
):
    try:
        f = await _upsert_manual_row(db, row, tenant_id=tenant_id_from_user(user))
        await db.commit()
        await db.refresh(f)
        return {"id": f.id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/bulk", status_code=200)
async def bulk_create_forecasts(
    body: ForecastBulkBody,
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
):
    if len(body.rows) > 5000:
        raise HTTPException(status_code=400, detail="Too many rows (max 5000)")
    tid = tenant_id_from_user(user)
    n = 0
    for row in body.rows:
        try:
            await _upsert_manual_row(db, row, tenant_id=tid)
            n += 1
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
    await db.commit()
    return {"created": n}


@router.delete("/{forecast_id}", status_code=204)
async def delete_forecast(forecast_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(FactDemandForecast, forecast_id)
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
        res = await db.execute(delete(FactDemandForecast))
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Cannot clear: rows are still referenced by other tables. Delete dependent rows first.",
        )
    return {"deleted": res.rowcount or 0}
