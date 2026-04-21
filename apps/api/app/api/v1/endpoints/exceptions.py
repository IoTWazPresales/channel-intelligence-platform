from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.derived import ExceptionInboxItem

router = APIRouter()


class ClearConfirmBody(BaseModel):
    confirm: bool = False


@router.get("")
async def list_exceptions(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(ExceptionInboxItem).order_by(ExceptionInboxItem.severity.desc()))
    rows = res.scalars().all()
    return [
        {
            "id": r.id,
            "exception_type": r.exception_type,
            "severity": r.severity,
            "title": r.title,
            "detail": r.detail,
            "explanation_summary": r.explanation_summary,
            "explanation_factors": r.explanation_factors,
            "status": r.status,
            "owner": r.owner,
        }
        for r in rows
    ]


@router.delete("/{item_id}", status_code=204)
async def delete_exception(item_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(ExceptionInboxItem, item_id)
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
async def clear_exceptions(body: ClearConfirmBody, db: AsyncSession = Depends(get_db)):
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Set confirm to true")
    try:
        res = await db.execute(delete(ExceptionInboxItem))
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Cannot clear: rows are still referenced by other tables. Delete dependent rows first.")
    return {"deleted": res.rowcount or 0}
