"""Pipeline: parse → validate → stage → deterministic resolve (H2 validate path)."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cpor_historical import CporHistoricalMappingProfile
from app.models.ingestion import ImportJob
from app.services.cpor.historical_import.profile_defaults import asus_default_profile_dict
from app.services.cpor.historical_import.resolve import resolve_staging_entities
from app.services.cpor.historical_import.staging import upsert_historical_staging_lines
from app.services.cpor.historical_import.validate import parse_and_validate_historical_workbook
from app.services.imports.import_job_background_metadata import persist_clear_background_task_metadata
from app.utils.json_safe import to_jsonable

STAGE_VALIDATED = "validated"
STAGE_FAILED = "failed"
TEMPLATE_SLUG = "cpor_historical_cases"


def _profile_for_job(db: Session, job: ImportJob) -> dict[str, Any]:
    meta = dict(job.staged_metadata or {})
    profile_code = (meta.get("cpor_historical_profile_code") or "").strip()
    if profile_code:
        row = db.scalar(
            select(CporHistoricalMappingProfile).where(
                CporHistoricalMappingProfile.profile_code == profile_code
            )
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
        select(CporHistoricalMappingProfile).where(CporHistoricalMappingProfile.is_default.is_(True))
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
    return asus_default_profile_dict()


def ensure_default_mapping_profile(db: Session) -> CporHistoricalMappingProfile:
    """Idempotent seed of ASUS default profile (profile #1, not schema)."""
    code = "asus_consumer_cpor_tracking_v1"
    existing = db.scalar(
        select(CporHistoricalMappingProfile).where(CporHistoricalMappingProfile.profile_code == code)
    )
    if existing is not None:
        return existing
    d = asus_default_profile_dict()
    row = CporHistoricalMappingProfile(
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


def process_cpor_historical_import(db: Session, job: ImportJob, data: bytes) -> dict[str, Any]:
    """Validate workbook into staging. Does not write cpor_case (apply is separate)."""
    ensure_default_mapping_profile(db)
    profile = _profile_for_job(db, job)
    file_hash = hashlib.sha256(data).hexdigest()

    result = parse_and_validate_historical_workbook(data, profile=profile, session=db)
    if not result.get("ok"):
        job.stage = STAGE_FAILED
        job.status = "failed"
        job.error_summary = "; ".join(
            str(e.get("message") or e) for e in (result.get("blocking_errors") or [])[:5]
        )[:2000] or "historical workbook parse failed"
        job.completed_at = datetime.now(timezone.utc)
        meta = dict(job.staged_metadata or {})
        meta["cpor_historical"] = {
            "file_sha256": file_hash,
            "blocking_errors": to_jsonable(result.get("blocking_errors") or []),
        }
        job.staged_metadata = to_jsonable(meta)
        persist_clear_background_task_metadata(db, job)
        db.flush()
        return {"ok": False, "error": job.error_summary}

    written = upsert_historical_staging_lines(db, job_id=int(job.id), rows=result["rows"])
    resolve_stats = resolve_staging_entities(db, job_id=int(job.id))

    validation = result.get("validation") or {}
    meta = dict(job.staged_metadata or {})
    meta["cpor_historical"] = {
        "file_sha256": file_hash,
        "profile_code": profile.get("profile_code"),
        "row_count": len(result["rows"]),
        "staging_upserted": written,
        "apply_candidate_count": validation.get("apply_candidate_count"),
        "skipped_count": validation.get("skipped_count"),
        "parity_variance_count": validation.get("parity_variance_count"),
        "case_count": len(validation.get("cases") or []),
        "case_blockers": validation.get("case_blockers") or {},
        "resolve_stats": resolve_stats,
    }
    job.staged_metadata = to_jsonable(meta)
    job.stage = STAGE_VALIDATED
    job.status = "completed"
    job.import_mode = job.import_mode or "validate"
    job.completed_at = datetime.now(timezone.utc)
    persist_clear_background_task_metadata(db, job)
    db.flush()
    return {"ok": True, **meta["cpor_historical"]}
