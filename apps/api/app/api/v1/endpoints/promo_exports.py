from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session_sync import SessionLocal
from app.models.dimensions import DimPromotion
from app.models.promo_export import PromoPlanExport, PromoPlanExportEvent
from app.services.promo_export.cpor_xlsx import TEMPLATE_CODE, build_promo_plan_workbook_bytes, validate_promotion_for_export
from app.services.promo_export.notify import maybe_send_export_email
from app.storage.local import LocalStorageBackend

router = APIRouter()


class RejectBody(BaseModel):
    comment: str = Field(min_length=1)


def _actor(x_user_id: str | None) -> str | None:
    return x_user_id


def _next_version(session: Session, promotion_id: int) -> int:
    current = session.scalar(
        select(func.coalesce(func.max(PromoPlanExport.export_version), 0)).where(PromoPlanExport.promotion_id == promotion_id)
    )
    return int(current or 0) + 1


def _record_event(
    session: Session,
    *,
    export_id: int,
    event_type: str,
    actor: str | None,
    comment: str | None = None,
    payload: dict | None = None,
) -> None:
    session.add(
        PromoPlanExportEvent(
            export_id=export_id,
            event_type=event_type,
            actor=actor,
            comment=comment,
            payload=payload,
        )
    )


@router.post("/{promotion_id}/exports/validate")
async def validate_export(
    promotion_id: int,
    customer_id: int | None = Query(default=None),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    _ = customer_id  # reserved for future row-level customer scoping on plans
    with SessionLocal() as session:
        promo = session.get(DimPromotion, promotion_id)
        if not promo:
            raise HTTPException(status_code=404, detail="Promotion not found")
        ok, errors, lines = validate_promotion_for_export(session, promotion_id)
        return {
            "promotion_id": promotion_id,
            "ok": ok,
            "errors": errors,
            "line_count": len(lines),
            "template_code": TEMPLATE_CODE,
            "actor": _actor(x_user_id),
        }


@router.post("/{promotion_id}/exports")
async def create_export(
    promotion_id: int,
    customer_id: int | None = Query(default=None),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    actor = _actor(x_user_id)
    storage = LocalStorageBackend()
    with SessionLocal() as session:
        promo = session.get(DimPromotion, promotion_id)
        if not promo:
            raise HTTPException(status_code=404, detail="Promotion not found")
        ok, errors, _lines = validate_promotion_for_export(session, promotion_id)
        if not ok:
            raise HTTPException(status_code=400, detail={"errors": errors})

        try:
            data, digest = build_promo_plan_workbook_bytes(
                session,
                promotion_id,
                default_customer_id=customer_id,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

        version = _next_version(session, promotion_id)
        export = PromoPlanExport(
            promotion_id=promotion_id,
            template_code=TEMPLATE_CODE,
            export_version=version,
            storage_key="pending",
            file_name=f"CPOR_PromoPlan_{promo.code}_v{version}.xlsx",
            checksum_sha256=digest,
            validation_status="passed",
            validation_detail=None,
            workflow_status="draft",
            created_by=actor,
        )
        session.add(export)
        session.flush()

        key = f"exports/promo/{export.id}/cpor_v{version}.xlsx"
        storage.save(key, data)
        export.storage_key = key
        _record_event(session, export_id=export.id, event_type="created", actor=actor, payload={"version": version})
        session.commit()
        session.refresh(export)
        return {
            "id": export.id,
            "promotion_id": export.promotion_id,
            "export_version": export.export_version,
            "template_code": export.template_code,
            "workflow_status": export.workflow_status,
            "validation_status": export.validation_status,
            "file_name": export.file_name,
            "checksum_sha256": export.checksum_sha256,
        }


@router.get("/{promotion_id}/exports")
async def list_exports(promotion_id: int):
    with SessionLocal() as session:
        promo = session.get(DimPromotion, promotion_id)
        if not promo:
            raise HTTPException(status_code=404, detail="Promotion not found")
        rows = session.execute(
            select(PromoPlanExport).where(PromoPlanExport.promotion_id == promotion_id).order_by(PromoPlanExport.export_version.desc())
        ).scalars().all()
        return [
            {
                "id": r.id,
                "export_version": r.export_version,
                "template_code": r.template_code,
                "workflow_status": r.workflow_status,
                "validation_status": r.validation_status,
                "file_name": r.file_name,
                "checksum_sha256": r.checksum_sha256,
                "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
                "decided_at": r.decided_at.isoformat() if r.decided_at else None,
                "decided_by": r.decided_by,
                "last_comment": r.last_comment,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]


@router.get("/exports/{export_id}/file")
async def download_export(export_id: int):
    storage = LocalStorageBackend()
    with SessionLocal() as session:
        export = session.get(PromoPlanExport, export_id)
        if not export:
            raise HTTPException(status_code=404, detail="Export not found")
        data = storage.read(export.storage_key)
        return StreamingResponse(
            iter([data]),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{export.file_name}"'},
        )


@router.get("/exports/{export_id}/events")
async def list_export_events(export_id: int):
    with SessionLocal() as session:
        export = session.get(PromoPlanExport, export_id)
        if not export:
            raise HTTPException(status_code=404, detail="Export not found")
        rows = session.execute(
            select(PromoPlanExportEvent).where(PromoPlanExportEvent.export_id == export_id).order_by(PromoPlanExportEvent.id.asc())
        ).scalars().all()
        return [
            {
                "id": r.id,
                "event_type": r.event_type,
                "actor": r.actor,
                "comment": r.comment,
                "payload": r.payload,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]


@router.post("/exports/{export_id}/submit")
async def submit_export(export_id: int, x_user_id: str | None = Header(default=None, alias="X-User-Id")):
    actor = _actor(x_user_id)
    settings = get_settings()
    with SessionLocal() as session:
        export = session.get(PromoPlanExport, export_id)
        if not export:
            raise HTTPException(status_code=404, detail="Export not found")
        export.workflow_status = "pending_approval"
        export.submitted_at = datetime.now(timezone.utc)
        export.last_comment = None
        _record_event(session, export_id=export.id, event_type="submitted", actor=actor)
        notify = maybe_send_export_email(
            export_id=export.id,
            to_address=settings.promo_export_default_recipient,
            storage_key=export.storage_key,
        )
        _record_event(session, export_id=export.id, event_type="email_stub", actor=actor, payload=notify)
        session.commit()
        return {"id": export.id, "workflow_status": export.workflow_status, "email": notify}


@router.post("/exports/{export_id}/approve")
async def approve_export(export_id: int, x_user_id: str | None = Header(default=None, alias="X-User-Id")):
    actor = _actor(x_user_id)
    with SessionLocal() as session:
        export = session.get(PromoPlanExport, export_id)
        if not export:
            raise HTTPException(status_code=404, detail="Export not found")
        export.workflow_status = "approved"
        export.decided_at = datetime.now(timezone.utc)
        export.decided_by = actor
        export.last_comment = None
        _record_event(session, export_id=export.id, event_type="approved", actor=actor)
        session.commit()
        return {"id": export.id, "workflow_status": export.workflow_status}


@router.post("/exports/{export_id}/reject")
async def reject_export(export_id: int, body: RejectBody, x_user_id: str | None = Header(default=None, alias="X-User-Id")):
    actor = _actor(x_user_id)
    with SessionLocal() as session:
        export = session.get(PromoPlanExport, export_id)
        if not export:
            raise HTTPException(status_code=404, detail="Export not found")
        export.workflow_status = "rejected"
        export.decided_at = datetime.now(timezone.utc)
        export.decided_by = actor
        export.last_comment = body.comment
        _record_event(session, export_id=export.id, event_type="rejected", actor=actor, comment=body.comment)
        session.commit()
        return {"id": export.id, "workflow_status": export.workflow_status}


@router.post("/exports/{export_id}/resend")
async def resend_export(export_id: int, x_user_id: str | None = Header(default=None, alias="X-User-Id")):
    """Create a new export version from the same promotion (does not mutate the original file)."""
    actor = _actor(x_user_id)
    storage = LocalStorageBackend()
    with SessionLocal() as session:
        prior = session.get(PromoPlanExport, export_id)
        if not prior:
            raise HTTPException(status_code=404, detail="Export not found")
        promo_id = prior.promotion_id
        promo = session.get(DimPromotion, promo_id)
        assert promo is not None
        ok, errors, _lines = validate_promotion_for_export(session, promo_id)
        if not ok:
            raise HTTPException(status_code=400, detail={"errors": errors})
        data, digest = build_promo_plan_workbook_bytes(session, promo_id)
        version = _next_version(session, promo_id)
        export = PromoPlanExport(
            promotion_id=promo_id,
            template_code=TEMPLATE_CODE,
            export_version=version,
            storage_key="pending",
            file_name=f"CPOR_PromoPlan_{promo.code}_v{version}_resend.xlsx",
            checksum_sha256=digest,
            validation_status="passed",
            validation_detail=None,
            workflow_status="draft",
            created_by=actor,
        )
        session.add(export)
        session.flush()
        key = f"exports/promo/{export.id}/cpor_v{version}.xlsx"
        storage.save(key, data)
        export.storage_key = key
        _record_event(
            session,
            export_id=export.id,
            event_type="created",
            actor=actor,
            payload={"resent_from_export_id": prior.id, "version": version},
        )
        session.commit()
        session.refresh(export)
        return {"id": export.id, "promotion_id": export.promotion_id, "export_version": export.export_version, "workflow_status": export.workflow_status}
