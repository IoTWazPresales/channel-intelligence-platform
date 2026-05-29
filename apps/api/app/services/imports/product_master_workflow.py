"""Product Master import: constrained mapping, staged metadata, validate vs commit."""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import pandas as pd
from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.ingestion.infer import infer_schema, read_tabular
from app.models.dimensions import DimChannel, DimProduct
from app.models.ingestion import ImportJob, ImportRowResult, RawFileMetadata, SourceDefinition
from app.services.catalog.product_import_sync import sync_bulk_upsert_products_from_rows
from app.services.imports.pm_commit_catalog import commit_catalog_and_eav
from app.services.imports.pm_field_catalog import (
    PM_CANONICAL_GENERIC,
    PM_IDENTITY_TARGETS,
    PM_REQUIRED_NON_IDENTITY,
    normalize_mapping_decisions,
    normalize_pm_mapping_target,
)
from app.services.imports.pm_dataframe_sanitize import (
    normalize_scalar_for_pm,
    scalar_to_clean_str,
    strip_leading_descriptor_rows,
)
from app.services.imports.pm_mapping_memory import load_by_header_norm, merge_memory_from_pm_save
from app.services.imports.pm_suggest_mapping import suggest_pm_mapping
from app.storage.local import get_storage_backend
from app.utils.json_safe import to_jsonable

logger = logging.getLogger(__name__)

Disposition = Literal["ignore", "stage_raw", "attribute_candidate"]

STAGE_PM_HEADERS = "pm_headers_ready"
STAGE_PM_MAPPING = "pm_mapping_saved"
STAGE_PM_VALIDATED = "pm_validated"
STAGE_PM_COMMITTED = "pm_committed"

STATUS_PM_COMMIT_QUEUED = "commit_queued"
STATUS_PM_COMMIT_RUNNING = "commit_running"
STATUS_PM_COMMIT_FAILED = "commit_failed"
STATUS_PM_VALIDATE_QUEUED = "validate_queued"
STATUS_PM_VALIDATE_RUNNING = "validate_running"

# If a worker dies mid-commit, allow a new enqueue after this (API-side reclaim).
STALE_COMMIT_RUNNING = timedelta(hours=1)
STALE_VALIDATE_RUNNING = timedelta(hours=1)


def _pm_commit_blocked_statuses() -> frozenset[str]:
    return frozenset({STATUS_PM_COMMIT_QUEUED, STATUS_PM_COMMIT_RUNNING})


def _pm_validate_blocked_statuses() -> frozenset[str]:
    return frozenset({STATUS_PM_VALIDATE_QUEUED, STATUS_PM_VALIDATE_RUNNING})


def build_pm_import_progress(job: ImportJob, severity_counts: dict[str, int]) -> dict[str, Any]:
    """Structured progress for Product Master GET /state (honest, server-derived; no fake %)."""
    st = job.stage or "uploaded"
    vp = job.validation_passed
    inf = job.inferred_schema if isinstance(job.inferred_schema, dict) else {}
    total_rows = inf.get("row_count")
    staged_row_count = len(job.staged_metadata) if isinstance(job.staged_metadata, dict) else 0

    warn_n = int(severity_counts.get("warning", 0))
    err_n = int(severity_counts.get("error", 0))
    info_n = int(severity_counts.get("info", 0))

    jst = (job.status or "").strip()
    commit_async_phase: str | None = None
    validate_async_phase: str | None = None

    # Rail: 0 Upload → 1 Map → 2 Validate → 3 Review → 4 Commit
    rail_index = 0
    phase_id = "upload"
    phase_label = "Upload"
    phase_description = "Upload a file to begin."
    if st == STAGE_PM_COMMITTED:
        rail_index = 4
        phase_id = "committed"
        phase_label = "Committed"
        phase_description = "Import applied to the product catalog."
    elif jst == STATUS_PM_VALIDATE_RUNNING:
        rail_index = 2
        phase_id = "validate_running"
        validate_async_phase = "running"
        phase_label = "Validating (background)"
        phase_description = "Row checks and staged metadata are running in the background worker. You can leave this page — status updates automatically."
    elif jst == STATUS_PM_VALIDATE_QUEUED:
        rail_index = 2
        phase_id = "validate_queued"
        validate_async_phase = "queued"
        phase_label = "Validation queued"
        phase_description = "Validation is queued for the background worker and will start shortly."
    elif jst == STATUS_PM_COMMIT_RUNNING:
        rail_index = 4
        phase_id = "commit_running"
        commit_async_phase = "running"
        phase_label = "Committing (background)"
        phase_description = "The worker is applying rows to dim_product and catalog. You can leave this page — status updates automatically."
    elif jst == STATUS_PM_COMMIT_QUEUED:
        rail_index = 4
        phase_id = "commit_queued"
        commit_async_phase = "queued"
        phase_label = "Commit queued"
        phase_description = "Commit is queued for the background worker and will start shortly."
    elif jst == STATUS_PM_COMMIT_FAILED and st == STAGE_PM_VALIDATED and vp is True:
        rail_index = 4
        phase_id = "commit_failed"
        commit_async_phase = "failed"
        phase_label = "Commit failed"
        phase_description = (
            job.error_summary or "The last commit attempt failed. Review import messages, fix data if needed, then try Commit again."
        )
    elif st == STAGE_PM_VALIDATED:
        rail_index = 3 if vp is True else 2
        if vp is True:
            phase_id = "review"
            phase_label = "Ready to commit"
            phase_description = "Validation passed. Review warnings, then commit when ready."
        else:
            phase_id = "validate_failed"
            phase_label = "Validation failed"
            phase_description = "Fix mapping or source data, then re-run validation."
    elif st == STAGE_PM_MAPPING:
        rail_index = 2
        phase_id = "validate_pending"
        phase_label = "Validate"
        phase_description = "Mapping saved. Run validation before commit."
    elif st == STAGE_PM_HEADERS:
        rail_index = 1
        phase_id = "map"
        phase_label = "Map columns"
        phase_description = "Match file columns to catalog fields and dispositions."
    elif st == "uploaded":
        rail_index = 0
        phase_id = "upload"
        phase_label = "Upload"
        phase_description = "Inferring headers from the uploaded file."

    steps_meta = [
        {"id": "upload", "label": "Upload", "description": "File received and parsed"},
        {"id": "map", "label": "Map", "description": "Column mapping & dispositions"},
        {"id": "validate", "label": "Validate", "description": "Row checks and staged metadata"},
        {"id": "review", "label": "Review", "description": "Confirm results before apply"},
        {"id": "commit", "label": "Commit", "description": "Write to dim_product and catalog"},
    ]
    steps_out: list[dict[str, Any]] = []
    for i, sm in enumerate(steps_meta):
        if i < rail_index:
            state = "complete"
        elif i == rail_index:
            state = "failed" if (st == STAGE_PM_VALIDATED and vp is False and i == 2) else "current"
        else:
            state = "waiting"
        if st == STAGE_PM_COMMITTED and i < 4:
            state = "complete"
        if st == STAGE_PM_COMMITTED and i == 4:
            state = "complete"
        steps_out.append({**sm, "state": state})

    started = job.started_at.isoformat() if job.started_at else None
    updated = job.updated_at.isoformat() if getattr(job, "updated_at", None) else None
    completed = job.completed_at.isoformat() if job.completed_at else None

    return {
        "phase_id": phase_id,
        "phase_label": phase_label,
        "phase_description": phase_description,
        "rail_index": rail_index,
        "step_count": len(steps_meta),
        "steps": steps_out,
        "job_stage": st,
        "job_status": job.status,
        "validation_passed": vp,
        "total_rows": total_rows,
        "staged_row_count": staged_row_count,
        "row_result_info": info_n,
        "row_result_warnings": warn_n,
        "row_result_errors": err_n,
        "error_summary": job.error_summary,
        "started_at": started,
        "updated_at": updated,
        "completed_at": completed,
        "commit_async_phase": commit_async_phase,
        "validate_async_phase": validate_async_phase,
    }


def try_enqueue_pm_commit_sync(db: Session, job_id: int, *, confirm_destructive: bool) -> dict[str, Any]:
    """Atomically enqueue a Product Master commit (row lock). Returns outcome for API layer."""
    job = db.execute(
        select(ImportJob)
        # Use selectinload with FOR UPDATE to avoid Postgres outer-join lock errors.
        .options(selectinload(ImportJob.source).selectinload(SourceDefinition.import_template))
        .where(ImportJob.id == job_id)
        .with_for_update()
    ).scalar_one_or_none()
    if not job or job.template_slug != "product_master":
        return {"outcome": "not_found", "http_status": 404, "message": "Job not found"}
    if job.stage == STAGE_PM_COMMITTED and (job.status or "") == "completed":
        return {"outcome": "already_completed", "http_status": 200, "message": "This import job is already committed."}

    now = datetime.now(timezone.utc)
    meta = dict(job.pm_commit_meta) if isinstance(job.pm_commit_meta, dict) else {}

    if job.status == STATUS_PM_COMMIT_RUNNING:
        started_s = meta.get("started_at")
        started: datetime | None = None
        if isinstance(started_s, str):
            try:
                started = datetime.fromisoformat(started_s.replace("Z", "+00:00"))
            except ValueError:
                started = None
        if started is not None and (now - started) > STALE_COMMIT_RUNNING:
            job.status = STATUS_PM_COMMIT_FAILED
            job.error_summary = (
                "Previous commit did not finish within the expected time (worker may have stopped). "
                "You may retry commit."
            )
            meta["recovered_at"] = now.isoformat()
            meta["recovered_reason"] = "stale_running"
            job.pm_commit_meta = meta
            db.add(
                ImportRowResult(
                    job_id=job.id,
                    row_number=0,
                    severity="warning",
                    code="pm_commit_stale_recovered",
                    message="Stale commit_running state was cleared so you can retry.",
                    raw_payload=None,
                )
            )
            db.commit()
            job = db.execute(
                select(ImportJob)
                .options(selectinload(ImportJob.source).selectinload(SourceDefinition.import_template))
                .where(ImportJob.id == job_id)
                .with_for_update()
            ).scalar_one_or_none()
            if not job:
                return {"outcome": "not_found", "http_status": 404, "message": "Job not found"}
            meta = dict(job.pm_commit_meta) if isinstance(job.pm_commit_meta, dict) else {}
        else:
            return {
                "outcome": "already_running",
                "http_status": 200,
                "message": "A commit is already running for this job.",
                "job_status": job.status,
            }

    if job.status == STATUS_PM_COMMIT_QUEUED:
        return {
            "outcome": "already_queued",
            "http_status": 200,
            "message": "A commit is already queued for this job.",
            "job_status": job.status,
        }

    if job.stage != STAGE_PM_VALIDATED or job.validation_passed is not True:
        return {"outcome": "not_eligible", "http_status": 400, "message": "validate successfully before commit"}
    tpl = job.source.import_template if job.source else None
    if tpl and tpl.destructive_apply_requires_confirm and not confirm_destructive:
        return {"outcome": "not_eligible", "http_status": 400, "message": "confirm_destructive required"}

    eligible_statuses = ("validated", STATUS_PM_COMMIT_FAILED)
    if (job.status or "") not in eligible_statuses:
        return {
            "outcome": "not_eligible",
            "http_status": 400,
            "message": f"Job status {job.status!r} does not allow commit (expected validated or commit_failed after a failed attempt).",
        }

    meta = {
        "phase": "queued",
        "queued_at": now.isoformat(),
    }
    job.pm_commit_meta = meta
    job.status = STATUS_PM_COMMIT_QUEUED
    job.error_summary = None
    db.commit()
    return {"outcome": "enqueued", "http_status": 202, "message": "Commit queued for background processing.", "job_id": job.id}


def run_pm_commit_worker(db: Session, job_id: int, *, confirm_destructive: bool, celery_task_id: str | None) -> None:
    """Celery entry: single-flight commit; must follow try_enqueue (status commit_queued)."""
    job = db.execute(
        select(ImportJob)
        .options(selectinload(ImportJob.source).selectinload(SourceDefinition.import_template))
        .where(ImportJob.id == job_id)
        .with_for_update()
    ).scalar_one_or_none()
    if not job or job.template_slug != "product_master":
        logger.warning("run_pm_commit_worker: missing job job_id=%s", job_id)
        return
    if job.status != STATUS_PM_COMMIT_QUEUED:
        logger.info(
            "run_pm_commit_worker: skip job_id=%s expected=%s got=%s",
            job_id,
            STATUS_PM_COMMIT_QUEUED,
            job.status,
        )
        return

    now = datetime.now(timezone.utc)
    meta = dict(job.pm_commit_meta) if isinstance(job.pm_commit_meta, dict) else {}
    meta["phase"] = "running"
    meta["started_at"] = now.isoformat()
    if celery_task_id:
        meta["celery_task_id"] = celery_task_id
    job.pm_commit_meta = meta
    job.status = STATUS_PM_COMMIT_RUNNING
    db.commit()

    try:
        commit_product_master_sync(db, job_id, confirm_destructive=confirm_destructive, from_worker=True)
    except Exception as exc:
        logger.exception("run_pm_commit_worker: commit failed job_id=%s", job_id)
        db.rollback()
        job2 = db.get(ImportJob, job_id)
        if job2:
            m2 = dict(job2.pm_commit_meta) if isinstance(job2.pm_commit_meta, dict) else {}
            m2["phase"] = "failed"
            m2["failed_at"] = datetime.now(timezone.utc).isoformat()
            m2["error_type"] = exc.__class__.__name__
            m2["error_message"] = str(exc)[:2000]
            job2.pm_commit_meta = m2
            job2.status = STATUS_PM_COMMIT_FAILED
            if not job2.error_summary:
                job2.error_summary = str(exc)[:2000]
            db.add(
                ImportRowResult(
                    job_id=job2.id,
                    row_number=0,
                    severity="error",
                    code="pm_commit_worker_failed",
                    message=f"Background commit failed: {str(exc)[:1200]}",
                    raw_payload=to_jsonable({"error_type": exc.__class__.__name__}),
                )
            )
            db.commit()
        raise


# Generic target → sync_bulk_upsert_products_from_rows key (dim columns).
_GENERIC_TO_SYNC: dict[str, str] = {
    "market_sku": "sales_model_name",
    "model_family": "model_name",
    "barcode_ean": "ean",
    "barcode_upc": "upc",
    "series": "series_name",
}


def _headers_from_df(df: pd.DataFrame) -> list[str]:
    return [str(c) for c in df.columns.tolist()]


def suggest_mapping_decisions(
    headers: list[str],
    source: Any,
    inferred_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    mem = load_by_header_norm(source)
    return suggest_pm_mapping(headers, source, inferred_schema, header_memory=mem)


def validate_mapping_payload(headers: list[str], columns: list[dict[str, Any]]) -> list[str]:
    errs: list[str] = []
    by_header = {str(c.get("header", "")).strip(): c for c in columns if c.get("header") is not None}
    for h in headers:
        if h not in by_header:
            errs.append(f"Missing mapping entry for header {h!r}")
    for h in headers:
        entry = by_header[h]
        tgt = entry.get("target")
        disp = entry.get("disposition")
        if tgt is not None and str(tgt).strip():
            tg = normalize_pm_mapping_target(str(tgt))
            if not tg or tg not in PM_CANONICAL_GENERIC:
                errs.append(f"Unknown canonical target {str(tgt).strip()!r} for column {h!r}")
        else:
            d = str(disp or "").strip()
            if d not in ("ignore", "stage_raw", "attribute_candidate"):
                errs.append(f"Unmapped column {h!r} needs disposition ignore|stage_raw|attribute_candidate")

    targets: list[str] = []
    for h in headers:
        raw_t = by_header[h].get("target")
        if raw_t:
            nt = normalize_pm_mapping_target(str(raw_t))
            if nt:
                targets.append(nt)

    for req in PM_REQUIRED_NON_IDENTITY:
        if req not in targets:
            errs.append(f"Required field {req!r} must be mapped to exactly one column")
    id_count = sum(1 for t in targets if t in PM_IDENTITY_TARGETS)
    if id_count != 1:
        errs.append("Map exactly one identity column: technical_product_id (legacy part_number/sku normalize here).")
    for c in PM_CANONICAL_GENERIC:
        if targets.count(c) > 1:
            errs.append(f"Canonical {c!r} mapped more than once")
    return errs


def decisions_from_columns(headers: list[str], columns: list[dict[str, Any]]) -> dict[str, Any]:
    by_header = {str(c["header"]): c for c in columns}
    return {h: by_header[h] for h in headers}


def _strip_disposition_for_mapped_targets(decisions: dict[str, Any] | None) -> dict[str, Any]:
    """Disposition applies only to unmapped columns; drop it when a canonical target is set."""
    if not decisions:
        return {}
    out: dict[str, Any] = {}
    for h, meta in decisions.items():
        if not isinstance(meta, dict):
            out[h] = meta
            continue
        m = dict(meta)
        if m.get("target") and str(m.get("target")).strip():
            m.pop("disposition", None)
        out[h] = m
    return out


def decisions_to_field_mapping(decisions: dict[str, Any]) -> dict[str, str]:
    m: dict[str, str] = {}
    for h, meta in decisions.items():
        if not isinstance(meta, dict):
            continue
        t = meta.get("target")
        if t:
            nt = normalize_pm_mapping_target(str(t))
            if nt:
                m[str(h)] = nt
    return m


def technical_id_column(field_mapping: dict[str, str]) -> str:
    """File column mapped to technical_product_id (already normalized)."""
    return next(k for k, v in field_mapping.items() if v == "technical_product_id")


def display_name_column(field_mapping: dict[str, str]) -> str:
    return next(k for k, v in field_mapping.items() if v == "display_name")


def infer_headers_sync(db: Session, job_id: int) -> ImportJob:
    job = db.get(ImportJob, job_id)
    if not job or job.template_slug != "product_master":
        raise ValueError("invalid job")
    raw = db.scalars(select(RawFileMetadata).where(RawFileMetadata.job_id == job_id)).one()
    storage = get_storage_backend()
    data = storage.read(raw.storage_key)
    df = read_tabular(job.file_name, data)
    df, dropped_desc = strip_leading_descriptor_rows(df)
    job.inferred_schema = infer_schema(df)
    job.file_headers = _headers_from_df(df)
    job.mapping_decisions = None
    job.field_mapping = None
    job.stage = STAGE_PM_HEADERS
    job.status = "draft"
    job.validation_passed = None
    job.staged_metadata = None
    job.started_at = datetime.now(timezone.utc)
    if dropped_desc:
        job.error_summary = (
            f"Excluded {len(dropped_desc)} leading descriptor-like row(s) before header inference."
        )
    else:
        job.error_summary = None
    db.commit()
    db.refresh(job)
    return job


def save_mapping_sync(db: Session, job_id: int, columns: list[dict[str, Any]]) -> ImportJob:
    job = db.get(ImportJob, job_id)
    if not job or job.template_slug != "product_master":
        raise ValueError("invalid job")
    if (job.status or "") in _pm_commit_blocked_statuses():
        raise ValueError("Cannot change mapping while a Product Master commit is queued or running.")
    if job.stage not in (STAGE_PM_HEADERS, STAGE_PM_MAPPING, STAGE_PM_VALIDATED):
        raise ValueError("job not in an editable mapping stage")
    headers = job.file_headers or []
    if not headers:
        raise ValueError("file headers missing; run infer first")
    errs = validate_mapping_payload(headers, columns)
    if errs:
        raise ValueError("; ".join(errs))
    raw_decisions = decisions_from_columns(headers, columns)
    job.mapping_decisions = _strip_disposition_for_mapped_targets(
        normalize_mapping_decisions(raw_decisions)
    )
    job.field_mapping = decisions_to_field_mapping(job.mapping_decisions)
    job.stage = STAGE_PM_MAPPING
    job.validation_passed = None
    job.staged_metadata = None
    job.error_summary = None
    merge_memory_from_pm_save(db, source_id=job.source_id, mapping_decisions=job.mapping_decisions or {})
    db.commit()
    db.refresh(job)
    return job


def _clear_row_results(db: Session, job_id: int) -> None:
    db.execute(delete(ImportRowResult).where(ImportRowResult.job_id == job_id))


def _append_pm_row_result(
    bucket: list[dict[str, Any]],
    *,
    job_id: int,
    row_number: int,
    severity: str,
    code: str,
    message: str,
    raw_payload: Any = None,
) -> None:
    bucket.append(
        {
            "job_id": job_id,
            "row_number": row_number,
            "severity": severity,
            "code": code,
            "message": message,
            "raw_payload": to_jsonable(raw_payload) if raw_payload is not None else None,
        }
    )


def _bulk_insert_row_results(db: Session, rows: list[dict[str, Any]], *, chunk_size: int = 2000) -> None:
    if not rows:
        return
    for offset in range(0, len(rows), chunk_size):
        db.execute(insert(ImportRowResult), rows[offset : offset + chunk_size])


def validate_product_master_sync(db: Session, job_id: int, *, from_worker: bool = False) -> ImportJob:
    job = db.get(ImportJob, job_id)
    if not job or job.template_slug != "product_master":
        raise ValueError("invalid job")
    if (job.status or "") in _pm_commit_blocked_statuses():
        raise ValueError("Cannot validate while a Product Master commit is queued or running.")
    if not from_worker and (job.status or "") in _pm_validate_blocked_statuses():
        raise ValueError("Validation is already queued or running for this job.")
    if from_worker and (job.status or "") not in (STATUS_PM_VALIDATE_RUNNING,):
        raise ValueError(f"expected status {STATUS_PM_VALIDATE_RUNNING!r}, got {(job.status or '')!r}")
    if job.stage not in (STAGE_PM_MAPPING,):
        raise ValueError("save mapping before validate")
    if not job.mapping_decisions:
        raise ValueError("mapping_decisions missing")
    _clear_row_results(db, job_id)
    row_results: list[dict[str, Any]] = []
    headers = job.file_headers or []
    cols_payload = [{"header": h, **(job.mapping_decisions[h])} for h in headers]
    errs = validate_mapping_payload(headers, cols_payload)
    if errs:
        raise ValueError("; ".join(errs))

    raw = db.scalars(select(RawFileMetadata).where(RawFileMetadata.job_id == job_id)).one()
    storage = get_storage_backend()
    df = read_tabular(job.file_name, storage.read(raw.storage_key))
    fm = decisions_to_field_mapping(job.mapping_decisions)

    tech_col = technical_id_column(fm)
    name_col = display_name_column(fm)
    df, dropped_desc = strip_leading_descriptor_rows(df, tech_col=tech_col, name_col=name_col)
    if dropped_desc:
        _append_pm_row_result(
            row_results,
            job_id=job.id,
            row_number=0,
            severity="info",
            code="leading_descriptor_rows_excluded",
            message=(
                f"Excluded {len(dropped_desc)} leading row(s) that look like column labels / "
                "a second header row (not product data)."
            ),
            raw_payload={"dropped_iloc_positions": dropped_desc},
        )
    market_col = next((k for k, v in fm.items() if v == "market_sku"), None)
    spc_col = next((k for k, v in fm.items() if v == "source_product_code"), None)
    cc_col = next((k for k, v in fm.items() if v == "country_code"), None)
    ean_col = next((k for k, v in fm.items() if v == "barcode_ean"), None)
    upc_col = next((k for k, v in fm.items() if v == "barcode_upc"), None)
    ch_col = next((k for k, v in fm.items() if v == "channel_code"), None)

    stage_cols = [
        h
        for h, m in (job.mapping_decisions or {}).items()
        if isinstance(m, dict) and m.get("disposition") == "stage_raw"
    ]
    cand_cols = [
        h
        for h, m in (job.mapping_decisions or {}).items()
        if isinstance(m, dict) and m.get("disposition") == "attribute_candidate"
    ]

    channels = {c.code.strip().lower(): c.id for c in db.scalars(select(DimChannel)).all()}
    staged: dict[str, dict[str, Any]] = {}
    errors = 0

    tech_values: list[str] = []
    market_vals: list[str] = []

    for idx, row in df.iterrows():
        tid = scalar_to_clean_str(row.get(tech_col)) or ""
        disp = scalar_to_clean_str(row.get(name_col)) or ""
        if tid:
            tech_values.append(tid)
        mk = ""
        if market_col:
            mk = scalar_to_clean_str(row.get(market_col)) or ""
            if mk:
                market_vals.append(mk)

        if not tid:
            _append_pm_row_result(
                row_results,
                job_id=job.id,
                row_number=int(idx) + 1,
                severity="warning",
                code="blank_technical_id",
                message="Blank technical_product_id",
            )
            continue
        if not disp:
            _append_pm_row_result(
                row_results,
                job_id=job.id,
                row_number=int(idx) + 1,
                severity="error",
                code="blank_display_name",
                message="Blank display_name",
            )
            errors += 1
            continue
        if len(tid) > 128:
            _append_pm_row_result(
                row_results,
                job_id=job.id,
                row_number=int(idx) + 1,
                severity="error",
                code="technical_id_too_long",
                message=f"technical_product_id must be at most 128 characters (got {len(tid)}).",
                raw_payload={"value": tid[:96]},
            )
            errors += 1
            continue
        if len(disp) > 512:
            _append_pm_row_result(
                row_results,
                job_id=job.id,
                row_number=int(idx) + 1,
                severity="error",
                code="display_name_too_long",
                message=f"display_name must be at most 512 characters (got {len(disp)}).",
            )
            errors += 1
            continue
        if spc_col:
            spv = scalar_to_clean_str(row.get(spc_col))
            if spv and len(spv) > 128:
                _append_pm_row_result(
                    row_results,
                    job_id=job.id,
                    row_number=int(idx) + 1,
                    severity="error",
                    code="source_product_code_too_long",
                    message=(
                        f"source_product_code (catalog source SKU) must be at most 128 characters "
                        f"(got {len(spv)})."
                    ),
                    raw_payload={"value": spv[:96]},
                )
                errors += 1
                continue
        if cc_col:
            ccv = scalar_to_clean_str(row.get(cc_col))
            if ccv and len(ccv) > 8:
                _append_pm_row_result(
                    row_results,
                    job_id=job.id,
                    row_number=int(idx) + 1,
                    severity="error",
                    code="country_code_too_long",
                    message=f"country_code must be at most 8 characters (got {len(ccv)}).",
                    raw_payload={"value": ccv[:64]},
                )
                errors += 1
                continue
        if ean_col:
            ev = scalar_to_clean_str(row.get(ean_col))
            if ev and len(ev) > 32:
                _append_pm_row_result(
                    row_results,
                    job_id=job.id,
                    row_number=int(idx) + 1,
                    severity="error",
                    code="ean_too_long",
                    message=f"EAN must be at most 32 characters (got {len(ev)}).",
                    raw_payload={"value": ev[:64]},
                )
                errors += 1
                continue
        if upc_col:
            uv = scalar_to_clean_str(row.get(upc_col))
            if uv and len(uv) > 32:
                _append_pm_row_result(
                    row_results,
                    job_id=job.id,
                    row_number=int(idx) + 1,
                    severity="error",
                    code="upc_too_long",
                    message=f"UPC must be at most 32 characters (got {len(uv)}).",
                    raw_payload={"value": uv[:64]},
                )
                errors += 1
                continue
        ch_raw = None
        if ch_col:
            v = normalize_scalar_for_pm(row.get(ch_col))
            if v is not None and str(v).strip():
                ch_raw = str(v).strip()
        if ch_raw and ch_raw.lower() not in channels:
            _append_pm_row_result(
                row_results,
                job_id=job.id,
                row_number=int(idx) + 1,
                severity="error",
                code="unknown_channel",
                message=f"Unknown channel_code {ch_raw!r}",
            )
            errors += 1
            continue
        row_stage: dict[str, Any] = {}
        for sc in stage_cols:
            v = normalize_scalar_for_pm(row.get(sc))
            if v is not None and str(v).strip() != "":
                row_stage[sc] = to_jsonable(v)
        if row_stage:
            staged[str(int(idx))] = row_stage

    tech_dups = [k for k, v in Counter(tech_values).items() if v > 1]
    if tech_dups:
        _append_pm_row_result(
            row_results,
            job_id=job.id,
            row_number=0,
            severity="warning",
            code="duplicate_technical_id",
            message=f"Duplicate technical_product_id values in file ({len(tech_dups)} id(s)); review rows.",
            raw_payload={"sample_ids": tech_dups[:20]},
        )
    mv_dups = [k for k, v in Counter(market_vals).items() if v > 1] if market_col else []
    if mv_dups:
        _append_pm_row_result(
            row_results,
            job_id=job.id,
            row_number=0,
            severity="warning",
            code="duplicate_market_sku",
            message=f"Duplicate market_sku values ({len(mv_dups)}); verify commercial keys.",
            raw_payload={"sample": mv_dups[:20]},
        )

    id_col_label = fm.get(tech_col) or "technical_product_id"
    missing_identity_rows = sum(
        1
        for idx, row in df.iterrows()
        if not (scalar_to_clean_str(row.get(tech_col)) or "")
        or not (scalar_to_clean_str(row.get(name_col)) or "")
    )
    if missing_identity_rows:
        _append_pm_row_result(
            row_results,
            job_id=job.id,
            row_number=0,
            severity="warning",
            code="identity_quality",
            message=f"{missing_identity_rows} row(s) missing technical id or display name.",
            raw_payload={"technical_column": tech_col, "mapped_as": id_col_label},
        )

    if cand_cols:
        _append_pm_row_result(
            row_results,
            job_id=job.id,
            row_number=0,
            severity="info",
            code="attribute_candidate",
            message="Columns flagged for steward review: " + ", ".join(repr(c) for c in cand_cols),
            raw_payload={"headers": cand_cols},
        )

    _append_pm_row_result(
        row_results,
        job_id=job.id,
        row_number=0,
        severity="info" if errors == 0 else "warning",
        code="pm_validation_summary",
        message=json.dumps({"row_errors": errors, "staged_row_count": len(staged)}),
    )
    _bulk_insert_row_results(db, row_results)

    job.staged_metadata = to_jsonable(staged) if staged else {}
    job.validation_passed = errors == 0
    job.stage = STAGE_PM_VALIDATED
    job.status = "validated" if errors == 0 else "validation_failed"
    job.error_summary = f"{errors} row errors" if errors else None
    _clear_pm_validate_task_metadata(job)
    db.commit()
    db.refresh(job)
    return job


def _clear_pm_validate_task_metadata(job: ImportJob) -> None:
    meta = dict(job.staged_metadata or {}) if isinstance(job.staged_metadata, dict) else {}
    if meta.pop("pm_validate_task", None) is not None:
        job.staged_metadata = to_jsonable(meta) if meta else None


def _persist_pm_validate_task_metadata(
    job: ImportJob,
    *,
    task_id: str,
    async_poll: bool,
) -> None:
    meta = dict(job.staged_metadata or {}) if isinstance(job.staged_metadata, dict) else {}
    meta["pm_validate_task"] = to_jsonable(
        {
            "task_id": task_id,
            "async_poll": async_poll,
            "kind": "product_master_validate",
            "label": "Validating product master…",
            "queued_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    job.staged_metadata = to_jsonable(meta)


def try_enqueue_pm_validate_sync(db: Session, job_id: int) -> dict[str, Any]:
    """Atomically enqueue Product Master validation (row lock). Returns outcome for API layer."""
    job = db.execute(
        select(ImportJob)
        .options(selectinload(ImportJob.source).selectinload(SourceDefinition.import_template))
        .where(ImportJob.id == job_id)
        .with_for_update()
    ).scalar_one_or_none()
    if not job or job.template_slug != "product_master":
        return {"outcome": "not_found", "http_status": 404, "message": "Job not found"}
    if (job.status or "") in _pm_commit_blocked_statuses():
        return {
            "outcome": "not_eligible",
            "http_status": 400,
            "message": "Cannot validate while a Product Master commit is queued or running.",
        }
    if job.status == STATUS_PM_VALIDATE_RUNNING:
        return {
            "outcome": "already_running",
            "http_status": 200,
            "message": "Validation is already running for this job.",
            "job_status": job.status,
        }
    if job.status == STATUS_PM_VALIDATE_QUEUED:
        return {
            "outcome": "already_queued",
            "http_status": 200,
            "message": "Validation is already queued for this job.",
            "job_status": job.status,
        }
    if job.stage != STAGE_PM_MAPPING:
        return {"outcome": "not_eligible", "http_status": 400, "message": "save mapping before validate"}
    if not job.mapping_decisions:
        return {"outcome": "not_eligible", "http_status": 400, "message": "mapping_decisions missing"}

    job.status = STATUS_PM_VALIDATE_QUEUED
    job.error_summary = None
    db.commit()
    return {
        "outcome": "enqueued",
        "http_status": 202,
        "message": "Validation queued for background processing.",
        "job_id": job.id,
    }


def run_pm_validate_worker(db: Session, job_id: int, *, celery_task_id: str | None) -> None:
    """Celery entry: run validation; must follow try_enqueue (status validate_queued)."""
    job = db.execute(
        select(ImportJob)
        .options(selectinload(ImportJob.source).selectinload(SourceDefinition.import_template))
        .where(ImportJob.id == job_id)
        .with_for_update()
    ).scalar_one_or_none()
    if not job or job.template_slug != "product_master":
        logger.warning("run_pm_validate_worker: missing job job_id=%s", job_id)
        return
    if job.status != STATUS_PM_VALIDATE_QUEUED:
        logger.info(
            "run_pm_validate_worker: skip job_id=%s expected=%s got=%s",
            job_id,
            STATUS_PM_VALIDATE_QUEUED,
            job.status,
        )
        return

    now = datetime.now(timezone.utc)
    job.status = STATUS_PM_VALIDATE_RUNNING
    _persist_pm_validate_task_metadata(
        job,
        task_id=str(celery_task_id or f"pm-validate-{job_id}"),
        async_poll=True,
    )
    db.commit()

    try:
        validate_product_master_sync(db, job_id, from_worker=True)
    except ValueError as exc:
        logger.warning("run_pm_validate_worker: validation rejected job_id=%s: %s", job_id, exc)
        db.rollback()
        job2 = db.get(ImportJob, job_id)
        if job2:
            _clear_pm_validate_task_metadata(job2)
            job2.status = "validation_failed"
            job2.error_summary = str(exc)[:2000]
            db.add(job2)
            db.commit()
    except Exception as exc:
        logger.exception("run_pm_validate_worker: validation failed job_id=%s", job_id)
        db.rollback()
        job2 = db.get(ImportJob, job_id)
        if job2:
            _clear_pm_validate_task_metadata(job2)
            job2.status = "validation_failed"
            if not job2.error_summary:
                job2.error_summary = str(exc)[:2000]
            db.add(
                ImportRowResult(
                    job_id=job2.id,
                    row_number=0,
                    severity="error",
                    code="pm_validate_worker_failed",
                    message=f"Background validation failed: {str(exc)[:1200]}",
                    raw_payload=to_jsonable({"error_type": exc.__class__.__name__}),
                )
            )
            db.commit()


def _sync_key_for_generic(gt: str) -> str | None:
    if gt in ("technical_product_id", "display_name", "source_product_code"):
        return None
    if gt in _GENERIC_TO_SYNC:
        return _GENERIC_TO_SYNC[gt]
    if gt in PM_CANONICAL_GENERIC:
        return gt
    return None


def _maybe_ai_remap_product_by_description(
    db: Session,
    pl: dict[str, Any],
    fm: dict[str, str],
    row: Any,
    job_id: int,
) -> dict[str, Any]:
    """After deterministic identity checks: optional description-based product match (AI only)."""
    from app.core.config import get_settings

    if not get_settings().ai_assist_enabled:
        return pl

    tid = str(pl.get("sku") or "").strip()
    if not tid:
        return pl

    exists = db.scalars(select(DimProduct.id).where(DimProduct.sku == tid)).first()
    if exists is not None:
        return pl

    ean_col = next((k for k, v in fm.items() if v == "barcode_ean"), None)
    if ean_col:
        ev = scalar_to_clean_str(row.get(ean_col))
        if ev:
            ean_match = db.scalars(select(DimProduct).where(DimProduct.ean == ev)).first()
            if ean_match is not None:
                return pl

    description = str(pl.get("name") or "").strip()
    if not description:
        return pl

    from app.services.imports.ai_resolver_wiring import (
        product_candidates_from_db,
        try_ai_token_resolution,
    )

    ai_id, ai_tag, _suggestion = try_ai_token_resolution(
        raw_token=description,
        token_type="product",
        candidates=product_candidates_from_db(db, description),
        import_type="product_master",
        job_id=job_id,
        extra_context={"match_by": "description"},
    )
    if ai_id is None or ai_tag != "ai_auto_resolved":
        second_id, second_tag, _ = try_ai_token_resolution(
            raw_token=tid,
            token_type="product",
            candidates=product_candidates_from_db(db, tid),
            import_type="product_master",
            job_id=job_id,
        )
        if second_id is not None and second_tag == "ai_auto_resolved":
            ai_id = second_id

    if ai_id is None:
        return pl

    prod = db.get(DimProduct, int(ai_id))
    if prod is None or not prod.sku:
        return pl

    out = dict(pl)
    out["sku"] = prod.sku
    out["part_number"] = prod.part_number or prod.sku
    return out


def _row_payload_for_dim(row: Any, fm: dict[str, str]) -> dict[str, Any] | None:
    tech_col = technical_id_column(fm)
    tech = scalar_to_clean_str(row.get(tech_col)) or ""
    dn_col = display_name_column(fm)
    disp = scalar_to_clean_str(row.get(dn_col)) or ""
    if not tech or not disp:
        return None

    pl: dict[str, Any] = {"sku": tech, "name": disp, "part_number": tech}

    for header, gt in fm.items():
        sk = _sync_key_for_generic(gt)
        if not sk:
            continue
        val = normalize_scalar_for_pm(row.get(header))
        if val is None or (isinstance(val, str) and not val.strip()):
            continue
        if isinstance(val, float) and pd.isna(val):
            continue
        if sk == "channel_code":
            pl["channel_code"] = str(val).strip()
        elif sk == "launch_date":
            pl["launch_date"] = val
        elif sk == "end_of_life_date":
            pl["end_of_life_date"] = val
        else:
            pl[sk] = val
    return pl


def commit_product_master_sync(
    db: Session, job_id: int, *, confirm_destructive: bool, from_worker: bool = False
) -> ImportJob:
    job = db.execute(
        select(ImportJob)
        .options(joinedload(ImportJob.source).joinedload(SourceDefinition.import_template))
        .where(ImportJob.id == job_id)
    ).scalar_one_or_none()
    if not job or job.template_slug != "product_master":
        raise ValueError("invalid job")
    if job.stage != STAGE_PM_VALIDATED or job.validation_passed is not True:
        raise ValueError("validate successfully before commit")
    jst = (job.status or "").strip()
    if from_worker:
        if jst != STATUS_PM_COMMIT_RUNNING:
            raise ValueError("Internal error: background commit requires job status commit_running.")
    else:
        if jst != "validated":
            raise ValueError(
                "Product Master commits run in the background; use the HTTP commit endpoint to enqueue work."
            )
    tpl = job.source.import_template if job.source else None
    if tpl and tpl.destructive_apply_requires_confirm and not confirm_destructive:
        raise ValueError("confirm_destructive required")

    raw = db.scalars(select(RawFileMetadata).where(RawFileMetadata.job_id == job_id)).one()
    storage = get_storage_backend()
    df = read_tabular(job.file_name, storage.read(raw.storage_key))
    fm = decisions_to_field_mapping(job.mapping_decisions or {})

    tech_col = technical_id_column(fm)
    name_col = display_name_column(fm)
    df, _dropped_commit = strip_leading_descriptor_rows(df, tech_col=tech_col, name_col=name_col)
    source_code_col = next((k for k, v in fm.items() if v == "source_product_code"), None)

    staged = job.staged_metadata or {}

    payloads: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        pl = _row_payload_for_dim(row, fm)
        if pl:
            pl = _maybe_ai_remap_product_by_description(db, pl, fm, row, int(job.id))
            payloads.append(pl)

    src = job.source
    try:
        sync_bulk_upsert_products_from_rows(db, payloads)
        catalog_rows = 0
        if src is not None and src.product_catalog_id is not None:
            catalog_rows = commit_catalog_and_eav(
                db,
                job,
                src,
                df,
                mapping_decisions=job.mapping_decisions,
                staged_row_values=staged,
                technical_id_col=tech_col,
                name_col=name_col,
                source_sku_col=source_code_col,
            )

        for idx, row in df.iterrows():
            tid = scalar_to_clean_str(row.get(tech_col)) or ""
            if not tid:
                continue
            rk = str(int(idx))
            frag = staged.get(rk)
            if not frag:
                continue
            prod = db.scalars(select(DimProduct).where(DimProduct.sku == tid)).first()
            if not prod:
                continue
            specs = dict(prod.specs_json or {})
            imp = dict(specs.get("import_staging") or {})
            for k, v in frag.items():
                imp[k] = v
            specs["import_staging"] = imp
            prod.specs_json = specs

        raw_commit_meta: dict[str, Any] | None = None
        if src is not None and src.product_catalog_id is not None:
            raw_commit_meta = {"catalog_product_rows": catalog_rows}
        db.add(
            ImportRowResult(
                job_id=job.id,
                row_number=0,
                severity="info",
                code="product_master_committed",
                message=f"Committed {len(payloads)} product row(s)"
                + (f"; catalog rows {catalog_rows}" if (src and src.product_catalog_id) else "")
                + ".",
                raw_payload=raw_commit_meta,
            )
        )
        job.pm_commit_meta = None
        job.stage = STAGE_PM_COMMITTED
        job.status = "completed"
        job.completed_at = datetime.now(timezone.utc)
        job.archived_at = datetime.now(timezone.utc)
        job.import_mode = "apply"
        db.commit()
    except ValueError as exc:
        db.rollback()
        db.add(
            ImportRowResult(
                job_id=job.id,
                row_number=0,
                severity="error",
                code="product_commit_validation",
                message=str(exc),
                raw_payload=None,
            )
        )
        db.commit()
        raise
    except Exception as exc:
        db.rollback()
        msg = str(exc).strip() or exc.__class__.__name__
        db.add(
            ImportRowResult(
                job_id=job.id,
                row_number=0,
                severity="error",
                code="product_commit_db_error",
                message=f"Commit blocked by database error: {msg[:1800]}",
                raw_payload=to_jsonable({"error_type": exc.__class__.__name__}),
            )
        )
        db.commit()
        raise ValueError(
            "Product commit failed due to a database constraint or type mismatch. "
            "See import row results for details."
        ) from exc
    db.refresh(job)
    return job
