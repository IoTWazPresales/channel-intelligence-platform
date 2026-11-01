"""On the water: vessels, positions and the figures around them, and the manual port conditions.

``GET /shipping/on-the-water`` takes the same filter query parameters as ``/shipping/commercial-summary`` and
``/shipping/lines`` (one page scope, one filter builder), so the map, the tiles and the grid always agree.
Rules and the pure computation live in ``app/services/shipping/on_the_water.py``.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.deps import get_db
from app.api.v1.endpoints.shipping import (
    _apply_fact_where_clause,
    _apply_outer_joins,
    _attach_lineup_filter_keys,
    _build_shipping_fact_filters,
    _cohort_clause,
    _dim_join_flags,
    _distributor_display,
    _iso_week_bounds,
    _lineup_filters_active,
    _lineup_matching_fact_ids,
    _lineup_po_prefilter_clause,
)
from app.core.security import Role, get_optional_current_user, require_roles
from app.core.tenant_scope import DEFAULT_TENANT_ID, tenant_id_from_user
from app.models.dimensions import DimDistributor
from app.models.facts import FactInboundShipment
from app.models.ingestion import ImportJob
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.models.shipment_evidence_observation import ShipmentEvidenceObservation
from app.models.shipment_water import PortCondition
from app.services.commercial_tenant_profile import on_the_water_overrides, reporting_today
from app.services.imports.shipment_report_date import report_date_from_file_name
from app.services.platform_audit import record_platform_audit
from app.services.shipping.amount_scale import amount_scale_suspect_clause
from app.services.shipping.on_the_water import (
    PORT_LABEL,
    WaterLine,
    build_payload,
    config_from_overrides,
)
from app.services.shipping_commercial_kpis import predicate_needs_look

router = APIRouter()

_INT_KEYS = ("import_job_id", "distributor_id", "customer_id", "purchase_order_id")
_STR_KEYS = (
    "line_state", "report_type", "product_resolution_status", "distributor_resolution_status",
    "customer_resolution_status", "status", "search", "eta_from", "eta_to", "date_from", "date_to",
    "currency_code", "operating_unit", "product_family", "product_model", "cohort", "vessel",
)
_LINEUP_KEYS = ("plan_quarter", "plan_quarter_label", "plan_business_unit", "lineup_attribution", "lifecycle_bucket", "slip_direction")


def _filters_from_query(params: Any, user: dict | None) -> dict[str, Any]:
    def s(key: str) -> str | None:
        v = params.get(key)
        return v.strip() if isinstance(v, str) and v.strip() else None

    def i(key: str) -> int | None:
        v = s(key)
        try:
            return int(v) if v is not None else None
        except ValueError:
            raise HTTPException(status_code=422, detail=f"{key} must be a whole number") from None

    pod = (s("pod_date_is_null") or "").lower()
    filt = _build_shipping_fact_filters(
        **{k: i(k) for k in _INT_KEYS},
        **{k: s(k) for k in _STR_KEYS},
        date_field=s("date_field") or "eta_date",
        pod_date_is_null={"true": True, "false": False}.get(pod),
        tenant_id=tenant_id_from_user(user),
    )
    _attach_lineup_filter_keys(filt, **{k: s(k) for k in _LINEUP_KEYS})
    return filt


def _line(row: FactInboundShipment, name: str | None, code: str | None, suspect: bool) -> WaterLine:
    return WaterLine(
        id=int(row.id),
        quantity=float(row.quantity or 0),
        amount=float(row.amount) if row.amount is not None else None,
        currency=row.currency_code,
        amount_suspect=bool(suspect),
        line_state=row.line_state,
        report_type=row.report_type,
        ship_way=row.ship_way,
        on_board=row.on_board_date,
        port_eta=row.port_eta_date,
        port_ata=row.port_ata_date,
        pod=row.pod_date,
        ship_confirm=row.ship_confirm_date,
        exwork=row.exwork_date,
        forwarder=row.forwarder_code,
        hub=row.origin_hub,
        deliver_port=row.deliver_port,
        vessel_name=row.vessel_name,
        voyage_no=row.voyage_no,
        delivery_no=row.delivery_no,
        model=row.sales_model_name,
        distributor=_distributor_display(row, name, code),
    )


async def _fetch_lines(db: AsyncSession, filt: dict[str, Any], *where: Any) -> list[WaterLine]:
    dd = aliased(DimDistributor)
    need_dist, need_prod, need_cust = _dim_join_flags(filt)
    stmt = (
        select(FactInboundShipment, dd.name, dd.code, amount_scale_suspect_clause().label("suspect"))
        .select_from(FactInboundShipment)
        .outerjoin(dd, FactInboundShipment.distributor_id == dd.id)
    )
    stmt = _apply_outer_joins(stmt, need_dist, need_prod, need_cust)
    stmt = _apply_fact_where_clause(stmt, join_distributor=need_dist, join_product=need_prod, join_customer=need_cust, **filt)
    for clause in where:
        if clause is not None:
            stmt = stmt.where(clause)
    rows = (await db.execute(stmt)).all()
    return [_line(r[0], r[1], r[2], r[3]) for r in rows]


_HISTORY_SQL = text(
    """
    WITH cur AS MATERIALIZED (
      SELECT f.id AS fact_id, o.line_identity_key AS k
      FROM fact_inbound_shipment f
      JOIN shipment_evidence_observation o ON o.evidence_line_id = f.shipment_evidence_line_id
      WHERE f.id = ANY(CAST(:ids AS integer[]))
    ), hist AS MATERIALIZED (
      SELECT c.fact_id, o.id, o.import_job_id, o.valid_from, o.port_eta_date, o.on_board_date
      FROM cur c JOIN shipment_evidence_observation o ON o.line_identity_key = c.k
    )
    SELECT DISTINCT ON (fact_id, kind) fact_id, kind, import_job_id, valid_from, d FROM (
      SELECT fact_id, 'seen' AS kind, import_job_id, valid_from, id, NULL::date AS d FROM hist
      UNION ALL
      SELECT fact_id, 'eta', import_job_id, valid_from, id, port_eta_date FROM hist WHERE port_eta_date IS NOT NULL
      UNION ALL
      SELECT fact_id, 'ob', import_job_id, valid_from, id, on_board_date FROM hist WHERE on_board_date IS NOT NULL
    ) u
    ORDER BY fact_id, kind, valid_from, id
    """
)


async def _report_dates(db: AsyncSession, tenant_id: str) -> dict[int, date]:
    """Report date (the YYYYMMDD in the file name) of every job that loaded shipment evidence."""
    rows = (
        await db.execute(
            select(ImportJob.id, ImportJob.file_name).where(
                ImportJob.tenant_id == tenant_id,
                or_(
                    ImportJob.id.in_(select(ShipmentEvidenceLine.import_job_id).distinct()),
                    ImportJob.id.in_(select(ShipmentEvidenceObservation.import_job_id).distinct()),
                ),
            )
        )
    ).all()
    return {int(i): d for i, name in rows if (d := report_date_from_file_name(name)) is not None}


async def _attach_history(db: AsyncSession, lines: list[WaterLine], report_by_job: dict[int, date]) -> None:
    ids = [ln.id for ln in lines]
    if not ids:
        return
    by_id = {ln.id: ln for ln in lines}
    for fact_id, kind, job_id, valid_from, d in (await db.execute(_HISTORY_SQL, {"ids": ids})).all():
        ln = by_id.get(int(fact_id))
        if ln is None:
            continue
        reported = report_by_job.get(int(job_id)) or (valid_from.date() if valid_from else None)
        if kind == "seen":
            ln.first_seen_report = reported
        elif kind == "eta":
            ln.first_eta, ln.first_eta_report = d, reported
        elif kind == "ob":
            ln.first_on_board = d


async def _current_conditions(db: AsyncSession, tenant_id: str) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(PortCondition)
            .where(PortCondition.tenant_id == tenant_id)
            .order_by(PortCondition.port_code, PortCondition.entered_at.desc(), PortCondition.id.desc())
        )
    ).scalars().all()
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for r in rows:
        code = r.port_code.upper()
        if code in seen:
            continue
        seen.add(code)
        out.append(_condition_dict(r))
    return out


def _condition_dict(r: PortCondition) -> dict[str, Any]:
    return {
        "id": int(r.id),
        "port_code": r.port_code,
        "label": PORT_LABEL.get(r.port_code.upper(), r.port_code),
        "delay_days": float(r.delay_days),
        "note": r.note,
        "entered_by": r.entered_by,
        "entered_at": r.entered_at.isoformat() if r.entered_at else None,
    }


@router.get("/on-the-water")
async def on_the_water(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    params = request.query_params
    filt = _filters_from_query(params, user)
    tenant_id = filt["tenant_id"]
    cfg = config_from_overrides(on_the_water_overrides(tenant_id))
    as_of = reporting_today(tenant_id)
    if (raw := params.get("as_of")) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        as_of = date.fromisoformat(raw)  # lets a test or a what-if fix the day
    w0, w1 = _iso_week_bounds(as_of)
    cohort_clause = _cohort_clause(filt, today=as_of, week_start=w0, week_end=w1)

    id_clause = None
    if _lineup_filters_active(filt):
        po_clause = await _lineup_po_prefilter_clause(db, filt)
        scoped = await _lineup_matching_fact_ids(db, filt, *[c for c in (po_clause, cohort_clause) if c is not None])
        id_clause = FactInboundShipment.id.in_(scoped) if scoped else FactInboundShipment.id.in_([])
        cohort_clause = None

    relevant = and_(
        FactInboundShipment.line_state.in_(("shipped", "open_order")),
        or_(FactInboundShipment.on_board_date.is_not(None), FactInboundShipment.port_ata_date.is_not(None)),
        FactInboundShipment.pod_date.is_(None),
    )
    lines = await _fetch_lines(db, filt, relevant, id_clause, cohort_clause)
    needs_look_lines = await _fetch_lines(db, filt, predicate_needs_look(as_of, cfg.needs_look_days), id_clause)

    report_by_job = await _report_dates(db, tenant_id)
    await _attach_history(db, lines, report_by_job)
    await _attach_history(db, needs_look_lines, report_by_job)

    dates = sorted(set(report_by_job.values()))
    report_date = dates[-1] if dates else None
    since_candidates = [ln.first_eta_report for ln in lines if ln.first_eta_report]
    reports = {
        "count": len(dates),
        "earlier": max(0, len(dates) - 1),
        "since": (min(since_candidates) if since_candidates else (dates[0] if dates else None)),
    }
    reports["since"] = reports["since"].isoformat() if reports["since"] else None

    payload = build_payload(
        lines,
        as_of=as_of,
        report_date=report_date,
        reports=reports,
        port_conditions=await _current_conditions(db, tenant_id),
        needs_look_lines=needs_look_lines,
        cfg=cfg,
    )
    payload["position_note"] = "Positions are estimated from the on-board date and the port ETA; live tracking is planned."
    return payload


# ---------------------------------------------------------------------------------- port conditions
class PortConditionIn(BaseModel):
    port_code: str = Field(min_length=3, max_length=16)
    delay_days: float = Field(ge=0, le=365)
    note: str | None = Field(default=None, max_length=1000)


@router.get("/port-conditions")
async def list_port_conditions(
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
    limit: int = 200,
) -> dict[str, Any]:
    tenant_id = tenant_id_from_user(user)
    rows = (
        await db.execute(
            select(PortCondition)
            .where(PortCondition.tenant_id == tenant_id)
            .order_by(PortCondition.entered_at.desc(), PortCondition.id.desc())
            .limit(max(1, min(int(limit), 500)))
        )
    ).scalars().all()
    return {"items": [_condition_dict(r) for r in rows], "current": await _current_conditions(db, tenant_id)}


@router.post("/port-conditions", status_code=status.HTTP_201_CREATED)
async def add_port_condition(
    body: PortConditionIn,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_roles(Role.ADMIN)),
) -> dict[str, Any]:
    """Append a manual port delay. A correction is a new row: rows are never changed or removed."""
    code = body.port_code.strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{3,16}", code):
        raise HTTPException(status_code=422, detail="Port code is the UN/LOCODE, for example ZADUR")
    who = str(admin.get("display_name") or admin.get("email") or admin.get("id") or "admin")[:256]
    row = PortCondition(
        tenant_id=tenant_id_from_user(admin) or DEFAULT_TENANT_ID,
        port_code=code,
        delay_days=body.delay_days,
        note=(body.note or "").strip() or None,
        entered_by=who,
        entered_at=datetime.now(timezone.utc),
    )
    db.add(row)
    await db.flush()
    await record_platform_audit(
        db,
        admin,
        area="admin",
        action="port_condition_add",
        target_type="port_condition",
        target_id=str(row.id),
        detail={"port_code": code, "delay_days": body.delay_days, "note": row.note},
    )
    await db.commit()
    await db.refresh(row)
    return _condition_dict(row)
