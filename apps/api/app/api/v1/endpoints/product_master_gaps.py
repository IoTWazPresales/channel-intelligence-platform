"""Product Master gap worklist + BACKLOG-072 scan/preview/confirm-apply."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.db.session_sync import SessionLocal
from app.services.imports.product_master_gap_resolve import (
    apply_gap_resolve,
    preview_gap_resolve,
    scan_open_gaps_for_matches,
)
from app.services.imports.product_master_gap_worklist import product_master_gap_worklist

router = APIRouter()


class TokensBody(BaseModel):
    tokens: list[str] = Field(min_length=1, max_length=500)


class ApplyBody(BaseModel):
    tokens: list[str] = Field(min_length=1, max_length=500)
    confirm: bool = False
    write_alias: bool = True


def _actor(x_user_id: str | None) -> str:
    return (x_user_id or "demo-user").strip() or "demo-user"


@router.get("/worklist")
async def get_product_master_gap_worklist(
    db: AsyncSession = Depends(get_db),
    source: Literal["shipment", "dsi", "cpor_claim", "cst"] | None = Query(default=None),
    status: Literal["unresolved", "ignored"] | None = Query(default=None),
    search: str | None = Query(default=None, max_length=128),
    limit: int = Query(default=2000, ge=1, le=5000),
):
    """Derived-on-read aggregation of product tokens that failed PM resolution."""
    return await product_master_gap_worklist(
        db,
        source=source,
        status=status,
        search=search,
        limit=limit,
    )


@router.post("/scan")
def post_gap_scan(limit: int = Query(default=500, ge=1, le=2000)):
    """On-demand: find open gap tokens that now exact-match Product Master."""
    with SessionLocal() as session:
        try:
            return scan_open_gaps_for_matches(session, limit=limit)
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail={"message": "gap scan unavailable", "data_unavailable": True, "error": str(exc)},
            ) from exc


@router.post("/preview")
def post_gap_preview(body: TokensBody):
    """Read-only preview: match + counts by source. No writes."""
    with SessionLocal() as session:
        try:
            return preview_gap_resolve(session, body.tokens)
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail={"message": "gap preview unavailable", "data_unavailable": True, "error": str(exc)},
            ) from exc


@router.post("/apply")
def post_gap_apply(
    body: ApplyBody,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    """Steward-confirmed set-based repoint. Requires confirm=true."""
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Set confirm=true to apply")
    with SessionLocal() as session:
        try:
            result = apply_gap_resolve(
                session,
                tokens=body.tokens,
                confirm=True,
                write_alias=body.write_alias,
                actor=_actor(x_user_id),
            )
            session.commit()
            return result
        except Exception as exc:
            session.rollback()
            raise HTTPException(
                status_code=503,
                detail={"message": "gap apply unavailable", "error": str(exc)},
            ) from exc
