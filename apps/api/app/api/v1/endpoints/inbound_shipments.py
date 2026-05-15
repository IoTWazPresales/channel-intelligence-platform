from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.dimensions import DimDistributor, DimProduct
from app.models.facts import FactInboundShipment

router = APIRouter()


class InboundPatch(BaseModel):
    distributor_id: int | None = None


class ClearConfirmBody(BaseModel):
    confirm: bool = False


@router.get("")
async def list_inbound(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(FactInboundShipment).order_by(FactInboundShipment.updated_at.desc()))
    rows = res.scalars().all()
    out = []
    for s in rows:
        prod = await db.get(DimProduct, s.product_id)
        dist = await db.get(DimDistributor, s.distributor_id) if s.distributor_id else None
        out.append(
            {
                "id": s.id,
                "product_sku": prod.sku if prod else None,
                "eta_date": s.eta_date.isoformat() if s.eta_date else None,
                "quantity": float(s.quantity) if s.quantity is not None else None,
                "reference": s.reference,
                "status": s.status,
                "line_state": s.line_state,
                "source_key": s.source_key,
                "import_job_id": s.import_job_id,
                "distributor_id": s.distributor_id,
                "distributor_code": dist.code if dist else None,
            }
        )
    return out


@router.patch("/{shipment_id}")
async def patch_inbound(shipment_id: int, body: InboundPatch, db: AsyncSession = Depends(get_db)):
    row = await db.get(FactInboundShipment, shipment_id)
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


@router.delete("/{shipment_id}", status_code=204)
async def delete_inbound(shipment_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(FactInboundShipment, shipment_id)
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
async def clear_inbound(body: ClearConfirmBody, db: AsyncSession = Depends(get_db)):
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Set confirm to true")
    try:
        res = await db.execute(delete(FactInboundShipment))
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Cannot clear: rows are still referenced by other tables. Delete dependent rows first.")
    return {"deleted": res.rowcount or 0}
