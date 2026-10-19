"""Sell-through overview API (Warren 2026-10-19): the Stock & Sell-through tab.

Read-only. Periods follow the tenant business calendar; sales value follows the tenant VAT setting
unless the request asks for the other basis.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request

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
from app.services.channel_intelligence.sell_through_dimensions import (
    MAX_FILTERS,
    available_dimensions,
    resolve_dimension_filters,
)

router = APIRouter()

# Addable filters arrive as repeated ``f.<key>=<value>`` parameters, e.g. ``f.spec:RAM=16GB``.
_DIM_PREFIX = "f."


def _dimension_picks(request: Request) -> dict[str, list[str]]:
    return {
        k[len(_DIM_PREFIX) :]: [v for v in request.query_params.getlist(k) if v.strip()]
        for k in request.query_params.keys()
        if k.startswith(_DIM_PREFIX)
    }


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
        dims = available_dimensions(session, tenant_id)
    return {
        **opts,
        "dimensions": dims,
        "max_dimensions": MAX_FILTERS,
        "presets": period_presets(cal, today),
        "today": today.isoformat(),
        "calendar": {"type": cal.type, "year": cal.year(today).as_dict()},
        "vat": commercial_tenant_profile.sales_value_vat_basis(tenant_id),
        "vat_rate_pct": commercial_tenant_profile.vat_rate_pct(tenant_id),
    }


@router.get("/overview")
def get_overview_route(
    request: Request,
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
    return get_overview(
        date_from, date_to, grain, compare, vat, customer_ids, business_units, categories, series, product_ids, user,
        picks=_dimension_picks(request),
    )


@router.get("/narrative")
def get_narrative(
    request: Request,
    date_from: date = Query(...),
    date_to: date = Query(...),
    grain: str = Query(default="week"),
    compare: str = Query(default="prior_year"),
    vat: str | None = Query(default=None),
    customer_ids: str | None = Query(default=None),
    business_units: str | None = Query(default=None),
    categories: str | None = Query(default=None),
    series: str | None = Query(default=None),
    product_ids: str | None = Query(default=None),
    user: dict = Depends(get_current_user),
):
    """A short written summary of the same view: AI-worded when configured, otherwise the rules."""
    from app.services.channel_intelligence.sell_through_narrative import narrate

    overview = get_overview(
        date_from, date_to, grain, compare, vat, customer_ids, business_units, categories, series, product_ids, user,
        picks=_dimension_picks(request),
    )
    return narrate(overview, tenant_id=tenant_id_from_user(user))


def get_overview(
    date_from: date,
    date_to: date,
    grain: str,
    compare: str,
    vat: str | None,
    customer_ids: str | None,
    business_units: str | None,
    categories: str | None,
    series: str | None,
    product_ids: str | None,
    user: dict,
    *,
    picks: dict[str, list[str]] | None = None,
) -> dict:
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
    cust = _ints(customer_ids)
    prods = _ints(product_ids)
    sites: list[str] = []
    with SessionLocal() as session:
        if picks:
            try:
                dim_products, dim_customers, sites = resolve_dimension_filters(session, tenant_id, picks)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            if dim_products is not None:
                prods = sorted(set(prods) & dim_products) if prods else sorted(dim_products)
                prods = prods or [-1]  # nothing matches: show nothing, not everything
            if dim_customers is not None:
                cust = sorted(set(cust) & dim_customers) if cust else sorted(dim_customers)
                cust = cust or [-1]
        f = OverviewFilters(
            date_from=date_from,
            date_to=date_to,
            grain=grain,
            compare=compare,
            vat=vat_basis,
            customer_ids=cust,
            business_units=_strs(business_units),
            categories=_strs(categories),
            series=_strs(series),
            product_ids=prods,
            sites=sites,
            tenant_id=tenant_id,
        )
        return build_overview(
            session,
            f,
            tenant_calendar(tenant_id),
            today=commercial_tenant_profile.reporting_today(tenant_id),
            vat_rate=commercial_tenant_profile.vat_rate_pct(tenant_id),
        )


@router.get("/product/{product_id}")
def get_product_detail(
    product_id: int,
    as_of: date | None = Query(default=None),
    vat: str | None = Query(default=None),
    customer_ids: str | None = Query(default=None),
    user: dict = Depends(get_current_user),
):
    """One product across customers: weekly sales, stock with its date and stores, and prices."""
    from app.services.channel_intelligence.sell_through_product import product_detail

    tenant_id = tenant_id_from_user(user)
    vat_basis = vat or commercial_tenant_profile.sales_value_vat_basis(tenant_id)
    if vat_basis not in ("ex_vat", "inc_vat"):
        raise HTTPException(status_code=400, detail="vat must be ex_vat or inc_vat")
    with SessionLocal() as session:
        out = product_detail(
            session,
            tenant_id=tenant_id,
            product_id=product_id,
            as_of=as_of or commercial_tenant_profile.reporting_today(tenant_id),
            vat=vat_basis,
            vat_rate=commercial_tenant_profile.vat_rate_pct(tenant_id),
            customer_ids=_ints(customer_ids) or None,
        )
    if out is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return out
