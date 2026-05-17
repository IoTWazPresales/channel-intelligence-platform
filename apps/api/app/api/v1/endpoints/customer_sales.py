"""Customer sales API endpoints for Channel Intelligence Platform."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.db.session_sync import SessionLocal
from app.models.customer_sales import DimStore, FactCustomerSales
from app.models.dimensions import DimCustomer, DimDistributor, DimProduct
from app.models.import_distributor_si import ImportEntityMappingCandidate
from app.models.ingestion import ImportJob

router = APIRouter()

_DATA_UNAVAILABLE = {"data_unavailable": True, "reason": "fact_customer_sales table not yet created"}


@router.get("/filter-options")
async def customer_sales_filter_options(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(8000, ge=1, le=20000),
) -> dict[str, Any]:
    dr = await db.execute(
        select(DimDistributor.id, DimDistributor.code, DimDistributor.name)
        .order_by(DimDistributor.name.asc(), DimDistributor.code.asc())
        .limit(limit)
    )
    cr = await db.execute(
        select(DimCustomer.id, DimCustomer.code, DimCustomer.name)
        .order_by(DimCustomer.name.asc(), DimCustomer.code.asc())
        .limit(limit)
    )
    dist_items = [{"id": int(r[0]), "distributor_code": r[1] or "", "distributor_name": r[2] or ""} for r in dr.all()]
    cust_items = [{"id": int(r[0]), "customer_code": r[1] or "", "customer_name": r[2] or ""} for r in cr.all()]
    return {"distributors": dist_items, "customers": cust_items}


@router.get("/commercial-summary")
async def customer_sales_commercial_summary(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    try:
        total_rows = int(await db.scalar(select(func.count()).select_from(FactCustomerSales)) or 0)
        total_units = float(
            await db.scalar(select(func.coalesce(func.sum(FactCustomerSales.quantity_sold), 0))) or 0
        )
        total_value = float(
            await db.scalar(select(func.coalesce(func.sum(FactCustomerSales.selling_price * FactCustomerSales.quantity_sold), 0))) or 0
        )
        latest_period = await db.execute(
            select(func.max(FactCustomerSales.report_year), func.max(FactCustomerSales.report_week))
        )
        row = latest_period.one_or_none()
        latest = f"{row[0]}-W{row[1]:02d}" if row and row[0] is not None else None
    except Exception:
        return _DATA_UNAVAILABLE
    return {
        "data_unavailable": False,
        "total_rows": total_rows,
        "total_units": total_units,
        "total_value": total_value,
        "latest_period": latest,
    }


@router.get("/commercial-lines")
async def customer_sales_commercial_lines(
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    customer_id: int | None = None,
    product_search: str | None = None,
    store_id: int | None = None,
    report_year: int | None = None,
    report_week: int | None = None,
    channel_type: str | None = None,
    product_resolution_status: str | None = None,
    smart_view: str | None = None,
) -> dict[str, Any]:
    try:
        q = (
            select(
                FactCustomerSales,
                DimProduct.sku.label("product_sku"),
                DimProduct.name.label("product_name"),
                DimCustomer.code.label("customer_code"),
                DimCustomer.name.label("customer_name"),
                DimStore.store_code.label("store_code"),
                DimStore.store_name.label("store_name"),
            )
            .outerjoin(DimProduct, FactCustomerSales.product_id == DimProduct.id)
            .outerjoin(DimCustomer, FactCustomerSales.customer_id == DimCustomer.id)
            .outerjoin(DimStore, FactCustomerSales.store_id == DimStore.id)
        )

        if customer_id is not None:
            q = q.where(FactCustomerSales.customer_id == int(customer_id))
        if store_id is not None:
            q = q.where(FactCustomerSales.store_id == int(store_id))
        if report_year is not None:
            q = q.where(FactCustomerSales.report_year == int(report_year))
        if report_week is not None:
            q = q.where(FactCustomerSales.report_week == int(report_week))
        if channel_type:
            q = q.where(FactCustomerSales.channel_type == channel_type)
        if product_resolution_status:
            q = q.where(FactCustomerSales.product_resolution_status == product_resolution_status)

        ps = (product_search or "").strip()
        if ps:
            like = f"%{ps.lower()}%"
            q = q.where(
                or_(
                    func.lower(DimProduct.sku).like(like),
                    func.lower(DimProduct.name).like(like),
                    func.lower(FactCustomerSales.source_article_code).like(like),
                )
            )

        smart = (smart_view or "").strip().lower()
        if smart == "fastest_movers":
            agg = (
                select(
                    FactCustomerSales.product_id.label("pid"),
                    func.sum(FactCustomerSales.quantity_sold).label("tu"),
                )
                .where(FactCustomerSales.product_id.is_not(None))
                .group_by(FactCustomerSales.product_id)
                .subquery()
            )
            top_sub = select(agg.c.pid).order_by(agg.c.tu.desc()).limit(60).subquery()
            q = q.where(FactCustomerSales.product_id.in_(select(top_sub.c.pid)))
        elif smart == "zero_sellout_products":
            sold_sub = select(FactCustomerSales.product_id).where(
                FactCustomerSales.quantity_sold > 0
            ).distinct()
            q = q.where(FactCustomerSales.product_id.not_in(sold_sub))

        count_q = select(func.count()).select_from(q.subquery())
        total = int((await db.scalar(count_q)) or 0)

        rows = (await db.execute(q.order_by(FactCustomerSales.id.desc()).offset(skip).limit(limit))).all()

        items: list[dict[str, Any]] = []
        for row in rows:
            s = row[0]
            items.append({
                "id": s.id,
                "source_key": s.source_key,
                "customer_id": s.customer_id,
                "customer_code": row.customer_code,
                "customer_name": row.customer_name,
                "product_id": s.product_id,
                "product_sku": row.product_sku,
                "product_name": row.product_name,
                "store_id": s.store_id,
                "store_code": row.store_code,
                "store_name": row.store_name,
                "report_year": s.report_year,
                "report_week": s.report_week,
                "report_period": s.report_period,
                "quantity_sold": float(s.quantity_sold) if s.quantity_sold is not None else None,
                "quantity_returned": float(s.quantity_returned) if s.quantity_returned is not None else None,
                "selling_price": float(s.selling_price) if s.selling_price is not None else None,
                "cost_price": float(s.cost_price) if s.cost_price is not None else None,
                "currency_code": s.currency_code,
                "channel_type": s.channel_type,
                "reported_soh": float(s.reported_soh) if s.reported_soh is not None else None,
                "product_resolution_status": s.product_resolution_status,
                "source_article_code": s.source_article_code,
                "import_job_id": s.import_job_id,
            })

    except Exception:
        return {"data_unavailable": True, "reason": "fact_customer_sales table not yet created", "total": 0, "skip": skip, "limit": limit, "items": []}

    return {"total": total, "skip": skip, "limit": limit, "items": items}


@router.get("/import-jobs/{job_id}/mapping-candidates")
async def list_customer_sales_import_job_mapping_candidates(
    job_id: int,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    job = await db.get(ImportJob, job_id)
    if not job or (job.template_slug or "") != "customer_sales":
        raise HTTPException(status_code=404, detail="Customer sales import job not found")
    res = await db.execute(
        select(ImportEntityMappingCandidate)
        .where(
            ImportEntityMappingCandidate.import_job_id == job_id,
            ImportEntityMappingCandidate.entity_type.in_(
                ("customer_sales_product",)
            ),
        )
        .order_by(ImportEntityMappingCandidate.entity_type, ImportEntityMappingCandidate.normalized_key)
    )
    rows = res.scalars().all()
    out: list[dict[str, Any]] = []
    for r in rows:
        ctx = r.context if isinstance(r.context, dict) else {}
        out.append({
            "id": r.id,
            "import_job_id": r.import_job_id,
            "source_definition_id": r.source_definition_id,
            "entity_type": r.entity_type,
            "normalized_key": r.normalized_key,
            "row_count": r.row_count,
            "total_units": float(r.total_units) if r.total_units is not None else None,
            "total_reported_value": float(r.total_reported_value) if r.total_reported_value is not None else None,
            "sample_raw_values": r.sample_raw_values,
            "suggested_entity_id": r.suggested_entity_id,
            "suggested_action": ctx.get("suggested_action"),
            "match_reason": r.match_reason,
            "confidence_score": float(r.confidence_score) if r.confidence_score is not None else None,
            "status": r.status,
            "context": r.context,
            "created_at": r.created_at.isoformat() if r.created_at is not None else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at is not None else None,
        })
    return out


class MapProductBody(BaseModel):
    product_id: int = Field(ge=1)


@router.post("/import-candidates/{candidate_id}/map-product")
async def customer_sales_import_candidate_map_product(
    candidate_id: int,
    body: MapProductBody,
) -> dict[str, Any]:
    try:
        from app.services.imports.customer_sales_steward_ops import execute_map_customer_sales_product
    except ImportError:
        raise HTTPException(status_code=501, detail="Steward ops module not yet available")
    with SessionLocal() as s:
        cand = s.get(ImportEntityMappingCandidate, candidate_id)
        if not cand:
            raise HTTPException(status_code=404, detail="Candidate not found")
        try:
            result = execute_map_customer_sales_product(s, cand, product_id=body.product_id)
            return result
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


class CreateProductAliasBody(BaseModel):
    product_id: int = Field(ge=1)
    customer_id: int = Field(ge=1)


@router.post("/import-candidates/{candidate_id}/create-product-alias")
async def customer_sales_import_candidate_create_product_alias(
    candidate_id: int,
    body: CreateProductAliasBody,
) -> dict[str, Any]:
    try:
        from app.services.imports.customer_sales_steward_ops import execute_create_customer_sales_product_alias
    except ImportError:
        raise HTTPException(status_code=501, detail="Steward ops module not yet available")
    with SessionLocal() as s:
        cand = s.get(ImportEntityMappingCandidate, candidate_id)
        if not cand:
            raise HTTPException(status_code=404, detail="Candidate not found")
        try:
            result = execute_create_customer_sales_product_alias(
                s, cand, product_id=body.product_id, customer_id=body.customer_id
            )
            return result
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/import-candidates/{candidate_id}/reject")
async def customer_sales_import_candidate_reject(
    candidate_id: int,
) -> dict[str, Any]:
    try:
        from app.services.imports.customer_sales_steward_ops import execute_reject_customer_sales_candidate
    except ImportError:
        raise HTTPException(status_code=501, detail="Steward ops module not yet available")
    with SessionLocal() as s:
        cand = s.get(ImportEntityMappingCandidate, candidate_id)
        if not cand:
            raise HTTPException(status_code=404, detail="Candidate not found")
        try:
            result = execute_reject_customer_sales_candidate(s, cand)
            return result
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/import-jobs/{job_id}/reresolve")
async def customer_sales_import_job_reresolve(
    job_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        from app.services.imports.customer_sales_steward_ops import execute_reresolve_customer_sales_job
    except ImportError:
        raise HTTPException(status_code=501, detail="Steward ops module not yet available")
    job = await db.get(ImportJob, job_id)
    if not job or (job.template_slug or "") != "customer_sales":
        raise HTTPException(status_code=404, detail="Customer sales import job not found")
    with SessionLocal() as s:
        try:
            result = execute_reresolve_customer_sales_job(s, job_id=job_id)
            return result
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


class CreateStoreBody(BaseModel):
    customer_id: int = Field(ge=1)
    store_code: str = Field(min_length=1, max_length=64)
    store_name: str | None = Field(default=None, max_length=256)


@router.post("/stores")
async def create_provisional_store(
    body: CreateStoreBody,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    customer = await db.get(DimCustomer, body.customer_id)
    if not customer:
        raise HTTPException(status_code=400, detail="Invalid customer_id")
    existing = await db.execute(
        select(DimStore).where(
            DimStore.customer_id == body.customer_id,
            DimStore.store_code == body.store_code.strip(),
        )
    )
    if existing.scalars().first():
        raise HTTPException(status_code=409, detail="Store code already exists for this customer")
    store = DimStore(
        customer_id=body.customer_id,
        store_code=body.store_code.strip(),
        store_name=body.store_name.strip() if body.store_name else None,
    )
    db.add(store)
    await db.commit()
    await db.refresh(store)
    return {
        "id": store.id,
        "customer_id": store.customer_id,
        "store_code": store.store_code,
        "store_name": store.store_name,
    }
