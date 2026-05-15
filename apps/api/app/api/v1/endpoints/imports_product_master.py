"""Product Master constrained mapping: infer → save mapping → validate → commit."""

from __future__ import annotations

import logging
import threading
import uuid

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.dev_celery_logging import DEV_CELERY_LOGGER
from app.db.session_sync import SessionLocal
from app.models.ingestion import ImportJob, ImportRowResult, RawFileMetadata, SourceDefinition
from app.services.imports.pm_field_catalog import (
    PM_CANONICAL_GENERIC,
    PM_IDENTITY_TARGETS,
    PM_REQUIRED_NON_IDENTITY,
    field_definitions_for_api,
    normalize_mapping_decisions,
)
from app.services.imports.pm_suggest_mapping import attach_pm_suggestion_summaries
from app.services.imports.product_master_workflow import (
    STATUS_PM_COMMIT_QUEUED,
    build_pm_import_progress,
    infer_headers_sync,
    save_mapping_sync,
    suggest_mapping_decisions,
    try_enqueue_pm_commit_sync,
    validate_product_master_sync,
)
from app.services.background_tasks.store import BackgroundTaskStore
from app.worker.tasks import product_master_commit_task, run_product_master_commit_job
from app.storage.local import get_storage_backend

router = APIRouter()
logger = logging.getLogger(__name__)


class PMColumnMapping(BaseModel):
    header: str = Field(min_length=1)
    target: str | None = None
    disposition: str | None = None

    @field_validator("target")
    @classmethod
    def strip_target(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        return s or None

    @field_validator("disposition")
    @classmethod
    def strip_disp(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        return s or None


class PMMappingBody(BaseModel):
    columns: list[PMColumnMapping]


def _require_admin(x_user_role: str | None) -> None:
    if (x_user_role or "").strip().lower() != "admin":
        raise HTTPException(status_code=403, detail="Product Master mapping workflow requires admin for this slice")


@router.post("/jobs")
async def create_product_master_job(
    source_id: int = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
):
    """Upload file only; infers headers. Does not apply catalog changes."""
    _require_admin(x_user_role)
    source = await db.scalar(
        select(SourceDefinition)
        .options(joinedload(SourceDefinition.import_template))
        .where(SourceDefinition.id == source_id)
    )
    if not source or not source.is_active:
        raise HTTPException(status_code=400, detail="Unknown or inactive source_id")
    tpl = source.import_template
    if not tpl or tpl.slug != "product_master":
        raise HTTPException(status_code=400, detail="source_id must reference a Product Master provider")

    raw_bytes = await file.read()
    storage = get_storage_backend()
    key = f"imports/{uuid.uuid4().hex}/{file.filename}"
    storage.save(key, raw_bytes, file.content_type)

    job = ImportJob(
        source_id=source_id,
        template_slug="product_master",
        import_mode="validate",
        status="draft",
        stage="uploaded",
        file_name=file.filename or "upload",
        content_type=file.content_type,
    )
    db.add(job)
    await db.flush()
    db.add(RawFileMetadata(job_id=job.id, storage_key=key, byte_size=len(raw_bytes), checksum=None))
    await db.commit()
    await db.refresh(job)

    try:
        with SessionLocal() as sync_db:
            infer_headers_sync(sync_db, job.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    await db.refresh(job)
    return {"id": job.id, "stage": job.stage, "file_headers": job.file_headers}


@router.get("/jobs/{job_id}/state")
async def get_product_master_job_state(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
):
    _require_admin(x_user_role)
    job = await db.scalar(
        select(ImportJob)
        .options(joinedload(ImportJob.source).joinedload(SourceDefinition.import_template))
        .where(ImportJob.id == job_id)
    )
    if not job or job.template_slug != "product_master":
        raise HTTPException(status_code=404, detail="Job not found")
    headers = job.file_headers or []
    suggestions = None
    if headers and job.source:
        suggestions = attach_pm_suggestion_summaries(
            suggest_mapping_decisions(headers, job.source, job.inferred_schema)
        )
    md_norm = normalize_mapping_decisions(job.mapping_decisions) if job.mapping_decisions else None
    sev_result = await db.execute(
        select(ImportRowResult.severity, func.count(ImportRowResult.id))
        .where(ImportRowResult.job_id == job_id)
        .group_by(ImportRowResult.severity)
    )
    sev_counts = {str(row[0]): int(row[1]) for row in sev_result.all()}
    progress = build_pm_import_progress(job, sev_counts)
    return {
        "id": job.id,
        "stage": job.stage,
        "status": job.status,
        "file_name": job.file_name,
        "file_headers": headers,
        "suggested_mapping": suggestions,
        "mapping_decisions": md_norm,
        "canonical_fields": sorted(PM_CANONICAL_GENERIC),
        "required_fields": sorted(PM_REQUIRED_NON_IDENTITY),
        "identity_targets": sorted(PM_IDENTITY_TARGETS),
        "identity_rule": "exactly_one",
        "field_definitions": field_definitions_for_api(),
        "validation_passed": job.validation_passed,
        "error_summary": job.error_summary,
        "staged_metadata_preview": job.staged_metadata,
        "inferred_schema": job.inferred_schema,
        "progress": progress,
    }


@router.put("/jobs/{job_id}/mapping")
async def put_product_master_mapping(
    job_id: int,
    body: PMMappingBody,
    db: AsyncSession = Depends(get_db),
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
):
    _require_admin(x_user_role)
    job = await db.get(ImportJob, job_id)
    if not job or job.template_slug != "product_master":
        raise HTTPException(status_code=404, detail="Job not found")
    cols = [c.model_dump(exclude_none=False) for c in body.columns]
    try:
        with SessionLocal() as sync_db:
            save_mapping_sync(sync_db, job_id, cols)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await db.refresh(job)
    return {"id": job.id, "stage": job.stage, "mapping_decisions": job.mapping_decisions}


@router.post("/jobs/{job_id}/validate")
async def post_product_master_validate(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
):
    _require_admin(x_user_role)
    try:
        with SessionLocal() as sync_db:
            validate_product_master_sync(sync_db, job_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("product_master validate failed job_id=%s", job_id)
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Product Master validation failed due to an internal error.",
                "code": "pm_validate_internal",
            },
        ) from e
    job = await db.get(ImportJob, job_id)
    return {
        "id": job_id,
        "stage": job.stage if job else None,
        "status": job.status if job else None,
        "validation_passed": job.validation_passed if job else None,
        "error_summary": job.error_summary if job else None,
    }


@router.post("/jobs/{job_id}/commit")
async def post_product_master_commit(
    job_id: int,
    confirm_destructive: bool = Form(default=False),
    db: AsyncSession = Depends(get_db),
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
):
    _require_admin(x_user_role)
    try:
        with SessionLocal() as sync_db:
            out = try_enqueue_pm_commit_sync(sync_db, job_id, confirm_destructive=confirm_destructive)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    oc = out["outcome"]
    if oc == "not_found":
        raise HTTPException(status_code=404, detail=out["message"])
    if oc == "not_eligible":
        raise HTTPException(status_code=400, detail=out["message"])

    if oc == "enqueued":
        tid = BackgroundTaskStore.create_task(
            task_type="product_master_commit",
            title="Product Master commit",
            status="queued",
            import_job_id=job_id,
            extra={"commit_phase": "queued"},
        )
        if tid:
            BackgroundTaskStore.link_pm_import_job(job_id, tid)
        settings = get_settings()
        if settings.cip_dev_celery_dispatch == "in_process_thread":

            def _in_process_pm_commit() -> None:
                try:
                    run_product_master_commit_job(
                        job_id,
                        confirm_destructive,
                        celery_task_id="dev-in-process-thread",
                    )
                except Exception:
                    logger.exception(
                        "product_master commit in-process thread failed job_id=%s (CIP_DEV_CELERY_DISPATCH=in_process_thread)",
                        job_id,
                    )

            DEV_CELERY_LOGGER.warning(
                "ENQUEUE: job_id=%s — CIP_DEV_CELERY_DISPATCH=in_process_thread (DEV ONLY). "
                "Starting daemon thread for PM commit (no Celery broker). Use broker + worker for production-like behavior.",
                job_id,
            )
            threading.Thread(target=_in_process_pm_commit, name=f"pm-commit-{job_id}", daemon=True).start()
        else:
            try:
                product_master_commit_task.delay(job_id, confirm_destructive)
            except Exception as e:
                logger.exception("product_master commit dispatch failed job_id=%s", job_id)
                with SessionLocal() as sync_db2:
                    j2 = sync_db2.get(ImportJob, job_id)
                    if j2 is not None and j2.status == STATUS_PM_COMMIT_QUEUED:
                        meta = dict(j2.pm_commit_meta) if isinstance(j2.pm_commit_meta, dict) else {}
                        meta["dispatch_error"] = str(e)[:800]
                        j2.pm_commit_meta = meta
                        j2.status = "validated"
                        j2.error_summary = "Commit could not be dispatched to the worker (broker unavailable?)."
                        sync_db2.commit()
                raise HTTPException(
                    status_code=503,
                    detail={
                        "message": "Commit was recorded but could not be dispatched to the worker. Check Redis and the worker service, or set CIP_DEV_CELERY_DISPATCH=in_process_thread for local dev only.",
                        "code": "pm_commit_dispatch_failed",
                    },
                ) from e

    job = await db.get(ImportJob, job_id)
    payload: dict = {
        "id": job_id,
        "stage": job.stage if job else None,
        "status": job.status if job else None,
        "pm_commit": {
            "outcome": oc,
            "message": out["message"],
        },
    }
    return JSONResponse(status_code=int(out["http_status"]), content=payload)
