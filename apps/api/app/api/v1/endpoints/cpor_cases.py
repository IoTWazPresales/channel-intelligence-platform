"""CPOR case / line API — Unit 3 (wires U1 models + U2 services). No client money math."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, File, Form, Header, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session_sync import SessionLocal
from app.models.cpor import CporCase, CporCaseEvent, CporCaseLine
from app.models.dimensions import DimCustomer, DimProduct
from app.services.cpor.claim_evidence_apply import apply_claim_evidence_to_case
from app.services.cpor.cost_suggestion import (
    detect_cost_basis_drift,
    resolve_default_margin,
    suggest_cost_basis,
)
from app.services.cpor.lifecycle import (
    EDITABLE_STATUSES,
    LIFECYCLE_ACTIONS,
    LIFECYCLE_TRANSITIONS,
    allowed_next,
    can_transition,
    target_status,
)
from app.services.cpor.pivot import build_case_pivot
from app.services.cpor.norms_and_comparable import build_comparable_cases, build_support_norms
from app.services.cpor.promo_plan_builder import build_promo_plan_draft
from app.services.cpor.portfolio_intelligence import build_portfolio_intelligence
from app.services.cpor.promotion_type_vocab import CPOR_CASE_STATUS_SET, CPOR_PROMOTION_TYPE_SET
from app.services.cpor.recompute import recompute_case, recompute_case_line
from app.services.cpor.settlement import (
    build_settlement_consolidation,
    rollup_result_qty_from_claims,
)

router = APIRouter()


# --- helpers -----------------------------------------------------------------


def _actor(x_user_id: str | None) -> str | None:
    return x_user_id


def _record_event(
    session: Session,
    *,
    case_id: int,
    event_type: str,
    actor: str | None,
    payload: dict | None = None,
) -> None:
    session.add(
        CporCaseEvent(
            case_id=case_id,
            event_type=event_type,
            actor=actor,
            payload_json=payload,
        )
    )


def _generate_case_code(session: Session) -> str:
    """Generate C{yy}C{nnnnn}-style code; unique against cpor_case.case_code."""
    yy = datetime.now(timezone.utc).strftime("%y")
    prefix = f"C{yy}C"
    existing = session.scalar(
        select(func.count()).select_from(CporCase).where(CporCase.case_code.like(f"{prefix}%"))
    )
    n = int(existing or 0) + 1
    for _ in range(50):
        code = f"{prefix}{n:05d}"
        if session.scalar(select(CporCase.id).where(CporCase.case_code == code)) is None:
            return code
        n += 1
    raise HTTPException(status_code=500, detail="Unable to allocate case_code")


def _line_flags(line: CporCaseLine) -> list[str]:
    flags: list[str] = []
    if line.distributor_id is None:
        flags.append("no_distributor")
    if line.cost_basis is None:
        flags.append("no_cost_basis")
    ev = line.cost_evidence_json or {}
    for f in ev.get("flags") or []:
        if f not in flags:
            flags.append(f)
    # also surface known keys stored at top-level of evidence
    for key in ("assumed_currency", "manual_deviation_from_evidence", "no_cost_evidence", "inter_tier_deviation"):
        if key in (ev.get("flags") or []) or ev.get(key):
            if key not in flags and key in (ev.get("flags") or []):
                flags.append(key)
    return flags


def _line_json(line: CporCaseLine, product: DimProduct | None = None) -> dict[str, Any]:
    flags = _line_flags(line)
    return {
        "id": line.id,
        "case_id": line.case_id,
        "product_id": line.product_id,
        "product_sku": product.sku if product else None,
        "product_name": product.name if product else None,
        "product_line": product.product_line if product else None,
        "business_unit": product.business_unit if product else None,
        "distributor_id": line.distributor_id,
        "pod_quarter": line.pod_quarter,
        "srp": float(line.srp) if line.srp is not None else None,
        "vat_rate": float(line.vat_rate) if line.vat_rate is not None else None,
        "dealer_margin_pct": float(line.dealer_margin_pct) if line.dealer_margin_pct is not None else None,
        "margin_source": line.margin_source,
        "cost_basis": float(line.cost_basis) if line.cost_basis is not None else None,
        "cost_source": line.cost_source,
        "cost_evidence_json": line.cost_evidence_json,
        "estimate_qty": float(line.estimate_qty) if line.estimate_qty is not None else None,
        "cap_qty": float(line.cap_qty) if line.cap_qty is not None else None,
        "soh_snapshot": float(line.soh_snapshot) if line.soh_snapshot is not None else None,
        "dealer_price": float(line.dealer_price) if line.dealer_price is not None else None,
        "support_unit": float(line.support_unit) if line.support_unit is not None else None,
        "ttl_support": float(line.ttl_support) if line.ttl_support is not None else None,
        "support_usd": float(line.support_usd) if line.support_usd is not None else None,
        "ttl_support_usd": float(line.ttl_support_usd) if line.ttl_support_usd is not None else None,
        "result_qty": float(line.result_qty) if line.result_qty is not None else None,
        "ttl_result": float(line.ttl_result) if line.ttl_result is not None else None,
        "ttl_result_usd": float(line.ttl_result_usd) if line.ttl_result_usd is not None else None,
        "remark": line.remark,
        "flags": flags,
    }


def _case_json(
    case: CporCase,
    *,
    customer: DimCustomer | None = None,
    lines: list[dict] | None = None,
    include_lines: bool = False,
) -> dict[str, Any]:
    ttl_zar = None
    ttl_usd = None
    if lines:
        zar_vals = [l["ttl_support"] for l in lines if l.get("ttl_support") is not None]
        # Prefer stored ttl_support_usd (recompute); fall back to support_usd * estimate_qty.
        line_usd = []
        for l in lines:
            if l.get("ttl_support_usd") is not None:
                line_usd.append(float(l["ttl_support_usd"]))
            elif l.get("support_usd") is not None and l.get("estimate_qty") is not None:
                line_usd.append(float(l["support_usd"]) * float(l["estimate_qty"]))
        ttl_zar = sum(zar_vals) if zar_vals else None
        ttl_usd = sum(line_usd) if line_usd else None
    out: dict[str, Any] = {
        "id": case.id,
        "case_code": case.case_code,
        "case_name": case.case_name,
        "customer_id": case.customer_id,
        "customer_code": customer.code if customer else None,
        "customer_name": customer.name if customer else None,
        "promotion_type": case.promotion_type,
        "window_start": case.window_start.isoformat() if case.window_start else None,
        "window_end": case.window_end.isoformat() if case.window_end else None,
        "status": case.status,
        "roe_snapshot": float(case.roe_snapshot) if case.roe_snapshot is not None else None,
        "currency_code": case.currency_code,
        "channel": case.channel,
        "notes": case.notes,
        "created_by": case.created_by,
        "export_version": case.export_version,
        "workflow_status": case.workflow_status,
        "last_comment": case.last_comment,
        "submitted_at": case.submitted_at.isoformat() if case.submitted_at else None,
        "decided_at": case.decided_at.isoformat() if case.decided_at else None,
        "decided_by": case.decided_by,
        "superseded_by_case_id": case.superseded_by_case_id,
        "allowed_next": allowed_next(case.status),
        "ttl_support_zar": ttl_zar,
        "ttl_support_usd": ttl_usd,
        "missing_roe": case.roe_snapshot is None,
    }
    if include_lines and lines is not None:
        out["lines"] = lines
        all_flags: list[str] = []
        for l in lines:
            all_flags.extend(l.get("flags") or [])
        out["flags"] = sorted(set(all_flags))
    return out


def _load_case(session: Session, case_id: int) -> CporCase:
    case = session.get(CporCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="CPOR case not found")
    return case


def _products_map(session: Session, product_ids: list[int]) -> dict[int, DimProduct]:
    if not product_ids:
        return {}
    rows = session.scalars(select(DimProduct).where(DimProduct.id.in_(product_ids))).all()
    return {int(p.id): p for p in rows}


def _run_drift_check(session: Session, case: CporCase, actor: str | None) -> list[dict]:
    """On approve/activate: flag drift, never rewrite cost_basis."""
    drifts: list[dict] = []
    lines = session.scalars(select(CporCaseLine).where(CporCaseLine.case_id == case.id)).all()
    as_of = case.created_at.date() if case.created_at else date.today()
    for line in lines:
        fresh = suggest_cost_basis(
            session,
            customer_id=case.customer_id,
            product_id=line.product_id,
            as_of=as_of,
            exclude_case_id=case.id,
        )
        drift = detect_cost_basis_drift(line.cost_basis, fresh)
        if drift:
            drifts.append({"line_id": line.id, **drift})
            ev = dict(line.cost_evidence_json or {})
            flags = list(ev.get("flags") or [])
            if "cost_basis_drift" not in flags:
                flags.append("cost_basis_drift")
            ev["flags"] = flags
            ev["cost_basis_drift"] = drift
            line.cost_evidence_json = ev
            session.add(line)
    if drifts:
        _record_event(
            session,
            case_id=case.id,
            event_type="cost_basis_drift",
            actor=actor,
            payload={"drifts": drifts},
        )
    return drifts


# --- request bodies ----------------------------------------------------------


class CaseCreate(BaseModel):
    customer_id: int
    promotion_type: str
    window_start: date
    window_end: date
    case_code: str | None = None
    case_name: str | None = None
    roe_snapshot: float | None = None
    currency_code: str = "ZAR"
    channel: str = "reseller"
    notes: str | None = None


class CasePatch(BaseModel):
    case_name: str | None = None
    promotion_type: str | None = None
    window_start: date | None = None
    window_end: date | None = None
    roe_snapshot: float | None = None
    currency_code: str | None = None
    notes: str | None = None


class LineCreate(BaseModel):
    product_id: int
    distributor_id: int | None = None
    pod_quarter: str | None = None
    srp: float
    vat_rate: float = 0.15
    dealer_margin_pct: float | None = None
    cost_basis: float | None = None
    cost_source: str | None = None
    estimate_qty: float
    cap_qty: float | None = None
    soh_snapshot: float | None = None
    remark: str | None = None
    accept_cost_suggestion: bool = True


class LinePatch(BaseModel):
    distributor_id: int | None = None
    pod_quarter: str | None = None
    srp: float | None = None
    vat_rate: float | None = None
    dealer_margin_pct: float | None = None
    cost_basis: float | None = None
    cost_source: str | None = None
    estimate_qty: float | None = None
    cap_qty: float | None = None
    soh_snapshot: float | None = None
    remark: str | None = None
    result_qty: float | None = None


class RejectBody(BaseModel):
    comment: str = Field(min_length=1)


class TransitionBody(BaseModel):
    action: str
    comment: str | None = None


class LayerSplitBody(BaseModel):
    layers: list[dict[str, Any]] = Field(
        ...,
        description="Each item: {pod_quarter, estimate_qty?, cost_basis?, soh_snapshot?, distributor_id?}",
        min_length=1,
    )


# --- case CRUD ---------------------------------------------------------------


@router.get("/cases")
def list_cases(
    status: str | None = Query(default=None),
    customer_id: int | None = Query(default=None),
    q: str | None = Query(default=None),
):
    with SessionLocal() as session:
        stmt = (
            select(CporCase, DimCustomer)
            .join(DimCustomer, DimCustomer.id == CporCase.customer_id)
            .order_by(CporCase.id.desc())
        )
        if status:
            if status not in CPOR_CASE_STATUS_SET:
                raise HTTPException(status_code=400, detail=f"Unknown status={status}")
            stmt = stmt.where(CporCase.status == status)
        if customer_id is not None:
            stmt = stmt.where(CporCase.customer_id == customer_id)
        if q and q.strip():
            needle = f"%{q.strip()}%"
            stmt = stmt.where(
                (CporCase.case_code.ilike(needle))
                | (CporCase.case_name.ilike(needle))
                | (DimCustomer.code.ilike(needle))
                | (DimCustomer.name.ilike(needle))
            )
        rows = session.execute(stmt).all()
        out = []
        for case, cust in rows:
            lines = session.scalars(select(CporCaseLine).where(CporCaseLine.case_id == case.id)).all()
            pmap = _products_map(session, [int(l.product_id) for l in lines])
            line_jsons = [_line_json(l, pmap.get(int(l.product_id))) for l in lines]
            out.append(_case_json(case, customer=cust, lines=line_jsons, include_lines=False))
        return out


@router.post("/cases", status_code=201)
def create_case(body: CaseCreate, x_user_id: str | None = Header(default=None, alias="X-User-Id")):
    actor = _actor(x_user_id)
    if body.promotion_type not in CPOR_PROMOTION_TYPE_SET:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown promotion_type; allowed={sorted(CPOR_PROMOTION_TYPE_SET)}",
        )
    if body.window_end < body.window_start:
        raise HTTPException(status_code=400, detail="window_end must be >= window_start")
    with SessionLocal() as session:
        cust = session.get(DimCustomer, body.customer_id)
        if not cust:
            raise HTTPException(status_code=400, detail=f"Unknown customer_id={body.customer_id}")
        code = (body.case_code or "").strip() or _generate_case_code(session)
        case = CporCase(
            case_code=code,
            case_name=(body.case_name or "").strip() or None,
            customer_id=body.customer_id,
            promotion_type=body.promotion_type,
            window_start=body.window_start,
            window_end=body.window_end,
            status="draft",
            roe_snapshot=body.roe_snapshot,
            currency_code=body.currency_code or "ZAR",
            channel=body.channel or "reseller",
            notes=body.notes,
            created_by=actor,
            export_version=1,
            workflow_status="draft",
        )
        session.add(case)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            raise HTTPException(status_code=409, detail="case_code already exists")
        _record_event(session, case_id=case.id, event_type="created", actor=actor, payload={"case_code": code})
        session.commit()
        session.refresh(case)
        return _case_json(case, customer=cust, lines=[], include_lines=True)


@router.get("/cases/{case_id}")
def get_case(case_id: int):
    with SessionLocal() as session:
        case = _load_case(session, case_id)
        cust = session.get(DimCustomer, case.customer_id)
        lines = session.scalars(select(CporCaseLine).where(CporCaseLine.case_id == case.id)).all()
        pmap = _products_map(session, [int(l.product_id) for l in lines])
        line_jsons = [_line_json(l, pmap.get(int(l.product_id))) for l in lines]
        return _case_json(case, customer=cust, lines=line_jsons, include_lines=True)


@router.patch("/cases/{case_id}")
def patch_case(
    case_id: int,
    body: CasePatch,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    actor = _actor(x_user_id)
    with SessionLocal() as session:
        case = _load_case(session, case_id)
        if case.status not in EDITABLE_STATUSES:
            raise HTTPException(
                status_code=409,
                detail=f"Case header not editable in status={case.status}; allowed={sorted(EDITABLE_STATUSES)}",
            )
        data = body.model_dump(exclude_unset=True)
        if not data:
            raise HTTPException(status_code=400, detail="No fields to update")
        if "promotion_type" in data and data["promotion_type"] not in CPOR_PROMOTION_TYPE_SET:
            raise HTTPException(status_code=400, detail="Unknown promotion_type")
        roe_changed = "roe_snapshot" in data
        for k, v in data.items():
            setattr(case, k, v)
        session.add(case)
        _record_event(session, case_id=case.id, event_type="case_patched", actor=actor, payload=data)
        recompute_report = None
        if roe_changed:
            recompute_report = recompute_case(session, case, actor=actor)
        session.commit()
        session.refresh(case)
        cust = session.get(DimCustomer, case.customer_id)
        lines = session.scalars(select(CporCaseLine).where(CporCaseLine.case_id == case.id)).all()
        pmap = _products_map(session, [int(l.product_id) for l in lines])
        line_jsons = [_line_json(l, pmap.get(int(l.product_id))) for l in lines]
        out = _case_json(case, customer=cust, lines=line_jsons, include_lines=True)
        if recompute_report:
            out["recompute"] = recompute_report
        return out


# --- lines -------------------------------------------------------------------


@router.post("/cases/{case_id}/lines", status_code=201)
def create_line(
    case_id: int,
    body: LineCreate,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    actor = _actor(x_user_id)
    with SessionLocal() as session:
        case = _load_case(session, case_id)
        if case.status not in EDITABLE_STATUSES and case.status not in {"proposed", "approved", "active"}:
            # allow line edits in draft/rejected primarily; also active for estimate tweaks is U5 territory —
            # keep to editable for U3
            if case.status not in EDITABLE_STATUSES:
                raise HTTPException(status_code=409, detail=f"Lines not editable in status={case.status}")
        prod = session.get(DimProduct, body.product_id)
        if not prod:
            raise HTTPException(status_code=400, detail=f"Unknown product_id={body.product_id}")

        margin = body.dealer_margin_pct
        margin_source = "manual_override"
        if margin is None:
            default_m, src = resolve_default_margin(session, case.customer_id)
            if default_m is None:
                raise HTTPException(
                    status_code=400,
                    detail="No dealer_margin_pct provided and no commercial_customer_term default",
                )
            margin = float(default_m)
            margin_source = src or "customer_default"

        as_of = case.created_at.date() if case.created_at else date.today()
        cost_basis = body.cost_basis
        cost_source = body.cost_source
        cost_evidence: dict | None = None

        if cost_basis is not None and (cost_source == "manual" or body.accept_cost_suggestion is False):
            sug = suggest_cost_basis(
                session,
                customer_id=case.customer_id,
                product_id=body.product_id,
                as_of=as_of,
                exclude_case_id=case.id,
                manual_cost=cost_basis,
            )
            cost_source = "manual"
            cost_evidence = {**sug.evidence, "flags": sug.flags}
        elif body.accept_cost_suggestion:
            sug = suggest_cost_basis(
                session,
                customer_id=case.customer_id,
                product_id=body.product_id,
                as_of=as_of,
                exclude_case_id=case.id,
                manual_cost=cost_basis if cost_source == "manual" else None,
            )
            if cost_basis is None and sug.cost_basis is not None:
                cost_basis = float(sug.cost_basis)
                cost_source = sug.cost_source
            cost_evidence = {**sug.evidence, "flags": sug.flags}
            if cost_basis is None:
                cost_evidence = cost_evidence or {"flags": ["no_cost_evidence"]}

        line = CporCaseLine(
            case_id=case.id,
            product_id=body.product_id,
            distributor_id=body.distributor_id,
            pod_quarter=body.pod_quarter,
            srp=body.srp,
            vat_rate=body.vat_rate,
            dealer_margin_pct=margin,
            margin_source=margin_source,
            cost_basis=cost_basis,
            cost_source=cost_source,
            cost_evidence_json=cost_evidence,
            estimate_qty=body.estimate_qty,
            cap_qty=body.cap_qty,
            soh_snapshot=body.soh_snapshot,
            remark=body.remark,
        )
        session.add(line)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            raise HTTPException(
                status_code=409,
                detail="Line grain conflict (case × product × distributor × pod_quarter must be unique)",
            )
        rep = recompute_case_line(session, line, case=case, actor=actor, write_event=False)
        _record_event(
            session,
            case_id=case.id,
            event_type="line_created",
            actor=actor,
            payload={"line_id": line.id, "recompute_flags": rep["flags"]},
        )
        session.commit()
        session.refresh(line)
        return _line_json(line, prod)


@router.patch("/cases/{case_id}/lines/{line_id}")
def patch_line(
    case_id: int,
    line_id: int,
    body: LinePatch,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    actor = _actor(x_user_id)
    with SessionLocal() as session:
        case = _load_case(session, case_id)
        if case.status not in EDITABLE_STATUSES:
            raise HTTPException(status_code=409, detail=f"Lines not editable in status={case.status}")
        line = session.get(CporCaseLine, line_id)
        if not line or line.case_id != case.id:
            raise HTTPException(status_code=404, detail="Line not found")
        data = body.model_dump(exclude_unset=True)
        if not data:
            raise HTTPException(status_code=400, detail="No fields to update")
        if "dealer_margin_pct" in data:
            line.margin_source = "manual_override"
        if "cost_basis" in data:
            line.cost_source = data.get("cost_source") or "manual"
            sug = suggest_cost_basis(
                session,
                customer_id=case.customer_id,
                product_id=line.product_id,
                as_of=case.created_at.date() if case.created_at else date.today(),
                exclude_case_id=case.id,
                manual_cost=data["cost_basis"],
            )
            line.cost_evidence_json = {**sug.evidence, "flags": sug.flags}
        for k, v in data.items():
            if k == "cost_source" and "cost_basis" in data:
                continue
            setattr(line, k, v)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            raise HTTPException(status_code=409, detail="Line grain conflict")
        rep = recompute_case_line(session, line, case=case, actor=actor, write_event=False)
        _record_event(
            session,
            case_id=case.id,
            event_type="line_patched",
            actor=actor,
            payload={"line_id": line.id, "fields": list(data.keys()), "flags": rep["flags"]},
        )
        session.commit()
        session.refresh(line)
        prod = session.get(DimProduct, line.product_id)
        return _line_json(line, prod)


@router.post("/cases/{case_id}/lines/{line_id}/void")
def void_line(
    case_id: int,
    line_id: int,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    """Soft-remove: zero estimate + remark; no hard delete. Row retained."""
    actor = _actor(x_user_id)
    with SessionLocal() as session:
        case = _load_case(session, case_id)
        if case.status not in EDITABLE_STATUSES:
            raise HTTPException(status_code=409, detail=f"Lines not editable in status={case.status}")
        line = session.get(CporCaseLine, line_id)
        if not line or line.case_id != case.id:
            raise HTTPException(status_code=404, detail="Line not found")
        line.estimate_qty = 0
        line.cap_qty = 0
        line.remark = (line.remark or "") + " [voided]"
        recompute_case_line(session, line, case=case, write_event=False)
        _record_event(
            session,
            case_id=case.id,
            event_type="line_voided",
            actor=actor,
            payload={"line_id": line.id},
        )
        session.commit()
        session.refresh(line)
        prod = session.get(DimProduct, line.product_id)
        return _line_json(line, prod)


@router.post("/cases/{case_id}/lines/{line_id}/split-layers", status_code=201)
def split_layers(
    case_id: int,
    line_id: int,
    body: LayerSplitBody,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    """Clone a line into explicit POD-quarter layers (no FIFO fabrication)."""
    actor = _actor(x_user_id)
    with SessionLocal() as session:
        case = _load_case(session, case_id)
        if case.status not in EDITABLE_STATUSES:
            raise HTTPException(status_code=409, detail=f"Lines not editable in status={case.status}")
        src = session.get(CporCaseLine, line_id)
        if not src or src.case_id != case.id:
            raise HTTPException(status_code=404, detail="Line not found")
        created = []
        for layer in body.layers:
            pq = layer.get("pod_quarter")
            if not pq:
                raise HTTPException(status_code=400, detail="Each layer requires pod_quarter")
            new_line = CporCaseLine(
                case_id=case.id,
                product_id=src.product_id,
                distributor_id=layer.get("distributor_id", src.distributor_id),
                pod_quarter=str(pq),
                srp=src.srp,
                vat_rate=src.vat_rate,
                dealer_margin_pct=src.dealer_margin_pct,
                margin_source=src.margin_source,
                cost_basis=layer.get("cost_basis", src.cost_basis),
                cost_source=src.cost_source if layer.get("cost_basis") is None else "manual",
                cost_evidence_json=src.cost_evidence_json,
                estimate_qty=layer.get("estimate_qty", src.estimate_qty),
                cap_qty=src.cap_qty,
                soh_snapshot=layer.get("soh_snapshot", src.soh_snapshot),
                remark=src.remark,
            )
            session.add(new_line)
            try:
                session.flush()
            except IntegrityError:
                session.rollback()
                raise HTTPException(status_code=409, detail=f"Layer grain conflict for pod_quarter={pq}")
            recompute_case_line(session, new_line, case=case, write_event=False)
            created.append(new_line)
        # Soft-void source after split
        src.estimate_qty = 0
        src.remark = (src.remark or "") + " [split into layers]"
        recompute_case_line(session, src, case=case, write_event=False)
        _record_event(
            session,
            case_id=case.id,
            event_type="line_split_layers",
            actor=actor,
            payload={"source_line_id": src.id, "new_line_ids": [l.id for l in created]},
        )
        session.commit()
        prod = session.get(DimProduct, src.product_id)
        return {
            "source": _line_json(src, prod),
            "layers": [_line_json(l, prod) for l in created],
        }


# --- utilities ---------------------------------------------------------------


@router.post("/cases/{case_id}/recompute")
def recompute(case_id: int, x_user_id: str | None = Header(default=None, alias="X-User-Id")):
    actor = _actor(x_user_id)
    with SessionLocal() as session:
        case = _load_case(session, case_id)
        report = recompute_case(session, case, actor=actor)
        session.commit()
        return report


@router.get("/cases/{case_id}/lines/{line_id}/cost-suggest")
def cost_suggest(case_id: int, line_id: int):
    with SessionLocal() as session:
        case = _load_case(session, case_id)
        line = session.get(CporCaseLine, line_id)
        if not line or line.case_id != case.id:
            raise HTTPException(status_code=404, detail="Line not found")
        as_of = case.created_at.date() if case.created_at else date.today()
        sug = suggest_cost_basis(
            session,
            customer_id=case.customer_id,
            product_id=line.product_id,
            as_of=as_of,
            exclude_case_id=case.id,
        )
        return {
            "line_id": line.id,
            "cost_basis": float(sug.cost_basis) if sug.cost_basis is not None else None,
            "cost_source": sug.cost_source,
            "evidence": sug.evidence,
            "flags": sug.flags,
            "stored_cost_basis": float(line.cost_basis) if line.cost_basis is not None else None,
            "drift": detect_cost_basis_drift(line.cost_basis, sug),
        }


@router.get("/cases/{case_id}/events")
def list_events(case_id: int):
    with SessionLocal() as session:
        _load_case(session, case_id)
        rows = session.scalars(
            select(CporCaseEvent).where(CporCaseEvent.case_id == case_id).order_by(CporCaseEvent.id.asc())
        ).all()
        return [
            {
                "id": e.id,
                "case_id": e.case_id,
                "event_type": e.event_type,
                "actor": e.actor,
                "payload_json": e.payload_json,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in rows
        ]


@router.get("/cases/{case_id}/pivot")
def case_pivot(case_id: int):
    """POD quarter × product_line → Ttl Support USD (sum of support_usd * estimate_qty)."""
    with SessionLocal() as session:
        case = _load_case(session, case_id)
        lines = list(session.scalars(select(CporCaseLine).where(CporCaseLine.case_id == case.id)).all())
        pmap = _products_map(session, [int(l.product_id) for l in lines])
        return build_case_pivot(session, case, lines, pmap)


# --- lifecycle ---------------------------------------------------------------


@router.post("/cases/{case_id}/transition")
def transition_case(
    case_id: int,
    body: TransitionBody,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    actor = _actor(x_user_id)
    action = body.action.strip().lower()
    if action not in LIFECYCLE_ACTIONS:
        raise HTTPException(status_code=400, detail=f"Unknown action; allowed={sorted(LIFECYCLE_ACTIONS)}")
    if action == "reject" and not (body.comment and body.comment.strip()):
        raise HTTPException(status_code=400, detail="reject requires comment")

    with SessionLocal() as session:
        case = _load_case(session, case_id)
        if not can_transition(case.status, action):
            raise HTTPException(
                status_code=409,
                detail={
                    "message": f"Illegal transition {case.status} --{action}-->",
                    "current": case.status,
                    "action": action,
                    "allowed_next": allowed_next(case.status),
                    "allowed_actions": [a for a, t in LIFECYCLE_ACTIONS.items() if can_transition(case.status, a)],
                },
            )

        drifts: list[dict] = []
        now = datetime.now(timezone.utc)
        from_status = case.status
        new_status = target_status(action)

        if action == "propose":
            case.status = "proposed"
            case.workflow_status = "pending_approval"
            case.submitted_at = now
            case.last_comment = None
        elif action == "approve":
            case.status = "approved"
            case.workflow_status = "approved"
            case.decided_at = now
            case.decided_by = actor
            case.last_comment = None
            drifts = _run_drift_check(session, case, actor)
        elif action == "reject":
            case.status = "rejected"
            case.workflow_status = "rejected"
            case.decided_at = now
            case.decided_by = actor
            case.last_comment = body.comment
        elif action == "resend":
            case.status = "proposed"
            case.workflow_status = "pending_approval"
            case.export_version = int(case.export_version or 1) + 1
            case.submitted_at = now
            case.decided_at = None
            case.decided_by = None
            case.last_comment = None
        elif action == "activate":
            case.status = "active"
            drifts = _run_drift_check(session, case, actor)
        elif action == "end":
            case.status = "ended"
        elif action == "settle":
            case.status = "settled"
        elif action == "cancel":
            case.status = "cancelled"

        session.add(case)
        _record_event(
            session,
            case_id=case.id,
            event_type=f"transition_{action}",
            actor=actor,
            payload={
                "from": from_status,
                "to": new_status,
                "action": action,
                "comment": body.comment,
                "export_version": case.export_version,
                "drifts": drifts,
            },
        )
        # Fix payload 'from' — we already mutated status; re-read from event is fine for U3
        session.commit()
        session.refresh(case)
        cust = session.get(DimCustomer, case.customer_id)
        lines = session.scalars(select(CporCaseLine).where(CporCaseLine.case_id == case.id)).all()
        pmap = _products_map(session, [int(l.product_id) for l in lines])
        line_jsons = [_line_json(l, pmap.get(int(l.product_id))) for l in lines]
        out = _case_json(case, customer=cust, lines=line_jsons, include_lines=True)
        out["drifts"] = drifts
        return out


@router.get("/intelligence/portfolio")
def cpor_portfolio_intelligence() -> dict[str, Any]:
    """A2-U1: support spend, delivery rate, support per unit sold (USD + ZAR display)."""
    with SessionLocal() as session:
        return build_portfolio_intelligence(session)


@router.get("/intelligence/norms")
def cpor_support_norms(
    trailing_quarters: int | None = Query(default=None, ge=1, le=16),
) -> dict[str, Any]:
    """A2-04: trailing-quarter support norms (absolute USD/ZAR + % of SRP)."""
    with SessionLocal() as session:
        return build_support_norms(session, trailing_quarters=trailing_quarters)


@router.get("/intelligence/comparable-cases")
def cpor_comparable_cases(
    case_id: int = Query(..., ge=1),
    limit: int = Query(25, ge=1, le=200),
) -> dict[str, Any]:
    """A2-05: ranked comparable cases (customer → BU → promo → quarter → volume)."""
    with SessionLocal() as session:
        return build_comparable_cases(session, case_id=case_id, limit=limit)


@router.get("/intelligence/promo-plan-draft")
def cpor_promo_plan_draft(
    seed_case_id: int = Query(..., ge=1),
    product_id: int | None = Query(default=None),
    customer_id: int | None = Query(default=None),
    planned_support_usd: float | None = Query(default=None, ge=0),
    planned_revenue_usd: float | None = Query(default=None, ge=0),
    period_label: str | None = Query(default=None),
    horizon_weeks: int = Query(default=13, ge=1, le=52),
    comparable_limit: int = Query(default=10, ge=1, le=50),
) -> dict[str, Any]:
    """B4 — draft promo plan: A2 comparables + B1 forecast volume + B2 budget check."""
    with SessionLocal() as session:
        return build_promo_plan_draft(
            session,
            seed_case_id=seed_case_id,
            product_id=product_id,
            customer_id=customer_id,
            planned_support_usd=planned_support_usd,
            planned_revenue_usd=planned_revenue_usd,
            period_label=period_label,
            horizon_weeks=horizon_weeks,
            comparable_limit=comparable_limit,
        )


@router.get("/meta/promotion-types")
def promotion_types():
    return {"promotion_types": sorted(CPOR_PROMOTION_TYPE_SET)}


# --- settlement (U5) ---------------------------------------------------------


@router.get("/cases/{case_id}/settlement")
def get_settlement(case_id: int):
    with SessionLocal() as session:
        _load_case(session, case_id)
        return build_settlement_consolidation(session, case_id)


@router.post("/cases/{case_id}/claim-evidence/import")
async def import_claim_evidence(
    case_id: int,
    file: UploadFile = File(...),
    include_out_of_window: bool = Form(default=False),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    """Case-scoped claim evidence upload → upsert cpor_claim_evidence_line + rollup."""
    actor = _actor(x_user_id)
    raw = await file.read()
    with SessionLocal() as session:
        _load_case(session, case_id)
        result = apply_claim_evidence_to_case(
            session,
            case_id=case_id,
            filename=file.filename or "claim.csv",
            raw_bytes=raw,
            include_out_of_window=bool(include_out_of_window),
        )
        if not result.get("ok"):
            raise HTTPException(status_code=422, detail=result)
        rollup = rollup_result_qty_from_claims(session, case_id, actor=actor)
        _record_event(
            session,
            case_id=case_id,
            event_type="claim_evidence_imported",
            actor=actor,
            payload={"import": result, "rollup": rollup},
        )
        session.commit()
        consolidation = build_settlement_consolidation(session, case_id)
        return {"import": result, "rollup": rollup, "settlement": consolidation}


@router.post("/cases/{case_id}/settlement/rollup")
def post_settlement_rollup(
    case_id: int,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    actor = _actor(x_user_id)
    with SessionLocal() as session:
        _load_case(session, case_id)
        rollup = rollup_result_qty_from_claims(session, case_id, actor=actor)
        session.commit()
        return {"rollup": rollup, "settlement": build_settlement_consolidation(session, case_id)}


@router.get("/meta/lifecycle")
def lifecycle_meta():
    return {
        "statuses": sorted(CPOR_CASE_STATUS_SET),
        "actions": LIFECYCLE_ACTIONS,
        "transitions": {k: sorted(v) for k, v in LIFECYCLE_TRANSITIONS.items()},
    }
