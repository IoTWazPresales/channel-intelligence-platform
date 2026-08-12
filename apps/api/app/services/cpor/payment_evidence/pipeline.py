"""Pipeline: parse → stage → deterministic resolve for cpor_payment_evidence."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cpor_payment import CporPaymentMappingProfile
from app.models.ingestion import ImportJob
from app.services.cpor.payment_evidence.apply_sync import run_cpor_payment_apply_sync
from app.services.cpor.payment_evidence.parser import parse_payment_workbook
from app.services.cpor.payment_evidence.profile_defaults import asus_pending_report_profile_dict
from app.services.cpor.payment_evidence.resolve import payment_job_summary, resolve_payment_staging
from app.services.cpor.payment_evidence.staging import upsert_payment_staging_lines
from app.utils.json_safe import to_jsonable

STAGE_VALIDATED = "validated"
STAGE_FAILED = "failed"
STAGE_LOADED = "loaded"
TEMPLATE_SLUG = "cpor_payment_evidence"


def _ensure_template_and_source(db: Session) -> None:
    """Idempotent template + source so own-surface import works before full seed."""
    from app.models.ingestion import ImportTemplate, SourceDefinition
    from app.services.imports.template_definitions import IMPORT_TEMPLATE_ROWS

    row = next(r for r in IMPORT_TEMPLATE_ROWS if r["slug"] == TEMPLATE_SLUG)
    tpl = db.scalar(select(ImportTemplate).where(ImportTemplate.slug == TEMPLATE_SLUG))
    if tpl is None:
        tpl = ImportTemplate(
            slug=row["slug"],
            display_name=row["display_name"],
            description=row["description"],
            enabled=row["enabled"],
            hidden=row["hidden"],
            admin_only=row["admin_only"],
            requires_provider=row["requires_provider"],
            pipeline_handler=row["pipeline_handler"],
            destructive_apply_requires_confirm=row["destructive_apply_requires_confirm"],
            accepted_file_types=row["accepted_file_types"],
            expected_columns=row["expected_columns"],
        )
        db.add(tpl)
        db.flush()
    src = db.scalar(
        select(SourceDefinition).where(SourceDefinition.code == "cpor_payment_evidence_default")
    )
    if src is None:
        db.add(
            SourceDefinition(
                code="cpor_payment_evidence_default",
                name="Default CPOR payment / credit-note evidence feed",
                import_template_id=tpl.id,
                source_kind="payment_cn_extract",
                is_active=True,
            )
        )
        db.flush()


def ensure_default_payment_profile(db: Session) -> CporPaymentMappingProfile:
    _ensure_template_and_source(db)
    code = "asus_cpor_pending_report_v1"
    existing = db.scalar(
        select(CporPaymentMappingProfile).where(CporPaymentMappingProfile.profile_code == code)
    )
    if existing is not None:
        return existing
    d = asus_pending_report_profile_dict()
    row = CporPaymentMappingProfile(
        profile_code=d["profile_code"],
        display_name=d["display_name"],
        header_row_index=int(d["header_row_index"]),
        sheet_roles_json=d["sheet_roles_json"],
        column_map_json=d["column_map_json"],
        value_maps_json=d["value_maps_json"],
        is_default=True,
        notes=d.get("notes"),
    )
    db.add(row)
    db.flush()
    return row


def _profile_for_job(db: Session, job: ImportJob) -> dict[str, Any]:
    meta = dict(job.staged_metadata or {})
    profile_code = (meta.get("cpor_payment_profile_code") or "").strip()
    if profile_code:
        row = db.scalar(
            select(CporPaymentMappingProfile).where(CporPaymentMappingProfile.profile_code == profile_code)
        )
        if row is not None:
            return {
                "profile_code": row.profile_code,
                "display_name": row.display_name,
                "header_row_index": row.header_row_index,
                "sheet_roles_json": row.sheet_roles_json,
                "column_map_json": row.column_map_json,
                "value_maps_json": row.value_maps_json,
            }
    default = db.scalar(
        select(CporPaymentMappingProfile).where(CporPaymentMappingProfile.is_default.is_(True))
    )
    if default is not None:
        return {
            "profile_code": default.profile_code,
            "display_name": default.display_name,
            "header_row_index": default.header_row_index,
            "sheet_roles_json": default.sheet_roles_json,
            "column_map_json": default.column_map_json,
            "value_maps_json": default.value_maps_json,
        }
    return asus_pending_report_profile_dict()


def process_cpor_payment_evidence_import(db: Session, job: ImportJob, data: bytes) -> dict[str, Any]:
    ensure_default_payment_profile(db)
    profile = _profile_for_job(db, job)
    file_hash = hashlib.sha256(data).hexdigest()
    result = parse_payment_workbook(data, profile=profile)
    if not result.get("ok"):
        job.stage = STAGE_FAILED
        job.status = "failed"
        job.error_summary = "; ".join(
            str(e.get("message") or e) for e in (result.get("blocking_errors") or [])[:5]
        )[:2000] or "payment evidence parse failed"
        job.completed_at = datetime.now(timezone.utc)
        meta = dict(job.staged_metadata or {})
        meta["cpor_payment_evidence"] = {
            "file_sha256": file_hash,
            "blocking_errors": to_jsonable(result.get("blocking_errors") or []),
            "sheet_summaries": to_jsonable(result.get("sheet_summaries") or []),
            "profile_code": profile.get("profile_code"),
        }
        job.staged_metadata = meta
        db.flush()
        return meta["cpor_payment_evidence"]

    n = upsert_payment_staging_lines(db, import_job_id=job.id, rows=list(result.get("rows") or []))
    resolve_stats = resolve_payment_staging(db, job.id)
    summary = payment_job_summary(db, job.id)

    job.stage = STAGE_VALIDATED
    job.status = "needs_review"
    job.completed_at = None
    meta = dict(job.staged_metadata or {})
    meta["cpor_payment_evidence"] = {
        "file_sha256": file_hash,
        "profile_code": profile.get("profile_code"),
        "sheet_summaries": to_jsonable(result.get("sheet_summaries") or []),
        "staged_rows": n,
        "resolve": resolve_stats,
        "summary": summary,
    }
    job.staged_metadata = meta
    job.row_count = n
    db.flush()
    return meta["cpor_payment_evidence"]


def apply_cpor_payment_evidence_job(
    db: Session, job: ImportJob, *, actor: str | None = None, tenant_id: str = "default"
) -> dict[str, Any]:
    out = run_cpor_payment_apply_sync(
        db, import_job_id=job.id, tenant_id=tenant_id, actor=actor
    )
    job.stage = STAGE_LOADED
    job.status = "completed"
    job.completed_at = datetime.now(timezone.utc)
    meta = dict(job.staged_metadata or {})
    pe = dict(meta.get("cpor_payment_evidence") or {})
    pe["apply"] = out
    meta["cpor_payment_evidence"] = pe
    job.staged_metadata = meta
    db.flush()
    return out
