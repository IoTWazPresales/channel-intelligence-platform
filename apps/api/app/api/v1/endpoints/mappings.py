from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.mapping import EntityMappingQueue

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
