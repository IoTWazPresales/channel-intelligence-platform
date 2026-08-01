from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_db
from app.models.dimensions import DimChannel, DimCustomer, DimProduct
from app.models.lineup import FactLineupPlanItem, LineupPlanItemEvent
from app.services.lineup.audit import record_lineup_approval_event
from app.services.lineup.bulk import bulk_upsert_lineup_items
from app.services.lineup.net_requirement import (
    DEFAULT_TARGET_COVER_WEEKS,
    build_net_requirement_rows,
)

router = APIRouter()


class ClearConfirmBody(BaseModel):
    confirm: bool = False


_LINEUP_APPROVAL_STATUSES = frozenset({"draft", "pending_approval", "submitted", "approved", "rejected"})


class LineupItemPatch(BaseModel):
    approval_status: str | None = None
    notes: str | None = None


class LineupBulkRow(BaseModel):
    customer_code: str = Field(min_length=1, max_length=64)
    channel_code: str | None = Field(default=None, max_length=32)
    period_start: date
    period_label: str | None = Field(default=None, max_length=32)
    sku: str = Field(min_length=1, max_length=64)
    predecessor_sku: str | None = Field(default=None, max_length=64)
    successor_sku: str | None = Field(default=None, max_length=64)
    planned_range_summary: str | None = Field(default=None, max_length=256)
    current_range_summary: str | None = Field(default=None, max_length=256)
    planned_launch_date: date | None = None
    planned_eol_date: date | None = None
    planned_volume_units: float = Field(default=0.0)
    current_volume_units: float | None = None
    overlap_cannibalization_flag: bool = False
    whitespace_gap_flag: bool = False
    approval_status: str | None = Field(default="draft", max_length=32)
    notes: str | None = None


class LineupBulkBody(BaseModel):
    rows: list[LineupBulkRow] = Field(default_factory=list)
    replace_matching: bool = Field(
        default=False,
        description="When false, existing natural keys are skipped. When true, matching rows are updated in place.",
    )

    @model_validator(mode="after")
    def _cap_rows(self) -> LineupBulkBody:
        if len(self.rows) > 2000:
            raise ValueError("Too many rows (max 2000)")
        return self


@router.get("/items")
async def list_lineup_items(
    customer_id: int | None = Query(default=None),
    channel_id: int | None = Query(default=None),
    period_start: date | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(FactLineupPlanItem).options(
        selectinload(FactLineupPlanItem.customer),
        selectinload(FactLineupPlanItem.channel),
        selectinload(FactLineupPlanItem.product),
        selectinload(FactLineupPlanItem.predecessor_product),
        selectinload(FactLineupPlanItem.successor_product),
    )
    if customer_id is not None:
        stmt = stmt.where(FactLineupPlanItem.customer_id == customer_id)
    if channel_id is not None:
        stmt = stmt.where(FactLineupPlanItem.channel_id == channel_id)
    if period_start is not None:
        stmt = stmt.where(FactLineupPlanItem.period_start == period_start)

    res = await db.execute(stmt.order_by(FactLineupPlanItem.period_start, FactLineupPlanItem.id))
    rows = res.scalars().unique().all()
    out: list[dict] = []
    for r in rows:
        cust: DimCustomer | None = r.customer
        ch: DimChannel | None = r.channel
        prod: DimProduct | None = r.product
        pred: DimProduct | None = r.predecessor_product
        succ: DimProduct | None = r.successor_product
        out.append(
            {
                "id": r.id,
                "customer_code": cust.code if cust else None,
                "customer_name": cust.name if cust else None,
                "channel_code": ch.code if ch else None,
                "period_start": r.period_start.isoformat(),
                "period_label": r.period_label,
                "sku": prod.sku if prod else None,
                "product_name": prod.name if prod else None,
                "predecessor_sku": pred.sku if pred else None,
                "successor_sku": succ.sku if succ else None,
                "current_range_summary": r.current_range_summary,
                "planned_range_summary": r.planned_range_summary,
                "planned_launch_date": r.planned_launch_date.isoformat() if r.planned_launch_date else None,
                "planned_eol_date": r.planned_eol_date.isoformat() if r.planned_eol_date else None,
                "current_volume_units": float(r.current_volume_units) if r.current_volume_units is not None else None,
                "planned_volume_units": float(r.planned_volume_units),
                "overlap_cannibalization_flag": r.overlap_cannibalization_flag,
                "whitespace_gap_flag": r.whitespace_gap_flag,
                "approval_status": r.approval_status,
                "link_buy_plan_id": r.link_buy_plan_id,
                "link_pricing_id": r.link_pricing_id,
                "link_promotion_id": r.link_promotion_id,
                "link_budget_request_id": r.link_budget_request_id,
                "link_roadmap_id": r.link_roadmap_id,
                "notes": r.notes,
            }
        )
    return out


@router.get("/items/{item_id}/events")
async def list_lineup_item_events(item_id: int, db: AsyncSession = Depends(get_db)):
    parent = await db.get(FactLineupPlanItem, item_id)
    if not parent:
        raise HTTPException(status_code=404, detail="Line-up item not found")
    res = await db.execute(
        select(LineupPlanItemEvent)
        .where(LineupPlanItemEvent.lineup_item_id == item_id)
        .order_by(LineupPlanItemEvent.created_at.desc())
    )
    rows = res.scalars().all()
    return [
        {
            "id": e.id,
            "event_type": e.event_type,
            "old_approval_status": e.old_approval_status,
            "new_approval_status": e.new_approval_status,
            "notes": e.notes,
            "actor": e.actor,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in rows
    ]


@router.post("/items/bulk", status_code=200)
async def bulk_import_lineup_items(body: LineupBulkBody, db: AsyncSession = Depends(get_db)):
    """Structured bulk upsert (CSV/XLSX should be parsed client-side or via imports pipeline into this JSON)."""
    payloads = [r.model_dump(mode="json") for r in body.rows]
    try:
        out = await bulk_upsert_lineup_items(db, payloads, replace_matching=body.replace_matching)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return out


@router.patch("/items/{item_id}")
async def patch_lineup_item(
    item_id: int,
    body: LineupItemPatch,
    db: AsyncSession = Depends(get_db),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    """Update approval workflow fields; logs an audit row when approval_status changes."""
    row = await db.get(FactLineupPlanItem, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    data = body.model_dump(exclude_unset=True)
    old_approval = row.approval_status
    approval_changed = False
    if "approval_status" in data:
        st = (data["approval_status"] or "").strip()
        if st not in _LINEUP_APPROVAL_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid approval_status; use one of: {', '.join(sorted(_LINEUP_APPROVAL_STATUSES))}",
            )
        if st != old_approval:
            approval_changed = True
        row.approval_status = st
    if "notes" in data:
        row.notes = (data["notes"] or "").strip() or None
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")
    if approval_changed:
        note_snap = data["notes"] if "notes" in data else None
        await record_lineup_approval_event(
            db,
            lineup_item_id=row.id,
            old_status=old_approval,
            new_status=row.approval_status,
            notes=note_snap,
            actor=x_user_id,
        )
    await db.commit()
    await db.refresh(row)
    return {
        "id": row.id,
        "approval_status": row.approval_status,
        "notes": row.notes,
    }


@router.delete("/items/{item_id}", status_code=204)
async def delete_lineup_item(item_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(FactLineupPlanItem, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        await db.delete(row)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Row is still referenced by other tables")
    return Response(status_code=204)


@router.post("/items/clear-all", status_code=200)
async def clear_lineup_items(body: ClearConfirmBody, db: AsyncSession = Depends(get_db)):
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Set confirm to true")
    try:
        res = await db.execute(delete(FactLineupPlanItem))
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Cannot clear: rows are still referenced by other tables. Delete dependent rows first.")
    return {"deleted": res.rowcount or 0}


@router.get("/net-requirement")
async def get_lineup_net_requirement(
    distributor_id: int | None = Query(default=None),
    product_id: int | None = Query(default=None),
    horizon_weeks: int = Query(default=13, ge=1, le=52),
    target_cover_weeks: float = Query(default=DEFAULT_TARGET_COVER_WEEKS, ge=0, le=52),
    include_customer_shares: bool = Query(default=True),
    limit: int = Query(default=200, ge=1, le=2000),
    db: AsyncSession = Depends(get_db),
):
    """B2-01 — net requirement at distributor × product (stock subtract at that grain).

    Customer shares are allocation hints only. Bias factor is 0 until B2-02 wires A1.
    """
    try:
        product_bu: dict[int, str] = {}
        prod_res = await db.execute(
            select(DimProduct.id, DimProduct.product_line, DimProduct.business_unit)
        )
        for pid, pl, bu in prod_res.all():
            label = (bu or pl or "").strip()
            if label:
                product_bu[int(pid)] = label

        return await build_net_requirement_rows(
            db,
            horizon_weeks=horizon_weeks,
            target_cover_weeks=target_cover_weeks,
            distributor_id=distributor_id,
            product_id=product_id,
            product_bu=product_bu,
            include_customer_shares=include_customer_shares,
            limit=limit,
        )
    except Exception:
        return {
            "data_unavailable": True,
            "row_count": 0,
            "rows": [],
            "message": "Net requirement read model unavailable",
        }
