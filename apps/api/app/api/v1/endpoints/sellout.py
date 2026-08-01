from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy import delete, desc, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.security import get_optional_current_user
from app.core.tenant_scope import where_tenant
from app.models.dimensions import DimCustomer, DimDistributor, DimProduct
from app.models.facts import FactSalesSellout

router = APIRouter()


def _parse_opt_date(s: str | None) -> date | None:
    if not s or not str(s).strip():
        return None
    try:
        return date.fromisoformat(str(s).strip()[:10])
    except ValueError:
        return None


class SelloutPatch(BaseModel):
    distributor_id: int | None = None


class ClearConfirmBody(BaseModel):
    confirm: bool = False


@router.get("/filter-options")
async def sellout_filter_options(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(8000, ge=1, le=20000),
    user: dict | None = Depends(get_optional_current_user),
) -> dict[str, object]:
    dr = await db.execute(
        select(DimDistributor.id, DimDistributor.code, DimDistributor.name)
        .where(where_tenant(DimDistributor.tenant_id, user))
        .order_by(DimDistributor.name.asc(), DimDistributor.code.asc())
        .limit(limit)
    )
    cr = await db.execute(
        select(DimCustomer.id, DimCustomer.code, DimCustomer.name)
        .where(where_tenant(DimCustomer.tenant_id, user))
        .order_by(DimCustomer.name.asc(), DimCustomer.code.asc())
        .limit(limit)
    )
    dist_items = [{"id": int(r[0]), "distributor_code": r[1] or "", "distributor_name": r[2] or ""} for r in dr.all()]
    cust_items = [{"id": int(r[0]), "customer_code": r[1] or "", "customer_name": r[2] or ""} for r in cr.all()]
    return {"distributors": dist_items, "customers": cust_items}


@router.get("/commercial-summary")
async def sellout_commercial_summary(
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
) -> dict[str, object]:
    tenant_f = where_tenant(FactSalesSellout.tenant_id, user)
    total_rows = int(
        await db.scalar(select(func.count()).select_from(FactSalesSellout).where(tenant_f)) or 0
    )
    total_units = float(
        await db.scalar(select(func.coalesce(func.sum(FactSalesSellout.units), 0)).where(tenant_f)) or 0
    )
    total_revenue = float(
        await db.scalar(select(func.coalesce(func.sum(FactSalesSellout.revenue), 0)).where(tenant_f)) or 0
    )
    latest = await db.scalar(select(func.max(FactSalesSellout.period_start)).where(tenant_f))
    return {
        "total_rows": total_rows,
        "total_units": total_units,
        "total_revenue": total_revenue,
        "latest_period_start": latest.isoformat() if latest else None,
    }


@router.get("/commercial-lines")
async def sellout_commercial_lines(
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    distributor_id: int | None = None,
    customer_id: int | None = None,
    product_search: str | None = None,
    period_from: str | None = None,
    period_to: str | None = None,
    smart_view: str | None = None,
    user: dict | None = Depends(get_optional_current_user),
) -> dict[str, object]:
    pf = _parse_opt_date(period_from)
    pt = _parse_opt_date(period_to)
    smart = (smart_view or "").strip().lower()
    tenant_f = where_tenant(FactSalesSellout.tenant_id, user)

    q = (
        select(
            FactSalesSellout,
            DimProduct.sku.label("product_sku"),
            DimProduct.name.label("product_name"),
            DimCustomer.code.label("customer_code"),
            DimCustomer.name.label("customer_name"),
            DimDistributor.code.label("distributor_code"),
            DimDistributor.name.label("distributor_name"),
        )
        .join(DimProduct, FactSalesSellout.product_id == DimProduct.id)
        .join(DimCustomer, FactSalesSellout.customer_id == DimCustomer.id)
        .outerjoin(DimDistributor, FactSalesSellout.distributor_id == DimDistributor.id)
        .where(tenant_f)
    )

    if distributor_id is not None:
        q = q.where(FactSalesSellout.distributor_id == int(distributor_id))
    if customer_id is not None:
        q = q.where(FactSalesSellout.customer_id == int(customer_id))
    if pf is not None:
        q = q.where(FactSalesSellout.period_start >= pf)
    if pt is not None:
        q = q.where(FactSalesSellout.period_start <= pt)
    ps = (product_search or "").strip()
    if ps:
        like = f"%{ps.lower()}%"
        q = q.where(
            or_(
                func.lower(DimProduct.sku).like(like),
                func.lower(DimProduct.name).like(like),
                func.lower(DimCustomer.code).like(like),
                func.lower(DimCustomer.name).like(like),
            )
        )

    if smart == "fastest_movers":
        cutoff = date.today() - timedelta(days=365)
        agg = (
            select(FactSalesSellout.product_id.label("pid"), func.sum(FactSalesSellout.units).label("tu"))
            .where(FactSalesSellout.period_start >= cutoff, tenant_f)
            .group_by(FactSalesSellout.product_id)
            .subquery()
        )
        top_sub = select(agg.c.pid).order_by(desc(agg.c.tu)).limit(60).subquery()
        q = q.where(FactSalesSellout.product_id.in_(select(top_sub.c.pid)))
    elif smart == "customers_increased_volume":
        d_now = date.today() - timedelta(days=90)
        d_prev_start = date.today() - timedelta(days=180)
        cur = (
            select(FactSalesSellout.customer_id.label("cid"), func.sum(FactSalesSellout.units).label("su"))
            .where(FactSalesSellout.period_start >= d_now, tenant_f)
            .group_by(FactSalesSellout.customer_id)
            .subquery()
        )
        prev = (
            select(FactSalesSellout.customer_id.label("cid"), func.sum(FactSalesSellout.units).label("pu"))
            .where(
                FactSalesSellout.period_start >= d_prev_start,
                FactSalesSellout.period_start < d_now,
                tenant_f,
            )
            .group_by(FactSalesSellout.customer_id)
            .subquery()
        )
        momentum = (
            select(cur.c.cid)
            .select_from(cur.join(prev, prev.c.cid == cur.c.cid))
            .where(cur.c.su > prev.c.pu * 1.2, prev.c.pu > 10)
            .subquery()
        )
        q = q.where(FactSalesSellout.customer_id.in_(select(momentum.c.cid)))
    elif smart == "customers_dropped_off":
        d_now = date.today() - timedelta(days=90)
        d_prev_start = date.today() - timedelta(days=180)
        cur = (
            select(FactSalesSellout.customer_id.label("cid"), func.sum(FactSalesSellout.units).label("su"))
            .where(FactSalesSellout.period_start >= d_now, tenant_f)
            .group_by(FactSalesSellout.customer_id)
            .subquery()
        )
        prev = (
            select(FactSalesSellout.customer_id.label("cid"), func.sum(FactSalesSellout.units).label("pu"))
            .where(
                FactSalesSellout.period_start >= d_prev_start,
                FactSalesSellout.period_start < d_now,
                tenant_f,
            )
            .group_by(FactSalesSellout.customer_id)
            .subquery()
        )
        dropped = (
            select(prev.c.cid)
            .select_from(prev.outerjoin(cur, cur.c.cid == prev.c.cid))
            .where(prev.c.pu > 20, func.coalesce(cur.c.su, 0) < prev.c.pu * 0.5)
            .subquery()
        )
        q = q.where(FactSalesSellout.customer_id.in_(select(dropped.c.cid)))

    count_q = select(func.count()).select_from(q.subquery())
    total = int((await db.scalar(count_q)) or 0)

    rows = (await db.execute(q.order_by(desc(FactSalesSellout.period_start)).offset(skip).limit(limit))).all()

    items: list[dict[str, object]] = []
    for row in rows:
        s = row[0]
        items.append(
            {
                "id": s.id,
                "source_key": s.source_key,
                "staging_line_id": s.staging_line_id,
                "product_id": s.product_id,
                "product_sku": row.product_sku,
                "product_name": row.product_name,
                "customer_id": s.customer_id,
                "customer_code": row.customer_code,
                "customer_name": row.customer_name,
                "distributor_id": s.distributor_id,
                "distributor_code": row.distributor_code,
                "distributor_name": row.distributor_name,
                "period_start": s.period_start.isoformat(),
                "units": float(s.units),
                "revenue": float(s.revenue),
                "unit_sellout_price_ex_tax_amount": float(s.unit_sellout_price_ex_tax_amount)
                if s.unit_sellout_price_ex_tax_amount is not None
                else None,
                "currency_code": s.currency_code,
                "source_import_job_id": s.source_import_job_id,
            }
        )

    return {"total": total, "skip": skip, "limit": limit, "items": items}


@router.get("/zero-sellout-products")
async def sellout_zero_products(
    db: AsyncSession = Depends(get_db),
    lookback_days: int = Query(365, ge=30, le=1095),
    limit: int = Query(100, ge=1, le=500),
    user: dict | None = Depends(get_optional_current_user),
) -> dict[str, object]:
    since = date.today() - timedelta(days=lookback_days)
    sold_sub = (
        select(FactSalesSellout.product_id)
        .where(
            FactSalesSellout.period_start >= since,
            where_tenant(FactSalesSellout.tenant_id, user),
        )
        .distinct()
    )
    res = await db.execute(
        select(DimProduct.id, DimProduct.sku, DimProduct.name)
        .where(DimProduct.is_active.is_(True), where_tenant(DimProduct.tenant_id, user))
        .where(DimProduct.id.not_in(sold_sub))
        .order_by(DimProduct.sku.asc())
        .limit(limit)
    )
    rows = res.all()
    return {
        "lookback_days": lookback_days,
        "items": [{"product_id": int(r[0]), "sku": r[1], "name": r[2]} for r in rows],
    }


@router.get("")
async def list_sellout(
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
):
    res = await db.execute(
        select(FactSalesSellout)
        .where(where_tenant(FactSalesSellout.tenant_id, user))
        .order_by(FactSalesSellout.period_start.desc())
    )
    rows = res.scalars().all()
    out = []
    for s in rows:
        prod = await db.get(DimProduct, s.product_id)
        cust = await db.get(DimCustomer, s.customer_id)
        dist = await db.get(DimDistributor, s.distributor_id) if s.distributor_id else None
        out.append(
            {
                "id": s.id,
                "product_sku": prod.sku if prod else None,
                "customer_code": cust.code if cust else None,
                "period_start": s.period_start.isoformat(),
                "units": float(s.units),
                "revenue": float(s.revenue),
                "distributor_id": s.distributor_id,
                "distributor_code": dist.code if dist else None,
                "unit_sellout_price_ex_tax_amount": float(s.unit_sellout_price_ex_tax_amount)
                if s.unit_sellout_price_ex_tax_amount is not None
                else None,
                "reported_revenue_amount": float(s.reported_revenue_amount)
                if s.reported_revenue_amount is not None
                else None,
                "computed_revenue_amount": float(s.computed_revenue_amount)
                if s.computed_revenue_amount is not None
                else None,
                "currency_code": s.currency_code,
                "source_import_job_id": s.source_import_job_id,
            }
        )
    return out


@router.patch("/{sellout_id}")
async def patch_sellout(sellout_id: int, body: SelloutPatch, db: AsyncSession = Depends(get_db)):
    row = await db.get(FactSalesSellout, sellout_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    data = body.model_dump(exclude_unset=True)
    if "distributor_id" in data:
        did = data["distributor_id"]
        if did is not None:
            d = await db.get(DimDistributor, did)
            if not d:
                raise HTTPException(status_code=400, detail="Invalid distributor_id")
        row.distributor_id = did
    await db.commit()
    await db.refresh(row)
    return {"id": row.id, "distributor_id": row.distributor_id}


@router.delete("/{sellout_id}", status_code=204)
async def delete_sellout(sellout_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(FactSalesSellout, sellout_id)
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
async def clear_sellout(body: ClearConfirmBody, db: AsyncSession = Depends(get_db)):
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Set confirm to true")
    try:
        res = await db.execute(delete(FactSalesSellout))
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Cannot clear: rows are still referenced by other tables. Delete dependent rows first.")
    return {"deleted": res.rowcount or 0}
