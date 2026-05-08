"""Read APIs for canonical shipment / order evidence lines."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.dimensions import DimDistributor, DimProduct
from app.models.ingestion import ImportJob
from app.models.shipment_evidence import ShipmentEvidenceLine

router = APIRouter()


def _is_admin(x_user_role: str | None) -> bool:
    return (x_user_role or "").strip().lower() == "admin"


def _require_admin(x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None) -> None:
    if not _is_admin(x_user_role):
        raise HTTPException(
            status_code=403,
            detail={"error": "admin_required", "message": "Requires X-User-Role: admin"},
        )


def _line_to_dict(
    row: ShipmentEvidenceLine,
    *,
    product_sku: str | None,
    distributor_code: str | None,
    include_raw_row: bool = False,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": row.id,
        "import_job_id": row.import_job_id,
        "source_sheet": row.source_sheet,
        "source_row_number": row.source_row_number,
        "report_type": row.report_type,
        "line_state": row.line_state,
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
        "ship_confirm_date": row.ship_confirm_date.isoformat() if row.ship_confirm_date else None,
        "schedule_ship_date": row.schedule_ship_date.isoformat() if row.schedule_ship_date else None,
        "promise_date": row.promise_date.isoformat() if row.promise_date else None,
        "exwork_date": row.exwork_date.isoformat() if row.exwork_date else None,
        "erd_date": row.erd_date.isoformat() if row.erd_date else None,
        "product_id": row.product_id,
        "product_sku": product_sku,
        "product_resolution_status": row.product_resolution_status,
        "product_resolution_token": row.product_resolution_token,
        "product_resolution_detail": row.product_resolution_detail,
        "distributor_id": row.distributor_id,
        "distributor_code": distributor_code,
        "distributor_resolution_status": row.distributor_resolution_status,
        "distributor_resolution_token": row.distributor_resolution_token,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
    if include_raw_row:
        out["raw_source_row"] = row.raw_source_row
    return out


def _apply_filters(stmt: Any, **kwargs: Any) -> Any:
    import_job_id = kwargs.get("import_job_id")
    line_state = kwargs.get("line_state")
    report_type = kwargs.get("report_type")
    product_resolution_status = kwargs.get("product_resolution_status")
    distributor_resolution_status = kwargs.get("distributor_resolution_status")
    search = kwargs.get("search")
    if import_job_id is not None:
        stmt = stmt.where(ShipmentEvidenceLine.import_job_id == import_job_id)
    if line_state:
        stmt = stmt.where(ShipmentEvidenceLine.line_state == line_state)
    if report_type:
        stmt = stmt.where(ShipmentEvidenceLine.report_type == report_type)
    if product_resolution_status:
        stmt = stmt.where(ShipmentEvidenceLine.product_resolution_status == product_resolution_status)
    if distributor_resolution_status:
        stmt = stmt.where(ShipmentEvidenceLine.distributor_resolution_status == distributor_resolution_status)
    if search and str(search).strip():
        term = f"%{str(search).strip()}%"
        stmt = stmt.where(
            or_(
                ShipmentEvidenceLine.bill_to_raw.ilike(term),
                ShipmentEvidenceLine.ship_to_raw.ilike(term),
                ShipmentEvidenceLine.item_code.ilike(term),
                ShipmentEvidenceLine.sales_model_name.ilike(term),
                ShipmentEvidenceLine.order_no.ilike(term),
                ShipmentEvidenceLine.delivery_no.ilike(term),
            )
        )
    return stmt


@router.get("/raw-column-keys")
async def list_shipment_evidence_raw_column_keys(
    db: AsyncSession = Depends(get_db),
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
    import_job_id: int = Query(..., ge=1),
) -> dict[str, Any]:
    """Distinct JSON keys present in ``raw_source_row`` for one import job (for admin column picker)."""
    _require_admin(x_user_role)
    sql = text(
        """
        SELECT DISTINCT jsonb_object_keys(raw_source_row) AS k
        FROM shipment_evidence_line
        WHERE import_job_id = :import_job_id
        ORDER BY 1
        """
    )
    res = await db.execute(sql, {"import_job_id": import_job_id})
    keys = [str(row[0]) for row in res.fetchall() if row[0] is not None]
    return {"import_job_id": import_job_id, "keys": keys}


@router.get("")
async def list_shipment_evidence(
    db: AsyncSession = Depends(get_db),
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    import_job_id: int | None = None,
    line_state: str | None = None,
    report_type: str | None = None,
    product_resolution_status: str | None = None,
    distributor_resolution_status: str | None = None,
    search: str | None = None,
    include_raw_row: bool = Query(False),
) -> dict[str, Any]:
    _require_admin(x_user_role)
    filt: dict[str, Any] = {
        "import_job_id": import_job_id,
        "line_state": line_state,
        "report_type": report_type,
        "product_resolution_status": product_resolution_status,
        "distributor_resolution_status": distributor_resolution_status,
        "search": search,
    }
    count_stmt = select(func.count()).select_from(ShipmentEvidenceLine)
    count_stmt = _apply_filters(count_stmt, **filt)
    total = int((await db.execute(count_stmt)).scalar_one())

    q = select(ShipmentEvidenceLine).order_by(ShipmentEvidenceLine.id.desc())
    q = _apply_filters(q, **filt)
    res = await db.execute(q.offset(skip).limit(limit))
    rows = res.scalars().all()

    prod_ids = {r.product_id for r in rows if r.product_id}
    dist_ids = {r.distributor_id for r in rows if r.distributor_id}
    products: dict[int, str] = {}
    distributors: dict[int, str] = {}
    if prod_ids:
        pr = await db.execute(select(DimProduct).where(DimProduct.id.in_(prod_ids)))
        for p in pr.scalars().all():
            products[int(p.id)] = p.sku or ""
    if dist_ids:
        dr = await db.execute(select(DimDistributor).where(DimDistributor.id.in_(dist_ids)))
        for d in dr.scalars().all():
            distributors[int(d.id)] = d.code or d.name or ""

    items = [
        _line_to_dict(
            r,
            product_sku=products.get(int(r.product_id)) if r.product_id else None,
            distributor_code=distributors.get(int(r.distributor_id)) if r.distributor_id else None,
            include_raw_row=include_raw_row,
        )
        for r in rows
    ]
    return {"total": total, "skip": skip, "limit": limit, "items": items}


@router.get("/{line_id}")
async def get_shipment_evidence_line(
    line_id: int,
    db: AsyncSession = Depends(get_db),
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
) -> dict[str, Any]:
    _require_admin(x_user_role)
    row = await db.get(ShipmentEvidenceLine, line_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    job = await db.get(ImportJob, row.import_job_id)
    product_sku = None
    distributor_code = None
    if row.product_id:
        p = await db.get(DimProduct, row.product_id)
        product_sku = p.sku if p else None
    if row.distributor_id:
        d = await db.get(DimDistributor, row.distributor_id)
        distributor_code = (d.code or d.name) if d else None
    out = _line_to_dict(
        row,
        product_sku=product_sku,
        distributor_code=distributor_code,
        include_raw_row=True,
    )
    out["import_job_file_name"] = job.file_name if job else None
    out["import_job_status"] = job.status if job else None
    return out
