"""Sell-through overview API (Warren 2026-10-19): the Stock & Sell-through tab.

Read-only. Periods follow the tenant business calendar; sales value follows the tenant VAT setting
unless the request asks for the other basis.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import get_current_user
from app.core.tenant_scope import tenant_id_from_user
from app.db.session_sync import SessionLocal
from app.services import commercial_tenant_profile
from app.services.business_calendar import tenant_calendar
from app.services.channel_intelligence.sell_through_overview import (
    COMPARES,
    GRAINS,
    OverviewFilters,
    build_overview,
    filter_options,
    period_presets,
)

router = APIRouter()


def _ints(raw: str | None) -> list[int]:
    out: list[int] = []
    for part in (raw or "").split(","):
        part = part.strip()
        if part:
            try:
                out.append(int(part))
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=f"not a number: {part}") from exc
    return out


def _strs(raw: str | None) -> list[str]:
    return [p.strip() for p in (raw or "").split("|") if p.strip()]


@router.get("/filters")
def get_filters(user: dict = Depends(get_current_user)):
    tenant_id = tenant_id_from_user(user)
    cal = tenant_calendar(tenant_id)
    today = commercial_tenant_profile.reporting_today(tenant_id)
    with SessionLocal() as session:
        opts = filter_options(session, tenant_id)
    return {
        **opts,
        "presets": period_presets(cal, today),
        "today": today.isoformat(),
        "calendar": {"type": cal.type, "year": cal.year(today).as_dict()},
        "vat": commercial_tenant_profile.sales_value_vat_basis(tenant_id),
        "vat_rate_pct": commercial_tenant_profile.vat_rate_pct(tenant_id),
    }


@router.get("/overview")
def get_overview(
    date_from: date = Query(...),
    date_to: date = Query(...),
    grain: str = Query(default="week"),
    compare: str = Query(default="prior_year"),
    vat: str | None = Query(default=None, description="ex_vat or inc_vat; default from Settings"),
    customer_ids: str | None = Query(default=None, description="comma-separated customer ids"),
    business_units: str | None = Query(default=None, description="|-separated"),
    categories: str | None = Query(default=None, description="|-separated"),
    series: str | None = Query(default=None, description="|-separated"),
    product_ids: str | None = Query(default=None, description="comma-separated product ids"),
    user: dict = Depends(get_current_user),
):
    if grain not in GRAINS:
        raise HTTPException(status_code=400, detail=f"grain must be one of {list(GRAINS)}")
    if compare not in COMPARES:
        raise HTTPException(status_code=400, detail=f"compare must be one of {list(COMPARES)}")
    if date_to < date_from:
        raise HTTPException(status_code=400, detail="date_to is before date_from")
    if (date_to - date_from).days > 3 * 366:
        raise HTTPException(status_code=400, detail="choose a window of three years or less")
    if grain == "day" and (date_to - date_from).days > 120:
        raise HTTPException(status_code=400, detail="show by week or month for windows longer than 120 days")
    tenant_id = tenant_id_from_user(user)
    vat_basis = vat or commercial_tenant_profile.sales_value_vat_basis(tenant_id)
    if vat_basis not in ("ex_vat", "inc_vat"):
        raise HTTPException(status_code=400, detail="vat must be ex_vat or inc_vat")
    f = OverviewFilters(
        date_from=date_from,
        date_to=date_to,
        grain=grain,
        compare=compare,
        vat=vat_basis,
        customer_ids=_ints(customer_ids),
        business_units=_strs(business_units),
        categories=_strs(categories),
        series=_strs(series),
        product_ids=_ints(product_ids),
        tenant_id=tenant_id,
    )
    with SessionLocal() as session:
        return build_overview(
            session,
            f,
            tenant_calendar(tenant_id),
            today=commercial_tenant_profile.reporting_today(tenant_id),
            vat_rate=commercial_tenant_profile.vat_rate_pct(tenant_id),
        )
