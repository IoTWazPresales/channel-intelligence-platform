"""Commercial read APIs for inbound shipment facts (truth layer)."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Date as SA_Date, cast, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.inspection import inspect as sa_inspect
from sqlalchemy.orm import InstrumentedAttribute

from app.api.deps import get_db
from app.models.dimensions import DimDistributor, DimProduct
from app.models.facts import FactInboundShipment

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


def _dim_join_flags(kwargs: dict[str, Any]) -> tuple[bool, bool]:
    search = (kwargs.get("search") or "").strip()
    pf = (kwargs.get("product_family") or "").strip()
    pm = (kwargs.get("product_model") or "").strip()
    # Product dimension joins are required for family filters and for model/SKU/name matches on dim.
    need_product = bool(search or pf or pm)
    need_distributor = bool(search)
    return need_distributor, need_product


def _apply_outer_joins(stmt: Any, need_dist: bool, need_product: bool) -> Any:
    if need_dist:
        stmt = stmt.outerjoin(DimDistributor, FactInboundShipment.distributor_id == DimDistributor.id)
    if need_product:
        stmt = stmt.outerjoin(DimProduct, FactInboundShipment.product_id == DimProduct.id)
    return stmt


def _apply_fact_where_clause(
    stmt: Any,
    *,
    join_distributor: bool,
    join_product: bool,
    **kwargs: Any,
) -> Any:
    import_job_id = kwargs.get("import_job_id")
    distributor_id = kwargs.get("distributor_id")
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
        stmt = stmt.where(or_(*parts))

    return stmt


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
    include_raw_row: bool,
) -> dict[str, Any]:
    dist_disp = _distributor_display(row, distributor_name, distributor_code)
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
    return {"items": [{"field": k, "label": _human_column_label(k)} for k in keys]}


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
) -> dict[str, Any]:
    df = str(date_field or "eta_date").strip()
    if df not in DATE_FIELD_MAP:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid date_field: {date_field!r}")

    eta_d0 = _parse_opt_date(eta_from)
    eta_d1 = _parse_opt_date(eta_to)
    d0 = _parse_opt_date(date_from)
    d1 = _parse_opt_date(date_to)

    filt: dict[str, Any] = {
        "import_job_id": import_job_id,
        "distributor_id": distributor_id,
        "line_state": line_state,
        "report_type": report_type,
        "product_resolution_status": product_resolution_status,
        "distributor_resolution_status": distributor_resolution_status,
        "customer_resolution_status": customer_resolution_status,
        "status": status,
        "search": search,
        "eta_from": eta_d0,
        "eta_to": eta_d1,
        "date_field": df,
        "date_from": d0,
        "date_to": d1,
        "pod_date_is_null": pod_date_is_null,
        "currency_code": currency_code,
        "operating_unit": operating_unit,
        "product_family": product_family,
        "product_model": product_model,
    }

    need_dist, need_prod = _dim_join_flags(filt)

    count_stmt = select(func.count(FactInboundShipment.id)).select_from(FactInboundShipment)
    count_stmt = _apply_outer_joins(count_stmt, need_dist, need_prod)
    count_stmt = _apply_fact_where_clause(
        count_stmt, join_distributor=need_dist, join_product=need_prod, **filt
    )
    total = int((await db.execute(count_stmt)).scalar_one())

    q = select(FactInboundShipment).order_by(FactInboundShipment.updated_at.desc())
    q = _apply_outer_joins(q, need_dist, need_prod)
    q = _apply_fact_where_clause(q, join_distributor=need_dist, join_product=need_prod, **filt)
    res = await db.execute(q.offset(skip).limit(limit))
    rows = res.scalars().all()

    prod_ids = {r.product_id for r in rows if r.product_id}
    dist_ids = {r.distributor_id for r in rows if r.distributor_id}
    products: dict[int, tuple[str, str]] = {}
    distributors: dict[int, tuple[str, str]] = {}
    if prod_ids:
        pr = await db.execute(select(DimProduct).where(DimProduct.id.in_(prod_ids)))
        for p in pr.scalars().all():
            products[int(p.id)] = (p.name or "", p.sku or "")
    if dist_ids:
        dr = await db.execute(select(DimDistributor).where(DimDistributor.id.in_(dist_ids)))
        for d in dr.scalars().all():
            distributors[int(d.id)] = (d.name or "", d.code or "")

    items = []
    for r in rows:
        pn, ps = products.get(int(r.product_id), (None, None)) if r.product_id else (None, None)
        dn, dc = distributors.get(int(r.distributor_id), (None, None)) if r.distributor_id else (None, None)
        items.append(
            _fact_to_dict(
                r,
                product_name=pn,
                product_sku=ps,
                distributor_name=dn,
                distributor_code=dc,
                include_raw_row=include_raw_row,
            )
        )
    return {"total": total, "skip": skip, "limit": limit, "items": items}
