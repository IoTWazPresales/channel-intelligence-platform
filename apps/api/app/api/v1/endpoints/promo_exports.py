from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter()

# Old promotion-plan exports were dropped with dim_promotion. Export the case instead.
_CPOR_EXPORT = {
    "message": "Promotion exports are case exports. Open the case and export it from there.",
    "href": "/commercial-planner/cpor-cases",
    "export_href": "/api/v1/cpor/cases/{case_id}/export",
}


def _parked_dim_promotion() -> None:
    raise HTTPException(status_code=409, detail=_CPOR_EXPORT)


class RejectBody(BaseModel):
    comment: str = Field(min_length=1)


@router.post("/{promotion_id}/exports/validate")
async def validate_export(
    promotion_id: int,
    customer_id: int | None = Query(default=None),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    _ = (promotion_id, customer_id, x_user_id)
    _parked_dim_promotion()


@router.post("/{promotion_id}/exports")
async def create_export(
    promotion_id: int,
    customer_id: int | None = Query(default=None),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    _ = (promotion_id, customer_id, x_user_id)
    _parked_dim_promotion()


@router.get("/{promotion_id}/exports")
async def list_exports(promotion_id: int):
    _ = promotion_id
    _parked_dim_promotion()


@router.get("/exports/{export_id}/file")
async def download_export(export_id: int):
    _ = export_id
    _parked_dim_promotion()


@router.get("/exports/{export_id}/events")
async def list_export_events(export_id: int):
    _ = export_id
    _parked_dim_promotion()


@router.post("/exports/{export_id}/submit")
async def submit_export(export_id: int, x_user_id: str | None = Header(default=None, alias="X-User-Id")):
    _ = (export_id, x_user_id)
    _parked_dim_promotion()


@router.post("/exports/{export_id}/approve")
async def approve_export(export_id: int, x_user_id: str | None = Header(default=None, alias="X-User-Id")):
    _ = (export_id, x_user_id)
    _parked_dim_promotion()


@router.post("/exports/{export_id}/reject")
async def reject_export(export_id: int, body: RejectBody, x_user_id: str | None = Header(default=None, alias="X-User-Id")):
    _ = (export_id, body, x_user_id)
    _parked_dim_promotion()


@router.post("/exports/{export_id}/resend")
async def resend_export(export_id: int, x_user_id: str | None = Header(default=None, alias="X-User-Id")):
    _ = (export_id, x_user_id)
    _parked_dim_promotion()
