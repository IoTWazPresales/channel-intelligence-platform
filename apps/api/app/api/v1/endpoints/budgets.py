from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.product_line_scope import request_editable_product_lines
from app.core.security import Role, require_roles
from app.models.dimensions import DimBudgetOwner
from app.models.derived import BudgetHealth
from app.models.facts import FactBudgetAllocation, FactBudgetRequest

router = APIRouter()


@router.get("/ledger")
async def budget_ledger_position(
    view: str = "campaign",
    grain: str = "line",
    db: AsyncSession = Depends(get_db),
):
    """Product line by quarter, or the same rows summed by customer and quarter."""
    from app.services.budget_ledger import customer_position_rows, position_rows

    chosen = view if view in {"campaign", "non_campaign"} else "campaign"
    chosen_grain = grain if grain in {"line", "customer"} else "line"
    try:
        if chosen_grain == "customer":
            rows = await db.run_sync(
                lambda sync, selected=chosen: customer_position_rows(sync, view=selected)
            )
        else:
            rows = await db.run_sync(lambda sync, selected=chosen: position_rows(sync, view=selected))
    except Exception:
        return {
            "data_unavailable": True,
            "items": [],
            "portfolio_cap_usd": None,
            "view": chosen,
            "grain": chosen_grain,
        }
    from app.services.cpor.budget_reapproval import money_ceiling_usd

    return {
        "data_unavailable": False,
        "items": rows,
        "portfolio_cap_usd": money_ceiling_usd(),
        "view": chosen,
        "grain": chosen_grain,
    }


@router.get("/ledger/entries")
async def budget_ledger_entries(
    product_line: str = "",
    landed_quarter: str = "",
    view: str = "campaign",
    grain: str = "line",
    customer_id: str = "",
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import or_, select

    from app.models.budget_ledger import BudgetLedgerEntry

    chosen = view if view in {"campaign", "non_campaign"} else "campaign"
    chosen_grain = grain if grain in {"line", "customer"} else "line"
    stmt = select(BudgetLedgerEntry).order_by(BudgetLedgerEntry.id.desc()).limit(500)
    stmt = stmt.where(BudgetLedgerEntry.landed_quarter == landed_quarter)
    if chosen_grain == "customer":
        raw_customer = customer_id.strip()
        if raw_customer == "":
            stmt = stmt.where(BudgetLedgerEntry.customer_id.is_(None))
        else:
            try:
                stmt = stmt.where(BudgetLedgerEntry.customer_id == int(raw_customer))
            except ValueError:
                return {"data_unavailable": False, "items": []}
        stmt = stmt.where(BudgetLedgerEntry.entry_type != "cap")
    else:
        stmt = stmt.where(BudgetLedgerEntry.product_line == product_line)
    if chosen == "non_campaign":
        stmt = stmt.where(BudgetLedgerEntry.source_tag == "non_campaign")
    else:
        stmt = stmt.where(
            or_(BudgetLedgerEntry.source_tag.is_(None), BudgetLedgerEntry.source_tag != "non_campaign")
        )
    try:
        rows = (await db.scalars(stmt)).all()
    except Exception:
        return {"data_unavailable": True, "items": []}
    return {
        "data_unavailable": False,
        "items": [
            {
                "id": int(row.id),
                "entry_type": row.entry_type,
                "product_line": row.product_line,
                "landed_quarter": row.landed_quarter,
                "amount_usd": float(row.amount_usd) if row.amount_usd is not None else None,
                "case_id": row.case_id,
                "case_line_id": row.case_line_id,
                "source_tag": row.source_tag,
                "created_at": row.created_at.isoformat() if row.created_at is not None else None,
            }
            for row in rows
        ],
    }


class TransferBody(BaseModel):
    source_product_line: str = ""
    source_landed_quarter: str = ""
    dest_product_line: str = ""
    dest_landed_quarter: str = ""
    amount_usd: float
    confirm_over: bool = False


def _may_transfer_line(product_line: str) -> bool:
    """Admin edits every line. A planner needs can_edit on the named line."""
    editable = request_editable_product_lines.get()
    if not editable:
        return False
    if "*" in editable:
        return True
    line = (product_line or "").strip()
    return bool(line) and line in editable


@router.post("/ledger/transfer")
async def transfer_budget(
    body: TransferBody,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles(Role.PLANNER, Role.ADMIN)),
):
    """Move campaign headroom. Two append-only rows, one out and one in."""
    if not _may_transfer_line(body.source_product_line) or not _may_transfer_line(body.dest_product_line):
        raise HTTPException(
            status_code=403,
            detail="A transfer needs edit access on both product lines.",
        )
    from app.services.budget_ledger import apply_budget_transfer

    actor = user.get("display_name") or user.get("email") or user.get("id")
    try:
        result = await db.run_sync(
            lambda sync: apply_budget_transfer(
                sync,
                source_product_line=body.source_product_line,
                source_landed_quarter=body.source_landed_quarter,
                dest_product_line=body.dest_product_line,
                dest_landed_quarter=body.dest_landed_quarter,
                amount_usd=body.amount_usd,
                actor=str(actor) if actor else None,
                confirm_over=body.confirm_over,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if result.get("needs_confirm"):
        raise HTTPException(
            status_code=409,
            detail=(
                f"This move is more than remaining ({result['source_remaining']}). "
                "Confirm to move it anyway."
            ),
        )
    await db.commit()
    return {
        "written": result["written"],
        "source_event_id": result["entries"][0]["source_event_id"] if result["entries"] else None,
        "over_remaining": result["over_remaining"],
        "source_remaining": result["source_remaining"],
    }


class CapBody(BaseModel):
    product_line: str = ""
    landed_quarter: str = ""
    amount_usd: float | None = None


@router.post("/ledger/cap")
async def set_budget_cap(
    body: CapBody,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_roles(Role.ADMIN)),
):
    """Append a cap for one product line and quarter. Null clears it. Never blocks spend."""
    from app.services.budget_ledger import apply_line_cap

    actor = user.get("display_name") or user.get("email") or user.get("id")
    try:
        result = await db.run_sync(
            lambda sync: apply_line_cap(
                sync,
                product_line=body.product_line,
                landed_quarter=body.landed_quarter,
                amount_usd=body.amount_usd,
                actor=str(actor) if actor else None,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return result


def _refuse_budget_delete():
    raise HTTPException(
        status_code=409,
        detail="Budget rows are not deleted. The ledger is append-only; a correction is a reversing row.",
    )


class ClearConfirmBody(BaseModel):
    confirm: bool = False


@router.get("/allocations")
async def allocations(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(FactBudgetAllocation))
    rows = res.scalars().all()
    out = []
    for a in rows:
        owner = await db.get(DimBudgetOwner, a.owner_id)
        out.append(
            {
                "id": a.id,
                "owner": owner.name if owner else None,
                "category": a.category,
                "period_start": a.period_start.isoformat(),
                "envelope_type": a.envelope_type,
                "allocated_amount": float(a.allocated_amount),
            }
        )
    return out


@router.get("/requests")
async def requests(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(FactBudgetRequest))
    rows = res.scalars().all()
    out = []
    for r in rows:
        owner = await db.get(DimBudgetOwner, r.owner_id)
        out.append(
            {
                "id": r.id,
                "owner": owner.name if owner else None,
                "amount": float(r.amount),
                "initiative_type": r.initiative_type,
                "status": r.status,
                "justification_summary": r.justification_summary,
                "expected_impact": r.expected_impact,
                "risk_of_not_funding": r.risk_of_not_funding,
            }
        )
    return out


@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(BudgetHealth))
    rows = res.scalars().all()
    out = []
    for h in rows:
        owner = await db.get(DimBudgetOwner, h.owner_id)
        out.append(
            {
                "id": h.id,
                "owner": owner.name if owner else None,
                "remaining_amount": float(h.remaining_amount),
                "pressure_state": h.pressure_state,
                "period_start": h.period_start.isoformat(),
            }
        )
    return out


@router.delete("/allocations/{row_id}", status_code=204)
async def delete_allocation(row_id: int, db: AsyncSession = Depends(get_db)):
    _refuse_budget_delete()
    row = await db.get(FactBudgetAllocation, row_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        await db.delete(row)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Row is still referenced by other tables")
    return Response(status_code=204)


@router.post("/allocations/clear-all", status_code=200)
async def clear_allocations(body: ClearConfirmBody, db: AsyncSession = Depends(get_db)):
    _refuse_budget_delete()
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Set confirm to true")
    try:
        res = await db.execute(delete(FactBudgetAllocation))
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Cannot clear: rows are still referenced by other tables. Delete dependent rows first.")
    return {"deleted": res.rowcount or 0}


@router.delete("/requests/{row_id}", status_code=204)
async def delete_budget_request(row_id: int, db: AsyncSession = Depends(get_db)):
    _refuse_budget_delete()
    row = await db.get(FactBudgetRequest, row_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        await db.delete(row)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Row is still referenced by other tables")
    return Response(status_code=204)


@router.post("/requests/clear-all", status_code=200)
async def clear_budget_requests(body: ClearConfirmBody, db: AsyncSession = Depends(get_db)):
    _refuse_budget_delete()
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Set confirm to true")
    try:
        res = await db.execute(delete(FactBudgetRequest))
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Cannot clear: rows are still referenced by other tables. Delete dependent rows first.")
    return {"deleted": res.rowcount or 0}


@router.delete("/health/{row_id}", status_code=204)
async def delete_budget_health(row_id: int, db: AsyncSession = Depends(get_db)):
    _refuse_budget_delete()
    row = await db.get(BudgetHealth, row_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        await db.delete(row)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Row is still referenced by other tables")
    return Response(status_code=204)


@router.post("/health/clear-all", status_code=200)
async def clear_budget_health(body: ClearConfirmBody, db: AsyncSession = Depends(get_db)):
    _refuse_budget_delete()
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Set confirm to true")
    try:
        res = await db.execute(delete(BudgetHealth))
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Cannot clear: rows are still referenced by other tables. Delete dependent rows first.")
    return {"deleted": res.rowcount or 0}
