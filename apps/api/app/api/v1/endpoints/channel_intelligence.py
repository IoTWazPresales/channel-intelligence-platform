"""Channel intelligence API — CST velocity / WoC / aged stock (CPOR U4.6)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import get_optional_current_user
from app.core.tenant_scope import tenant_id_from_user
from app.db.session_sync import SessionLocal
from app.services.channel_intelligence.cst_read_model import (
    DEFAULT_AGED_LOOKBACK_WEEKS,
    DEFAULT_MIN_OBSERVED_WEEKS,
    load_cst_read_model,
)

router = APIRouter()


@router.get("")
def get_channel_intelligence(
    customer_id: int | None = Query(default=None),
    product_id: int | None = Query(default=None),
    site_label: str | None = Query(default=None, max_length=256),
    as_of: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    min_observed_weeks: int = Query(default=DEFAULT_MIN_OBSERVED_WEEKS, ge=1, le=52),
    aged_lookback_weeks: int = Query(default=DEFAULT_AGED_LOOKBACK_WEEKS, ge=1, le=52),
    user: dict | None = Depends(get_optional_current_user),
):
    """Read-only CST channel intelligence. FLAG≠BLOCK; no writes."""
    try:
        with SessionLocal() as session:
            return load_cst_read_model(
                session,
                customer_id=customer_id,
                product_id=product_id,
                site_label=site_label,
                as_of=as_of,
                page=page,
                page_size=page_size,
                min_observed_weeks=min_observed_weeks,
                aged_lookback_weeks=aged_lookback_weeks,
                tenant_id=tenant_id_from_user(user),
            )
    except Exception as exc:  # pragma: no cover — defensive empty-state
        raise HTTPException(
            status_code=503,
            detail={"message": "channel intelligence unavailable", "data_unavailable": True, "error": str(exc)},
        ) from exc
