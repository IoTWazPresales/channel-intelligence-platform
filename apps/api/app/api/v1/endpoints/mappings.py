from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.import_distributor_si import CustomerSourceTokenAlias, ImportEntityMappingCandidate
from app.models.mapping import EntityMappingQueue
from app.services.imports.distributor_sales_inventory import _norm_key

router = APIRouter()


class ClearConfirmBody(BaseModel):
    confirm: bool = False


@router.get("/queue")
async def mapping_queue(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(EntityMappingQueue).order_by(EntityMappingQueue.id.desc()))
    rows = res.scalars().all()
    return [
        {
            "id": r.id,
            "entity_type": r.entity_type,
            "raw_value": r.raw_value,
            "normalized_value": r.normalized_value,
            "suggested_entity_id": r.suggested_entity_id,
            "match_method": r.match_method,
            "confidence_score": float(r.confidence_score) if r.confidence_score is not None else None,
            "status": r.status,
            "job_id": r.job_id,
            "context": r.context,
        }
        for r in rows
    ]


@router.post("/queue/{item_id}/approve")
async def approve(
    item_id: int, entity_id: int = Query(...), db: AsyncSession = Depends(get_db)
):
    item = await db.get(EntityMappingQueue, item_id)
    if not item:
        return {"ok": False}
    item.status = "approved"
    item.suggested_entity_id = entity_id
    item.match_method = "manual"
    await db.commit()
    return {"ok": True, "id": item_id}


@router.post("/queue/{item_id}/reject")
async def reject(item_id: int, db: AsyncSession = Depends(get_db)):
    item = await db.get(EntityMappingQueue, item_id)
    if not item:
        return {"ok": False}
    item.status = "rejected"
    await db.commit()
    return {"ok": True, "id": item_id}


@router.delete("/queue/{item_id}", status_code=204)
async def delete_queue_item(item_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(EntityMappingQueue, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        await db.delete(row)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Row is still referenced by other tables")
    return Response(status_code=204)


@router.post("/queue/clear-all", status_code=200)
async def clear_mapping_queue(body: ClearConfirmBody, db: AsyncSession = Depends(get_db)):
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Set confirm to true")
    try:
        res = await db.execute(delete(EntityMappingQueue))
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Cannot clear: rows are still referenced by other tables. Delete dependent rows first.")
    return {"deleted": res.rowcount or 0}


@router.get("/import-jobs/{job_id}/distributor-si-candidates")
async def list_distributor_si_mapping_candidates(job_id: int, db: AsyncSession = Depends(get_db)):
    """Aggregated unresolved distributor/product/customer tokens from a distributor sales & inventory import job."""
    res = await db.execute(
        select(ImportEntityMappingCandidate)
        .where(ImportEntityMappingCandidate.import_job_id == job_id)
        .order_by(ImportEntityMappingCandidate.entity_type, ImportEntityMappingCandidate.normalized_key)
    )
    rows = res.scalars().all()
    return [
        {
            "id": r.id,
            "import_job_id": r.import_job_id,
            "source_definition_id": r.source_definition_id,
            "entity_type": r.entity_type,
            "normalized_key": r.normalized_key,
            "dealer_group_token": r.dealer_group_token,
            "row_count": r.row_count,
            "total_units": float(r.total_units) if r.total_units is not None else None,
            "total_reported_value": float(r.total_reported_value) if r.total_reported_value is not None else None,
            "sample_raw_values": r.sample_raw_values,
            "suggested_entity_id": r.suggested_entity_id,
            "match_reason": r.match_reason,
            "confidence_score": float(r.confidence_score) if r.confidence_score is not None else None,
            "status": r.status,
            "context": r.context,
            "created_at": r.created_at.isoformat() if r.created_at is not None else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at is not None else None,
        }
        for r in rows
    ]


class CustomerSourceTokenAliasCreate(BaseModel):
    """Explicit approval: map a raw distributor-reported customer/dealer token to an existing dim_customer row."""

    customer_id: int = Field(..., ge=1)
    raw_token: str = Field(..., min_length=1, max_length=512)
    source_definition_id: int | None = None
    distributor_id: int | None = None
    dealer_group_token: str | None = Field(default=None, max_length=512)
    notes: str | None = None


@router.post("/customer-source-token-aliases", status_code=201)
async def create_customer_source_token_alias(body: CustomerSourceTokenAliasCreate, db: AsyncSession = Depends(get_db)):
    nt = _norm_key(body.raw_token)
    if not nt:
        raise HTTPException(status_code=400, detail="raw_token is empty after normalization")
    row = CustomerSourceTokenAlias(
        customer_id=body.customer_id,
        raw_token=body.raw_token.strip()[:512],
        normalized_token=nt[:512],
        source_definition_id=body.source_definition_id,
        distributor_id=body.distributor_id,
        dealer_group_token=(body.dealer_group_token.strip()[:512] if body.dealer_group_token else None),
        status="approved",
        notes=body.notes,
    )
    db.add(row)
    try:
        await db.commit()
        await db.refresh(row)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Could not create alias (invalid customer or source reference)")
    return {
        "id": row.id,
        "customer_id": row.customer_id,
        "normalized_token": row.normalized_token,
        "source_definition_id": row.source_definition_id,
        "distributor_id": row.distributor_id,
        "status": row.status,
    }
