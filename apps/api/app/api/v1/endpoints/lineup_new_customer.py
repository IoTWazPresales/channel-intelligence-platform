"""Final wave (a): propose and approve a new customer's line-up from database SKUs.

Registered by the coordinator, mounted under the line-up prefix, so the paths are
``GET  /lineup/new-customer/{customer_id}/proposal?source=...&period_start=...`` and
``POST /lineup/new-customer/{customer_id}/approve``.

Access is sign-in only, the same as the existing line-up approval (role check pending: BACKLOG-251).
The rules live in ``app.services.lineup.new_customer_proposal``.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.services.lineup.audit import record_lineup_approval_event
from app.services.lineup.new_customer_proposal import (
    ProposalError,
    build_proposal,
    list_reporting_customers,
    write_new_customer_lineup,
)

router = APIRouter()


class NewCustomerApproveBody(BaseModel):
    source: str = Field(description="pm_bottom_cost or previous_lineups")
    period_start: date
    product_ids: list[int] = Field(
        min_length=1, max_length=2000, description="The lines left ticked."
    )


def _http(err: ProposalError) -> HTTPException:
    return HTTPException(
        status_code=err.status_code, detail={"code": err.code, "message": err.message}
    )


@router.get("/new-customer/reporting-customers")
async def get_new_customer_reporting_customers(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Customers that can be given a new line-up (reports expected)."""
    return {"customers": await db.run_sync(lambda sync: list_reporting_customers(sync))}


@router.get("/new-customer/{customer_id}/proposal")
async def get_new_customer_proposal(
    customer_id: int,
    source: str = Query(description="pm_bottom_cost or previous_lineups"),
    period_start: date = Query(),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Proposed lines for a reporting customer that has no line-up rows yet for the period."""
    try:
        return await db.run_sync(
            lambda sync: build_proposal(
                sync, customer_id=customer_id, source=source, period_start=period_start
            )
        )
    except ProposalError as err:
        raise _http(err) from err


@router.post("/new-customer/{customer_id}/approve")
async def approve_new_customer_lineup(
    customer_id: int,
    body: NewCustomerApproveBody,
    db: AsyncSession = Depends(get_db),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> dict[str, Any]:
    """Create the ticked lines as the customer's line-up and approve them, in one transaction."""
    try:
        result = await db.run_sync(
            lambda sync: write_new_customer_lineup(
                sync,
                customer_id=customer_id,
                source=body.source,
                period_start=body.period_start,
                product_ids=body.product_ids,
                actor=x_user_id,
            )
        )
        for item in result["created"]:
            await record_lineup_approval_event(
                db,
                lineup_item_id=item["item_id"],
                old_status="draft",
                new_status="approved",
                notes=f"New-customer proposal ({body.source}) approved on screen.",
                actor=x_user_id,
            )
        await db.commit()
    except ProposalError as err:
        await db.rollback()
        raise _http(err) from err
    except Exception:
        await db.rollback()
        raise
    return {**result, "approved_count": len(result["created"])}
