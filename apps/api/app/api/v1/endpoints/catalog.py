from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.dimensions import DimChannel, DimRegion
from app.services.channel_usage import channel_hard_reference_breakdown
from app.services.master_entity_bulk_delete import confirm_master_bulk_delete, preview_master_bulk_delete
from app.services.region_usage import region_hard_reference_breakdown

router = APIRouter()


class MasterBulkIdsBody(BaseModel):
    entity_ids: list[int] = Field(default_factory=list, max_length=200)


@router.post("/channels/bulk-delete-preview")
async def post_channels_bulk_delete_preview(body: MasterBulkIdsBody, db: AsyncSession = Depends(get_db)):
    if not body.entity_ids:
        raise HTTPException(
            status_code=400,
            detail={"error": "no_valid_entity_ids", "message": "Provide at least one valid channel id."},
        )
    return await preview_master_bulk_delete(db, "channels", body.entity_ids)


@router.post("/channels/bulk-delete-confirm")
async def post_channels_bulk_delete_confirm(body: MasterBulkIdsBody, db: AsyncSession = Depends(get_db)):
    if not body.entity_ids:
        raise HTTPException(
            status_code=400,
            detail={"error": "no_valid_entity_ids", "message": "Provide at least one valid channel id."},
        )
    try:
        return await confirm_master_bulk_delete(db, "channels", body.entity_ids)
    except ValueError as exc:
        code = str(exc)
        if code == "not_all_entities_found":
            raise HTTPException(
                status_code=409,
                detail={
                    "error": code,
                    "message": "One or more channel ids no longer exist; refresh the list and try again.",
                },
            ) from None
        if code == "entities_still_blocked":
            raise HTTPException(
                status_code=409,
                detail={"error": code, "message": "No selected channels can be deleted; all are still referenced."},
            ) from None
        raise


@router.post("/regions/bulk-delete-preview")
async def post_regions_bulk_delete_preview(body: MasterBulkIdsBody, db: AsyncSession = Depends(get_db)):
    if not body.entity_ids:
        raise HTTPException(
            status_code=400,
            detail={"error": "no_valid_entity_ids", "message": "Provide at least one valid region id."},
        )
    return await preview_master_bulk_delete(db, "regions", body.entity_ids)


@router.post("/regions/bulk-delete-confirm")
async def post_regions_bulk_delete_confirm(body: MasterBulkIdsBody, db: AsyncSession = Depends(get_db)):
    if not body.entity_ids:
        raise HTTPException(
            status_code=400,
            detail={"error": "no_valid_entity_ids", "message": "Provide at least one valid region id."},
        )
    try:
        return await confirm_master_bulk_delete(db, "regions", body.entity_ids)
    except ValueError as exc:
        code = str(exc)
        if code == "not_all_entities_found":
            raise HTTPException(
                status_code=409,
                detail={
                    "error": code,
                    "message": "One or more region ids no longer exist; refresh the list and try again.",
                },
            ) from None
        if code == "entities_still_blocked":
            raise HTTPException(
                status_code=409,
                detail={"error": code, "message": "No selected regions can be deleted; all are still referenced."},
            ) from None
        raise


@router.get("/channels")
async def list_channels(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(DimChannel).order_by(DimChannel.code))
    rows = res.scalars().all()
    return [{"id": c.id, "code": c.code, "name": c.name} for c in rows]


@router.get("/regions")
async def list_regions(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(DimRegion).order_by(DimRegion.code))
    rows = res.scalars().all()
    return [{"id": r.id, "code": r.code, "name": r.name} for r in rows]


async def _channel_references_bundle(db: AsyncSession, channel_id: int) -> dict:
    row = await db.get(DimChannel, channel_id)
    if not row:
        raise HTTPException(status_code=404, detail={"error": "channel_not_found", "channel_id": channel_id})
    refs = await channel_hard_reference_breakdown(db, channel_id)
    return {"channel_code": row.code, "references": refs, "blocked": len(refs) > 0}


@router.get("/channels/references")
async def get_channel_references_by_query(
    channel_id: int = Query(..., ge=1, description="dim_channel.id"),
    db: AsyncSession = Depends(get_db),
):
    return await _channel_references_bundle(db, channel_id)


@router.get("/channels/id/{channel_id}/refs")
async def get_channel_refs_for_delete_ux(channel_id: int, db: AsyncSession = Depends(get_db)):
    return await _channel_references_bundle(db, channel_id)


@router.delete("/channels/{channel_id}", status_code=204)
async def delete_channel(channel_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(DimChannel, channel_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    refs = await channel_hard_reference_breakdown(db, channel_id)
    if refs:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Channel is still referenced; remove or reassign dependent rows first.",
                "references": refs,
            },
        )
    await db.delete(row)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        refs2 = await channel_hard_reference_breakdown(db, channel_id)
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Channel could not be deleted (database constraint).",
                "references": refs2
                if refs2
                else [{"label": "Unknown referencing rows (try refresh)", "count": 1}],
            },
        ) from None
    return Response(status_code=204)


async def _region_references_bundle(db: AsyncSession, region_id: int) -> dict:
    row = await db.get(DimRegion, region_id)
    if not row:
        raise HTTPException(status_code=404, detail={"error": "region_not_found", "region_id": region_id})
    refs = await region_hard_reference_breakdown(db, region_id)
    return {"region_code": row.code, "references": refs, "blocked": len(refs) > 0}


@router.get("/regions/references")
async def get_region_references_by_query(
    region_id: int = Query(..., ge=1, description="dim_region.id"),
    db: AsyncSession = Depends(get_db),
):
    return await _region_references_bundle(db, region_id)


@router.get("/regions/id/{region_id}/refs")
async def get_region_refs_for_delete_ux(region_id: int, db: AsyncSession = Depends(get_db)):
    return await _region_references_bundle(db, region_id)


@router.delete("/regions/{region_id}", status_code=204)
async def delete_region(region_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(DimRegion, region_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    refs = await region_hard_reference_breakdown(db, region_id)
    if refs:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Region is still referenced; remove or reassign dependent rows first.",
                "references": refs,
            },
        )
    await db.delete(row)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        refs2 = await region_hard_reference_breakdown(db, region_id)
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Region could not be deleted (database constraint).",
                "references": refs2
                if refs2
                else [{"label": "Unknown referencing rows (try refresh)", "count": 1}],
            },
        ) from None
    return Response(status_code=204)
