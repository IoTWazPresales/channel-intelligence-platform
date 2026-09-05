"""CPOR case / line API — Unit 3 (wires U1 models + U2 services). No client money math."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.core.tenant_scope import tenant_id_from_user, where_tenant
from app.db.session_sync import SessionLocal
from app.models.cpor import CporCase, CporCaseEvent, CporCaseLine, CporClaimEvidenceLine
from app.models.dimensions import DimCustomer, DimProduct
from app.services.cpor.claim_evidence_apply import apply_claim_evidence_to_case
from app.services.cpor.cost_suggestion import (
    CostSuggestion,
    detect_cost_basis_drift,
    resolve_default_margin,
    suggest_cost_basis,
)
from app.services.cpor.intake_weighted_mac import suggest_intake_weighted_mac
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
from app.services.cpor.promo_plan_builder import build_promo_plan_draft, create_case_from_promo_draft
from app.services.cpor.portfolio_intelligence import build_portfolio_intelligence
from app.services.cpor.settlement_book_read import build_settlement_book_read_model
from app.services.cpor.support_bias import build_support_bias
from app.services.cpor.payment_recon import load_payment_recon_by_case_id
from app.services.cpor.promo_load_recon import build_promo_load_recon
from app.services.cpor.promotion_type_vocab import CPOR_CASE_STATUS_SET, CPOR_PROMOTION_TYPE_SET
from app.services.cpor.recompute import recompute_case, recompute_case_line
from app.services.cpor.fx_rate import (
    SOURCE_OPERATOR,
    apply_create_fx,
    book_on_approve,
    fx_fields_json,
    set_proposed,
)
from app.services.cpor.settle_readiness import (
    build_settle_readiness,
    case_missing_roe,
    count_open_assumptions_from_line_flags,
    fx_declared,
    fx_mode_valid,
    FX_MODES,
    load_claim_counts_by_case_id,
    load_settle_readiness_by_case_id,
    settle_fx_blocked,
)
from app.services.cpor.settlement import (
    build_settlement_consolidation,
    rollup_result_qty_from_claims,
)

router = APIRouter()


# --- helpers -----------------------------------------------------------------


def _actor(user: dict) -> str:
    """Stable non-null identifier from the authenticated user — never a request header."""
    raw = user.get("id")
    ident = str(raw).strip() if raw is not None else ""
    if not ident:
        raise HTTPException(status_code=500, detail="Authenticated user missing id")
    return ident


def _actor_trail(user: dict) -> dict[str, Any]:
    trail: dict[str, Any] = {}
    email = user.get("email")
    if isinstance(email, str) and email.strip():
        trail["actor_email"] = email.strip()
    role = user.get("role")
    if role is not None:
        trail["actor_role"] = str(getattr(role, "value", role))
    return trail


def _record_event(
    session: Session,
    *,
    case_id: int,
    event_type: str,
    actor: str | None,
    payload: dict | None = None,
    user: dict | None = None,
) -> None:
    payload_json: dict[str, Any] | None
    if payload is None and user is None:
        payload_json = None
    else:
        payload_json = dict(payload or {})
        if user is not None:
            payload_json.update(_actor_trail(user))
    session.add(
        CporCaseEvent(
            case_id=case_id,
            event_type=event_type,
            actor=actor,
            payload_json=payload_json,
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
        "fx_mode": getattr(case, "fx_mode", None),
        "fx_declared_at": case.fx_declared_at.isoformat() if getattr(case, "fx_declared_at", None) else None,
        "fx_declared_by": getattr(case, "fx_declared_by", None),
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
        "needs_reapproval": bool(getattr(case, "needs_reapproval", False)),
        "superseded_by_case_id": case.superseded_by_case_id,
        "allowed_next": allowed_next(case.status),
        "ttl_support_zar": ttl_zar,
        "ttl_support_usd": ttl_usd,
        "missing_roe": case_missing_roe(case),
        "origin": getattr(case, "origin", None) or "native",
        **fx_fields_json(case),
    }
    if include_lines and lines is not None:
        out["lines"] = lines
        all_flags: list[str] = []
        for l in lines:
            all_flags.extend(l.get("flags") or [])
        out["flags"] = sorted(set(all_flags))
    return out


def _cost_suggestion_json(sug: CostSuggestion) -> dict[str, Any]:
    return {
        "cost_basis": float(sug.cost_basis) if sug.cost_basis is not None else None,
        "cost_source": sug.cost_source,
        "evidence": sug.evidence,
        "flags": sug.flags,
    }


def _last_claim_sale_by_case_id(session: Session, case_ids: list[int]) -> dict[int, date]:
    """Max claim sale_date per case — ageing is days since claim, never window_end."""
    if not case_ids:
        return {}
    rows = session.execute(
        select(CporClaimEvidenceLine.case_id, func.max(CporClaimEvidenceLine.sale_date))
        .where(CporClaimEvidenceLine.case_id.in_(case_ids))
        .group_by(CporClaimEvidenceLine.case_id)
    ).all()
    return {int(cid): d for cid, d in rows if d is not None}


def _case_line_aggregates(session: Session, case_ids: list[int]) -> dict[int, dict[str, Any]]:
    """Set-based line totals for the list view.

    List support must be the waterfall sum of ``cpor_case_line.ttl_support`` — the same figure
    the case workspace shows — never payment-recon ``owed_amount``.
    """
    if not case_ids:
        return {}
    rows = session.execute(
        select(
            CporCaseLine.case_id,
            func.count(CporCaseLine.id),
            func.sum(CporCaseLine.estimate_qty),
            func.sum(CporCaseLine.ttl_support),
            func.sum(CporCaseLine.ttl_support_usd),
        )
        .where(CporCaseLine.case_id.in_(case_ids))
        .group_by(CporCaseLine.case_id)
    ).all()
    out: dict[int, dict[str, Any]] = {}
    for case_id, n_lines, est, ttl, ttl_usd in rows:
        out[int(case_id)] = {
            "line_count": int(n_lines or 0),
            "estimate_qty_sum": float(est) if est is not None else None,
            "ttl_support": float(ttl) if ttl is not None else None,
            "ttl_support_usd": float(ttl_usd) if ttl_usd is not None else None,
        }
    return out


def _status_counts(session: Session, user: dict) -> dict[str, int]:
    rows = session.execute(
        select(CporCase.status, func.count())
        .where(where_tenant(CporCase.tenant_id, user))
        .group_by(CporCase.status)
    ).all()
    return {str(status): int(n) for status, n in rows}


def _review_queue_count(session: Session, user: dict) -> int:
    """Proposed cases plus any current case flagged for money-ceiling reapproval."""
    return int(
        session.scalar(
            select(func.count())
            .select_from(CporCase)
            .where(where_tenant(CporCase.tenant_id, user))
            .where(CporCase.superseded_by_case_id.is_(None))
            .where(or_(CporCase.status == "proposed", CporCase.needs_reapproval.is_(True)))
        )
        or 0
    )


def _load_case(session: Session, case_id: int, user: dict | None = None) -> CporCase:
    case = session.get(CporCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="CPOR case not found")
    if user is not None and (case.tenant_id or "default") != tenant_id_from_user(user):
        raise HTTPException(status_code=404, detail="CPOR case not found")
    return case


def _products_map(session: Session, product_ids: list[int]) -> dict[int, DimProduct]:
    if not product_ids:
        return {}
    rows = session.scalars(select(DimProduct).where(DimProduct.id.in_(product_ids))).all()
    return {int(p.id): p for p in rows}


def _run_drift_check(session: Session, case: CporCase, actor: str | None, user: dict) -> list[dict]:
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
            user=user,
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
    fx_proposed_rate: float | None = None
    fx_mode: str | None = None
    currency_code: str = "ZAR"
    channel: str = "reseller"
    notes: str | None = None


class CasePatch(BaseModel):
    case_name: str | None = None
    promotion_type: str | None = None
    window_start: date | None = None
    window_end: date | None = None
    roe_snapshot: float | None = None
    fx_proposed_rate: float | None = None
    fx_mode: str | None = None
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
    confirm_over_budget_reapproval: bool = False
    fx_rate: float | None = None


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
    page: int | None = Query(default=None, ge=1),
    page_size: int | None = Query(default=None, ge=1, le=500),
    user: dict = Depends(get_current_user),
):
    """List CPOR cases.

    Legacy: no page → JSON array (existing clients/tests).
    Paginated: page+page_size → {items, total, page, page_size} for MasterDataGridShell.
    """
    with SessionLocal() as session:
        stmt = (
            select(CporCase, DimCustomer)
            .join(DimCustomer, DimCustomer.id == CporCase.customer_id)
            .where(where_tenant(CporCase.tenant_id, user))
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

        paginate = page is not None and page_size is not None
        if paginate:
            count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
            total = int(session.scalar(count_stmt) or 0)
            stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        else:
            total = None

        rows = session.execute(stmt).all()
        cases = [case for case, _ in rows]
        cust_map = {cust.id: cust for _, cust in rows}
        recon_by = load_payment_recon_by_case_id(session, cases, customers=cust_map)
        readiness_by = load_settle_readiness_by_case_id(session, cases)
        line_agg = _case_line_aggregates(session, [c.id for c in cases])
        claim_sale_by = _last_claim_sale_by_case_id(session, [c.id for c in cases])
        status_counts = _status_counts(session, user)
        review_queue_count = _review_queue_count(session, user)

        out = []
        for case, cust in rows:
            # List view: do not N+1 load every case line into JSON.
            # Support totals come from a set-based line aggregate (same grain as the workspace).
            # Owed/paid/outstanding stay on the payment-recon fields — they are not support.
            row = _case_json(case, customer=cust, lines=None, include_lines=False)
            recon = recon_by.get(case.id) or {}
            agg = line_agg.get(case.id) or {}
            row["line_count"] = int(agg.get("line_count") or 0)
            row["estimate_qty_sum"] = agg.get("estimate_qty_sum")
            row["ttl_support_zar"] = agg.get("ttl_support")
            if agg.get("ttl_support_usd") is not None:
                row["ttl_support_usd"] = agg["ttl_support_usd"]
            row["payment_evidence_count"] = int(recon.get("payment_evidence_count") or 0)
            row["paid_amount_sum"] = recon.get("paid_amount")
            row["owed_amount"] = recon.get("owed_amount")
            row["outstanding_amount"] = recon.get("outstanding_amount")
            row["recon_status"] = recon.get("recon_status")
            row["recon_flags"] = recon.get("flags") or []
            row["last_payment_date"] = recon.get("last_payment_date")
            row["latest_payment_status"] = recon.get("latest_payment_status")
            row["credit_note_ids"] = recon.get("credit_note_ids") or []
            row["settle_readiness"] = readiness_by.get(
                case.id,
                build_settle_readiness(case, claim_row_count=0, open_assumption_count=0),
            )
            sale = claim_sale_by.get(case.id)
            row["last_claim_sale_date"] = sale.isoformat() if sale is not None else None
            out.append(row)

        if paginate:
            return {
                "items": out,
                "total": total,
                "page": page,
                "page_size": page_size,
                "status_counts": status_counts,
                "review_queue_count": review_queue_count,
            }
        return out


@router.post("/cases", status_code=201)
def create_case(
    body: CaseCreate,
    user: dict = Depends(get_current_user),
):
    actor = _actor(user)
    if body.promotion_type not in CPOR_PROMOTION_TYPE_SET:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown promotion_type; allowed={sorted(CPOR_PROMOTION_TYPE_SET)}",
        )
    if body.window_end < body.window_start:
        raise HTTPException(status_code=400, detail="window_end must be >= window_start")
    fx_mode = (body.fx_mode or "booked").strip().lower() or "booked"
    if fx_mode not in FX_MODES:
        raise HTTPException(status_code=400, detail=f"fx_mode must be one of: {sorted(FX_MODES)}")
    with SessionLocal() as session:
        cust = session.get(DimCustomer, body.customer_id)
        if not cust:
            raise HTTPException(status_code=400, detail=f"Unknown customer_id={body.customer_id}")
        if (getattr(cust, "tenant_id", None) or "default") != tenant_id_from_user(user):
            raise HTTPException(status_code=400, detail=f"Unknown customer_id={body.customer_id}")
        code = (body.case_code or "").strip() or _generate_case_code(session)
        case = CporCase(
            case_code=code,
            case_name=(body.case_name or "").strip() or None,
            tenant_id=tenant_id_from_user(user),
            customer_id=body.customer_id,
            promotion_type=body.promotion_type,
            window_start=body.window_start,
            window_end=body.window_end,
            status="draft",
            roe_snapshot=body.roe_snapshot,
            fx_mode=fx_mode,
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
        apply_create_fx(
            session,
            case,
            actor=actor,
            proposed_override=body.fx_proposed_rate,
            explicit_roe=body.roe_snapshot,
        )
        _record_event(
            session, case_id=case.id, event_type="created", actor=actor, payload={"case_code": code}, user=user
        )
        session.commit()
        session.refresh(case)
        return _case_json(case, customer=cust, lines=[], include_lines=True)


@router.get("/cases/{case_id}")
def get_case(case_id: int, user: dict = Depends(get_current_user)):
    with SessionLocal() as session:
        case = _load_case(session, case_id, user=user)
        cust = session.get(DimCustomer, case.customer_id)
        lines = session.scalars(select(CporCaseLine).where(CporCaseLine.case_id == case.id)).all()
        pmap = _products_map(session, [int(l.product_id) for l in lines])
        line_jsons = [_line_json(l, pmap.get(int(l.product_id))) for l in lines]
        claim_count = load_claim_counts_by_case_id(session, [case.id]).get(int(case.id), 0)
        open_assumptions = sum(
            1
            for lj in line_jsons
            if count_open_assumptions_from_line_flags(lj.get("flags") or []) > 0
        )
        out = _case_json(case, customer=cust, lines=line_jsons, include_lines=True)
        out["settle_readiness"] = build_settle_readiness(
            case,
            claim_row_count=claim_count,
            open_assumption_count=open_assumptions,
        )
        return out


@router.patch("/cases/{case_id}")
def patch_case(
    case_id: int,
    body: CasePatch,
    user: dict = Depends(get_current_user),
):
    actor = _actor(user)
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
        if "fx_mode" in data:
            mode = (data["fx_mode"] or "").strip().lower() if data["fx_mode"] is not None else None
            if mode is not None and mode not in FX_MODES:
                raise HTTPException(status_code=400, detail=f"fx_mode must be one of: {sorted(FX_MODES)}")
            data["fx_mode"] = mode
        if "fx_proposed_rate" in data:
            proposed_val = data.pop("fx_proposed_rate")
            if proposed_val is not None and not set_proposed(
                case, float(proposed_val), actor, source=SOURCE_OPERATOR
            ):
                raise HTTPException(status_code=400, detail="fx_proposed_rate must be a positive number")
        if "roe_snapshot" in data and not fx_declared(case):
            roe_val = data.pop("roe_snapshot")
            if roe_val is not None and not set_proposed(case, float(roe_val), actor, source=SOURCE_OPERATOR):
                raise HTTPException(status_code=400, detail="roe_snapshot must be a positive number")
        roe_changed = "roe_snapshot" in data
        fx_mode_changed = "fx_mode" in data
        for k, v in data.items():
            setattr(case, k, v)
        if fx_declared(case) and not fx_mode_valid(case):
            raise HTTPException(
                status_code=400,
                detail="fx_mode (booked or floating) required when ROE is declared",
            )
        if fx_declared(case) and fx_mode_valid(case) and (roe_changed or fx_mode_changed):
            case.fx_declared_at = datetime.now(timezone.utc)
            case.fx_declared_by = actor
        session.add(case)
        _record_event(session, case_id=case.id, event_type="case_patched", actor=actor, payload=data, user=user)
        recompute_report = None
        if roe_changed:
            recompute_report = recompute_case(session, case, actor=actor)
        session.commit()
        session.refresh(case)
        cust = session.get(DimCustomer, case.customer_id)
        lines = session.scalars(select(CporCaseLine).where(CporCaseLine.case_id == case.id)).all()
        pmap = _products_map(session, [int(l.product_id) for l in lines])
        line_jsons = [_line_json(l, pmap.get(int(l.product_id))) for l in lines]
        claim_count = load_claim_counts_by_case_id(session, [case.id]).get(int(case.id), 0)
        open_assumptions = sum(
            1
            for lj in line_jsons
            if count_open_assumptions_from_line_flags(lj.get("flags") or []) > 0
        )
        out = _case_json(case, customer=cust, lines=line_jsons, include_lines=True)
        out["settle_readiness"] = build_settle_readiness(
            case,
            claim_row_count=claim_count,
            open_assumption_count=open_assumptions,
        )
        if recompute_report:
            out["recompute"] = recompute_report
        return out


# --- lines -------------------------------------------------------------------


@router.post("/cases/{case_id}/lines", status_code=201)
def create_line(
    case_id: int,
    body: LineCreate,
    user: dict = Depends(get_current_user),
):
    actor = _actor(user)
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
            user=user,
        )
        session.commit()
        session.refresh(line)
        return _line_json(line, prod)


@router.patch("/cases/{case_id}/lines/{line_id}")
def patch_line(
    case_id: int,
    line_id: int,
    body: LinePatch,
    user: dict = Depends(get_current_user),
):
    actor = _actor(user)
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
            user=user,
        )
        session.commit()
        session.refresh(line)
        prod = session.get(DimProduct, line.product_id)
        return _line_json(line, prod)


@router.post("/cases/{case_id}/lines/{line_id}/void")
def void_line(
    case_id: int,
    line_id: int,
    user: dict = Depends(get_current_user),
):
    """Soft-remove: zero estimate + remark; no hard delete. Row retained."""
    actor = _actor(user)
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
            user=user,
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
    user: dict = Depends(get_current_user),
):
    """Clone a line into explicit POD-quarter layers (no FIFO fabrication)."""
    actor = _actor(user)
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
            user=user,
        )
        session.commit()
        prod = session.get(DimProduct, src.product_id)
        return {
            "source": _line_json(src, prod),
            "layers": [_line_json(l, prod) for l in created],
        }


# --- utilities ---------------------------------------------------------------


@router.post("/cases/{case_id}/recompute")
def recompute(case_id: int, user: dict = Depends(get_current_user)):
    actor = _actor(user)
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
        intake = suggest_intake_weighted_mac(
            session,
            customer_id=case.customer_id,
            product_id=line.product_id,
            distributor_id=line.distributor_id,
            window_start=case.window_start,
            window_end=case.window_end,
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
            "intake_weighted": _cost_suggestion_json(intake),
            "intake_weighted_drift": detect_cost_basis_drift(line.cost_basis, intake),
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
    user: dict = Depends(get_current_user),
):
    actor = _actor(user)
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

        from app.services.cpor.budget_reapproval import (
            apply_reapproval_flag,
            evaluate_money_position,
            gate_detail,
            should_require_reapproval,
        )

        if action in ("propose", "resend"):
            # Include this case in committed draw once it becomes proposed.
            pos = evaluate_money_position(session, case_id=case.id, include_this_case=True)
            apply_reapproval_flag(session, case, money_over=bool(pos.get("money_over")))

        if action == "approve":
            pos = evaluate_money_position(session, case_id=case.id, include_this_case=True)
            apply_reapproval_flag(session, case, money_over=bool(pos.get("money_over")))
            if (
                tenant_profile_hard_enforce()
                and should_require_reapproval(
                    {**pos, "needs_reapproval": bool(case.needs_reapproval)}
                )
                and not body.confirm_over_budget_reapproval
            ):
                session.add(case)
                session.commit()
                pos = evaluate_money_position(session, case_id=case.id, include_this_case=True)
                raise HTTPException(status_code=409, detail=gate_detail(pos, action="approve"))

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
            case.needs_reapproval = False
            book_on_approve(case, actor=actor, override=body.fx_rate)
            drifts = _run_drift_check(session, case, actor, user)
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
            drifts = _run_drift_check(session, case, actor, user)
        elif action == "end":
            case.status = "ended"
        elif action == "settle":
            if settle_fx_blocked(case):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "fx_blocked",
                        "message": "Settle refused: declare positive ROE and fx_mode (booked or floating) before settling.",
                        "missing_roe": case_missing_roe(case),
                        "fx_mode": getattr(case, "fx_mode", None),
                        "fx_basis_line": build_settle_readiness(
                            case,
                            claim_row_count=load_claim_counts_by_case_id(session, [case.id]).get(int(case.id), 0),
                            open_assumption_count=0,
                        ).get("fx_basis_line"),
                    },
                )
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
                "confirm_over_budget_reapproval": body.confirm_over_budget_reapproval,
                "needs_reapproval": bool(case.needs_reapproval),
                "fx_rate": body.fx_rate,
                "roe_snapshot": float(case.roe_snapshot) if case.roe_snapshot is not None else None,
            },
            user=user,
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
        out["budget_gate"] = evaluate_money_position(session, case_id=case.id, include_this_case=True)
        return out


def tenant_profile_hard_enforce() -> bool:
    from app.services import commercial_tenant_profile as tenant_profile

    return bool(tenant_profile.HARD_ENFORCE_BUDGET)


@router.get("/settlement/book")
def cpor_settlement_book(user: dict = Depends(get_current_user)) -> dict[str, Any]:
    """NS-4 book read model: regime totals, shape segments, concentration."""
    _ = user
    with SessionLocal() as session:
        return build_settlement_book_read_model(session)


@router.get("/intelligence/portfolio")
def cpor_portfolio_intelligence() -> dict[str, Any]:
    """A2-U1: support spend, delivery rate, support per unit sold (USD + ZAR display).

    Also includes BACKLOG-089 incremental unit cost summary (FLAG when baseline weak).
    """
    with SessionLocal() as session:
        return build_portfolio_intelligence(session)


@router.get("/intelligence/incremental-unit-cost")
def cpor_incremental_unit_cost() -> dict[str, Any]:
    """BACKLOG-089: cost per incremental unit vs sell-through baseline (null when weak)."""
    from app.services.cpor.incremental_unit_cost import build_portfolio_incremental_summary

    with SessionLocal() as session:
        return build_portfolio_incremental_summary(session)


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


@router.get("/intelligence/support-bias")
def cpor_support_bias(
    period_start: date | None = Query(default=None),
    period_end: date | None = Query(default=None),
    customer_id: int | None = Query(default=None, ge=1),
    case_id: int | None = Query(default=None, ge=1),
    limit_cases: int = Query(default=200, ge=1, le=500),
) -> dict[str, Any]:
    """A1-09: planned campaign reservation (derived_from_profit) vs actual CPOR support USD."""
    with SessionLocal() as session:
        return build_support_bias(
            session,
            period_start=period_start,
            period_end=period_end,
            customer_id=customer_id,
            case_id=case_id,
            limit_cases=limit_cases,
        )


@router.get("/cases/{case_id}/promo-load-recon")
def cpor_promo_load_recon(case_id: int) -> dict[str, Any]:
    """BACKLOG-093: CST vs approved case terms (promo load). Not settlement claim recon."""
    with SessionLocal() as session:
        try:
            return build_promo_load_recon(session, case_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/cases/{case_id}/payment-recon")
def cpor_payment_recon(
    case_id: int,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """BACKLOG-092: paid vs owed. Owed = line ttl_support; paid = mapped evidence."""
    with SessionLocal() as session:
        case = _load_case(session, case_id, user)
        cust = session.get(DimCustomer, case.customer_id)
        recon = load_payment_recon_by_case_id(
            session, [case], customers={case.customer_id: cust} if cust else None
        )
        return recon[case.id]


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
    """B4 — draft promo plan: per-line A2 + B1 + intake-weighted MAC + B2 budget check."""
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


class PromoPlanDraftLineSpec(BaseModel):
    product_id: int = Field(ge=1)
    distributor_id: int | None = None
    pod_quarter: str | None = None
    srp: float | None = None
    estimate_qty: float | None = None
    cover_override: float | None = Field(default=None, ge=0, le=52)
    seed_line_id: int | None = None


class PromoPlanRecomputeBody(BaseModel):
    seed_case_id: int = Field(ge=1)
    product_id: int | None = None
    customer_id: int | None = None
    planned_support_usd: float | None = Field(default=None, ge=0)
    planned_revenue_usd: float | None = Field(default=None, ge=0)
    period_label: str | None = None
    horizon_weeks: int = Field(default=13, ge=1, le=52)
    comparable_limit: int = Field(default=10, ge=1, le=50)
    lines: list[PromoPlanDraftLineSpec] = Field(default_factory=list)


@router.post("/intelligence/promo-plan-draft/recompute")
def cpor_promo_plan_recompute(
    body: PromoPlanRecomputeBody,
    _user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Recompute per-line suggestions for the given identities. Dirty merge is client-owned (D-052)."""
    with SessionLocal() as session:
        return build_promo_plan_draft(
            session,
            seed_case_id=body.seed_case_id,
            product_id=body.product_id,
            customer_id=body.customer_id,
            planned_support_usd=body.planned_support_usd,
            planned_revenue_usd=body.planned_revenue_usd,
            period_label=body.period_label,
            horizon_weeks=body.horizon_weeks,
            comparable_limit=body.comparable_limit,
            line_specs=[row.model_dump() for row in body.lines] if body.lines else None,
        )


class PromoPlanCreateLineBody(BaseModel):
    product_id: int = Field(ge=1)
    distributor_id: int | None = None
    srp: float = Field(gt=0)
    estimate_qty: float = Field(gt=0)
    cost_basis: float | None = None
    cost_source: str | None = None
    pod_quarter: str | None = None
    cover_override: float | None = Field(default=None, ge=0, le=52)
    dirty_fields: list[str] = Field(default_factory=list)
    seed_line_id: int | None = None


class PromoPlanCreateFromDraftBody(BaseModel):
    seed_case_id: int = Field(ge=1)
    product_id: int | None = None
    period_label: str | None = None
    planned_support_usd: float | None = Field(default=None, ge=0)
    planned_revenue_usd: float | None = Field(default=None, ge=0)
    horizon_weeks: int = Field(default=13, ge=1, le=52)
    confirm_over_budget: bool = False
    lines: list[PromoPlanCreateLineBody] | None = None


@router.post("/intelligence/promo-plan-draft/create-case", status_code=201)
def cpor_promo_plan_create_case(
    body: PromoPlanCreateFromDraftBody,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """B4 — write a draft CPOR case from compose output (existing case/line path)."""
    actor = _actor(user)

    def _record_event_for_user(
        session,
        *,
        case_id: int,
        event_type: str,
        actor: str | None,
        payload: dict | None = None,
    ) -> None:
        _record_event(
            session,
            case_id=case_id,
            event_type=event_type,
            actor=actor,
            payload=payload,
            user=user,
        )

    with SessionLocal() as session:
        try:
            return create_case_from_promo_draft(
                session,
                seed_case_id=body.seed_case_id,
                product_id=body.product_id,
                period_label=body.period_label,
                planned_support_usd=body.planned_support_usd,
                planned_revenue_usd=body.planned_revenue_usd,
                horizon_weeks=body.horizon_weeks,
                confirm_over_budget=body.confirm_over_budget,
                actor=actor,
                lines=[row.model_dump() for row in body.lines] if body.lines is not None else None,
                generate_case_code=_generate_case_code,
                record_event=_record_event_for_user,
                recompute_case_line=recompute_case_line,
                resolve_default_margin=resolve_default_margin,
                suggest_cost_basis=suggest_cost_basis,
            )
        except ValueError as exc:
            msg = str(exc)
            code = 400
            if msg.startswith("seed_case_not_found"):
                code = 404
            raise HTTPException(status_code=code, detail=msg) from exc


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
    user: dict = Depends(get_current_user),
):
    """Case-scoped claim evidence upload → upsert cpor_claim_evidence_line + rollup."""
    actor = _actor(user)
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
            user=user,
        )
        session.commit()
        consolidation = build_settlement_consolidation(session, case_id)
        return {"import": result, "rollup": rollup, "settlement": consolidation}


@router.post("/cases/{case_id}/settlement/rollup")
def post_settlement_rollup(
    case_id: int,
    user: dict = Depends(get_current_user),
):
    actor = _actor(user)
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
