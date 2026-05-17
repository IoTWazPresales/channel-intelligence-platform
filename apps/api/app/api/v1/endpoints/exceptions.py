from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import delete, desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.derived import ExceptionInboxItem
from app.models.dimensions import DimDistributor
from app.models.facts import FactInboundShipment, FactSalesSellout
from app.models.import_distributor_si import ImportDistributorSiStagingLine
from app.models.shipment_evidence import ShipmentEvidenceLine

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


@router.get("/analysis/unresolved-products")
async def unresolved_products(db: AsyncSession = Depends(get_db)):
    shipment_q = (
        select(
            ShipmentEvidenceLine.item_code,
            func.min(ShipmentEvidenceLine.sales_model_name).label("sample_sales_model"),
            func.count().label("cnt"),
        )
        .where(ShipmentEvidenceLine.product_resolution_status == "no_match")
        .group_by(ShipmentEvidenceLine.item_code)
        .order_by(desc("cnt"))
        .limit(50)
    )
    shipment_rows = (await db.execute(shipment_q)).all()
    shipment_unresolved = [
        {"item_code": r.item_code, "sample_sales_model": r.sample_sales_model, "count": int(r.cnt)}
        for r in shipment_rows
    ]

    dsi_q = (
        select(
            ImportDistributorSiStagingLine.raw_product_token,
            func.count().label("cnt"),
        )
        .where(
            ImportDistributorSiStagingLine.resolved_product_id.is_(None),
            ImportDistributorSiStagingLine.raw_product_token.is_not(None),
        )
        .group_by(ImportDistributorSiStagingLine.raw_product_token)
        .order_by(desc("cnt"))
        .limit(50)
    )
    dsi_rows = (await db.execute(dsi_q)).all()
    dsi_unresolved = [
        {"raw_product_token": r.raw_product_token, "count": int(r.cnt)}
        for r in dsi_rows
    ]

    total = sum(r["count"] for r in shipment_unresolved) + sum(r["count"] for r in dsi_unresolved)
    return {
        "shipment_unresolved": shipment_unresolved,
        "dsi_unresolved": dsi_unresolved,
        "total_unresolved": total,
    }


@router.get("/analysis/distributor-gaps")
async def distributor_gaps(db: AsyncSession = Depends(get_db)):
    inbound_count = (
        select(
            FactInboundShipment.distributor_id.label("distributor_id"),
            func.count(FactInboundShipment.id).label("inbound_cnt"),
        )
        .where(FactInboundShipment.distributor_id.is_not(None))
        .group_by(FactInboundShipment.distributor_id)
        .subquery()
    )
    sellout_count = (
        select(
            FactSalesSellout.distributor_id.label("distributor_id"),
            func.count(FactSalesSellout.id).label("sellout_cnt"),
        )
        .where(FactSalesSellout.distributor_id.is_not(None))
        .group_by(FactSalesSellout.distributor_id)
        .subquery()
    )
    q = (
        select(DimDistributor)
        .outerjoin(inbound_count, inbound_count.c.distributor_id == DimDistributor.id)
        .outerjoin(sellout_count, sellout_count.c.distributor_id == DimDistributor.id)
        .where(
            func.coalesce(inbound_count.c.inbound_cnt, 0) == 0,
            func.coalesce(sellout_count.c.sellout_cnt, 0) == 0,
        )
        .order_by(DimDistributor.code)
    )
    rows = (await db.execute(q)).scalars().all()
    items = [
        {"id": r.id, "distributor_code": r.code, "distributor_name": r.name}
        for r in rows
    ]
    return {"items": items, "total": len(items)}


@router.get("/analysis/data-quality")
async def data_quality():
    return {
        "checks": [
            {"name": "More exception types coming soon", "status": "placeholder"}
        ]
    }
