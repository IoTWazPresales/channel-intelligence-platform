"""Commercial read APIs for inbound shipment facts (truth layer)."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.dimensions import DimDistributor, DimProduct
from app.models.facts import FactInboundShipment

router = APIRouter()


def _parse_opt_date(raw: str | None) -> date | None:
    if raw is None or not str(raw).strip():
        return None
    try:
        return date.fromisoformat(str(raw).strip()[:10])
    except ValueError:
        return None


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


def _apply_fact_filters(stmt: Any, **kwargs: Any) -> Any:
    import_job_id = kwargs.get("import_job_id")
    distributor_id = kwargs.get("distributor_id")
    line_state = kwargs.get("line_state")
    report_type = kwargs.get("report_type")
    product_resolution_status = kwargs.get("product_resolution_status")
    distributor_resolution_status = kwargs.get("distributor_resolution_status")
    customer_resolution_status = kwargs.get("customer_resolution_status")
    status = kwargs.get("status")
    search = kwargs.get("search")
    eta_from = kwargs.get("eta_from")
    eta_to = kwargs.get("eta_to")
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
    if status:
        stmt = stmt.where(FactInboundShipment.status == status)
    if eta_from is not None:
        stmt = stmt.where(FactInboundShipment.eta_date >= eta_from)
    if eta_to is not None:
        stmt = stmt.where(FactInboundShipment.eta_date <= eta_to)
    if search and str(search).strip():
        term = f"%{str(search).strip()}%"
        stmt = stmt.where(
            or_(
                FactInboundShipment.bill_to_raw.ilike(term),
                FactInboundShipment.ship_to_raw.ilike(term),
                FactInboundShipment.customer_dealer_token.ilike(term),
                FactInboundShipment.item_code.ilike(term),
                FactInboundShipment.sales_model_name.ilike(term),
                FactInboundShipment.order_no.ilike(term),
                FactInboundShipment.delivery_no.ilike(term),
            )
        )
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
    include_raw_row: bool = Query(False),
) -> dict[str, Any]:
    eta_d0 = _parse_opt_date(eta_from)
    eta_d1 = _parse_opt_date(eta_to)
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
    }
    count_stmt = select(func.count()).select_from(FactInboundShipment)
    count_stmt = _apply_fact_filters(count_stmt, **filt)
    total = int((await db.execute(count_stmt)).scalar_one())

    q = select(FactInboundShipment).order_by(FactInboundShipment.updated_at.desc())
    q = _apply_fact_filters(q, **filt)
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
