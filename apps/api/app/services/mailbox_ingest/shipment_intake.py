"""Create an inbound_shipments ImportJob from mailbox bytes and run existing sync services."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ingestion.pipeline import STAGE_VALIDATED, process_import_job_sync
from app.models.import_distributor_si import ImportEntityMappingCandidate
from app.models.ingestion import ImportJob, RawFileMetadata, SourceDefinition
from app.services.imports.shipment_apply_sync import run_shipment_apply_sync
from app.services.imports.shipment_evidence_resolution_plan import (
    SHIPMENT_CUSTOMER_ENTITY,
    SHIPMENT_DISTRIBUTOR_ENTITY,
)
from app.services.imports.shipment_field_mapping import (
    infer_shipment_import_job_sync,
    shipment_mapping_gate_errors,
)
from app.services.imports.shipment_resolution_plan import build_shipment_resolution_plan_effective_sync
from app.services.imports.shipment_resolution_plan_apply_sync import (
    run_shipment_resolution_plan_apply_orchestrator,
)
from app.storage.local import get_storage_backend
from app.utils.json_safe import to_jsonable

from app.services.mailbox_ingest.imap_fetch import MailboxAttachment

logger = logging.getLogger(__name__)

_PROVISIONAL_ACTIONS = frozenset({"create_provisional_customer", "create_provisional_distributor"})
_AUTH_FLAG_KIND = "auth_error"
_AUTH_FLAG_COOLDOWN = timedelta(hours=6)

FetchFn = Callable[[], list[MailboxAttachment]]
MarkSeenFn = Callable[[str], None]


def attachment_already_ingested(
    db: Session,
    *,
    checksum: str,
    message_id: str,
) -> str | None:
    """Return skip reason if this attachment or IMAP message was already ingested."""
    if checksum:
        hit = db.scalar(select(RawFileMetadata.id).where(RawFileMetadata.checksum == checksum).limit(1))
        if hit is not None:
            return "checksum"
    mid = (message_id or "").strip()
    if mid:
        hit_job = db.scalar(
            select(ImportJob.id).where(
                ImportJob.template_slug == "inbound_shipments",
                func.jsonb_extract_path_text(ImportJob.staged_metadata, "mail", "message_id") == mid,
            ).limit(1)
        )
        if hit_job is not None:
            return "message_id"
    return None


def create_shipment_job_from_attachment(
    db: Session,
    *,
    source_id: int,
    attachment: MailboxAttachment,
    tenant_id: str = "default",
) -> ImportJob:
    source = db.get(SourceDefinition, source_id)
    if source is None or not source.is_active:
        raise ValueError(f"Unknown or inactive source_id={source_id}")

    storage = get_storage_backend()
    key = f"imports/{uuid.uuid4().hex}/{attachment.filename}"
    lower = attachment.filename.lower()
    content_type = "text/csv" if lower.endswith(".csv") else (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    storage.save(key, attachment.payload, content_type)

    job = ImportJob(
        source_id=source_id,
        template_slug="inbound_shipments",
        import_mode="validate",
        status="pending",
        stage="uploaded",
        file_name=attachment.filename,
        content_type=content_type,
        tenant_id=tenant_id,
        staged_metadata=to_jsonable(
            {
                "mail": {
                    "message_id": attachment.message_id,
                    "from": attachment.from_addr,
                    "subject": attachment.subject,
                    "received_at": attachment.received_at,
                    "attachment_name": attachment.filename,
                    "imap_uid": attachment.uid,
                }
            }
        ),
    )
    db.add(job)
    db.flush()
    db.add(
        RawFileMetadata(
            job_id=job.id,
            storage_key=key,
            byte_size=len(attachment.payload),
            checksum=attachment.checksum_sha256,
        )
    )
    db.commit()
    db.refresh(job)
    infer_shipment_import_job_sync(db, job.id)
    db.refresh(job)
    return job


def _needs_review_candidate_ids(db: Session, job_id: int) -> list[int]:
    return list(
        db.scalars(
            select(ImportEntityMappingCandidate.id).where(
                ImportEntityMappingCandidate.import_job_id == int(job_id),
                ImportEntityMappingCandidate.status == "needs_review",
                ImportEntityMappingCandidate.entity_type.in_(
                    (SHIPMENT_CUSTOMER_ENTITY, SHIPMENT_DISTRIBUTOR_ENTITY)
                ),
            ).order_by(ImportEntityMappingCandidate.id)
        ).all()
    )


def apply_unattended_provisionals(db: Session, job_id: int) -> dict[str, Any]:
    """Run existing plan-apply only for ready create_provisional_* rows (junk stays needs_review)."""
    ids = _needs_review_candidate_ids(db, job_id)
    if not ids:
        return {"applied": 0, "candidate_ids": []}
    plan = build_shipment_resolution_plan_effective_sync(
        db, job_id, candidate_ids=ids, overrides=[]
    )
    prov_ids = [
        int(r["candidate_id"])
        for r in (plan.get("rows") or [])
        if r.get("ready") and str(r.get("suggested_action") or "") in _PROVISIONAL_ACTIONS
    ]
    if not prov_ids:
        return {"applied": 0, "candidate_ids": []}
    return run_shipment_resolution_plan_apply_orchestrator(
        db, job_id, {"candidate_ids": prov_ids}
    )


def run_known_layout_pipeline(db: Session, job_id: int) -> dict[str, Any]:
    """Validate → unattended provisionals → apply (0.95 maps live inside apply)."""
    process_import_job_sync(db, job_id)
    db.refresh(db.get(ImportJob, job_id))
    job = db.get(ImportJob, job_id)
    if job is None:
        return {"outcome": "missing_job"}
    if str(job.status or "") == "failed" or str(job.stage or "") != STAGE_VALIDATED:
        return {
            "outcome": "validate_incomplete",
            "status": job.status,
            "stage": job.stage,
            "error_summary": job.error_summary,
        }
    apply_unattended_provisionals(db, job_id)
    apply_out = run_shipment_apply_sync(db, job_id)
    return {"outcome": "applied", "apply": apply_out}


def ingest_mailbox_attachment(
    db: Session,
    *,
    source_id: int,
    attachment: MailboxAttachment,
) -> dict[str, Any]:
    skip = attachment_already_ingested(
        db, checksum=attachment.checksum_sha256, message_id=attachment.message_id
    )
    if skip:
        logger.warning(
            "FLAG mailbox skip duplicate reason=%s message_id=%s checksum=%s file=%s",
            skip,
            attachment.message_id,
            attachment.checksum_sha256[:12],
            attachment.filename,
        )
        return {"outcome": "skipped_duplicate", "reason": skip}

    job = create_shipment_job_from_attachment(db, source_id=source_id, attachment=attachment)
    mapping = dict(job.field_mapping or {})
    gate = shipment_mapping_gate_errors(mapping)
    if gate:
        logger.warning(
            "FLAG mailbox unknown/incomplete mapping job_id=%s file=%s errors=%s",
            job.id,
            attachment.filename,
            gate,
        )
        return {
            "outcome": "needs_mapping",
            "job_id": int(job.id),
            "gate": gate,
        }
    try:
        pipeline = run_known_layout_pipeline(db, int(job.id))
    except Exception as exc:
        logger.exception("FLAG mailbox pipeline failed job_id=%s", job.id)
        job = db.get(ImportJob, job.id)
        if job is not None:
            job.status = "failed"
            job.stage = "failed"
            job.error_summary = f"FLAG mailbox pipeline: {str(exc)[:1800]}"
            db.commit()
        raise
    pipeline["job_id"] = int(job.id)
    return pipeline


def flag_mailbox_auth_failure(db: Session, *, source_id: int, error: str) -> None:
    """At most one failed ImportJob per 6h for IMAP auth/connect so the poller does not flood."""
    logger.warning("FLAG mailbox auth/connect failed: %s", error[:500])
    cutoff = datetime.now(timezone.utc) - _AUTH_FLAG_COOLDOWN
    existing = db.scalar(
        select(ImportJob.id).where(
            ImportJob.template_slug == "inbound_shipments",
            ImportJob.status == "failed",
            ImportJob.created_at >= cutoff,
            func.jsonb_extract_path_text(ImportJob.staged_metadata, "mail", "kind") == _AUTH_FLAG_KIND,
        ).limit(1)
    )
    if existing is not None:
        return
    job = ImportJob(
        source_id=source_id,
        template_slug="inbound_shipments",
        import_mode="validate",
        status="failed",
        stage="failed",
        file_name="mailbox-ingest-auth-error",
        content_type="text/plain",
        tenant_id="default",
        error_summary=f"FLAG mailbox auth: {error[:1800]}",
        staged_metadata=to_jsonable({"mail": {"kind": _AUTH_FLAG_KIND}}),
        completed_at=datetime.now(timezone.utc),
    )
    db.add(job)
    db.commit()


def flag_mailbox_message_failure(
    db: Session,
    *,
    source_id: int,
    attachment: MailboxAttachment | None,
    error: str,
) -> None:
    logger.warning(
        "FLAG mailbox ingest failed file=%s message_id=%s err=%s",
        attachment.filename if attachment else None,
        attachment.message_id if attachment else None,
        error[:500],
    )
    name = attachment.filename if attachment else "mailbox-ingest-error"
    job = ImportJob(
        source_id=source_id,
        template_slug="inbound_shipments",
        import_mode="validate",
        status="failed",
        stage="failed",
        file_name=name,
        content_type="text/plain",
        tenant_id="default",
        error_summary=f"FLAG mailbox ingest: {error[:1800]}",
        staged_metadata=to_jsonable(
            {
                "mail": {
                    "kind": "ingest_error",
                    "message_id": attachment.message_id if attachment else None,
                    "from": attachment.from_addr if attachment else None,
                    "subject": attachment.subject if attachment else None,
                    "attachment_name": name,
                }
            }
        ),
        completed_at=datetime.now(timezone.utc),
    )
    db.add(job)
    db.commit()
