"""Commercial read APIs for inbound shipment facts (truth layer)."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Date as SA_Date, cast, desc, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.inspection import inspect as sa_inspect
from sqlalchemy.orm import InstrumentedAttribute

from app.api.deps import get_db
from app.models.dimensions import DimCustomer, DimDistributor, DimProduct
from app.models.facts import FactInboundShipment
from app.models.shipment_evidence_observation import ShipmentEvidenceObservation
from app.services.commercial_planner.inbound_lineup_quarter import (
    available_plan_periods,
    enrich_fact_lineup_fields,
    lineup_quarter_summary,
    load_attribution_context,
    normalize_plan_quarter_filter,
    po_ids_for_plan_quarter,
    row_matches_lineup_filters,
)
from app.services.commercial_planner.lineup_period_canonical import parse_period_filter_to_year_quarter

router = APIRouter()

# Fact columns already shown as dedicated default grid cells (not offered as toggles).
INBOUND_GRID_DEFAULT_FACT_KEYS: frozenset[str] = frozenset(
    {
        "line_state",
        "status",
        "eta_date",
        "promise_date",
        "pod_date",
        "sales_model_name",
        "item_code",
        "bill_to_raw",
        "ship_to_raw",
    }
)

DATE_FIELD_MAP: dict[str, InstrumentedAttribute[Any]] = {
    "eta_date": FactInboundShipment.eta_date,
    "promise_date": FactInboundShipment.promise_date,
    "pod_date": FactInboundShipment.pod_date,
    "ship_confirm_date": FactInboundShipment.ship_confirm_date,
    "schedule_ship_date": FactInboundShipment.schedule_ship_date,
    "exwork_date": FactInboundShipment.exwork_date,
    "erd_date": FactInboundShipment.erd_date,
    "est_pod_date": FactInboundShipment.est_pod_date,
    "created_at": FactInboundShipment.created_at,
    "updated_at": FactInboundShipment.updated_at,
}

DATETIME_RANGE_KEYS: frozenset[str] = frozenset({"created_at", "updated_at"})

# Human labels for optional columns (import / steward semantics).
INBOUND_OPTIONAL_LABEL_OVERRIDES: dict[str, str] = {
    "customer_dealer_token": "Customer remarks (source)",
}


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


def _iso_week_bounds(d: date) -> tuple[date, date]:
    weekday = d.weekday()  # Monday = 0
    mon = d - timedelta(days=weekday)
    sun = mon + timedelta(days=6)
    return mon, sun


def _parse_opt_date(raw: str | None) -> date | None:
    if raw is None or not str(raw).strip():
        return None
    try:
        return date.fromisoformat(str(raw).strip()[:10])
    except ValueError:
        return None


def _human_column_label(key: str) -> str:
    return re.sub(r"_+", " ", key).strip().title()


def _distributor_display(
    row: FactInboundShipment,
    distributor_name: str | None,
    distributor_code: str | None,
) -> str:
    dn = (distributor_name or "").strip()
    dc = (distributor_code or "").strip()
    if dn:
        return dn
    if dc and not dc.upper().startswith("TMP-DIST"):
        return dc
    br = (row.bill_to_raw or "").strip()
    if br:
        return br[:240]
    sr = (row.ship_to_raw or "").strip()
    if sr:
        return sr[:240]
    tok = (row.distributor_resolution_token or "").strip()
    if tok:
        return tok[:240]
    return dc or "—"


def _dim_join_flags(kwargs: dict[str, Any]) -> tuple[bool, bool, bool]:
    search = (kwargs.get("search") or "").strip()
    pf = (kwargs.get("product_family") or "").strip()
    pm = (kwargs.get("product_model") or "").strip()
    need_product = bool(search or pf or pm)
    need_distributor = bool(search)
    need_customer = bool(search)
    return need_distributor, need_product, need_customer


def _apply_outer_joins(stmt: Any, need_dist: bool, need_product: bool, need_customer: bool) -> Any:
    if need_dist:
        stmt = stmt.outerjoin(DimDistributor, FactInboundShipment.distributor_id == DimDistributor.id)
    if need_product:
        stmt = stmt.outerjoin(DimProduct, FactInboundShipment.product_id == DimProduct.id)
    if need_customer:
        stmt = stmt.outerjoin(DimCustomer, FactInboundShipment.customer_id == DimCustomer.id)
    return stmt


def _apply_fact_where_clause(
    stmt: Any,
    *,
    join_distributor: bool,
    join_product: bool,
    join_customer: bool,
    **kwargs: Any,
) -> Any:
    import_job_id = kwargs.get("import_job_id")
    distributor_id = kwargs.get("distributor_id")
    customer_id = kwargs.get("customer_id")
    purchase_order_id = kwargs.get("purchase_order_id")
    line_state = kwargs.get("line_state")
    report_type = kwargs.get("report_type")
    product_resolution_status = kwargs.get("product_resolution_status")
    distributor_resolution_status = kwargs.get("distributor_resolution_status")
    customer_resolution_status = kwargs.get("customer_resolution_status")
    status_v = kwargs.get("status")
    search = kwargs.get("search")
    date_field = kwargs.get("date_field") or "eta_date"
    date_from = kwargs.get("date_from")
    date_to = kwargs.get("date_to")
    eta_from = kwargs.get("eta_from")
    eta_to = kwargs.get("eta_to")
    pod_date_is_null = kwargs.get("pod_date_is_null")
    currency_code = kwargs.get("currency_code")
    operating_unit = kwargs.get("operating_unit")
    product_family = kwargs.get("product_family")
    product_model = kwargs.get("product_model")

    if import_job_id is not None:
        stmt = stmt.where(FactInboundShipment.import_job_id == import_job_id)
    if distributor_id is not None:
        stmt = stmt.where(FactInboundShipment.distributor_id == int(distributor_id))
    if customer_id is not None:
        stmt = stmt.where(FactInboundShipment.customer_id == int(customer_id))
    if purchase_order_id is not None:
        stmt = stmt.where(FactInboundShipment.purchase_order_id == int(purchase_order_id))
    if line_state:
        stmt = stmt.where(FactInboundShipment.line_state == line_state)
    if report_type:
        stmt = stmt.where(FactInboundShipment.report_type == report_type)
    if product_resolution_status:
        stmt = stmt.where(FactInboundShipment.product_resolution_status == product_resolution_status)
    if distributor_resolution_status:
        stmt = stmt.where(FactInboundShipment.distributor_resolution_status == distributor_resolution_status)
    if customer_resolution_status:
        stmt = stmt.where(FactInboundShipment.customer_resolution_status == customer_resolution_status)
    if status_v:
        stmt = stmt.where(FactInboundShipment.status == status_v)

    if pod_date_is_null is True:
        stmt = stmt.where(FactInboundShipment.pod_date.is_(None))
    elif pod_date_is_null is False:
        stmt = stmt.where(FactInboundShipment.pod_date.is_not(None))

    if currency_code and str(currency_code).strip():
        cc = str(currency_code).strip()
        stmt = stmt.where(FactInboundShipment.currency_code.is_not(None))
        stmt = stmt.where(FactInboundShipment.currency_code.ilike(cc))

    if operating_unit and str(operating_unit).strip():
        ou = f"%{str(operating_unit).strip()}%"
        stmt = stmt.where(FactInboundShipment.operating_unit.ilike(ou))

    d0 = date_from
    d1 = date_to
    field_key = str(date_field).strip() if date_field else "eta_date"
    if field_key not in DATE_FIELD_MAP:
        field_key = "eta_date"
    if d0 is None and d1 is None and (eta_from is not None or eta_to is not None):
        field_key = "eta_date"
        d0 = eta_from
        d1 = eta_to

    if d0 is not None or d1 is not None:
        raw_col = DATE_FIELD_MAP[field_key]
        col: Any = cast(raw_col, SA_Date) if field_key in DATETIME_RANGE_KEYS else raw_col
        if d0 is not None:
            stmt = stmt.where(col >= d0)
        if d1 is not None:
            stmt = stmt.where(col <= d1)

    if join_product and product_family and str(product_family).strip():
        pf = f"%{str(product_family).strip()}%"
        stmt = stmt.where(
            or_(
                DimProduct.category.ilike(pf),
                DimProduct.product_line.ilike(pf),
                DimProduct.series_name.ilike(pf),
            )
        )

    if product_model and str(product_model).strip():
        pm = f"%{str(product_model).strip()}%"
        parts = [
            FactInboundShipment.sales_model_name.ilike(pm),
            FactInboundShipment.item_code.ilike(pm),
        ]
        if join_product:
            parts.extend(
                [
                    DimProduct.model_name.ilike(pm),
                    DimProduct.marketing_name.ilike(pm),
                    DimProduct.sales_model_name.ilike(pm),
                    DimProduct.part_number.ilike(pm),
                    DimProduct.sku.ilike(pm),
                ]
            )
        stmt = stmt.where(or_(*parts))

    if search and str(search).strip():
        term = f"%{str(search).strip()}%"
        parts: list[Any] = [
            FactInboundShipment.bill_to_raw.ilike(term),
            FactInboundShipment.ship_to_raw.ilike(term),
            FactInboundShipment.customer_dealer_token.ilike(term),
            FactInboundShipment.item_code.ilike(term),
            FactInboundShipment.sales_model_name.ilike(term),
            FactInboundShipment.order_no.ilike(term),
            FactInboundShipment.customer_po.ilike(term),
            FactInboundShipment.delivery_no.ilike(term),
        ]
        if join_distributor:
            parts.extend(
                [
                    DimDistributor.name.ilike(term),
                    DimDistributor.code.ilike(term),
                ]
            )
        if join_product:
            parts.extend(
                [
                    DimProduct.name.ilike(term),
                    DimProduct.sku.ilike(term),
                    DimProduct.sales_model_name.ilike(term),
                    DimProduct.part_number.ilike(term),
                ]
            )
        if join_customer:
            parts.extend(
                [
                    DimCustomer.name.ilike(term),
                    DimCustomer.code.ilike(term),
                ]
            )
        stmt = stmt.where(or_(*parts))

    return stmt


def _build_shipping_fact_filters(
    *,
    import_job_id: int | None = None,
    distributor_id: int | None = None,
    customer_id: int | None = None,
    purchase_order_id: int | None = None,
    line_state: str | None = None,
    report_type: str | None = None,
    product_resolution_status: str | None = None,
    distributor_resolution_status: str | None = None,
    customer_resolution_status: str | None = None,
    status: str | None = None,
    search: str | None = None,
    eta_from: str | None = None,
    eta_to: str | None = None,
    date_field: str = "eta_date",
    date_from: str | None = None,
    date_to: str | None = None,
    pod_date_is_null: bool | None = None,
    currency_code: str | None = None,
    operating_unit: str | None = None,
    product_family: str | None = None,
    product_model: str | None = None,
) -> dict[str, Any]:
    """Shared filter kwargs for ``/lines`` and ``/commercial-summary`` (must stay aligned)."""
    df = str(date_field or "eta_date").strip()
    if df not in DATE_FIELD_MAP:
        df = "eta_date"
    return {
        "import_job_id": import_job_id,
        "distributor_id": distributor_id,
        "customer_id": customer_id,
        "purchase_order_id": purchase_order_id,
        "line_state": line_state,
        "report_type": report_type,
        "product_resolution_status": product_resolution_status,
        "distributor_resolution_status": distributor_resolution_status,
        "customer_resolution_status": customer_resolution_status,
        "status": status,
        "search": search,
        "eta_from": _parse_opt_date(eta_from),
        "eta_to": _parse_opt_date(eta_to),
        "date_field": df,
        "date_from": _parse_opt_date(date_from),
        "date_to": _parse_opt_date(date_to),
        "pod_date_is_null": pod_date_is_null,
        "currency_code": currency_code,
        "operating_unit": operating_unit,
        "product_family": product_family,
        "product_model": product_model,
    }


def _shipping_filters_active(filt: dict[str, Any]) -> bool:
    if filt.get("import_job_id") is not None:
        return True
    if filt.get("distributor_id") is not None:
        return True
    if filt.get("customer_id") is not None:
        return True
    if filt.get("purchase_order_id") is not None:
        return True
    for key in (
        "line_state",
        "report_type",
        "product_resolution_status",
        "distributor_resolution_status",
        "customer_resolution_status",
        "status",
        "search",
        "currency_code",
        "operating_unit",
        "product_family",
        "product_model",
    ):
        if (filt.get(key) or "").strip():
            return True
    if filt.get("eta_from") is not None or filt.get("eta_to") is not None:
        return True
    if filt.get("date_from") is not None or filt.get("date_to") is not None:
        return True
    if filt.get("pod_date_is_null") is not None:
        return True
    for key in ("plan_quarter", "plan_quarter_label", "plan_business_unit", "lineup_attribution", "lifecycle_bucket", "slip_direction"):
        if (filt.get(key) or "").strip():
            return True
    return False


def _lineup_filters_active(filt: dict[str, Any]) -> bool:
    for key in (
        "plan_quarter",
        "plan_quarter_label",
        "plan_business_unit",
        "lineup_attribution",
        "lifecycle_bucket",
        "slip_direction",
    ):
        if (filt.get(key) or "").strip():
            return True
    return False


async def _count_shipment_facts(db: AsyncSession, filt: dict[str, Any], *extra_where: Any) -> int:
    need_dist, need_prod, need_cust = _dim_join_flags(filt)
    stmt = select(func.count(FactInboundShipment.id)).select_from(FactInboundShipment)
    stmt = _apply_outer_joins(stmt, need_dist, need_prod, need_cust)
    stmt = _apply_fact_where_clause(
        stmt,
        join_distributor=need_dist,
        join_product=need_prod,
        join_customer=need_cust,
        **filt,
    )
    for clause in extra_where:
        stmt = stmt.where(clause)
    return int((await db.execute(stmt)).scalar_one() or 0)


def _fmt_date(d: Any) -> str | None:
    if d is None:
        return None
    return d.isoformat() if hasattr(d, "isoformat") else str(d)


def _fact_to_dict(
    row: FactInboundShipment,
    *,
    product_name: str | None,
    product_sku: str | None,
    distributor_name: str | None,
    distributor_code: str | None,
    customer_name: str | None,
    customer_code: str | None,
    include_raw_row: bool,
) -> dict[str, Any]:
    dist_disp = _distributor_display(row, distributor_name, distributor_code)
    cn = (customer_name or "").strip()
    cc = (customer_code or "").strip()
    tok = (row.customer_dealer_token or "").strip()
    if cn:
        cp_label = cn
        cp_caption = cc if cc else (tok[:160] + ("…" if len(tok) > 160 else "") if tok else None)
    elif tok:
        cp_label = "Channel partner"
        cp_caption = tok[:200] + ("…" if len(tok) > 200 else "")
    else:
        cp_label = "—"
        cp_caption = None
    out: dict[str, Any] = {
        "id": row.id,
        "import_job_id": row.import_job_id,
        "source_key": row.source_key,
        "shipment_evidence_line_id": row.shipment_evidence_line_id,
        "source_sheet": row.source_sheet,
        "source_row_number": row.source_row_number,
        "report_type": row.report_type,
        "line_state": row.line_state,
        "status": row.status,
        "operating_unit": row.operating_unit,
        "bill_to_raw": row.bill_to_raw,
        "ship_to_raw": row.ship_to_raw,
        "order_no": row.order_no,
        "customer_po": row.customer_po,
        "purchase_order_id": row.purchase_order_id,
        "order_line": row.order_line,
        "delivery_no": row.delivery_no,
        "invoice_line": row.invoice_line,
        "item_code": row.item_code,
        "sales_model_name": row.sales_model_name,
        "customer_item": row.customer_item,
        "ean_code": row.ean_code,
        "upc_code": row.upc_code,
        "mpor_item_no": row.mpor_item_no,
        "quantity": float(row.quantity) if row.quantity is not None else None,
        "unit_price": float(row.unit_price) if row.unit_price is not None else None,
        "amount": float(row.amount) if row.amount is not None else None,
        "currency_code": row.currency_code,
        "ship_confirm_date": _fmt_date(row.ship_confirm_date),
        "schedule_ship_date": _fmt_date(row.schedule_ship_date),
        "promise_date": _fmt_date(row.promise_date),
        "exwork_date": _fmt_date(row.exwork_date),
        "erd_date": _fmt_date(row.erd_date),
        "est_pod_date": _fmt_date(row.est_pod_date),
        "pod_date": _fmt_date(row.pod_date),
        "eta_date": _fmt_date(row.eta_date),
        "reference": row.reference,
        "product_id": row.product_id,
        "product_sku": product_sku,
        "product_name": product_name,
        "product_resolution_status": row.product_resolution_status,
        "product_resolution_token": row.product_resolution_token,
        "product_resolution_detail": row.product_resolution_detail,
        "distributor_id": row.distributor_id,
        "distributor_code": distributor_code,
        "distributor_name": distributor_name,
        "distributor_display": dist_disp,
        "distributor_resolution_status": row.distributor_resolution_status,
        "distributor_resolution_token": row.distributor_resolution_token,
        "customer_id": row.customer_id,
        "customer_name": customer_name,
        "customer_code": customer_code,
        "channel_partner_label": cp_label,
        "channel_partner_caption": cp_caption,
        "customer_dealer_token": row.customer_dealer_token,
        "customer_resolution_status": row.customer_resolution_status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
    if include_raw_row:
        out["raw_source_row"] = row.raw_source_row
    return out


@router.get("/inbound-optional-columns")
async def inbound_optional_columns() -> dict[str, Any]:
    """Every ``fact_inbound_shipment`` column not covered by the default grid."""
    mapper = sa_inspect(FactInboundShipment)
    keys = sorted(
        attr.key for attr in mapper.mapper.column_attrs if attr.key not in INBOUND_GRID_DEFAULT_FACT_KEYS
    )
    return {
        "items": [
            {"field": k, "label": INBOUND_OPTIONAL_LABEL_OVERRIDES.get(k, _human_column_label(k))} for k in keys
        ]
    }


async def _eta_shift_metrics(
    db: AsyncSession, *, sample_limit: int, filt: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Compare consecutive observations per ``line_identity_key`` (LAG on ``valid_from``)."""
    lag_est = func.lag(ShipmentEvidenceObservation.est_pod_date).over(
        partition_by=ShipmentEvidenceObservation.line_identity_key,
        order_by=ShipmentEvidenceObservation.valid_from.asc(),
    )
    lag_prom = func.lag(ShipmentEvidenceObservation.promise_date).over(
        partition_by=ShipmentEvidenceObservation.line_identity_key,
        order_by=ShipmentEvidenceObservation.valid_from.asc(),
    )
    line_win = select(
        ShipmentEvidenceObservation.id,
        ShipmentEvidenceObservation.line_identity_key,
        ShipmentEvidenceObservation.source_key,
        ShipmentEvidenceObservation.import_job_id,
        ShipmentEvidenceObservation.evidence_line_id,
        ShipmentEvidenceObservation.est_pod_date,
        ShipmentEvidenceObservation.promise_date,
        lag_est.label("prev_est"),
        lag_prom.label("prev_prom"),
    ).subquery()

    cur_eff = func.coalesce(line_win.c.est_pod_date, line_win.c.promise_date)
    prev_eff = func.coalesce(line_win.c.prev_est, line_win.c.prev_prom)
    delta_days = (cur_eff - prev_eff)

    base = (
        select(
            line_win.c.source_key,
            cur_eff.label("current_effective"),
            prev_eff.label("previous_effective"),
            line_win.c.est_pod_date.label("current_est_pod"),
            line_win.c.promise_date.label("current_promise"),
            line_win.c.prev_est.label("previous_est_pod"),
            line_win.c.prev_prom.label("previous_promise"),
            delta_days.label("delta_days"),
        )
        .select_from(line_win)
        .join(FactInboundShipment, FactInboundShipment.shipment_evidence_line_id == line_win.c.evidence_line_id)
        .where(prev_eff.is_not(None), cur_eff.is_not(None))
    )
    if filt is not None and _shipping_filters_active(filt):
        need_dist, need_prod, need_cust = _dim_join_flags(filt)
        scoped_ids = select(FactInboundShipment.id).select_from(FactInboundShipment)
        scoped_ids = _apply_outer_joins(scoped_ids, need_dist, need_prod, need_cust)
        scoped_ids = _apply_fact_where_clause(
            scoped_ids,
            join_distributor=need_dist,
            join_product=need_prod,
            join_customer=need_cust,
            **filt,
        )
        base = base.where(FactInboundShipment.id.in_(scoped_ids))

    slipped_sub = base.where(cur_eff > prev_eff).subquery()
    improved_sub = base.where(cur_eff < prev_eff).subquery()
    slipped_count = int((await db.scalar(select(func.count()).select_from(slipped_sub))) or 0)
    improved_count = int((await db.scalar(select(func.count()).select_from(improved_sub))) or 0)

    samples: list[dict[str, Any]] = []
    lim = max(0, min(sample_limit, 50))
    if lim > 0:
        slip_rows = (
            (
                await db.execute(
                    select(slipped_sub).order_by(desc(slipped_sub.c.delta_days)).limit(lim)
                )
            )
            .mappings()
            .all()
        )
        imp_rows = (
            (
                await db.execute(
                    select(improved_sub).order_by(improved_sub.c.delta_days.asc()).limit(lim)
                )
            )
            .mappings()
            .all()
        )

        def _row_to_sample(row: dict[str, Any], direction: str) -> dict[str, Any]:
            ce = row.get("current_effective")
            pe = row.get("previous_effective")
            dd = row.get("delta_days")
            cep = row.get("current_est_pod")
            cpr = row.get("current_promise")
            return {
                "source_key": row.get("source_key"),
                "direction": direction,
                "previous_effective": pe.isoformat() if pe is not None and hasattr(pe, "isoformat") else pe,
                "current_effective": ce.isoformat() if ce is not None and hasattr(ce, "isoformat") else ce,
                "delta_days": int(dd) if dd is not None else None,
                "current_est_pod": cep.isoformat() if cep is not None and hasattr(cep, "isoformat") else cep,
                "current_promise": cpr.isoformat() if cpr is not None and hasattr(cpr, "isoformat") else cpr,
            }

        for r in slip_rows:
            samples.append(_row_to_sample(dict(r), "slipped"))
        for r in imp_rows:
            samples.append(_row_to_sample(dict(r), "improved"))

    net = "neutral"
    if slipped_count > improved_count:
        net = "slipped"
    elif improved_count > slipped_count:
        net = "improved"

    return {
        "slipped_count": slipped_count,
        "improved_count": improved_count,
        "net_direction": net,
        "samples": samples,
    }


@router.get("/filter-options")
async def shipping_filter_options(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(8000, ge=1, le=20000),
) -> dict[str, Any]:
    """Canonical distributors and customers for inbound filter dropdowns (no search required)."""
    dr = await db.execute(
        select(DimDistributor.id, DimDistributor.code, DimDistributor.name)
        .order_by(DimDistributor.name.asc(), DimDistributor.code.asc())
        .limit(limit)
    )
    cr = await db.execute(
        select(DimCustomer.id, DimCustomer.code, DimCustomer.name)
        .order_by(DimCustomer.name.asc(), DimCustomer.code.asc())
        .limit(limit)
    )
    dist_items = [
        {"id": int(r[0]), "distributor_code": r[1] or "", "distributor_name": r[2] or ""} for r in dr.all()
    ]
    cust_items = [{"id": int(r[0]), "customer_code": r[1] or "", "customer_name": r[2] or ""} for r in cr.all()]
    return {"distributors": dist_items, "customers": cust_items}


@router.get("/commercial-summary")
async def shipping_commercial_summary(
    db: AsyncSession = Depends(get_db),
    import_job_id: int | None = None,
    distributor_id: int | None = None,
    customer_id: int | None = None,
    line_state: str | None = None,
    report_type: str | None = None,
    product_resolution_status: str | None = None,
    distributor_resolution_status: str | None = None,
    customer_resolution_status: str | None = None,
    status: str | None = None,
    search: str | None = None,
    eta_from: str | None = None,
    eta_to: str | None = None,
    date_field: str = Query("eta_date"),
    date_from: str | None = None,
    date_to: str | None = None,
    pod_date_is_null: bool | None = None,
    currency_code: str | None = None,
    operating_unit: str | None = None,
    product_family: str | None = None,
    product_model: str | None = None,
) -> dict[str, Any]:
    """KPI payloads for inbound commercial dashboard cards (same filter contract as ``/lines``)."""
    filt = _build_shipping_fact_filters(
        import_job_id=import_job_id,
        distributor_id=distributor_id,
        customer_id=customer_id,
        line_state=line_state,
        report_type=report_type,
        product_resolution_status=product_resolution_status,
        distributor_resolution_status=distributor_resolution_status,
        customer_resolution_status=customer_resolution_status,
        status=status,
        search=search,
        eta_from=eta_from,
        eta_to=eta_to,
        date_field=date_field,
        date_from=date_from,
        date_to=date_to,
        pod_date_is_null=pod_date_is_null,
        currency_code=currency_code,
        operating_unit=operating_unit,
        product_family=product_family,
        product_model=product_model,
    )
    filters_active = _shipping_filters_active(filt)
    today = _utc_today()
    w0, w1 = _iso_week_bounds(today)

    total_lines = await _count_shipment_facts(db, filt)

    need_dist, need_prod, need_cust = _dim_join_flags(filt)
    pipe_stmt = (
        select(FactInboundShipment.currency_code, func.coalesce(func.sum(FactInboundShipment.amount), 0))
        .select_from(FactInboundShipment)
        .where(FactInboundShipment.status == "scheduled", FactInboundShipment.amount.is_not(None))
    )
    pipe_stmt = _apply_outer_joins(pipe_stmt, need_dist, need_prod, need_cust)
    pipe_stmt = _apply_fact_where_clause(
        pipe_stmt,
        join_distributor=need_dist,
        join_product=need_prod,
        join_customer=need_cust,
        **filt,
    )
    pipe_stmt = pipe_stmt.group_by(FactInboundShipment.currency_code)
    pipe_rows = await db.execute(pipe_stmt)
    pipeline_by_currency = [
        {"currency_code": (r[0] or "").strip() or "—", "amount": float(r[1] or 0)} for r in pipe_rows.all()
    ]
    pipeline_lines = await _count_shipment_facts(
        db, filt, FactInboundShipment.status == "scheduled", FactInboundShipment.amount.is_not(None)
    )

    dist_lbl = func.left(
        func.coalesce(DimDistributor.name, FactInboundShipment.bill_to_raw, literal("Unknown")),
        48,
    )
    arr_stmt = (
        select(dist_lbl, func.count())
        .select_from(FactInboundShipment)
        .outerjoin(DimDistributor, FactInboundShipment.distributor_id == DimDistributor.id)
        .where(
            FactInboundShipment.status == "scheduled",
            FactInboundShipment.eta_date.is_not(None),
            FactInboundShipment.eta_date >= w0,
            FactInboundShipment.eta_date <= w1,
        )
    )
    arr_stmt = _apply_outer_joins(arr_stmt, need_dist, need_prod, need_cust)
    arr_stmt = _apply_fact_where_clause(
        arr_stmt,
        join_distributor=need_dist,
        join_product=need_prod,
        join_customer=need_cust,
        **filt,
    )
    arr_stmt = arr_stmt.group_by(dist_lbl).order_by(desc(func.count())).limit(12)
    arr_rows = await db.execute(arr_stmt)
    arriving_by_distributor = [
        {"label": str(r[0]), "count": int(r[1])} for r in arr_rows.all() if r[0] is not None
    ]
    arriving_total = await _count_shipment_facts(
        db,
        filt,
        FactInboundShipment.status == "scheduled",
        FactInboundShipment.eta_date.is_not(None),
        FactInboundShipment.eta_date >= w0,
        FactInboundShipment.eta_date <= w1,
    )

    scheduled_pipeline = await _count_shipment_facts(db, filt, FactInboundShipment.status == "scheduled")

    overdue_count = await _count_shipment_facts(
        db,
        filt,
        FactInboundShipment.status == "scheduled",
        FactInboundShipment.promise_date.is_not(None),
        FactInboundShipment.promise_date < today,
        FactInboundShipment.pod_date.is_(None),
    )
    overdue_pct = (overdue_count / total_lines) if total_lines else 0.0
    overdue_pct_of_scheduled = (overdue_count / scheduled_pipeline) if scheduled_pipeline else 0.0

    delivered_week_total = await _count_shipment_facts(
        db,
        filt,
        FactInboundShipment.status == "received",
        FactInboundShipment.pod_date.is_not(None),
        FactInboundShipment.pod_date >= w0,
        FactInboundShipment.pod_date <= w1,
    )

    shifts = await _eta_shift_metrics(db, sample_limit=0, filt=filt)
    shifts_light = {k: shifts[k] for k in ("slipped_count", "improved_count", "net_direction")}

    return {
        "reference_date": today.isoformat(),
        "week_start": w0.isoformat(),
        "week_end": w1.isoformat(),
        "filter_scope": {"active": filters_active, "cohort_line_count": total_lines},
        "total_lines": total_lines,
        "pipeline_in_transit": {
            "line_count": pipeline_lines,
            "by_currency": pipeline_by_currency,
        },
        "arriving_this_week": {
            "total": arriving_total,
            "by_distributor": arriving_by_distributor,
        },
        "overdue": {
            "count": overdue_count,
            "pct_of_total_lines": overdue_pct,
            "pct_of_scheduled_pipeline": overdue_pct_of_scheduled,
            "scheduled_pipeline_lines": scheduled_pipeline,
        },
        "landed_this_week": {"total": delivered_week_total},
        "delivered_this_week": {"total": delivered_week_total},
        "eta_shifts": shifts_light,
    }


@router.get("/eta-shifts")
async def shipping_eta_shifts(
    db: AsyncSession = Depends(get_db),
    sample_limit: int = Query(15, ge=1, le=50),
    import_job_id: int | None = None,
    distributor_id: int | None = None,
    customer_id: int | None = None,
    line_state: str | None = None,
    report_type: str | None = None,
    product_resolution_status: str | None = None,
    distributor_resolution_status: str | None = None,
    customer_resolution_status: str | None = None,
    status: str | None = None,
    search: str | None = None,
    eta_from: str | None = None,
    eta_to: str | None = None,
    date_field: str = Query("eta_date"),
    date_from: str | None = None,
    date_to: str | None = None,
    pod_date_is_null: bool | None = None,
    currency_code: str | None = None,
    operating_unit: str | None = None,
    product_family: str | None = None,
    product_model: str | None = None,
) -> dict[str, Any]:
    """ETA / promise slip vs prior inbound job per ``source_key`` (evidence line LAG)."""
    filt = _build_shipping_fact_filters(
        import_job_id=import_job_id,
        distributor_id=distributor_id,
        customer_id=customer_id,
        line_state=line_state,
        report_type=report_type,
        product_resolution_status=product_resolution_status,
        distributor_resolution_status=distributor_resolution_status,
        customer_resolution_status=customer_resolution_status,
        status=status,
        search=search,
        eta_from=eta_from,
        eta_to=eta_to,
        date_field=date_field,
        date_from=date_from,
        date_to=date_to,
        pod_date_is_null=pod_date_is_null,
        currency_code=currency_code,
        operating_unit=operating_unit,
        product_family=product_family,
        product_model=product_model,
    )
    return await _eta_shift_metrics(db, sample_limit=sample_limit, filt=filt)


@router.get("/lineup-plan-periods")
async def shipping_lineup_plan_periods(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Plan-quarter options — same enumeration as Plan vs Executed (coverage groups)."""
    try:
        periods = await available_plan_periods(db)
        return {"items": periods, "data_unavailable": False}
    except Exception:
        return {"items": [], "data_unavailable": True}


@router.get("/lineup-quarter-summary")
async def shipping_lineup_quarter_summary(
    db: AsyncSession = Depends(get_db),
    plan_quarter: str = Query(..., min_length=2),
    customer_id: int | None = None,
    plan_business_unit: str | None = None,
) -> dict[str, Any]:
    """Summary strip for the active lineup plan-quarter filter (derived-on-read)."""
    try:
        return await lineup_quarter_summary(
            db,
            plan_quarter=plan_quarter,
            customer_id=customer_id,
            business_unit=plan_business_unit,
        )
    except Exception:
        return {"data_unavailable": True, "plan_quarter": plan_quarter}


@router.get("/summary")
async def shipping_evidence_summary(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Structured counts for dashboard tiles (``fact_inbound_shipment``)."""
    by_state = await db.execute(
        select(FactInboundShipment.line_state, func.count())
        .group_by(FactInboundShipment.line_state)
        .order_by(FactInboundShipment.line_state)
    )
    by_cargo = await db.execute(
        select(FactInboundShipment.status, func.count())
        .group_by(FactInboundShipment.status)
        .order_by(FactInboundShipment.status)
    )
    dist_bucket = func.left(
        func.coalesce(
            DimDistributor.name,
            FactInboundShipment.bill_to_raw,
            FactInboundShipment.ship_to_raw,
            literal("—"),
        ),
        96,
    )
    by_dist = await db.execute(
        select(dist_bucket, func.count())
        .select_from(FactInboundShipment)
        .outerjoin(DimDistributor, FactInboundShipment.distributor_id == DimDistributor.id)
        .group_by(dist_bucket)
        .order_by(dist_bucket)
    )
    total = await db.scalar(select(func.count()).select_from(FactInboundShipment)) or 0

    def rows_to_items(res: Any) -> list[dict[str, Any]]:
        return [{"key": str(r[0]), "count": int(r[1])} for r in res.all() if r[0] is not None]

    return {
        "total_lines": int(total),
        "by_line_state": rows_to_items(by_state),
        "by_status": rows_to_items(by_cargo),
        "by_distributor": rows_to_items(by_dist),
    }


@router.get("/lines")
async def shipping_evidence_lines(
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    import_job_id: int | None = None,
    distributor_id: int | None = None,
    customer_id: int | None = None,
    purchase_order_id: int | None = None,
    line_state: str | None = None,
    report_type: str | None = None,
    product_resolution_status: str | None = None,
    distributor_resolution_status: str | None = None,
    customer_resolution_status: str | None = None,
    status: str | None = None,
    search: str | None = None,
    eta_from: str | None = None,
    eta_to: str | None = None,
    date_field: str = Query("eta_date"),
    date_from: str | None = None,
    date_to: str | None = None,
    pod_date_is_null: bool | None = None,
    currency_code: str | None = None,
    operating_unit: str | None = None,
    product_family: str | None = None,
    product_model: str | None = None,
    include_raw_row: bool = Query(False),
    plan_quarter: str | None = None,
    plan_quarter_label: str | None = None,
    plan_business_unit: str | None = None,
    lineup_attribution: str | None = None,
    lifecycle_bucket: str | None = None,
    slip_direction: str | None = None,
) -> dict[str, Any]:
    df = str(date_field or "eta_date").strip()
    if df not in DATE_FIELD_MAP:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid date_field: {date_field!r}")

    filt = _build_shipping_fact_filters(
        import_job_id=import_job_id,
        distributor_id=distributor_id,
        customer_id=customer_id,
        purchase_order_id=purchase_order_id,
        line_state=line_state,
        report_type=report_type,
        product_resolution_status=product_resolution_status,
        distributor_resolution_status=distributor_resolution_status,
        customer_resolution_status=customer_resolution_status,
        status=status,
        search=search,
        eta_from=eta_from,
        eta_to=eta_to,
        date_field=df,
        date_from=date_from,
        date_to=date_to,
        pod_date_is_null=pod_date_is_null,
        currency_code=currency_code,
        operating_unit=operating_unit,
        product_family=product_family,
        product_model=product_model,
    )
    filt["plan_quarter"] = (plan_quarter or "").strip() or None
    filt["plan_quarter_label"] = (plan_quarter_label or "").strip() or None
    filt["plan_business_unit"] = (plan_business_unit or "").strip() or None
    filt["lineup_attribution"] = (lineup_attribution or "").strip() or None
    filt["lifecycle_bucket"] = (lifecycle_bucket or "").strip() or None
    filt["slip_direction"] = (slip_direction or "").strip() or None

    plan_q_key, plan_q_label = normalize_plan_quarter_filter(
        filt.get("plan_quarter"), filt.get("plan_quarter_label")
    )
    lineup_active = _lineup_filters_active(filt)

    need_dist, need_prod, need_cust = _dim_join_flags(filt)

    extra_where: list[Any] = []
    if lineup_active and filt.get("lineup_attribution") != "unattributed" and plan_q_key:
        year, quarter = parse_period_filter_to_year_quarter(plan_q_key)
        if year is not None and quarter is not None:
            po_ids = await po_ids_for_plan_quarter(
                db,
                year=year,
                quarter=quarter,
                business_unit=filt.get("plan_business_unit"),
            )
            if po_ids:
                extra_where.append(FactInboundShipment.purchase_order_id.in_(po_ids))
            else:
                return {"total": 0, "skip": skip, "limit": limit, "items": [], "lineup_filter_active": True}

    if lineup_active:
        q = select(FactInboundShipment).order_by(FactInboundShipment.updated_at.desc())
        q = _apply_outer_joins(q, need_dist, need_prod, need_cust)
        q = _apply_fact_where_clause(
            q, join_distributor=need_dist, join_product=need_prod, join_customer=need_cust, **filt
        )
        for clause in extra_where:
            q = q.where(clause)
        res = await db.execute(q)
        all_rows = res.scalars().all()

        ctx = await load_attribution_context(db)
        prod_ids = {int(r.product_id) for r in all_rows if r.product_id is not None}
        product_meta: dict[int, tuple[str | None, str | None]] = {}
        if prod_ids:
            for pid, pl, bu in (
                await db.execute(
                    select(DimProduct.id, DimProduct.product_line, DimProduct.business_unit).where(
                        DimProduct.id.in_(prod_ids)
                    )
                )
            ).all():
                product_meta[int(pid)] = (pl, bu)

        filtered: list[tuple[FactInboundShipment, dict[str, Any]]] = []
        for r in all_rows:
            pl, bu = product_meta.get(int(r.product_id), (None, None)) if r.product_id else (None, None)
            enriched = enrich_fact_lineup_fields(r, ctx=ctx, product_line=pl, business_unit=bu)
            if row_matches_lineup_filters(
                enriched,
                plan_quarter=plan_q_key,
                plan_quarter_label=plan_q_label,
                lineup_attribution=filt.get("lineup_attribution"),
                lifecycle_bucket_filter=filt.get("lifecycle_bucket"),
                slip_direction=filt.get("slip_direction"),
            ):
                filtered.append((r, enriched))

        total = len(filtered)
        page_rows = filtered[skip : skip + limit]
        rows = [r for r, _e in page_rows]
        enrich_by_id = {int(r.id): e for r, e in page_rows}
    else:
        total = await _count_shipment_facts(db, filt)
        q = select(FactInboundShipment).order_by(FactInboundShipment.updated_at.desc())
        q = _apply_outer_joins(q, need_dist, need_prod, need_cust)
        q = _apply_fact_where_clause(
            q, join_distributor=need_dist, join_product=need_prod, join_customer=need_cust, **filt
        )
        res = await db.execute(q.offset(skip).limit(limit))
        rows = res.scalars().all()
        enrich_by_id = {}
        ctx = await load_attribution_context(db) if rows else None

    prod_ids = {r.product_id for r in rows if r.product_id}
    dist_ids = {r.distributor_id for r in rows if r.distributor_id}
    cust_ids = {r.customer_id for r in rows if r.customer_id}
    products: dict[int, tuple[str, str]] = {}
    distributors: dict[int, tuple[str, str]] = {}
    customers: dict[int, tuple[str, str]] = {}
    product_lines: dict[int, tuple[str | None, str | None]] = {}
    if prod_ids:
        pr = await db.execute(select(DimProduct).where(DimProduct.id.in_(prod_ids)))
        for p in pr.scalars().all():
            products[int(p.id)] = (p.name or "", p.sku or "")
            product_lines[int(p.id)] = (p.product_line, p.business_unit)
    if dist_ids:
        dr = await db.execute(select(DimDistributor).where(DimDistributor.id.in_(dist_ids)))
        for d in dr.scalars().all():
            distributors[int(d.id)] = (d.name or "", d.code or "")
    if cust_ids:
        cr = await db.execute(select(DimCustomer).where(DimCustomer.id.in_(cust_ids)))
        for c in cr.scalars().all():
            customers[int(c.id)] = (c.name or "", c.code or "")

    items = []
    for r in rows:
        pn, ps = products.get(int(r.product_id), (None, None)) if r.product_id else (None, None)
        dn, dc = distributors.get(int(r.distributor_id), (None, None)) if r.distributor_id else (None, None)
        cname, ccode = customers.get(int(r.customer_id), (None, None)) if r.customer_id else (None, None)
        pl, bu = product_lines.get(int(r.product_id), (None, None)) if r.product_id else (None, None)
        payload = _fact_to_dict(
            r,
            product_name=pn,
            product_sku=ps,
            distributor_name=dn,
            distributor_code=dc,
            customer_name=cname,
            customer_code=ccode,
            include_raw_row=include_raw_row,
        )
        if int(r.id) in enrich_by_id:
            payload.update(enrich_by_id[int(r.id)])
        elif ctx is not None:
            payload.update(
                enrich_fact_lineup_fields(r, ctx=ctx, product_line=pl, business_unit=bu)
            )
        items.append(payload)

    out: dict[str, Any] = {"total": total, "skip": skip, "limit": limit, "items": items}
    if lineup_active:
        out["lineup_filter_active"] = True
    return out
