"""CPOR payment / CN evidence import API — validate, steward resolve, apply."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.endpoints.cpor_cases import _actor
from app.core.security import get_current_user
from app.db.session_sync import SessionLocal
from app.models.cpor_payment import CporPaymentEvidence, CporPaymentMappingProfile
from app.models.ingestion import ImportJob
from app.services.cpor.payment_evidence.overlay_read import (
    build_payment_evidence_overlay,
    cn_closed_date_from_raw,
    cn_status_from_raw,
    deduction_no_from_raw,
    latest_comment_from_raw,
)
from app.services.cpor.payment_evidence.pipeline import (
    apply_cpor_payment_evidence_job,
    ensure_default_payment_profile,
)
from app.services.cpor.payment_evidence.resolve import (
    list_unresolved_payment_tokens,
    map_payment_token,
    mark_shell_case_for_code,
    payment_job_summary,
    resolve_payment_staging,
)
from app.services.steward_audit import record_steward_audit_sync

router = APIRouter()
TEMPLATE_SLUG = "cpor_payment_evidence"


class MapTokenBody(BaseModel):
    entity: Literal["customer", "distributor"]
    token: str = Field(min_length=1, max_length=256)
    dim_id: int = Field(gt=0)
    create_shell_case: bool | None = None


class ShellCaseBody(BaseModel):
    case_code: str = Field(min_length=1, max_length=64)
    enabled: bool = True


class ApplyBody(BaseModel):
    confirm: bool = False


def _sync_db() -> Session:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _job_or_404(db: Session, job_id: int) -> ImportJob:
    job = db.get(ImportJob, job_id)
    if job is None or (job.template_slug or "") != TEMPLATE_SLUG:
        raise HTTPException(status_code=404, detail="Payment evidence import job not found")
    return job


@router.get("/payment-evidence/profiles")
def list_profiles(
    _user: Annotated[dict, Depends(get_current_user)] = None,
    db: Session = Depends(_sync_db),
) -> dict[str, Any]:
    ensure_default_payment_profile(db)
    rows = list(db.scalars(select(CporPaymentMappingProfile).order_by(CporPaymentMappingProfile.id)).all())
    return {
        "profiles": [
            {
                "id": r.id,
                "profile_code": r.profile_code,
                "display_name": r.display_name,
                "column_map_json": r.column_map_json,
                "sheet_roles_json": r.sheet_roles_json,
                "is_default": r.is_default,
            }
            for r in rows
        ]
    }


@router.get("/payment-evidence/overlay")
def payment_evidence_overlay(
    _user: Annotated[dict, Depends(get_current_user)] = None,
    db: Session = Depends(_sync_db),
) -> dict[str, Any]:
    """Applied-evidence overlay: exact Case ID match + pending Latest Comment. Read-only."""
    return build_payment_evidence_overlay(db)


@router.get("/payment-evidence/jobs/{job_id}/summary")
def job_summary(
    job_id: int,
    _user: Annotated[dict, Depends(get_current_user)] = None,
    db: Session = Depends(_sync_db),
) -> dict[str, Any]:
    job = _job_or_404(db, job_id)
    summary = payment_job_summary(db, job_id)
    meta = dict(job.staged_metadata or {}).get("cpor_payment_evidence") or {}
    return {
        "job_id": job_id,
        "status": job.status,
        "stage": job.stage,
        "summary": summary,
        "meta": meta,
    }


@router.get("/payment-evidence/jobs/{job_id}/candidates")
def candidates(
    job_id: int,
    entity: Literal["customer", "distributor", "case"] = Query(...),
    _user: Annotated[dict, Depends(get_current_user)] = None,
    db: Session = Depends(_sync_db),
) -> dict[str, Any]:
    _job_or_404(db, job_id)
    items = list_unresolved_payment_tokens(db, import_job_id=job_id, entity=entity)
    return {"entity": entity, "items": items, "total": len(items)}


@router.post("/payment-evidence/jobs/{job_id}/map-token")
def map_token(
    job_id: int,
    body: MapTokenBody,
    _user: Annotated[dict, Depends(get_current_user)] = None,
    db: Session = Depends(_sync_db),
) -> dict[str, Any]:
    _job_or_404(db, job_id)
    out = map_payment_token(
        db,
        import_job_id=job_id,
        entity=body.entity,
        token=body.token,
        entity_id=body.dim_id,
        create_shell_case=body.create_shell_case,
    )
    record_steward_audit_sync(
        _user,
        action="cpor_payment_map_token",
        importer="cpor_payment_evidence",
        entity_type=body.entity,
        entity_token=body.token,
        import_job_id=job_id,
        target_id=body.dim_id,
        payload=out,
        db=db,
    )
    return out


@router.post("/payment-evidence/jobs/{job_id}/mark-shell-case")
def mark_shell(
    job_id: int,
    body: ShellCaseBody,
    _user: Annotated[dict, Depends(get_current_user)] = None,
    db: Session = Depends(_sync_db),
) -> dict[str, Any]:
    _job_or_404(db, job_id)
    n = mark_shell_case_for_code(
        db, import_job_id=job_id, case_code=body.case_code, enabled=body.enabled
    )
    record_steward_audit_sync(
        _user,
        action="cpor_payment_mark_shell_case",
        importer="cpor_payment_evidence",
        entity_type="cpor_case",
        entity_token=body.case_code,
        import_job_id=job_id,
        payload={"enabled": body.enabled, "rows": n},
        db=db,
    )
    return {"case_code": body.case_code, "rows_updated": n, "enabled": body.enabled}


@router.post("/payment-evidence/jobs/{job_id}/re-resolve")
def re_resolve(
    job_id: int,
    _user: Annotated[dict, Depends(get_current_user)] = None,
    db: Session = Depends(_sync_db),
) -> dict[str, Any]:
    _job_or_404(db, job_id)
    stats = resolve_payment_staging(db, job_id)
    return {"resolve": stats, "summary": payment_job_summary(db, job_id)}


@router.post("/payment-evidence/jobs/{job_id}/apply")
def apply_job(
    job_id: int,
    body: ApplyBody,
    _user: Annotated[dict, Depends(get_current_user)] = None,
    db: Session = Depends(_sync_db),
) -> dict[str, Any]:
    if not body.confirm:
        raise HTTPException(status_code=400, detail="confirm=true required")
    job = _job_or_404(db, job_id)
    out = apply_cpor_payment_evidence_job(db, job, actor=_actor(_user))
    record_steward_audit_sync(
        _user,
        action="cpor_payment_apply",
        importer="cpor_payment_evidence",
        entity_type="import_job",
        import_job_id=job_id,
        payload=out,
        db=db,
    )
    return out


@router.get("/cases/{case_id}/payment-evidence")
def list_case_payment_evidence(
    case_id: int,
    _user: Annotated[dict, Depends(get_current_user)] = None,
    db: Session = Depends(_sync_db),
) -> dict[str, Any]:
    rows = list(
        db.scalars(
            select(CporPaymentEvidence)
            .where(CporPaymentEvidence.case_id == case_id)
            .order_by(CporPaymentEvidence.payment_date.desc().nullslast(), CporPaymentEvidence.id.desc())
        ).all()
    )
    # Also include unlinked rows matching case_code when case exists
    from app.models.cpor import CporCase

    case = db.get(CporCase, case_id)
    if case is not None:
        extras = list(
            db.scalars(
                select(CporPaymentEvidence).where(
                    CporPaymentEvidence.case_id.is_(None),
                    CporPaymentEvidence.external_case_code == case.case_code,
                )
            ).all()
        )
        seen = {r.id for r in rows}
        for e in extras:
            if e.id not in seen:
                rows.append(e)

    def _row(r: CporPaymentEvidence) -> dict[str, Any]:
        return {
            "id": r.id,
            "source_key": r.source_key,
            "external_case_code": r.external_case_code,
            "credit_note_id": r.credit_note_id,
            "case_status_raw": r.case_status_raw,
            "payment_status": r.payment_status,
            "payment_status_raw": r.payment_status_raw,
            "payment_date": r.payment_date.isoformat() if r.payment_date else None,
            "amount": float(r.amount) if r.amount is not None else None,
            "currency_code": r.currency_code,
            "customer_token": r.customer_token,
            "distributor_token": r.distributor_token,
            "description": r.description,
            "case_id": r.case_id,
            "latest_comment": latest_comment_from_raw(r.raw_source_row),
            "deduction_no": deduction_no_from_raw(r.raw_source_row),
            "cn_status": cn_status_from_raw(r.raw_source_row),
            "cn_closed_date": cn_closed_date_from_raw(r.raw_source_row),
        }

    return {"case_id": case_id, "items": [_row(r) for r in rows], "total": len(rows)}
