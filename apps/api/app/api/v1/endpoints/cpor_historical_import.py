"""CPOR historical import API — validate, steward resolve, async apply (H2)."""

from __future__ import annotations

import logging
import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.dev_celery_logging import DEV_CELERY_LOGGER
from app.db.session_sync import SessionLocal
from app.models.cpor_historical import CporHistoricalMappingProfile, ImportCporHistoricalStagingLine
from app.models.ingestion import ImportJob
from app.services.cpor.historical_import.apply_sync import run_cpor_historical_apply_sync
from app.services.cpor.historical_import.pipeline import ensure_default_mapping_profile
from app.services.cpor.historical_import.resolve import (
    case_apply_blockers,
    list_unresolved_candidates,
    map_staging_token,
    map_staging_tokens,
    plan_class_counts,
)
from app.services.imports.import_background_slots import SLOT_MAIN, set_task_slot_on_job
from app.services.imports.import_dispatch import enqueue_import_worker_task
from app.services.imports.import_pipeline_dispatch_claim import claim_import_pipeline_dispatch
from app.ingestion.pipeline import process_import_job_sync
from app.services.task_run_ledger import (
    ENTITY_IMPORT_JOB,
    TRANSPORT_BROKER,
    TRANSPORT_INLINE_SYNC,
    TRANSPORT_IN_PROCESS_THREAD,
    create_queued_task_run,
    run_inline_with_ledger,
    spawn_in_process_thread_with_ledger,
)
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)
router = APIRouter()

TEMPLATE_SLUG = "cpor_historical_cases"


class MapTokenBody(BaseModel):
    entity: Literal["product", "customer", "distributor"]
    token: str = Field(min_length=1, max_length=256)
    dim_id: int = Field(gt=0)


class BulkMapTokenBody(BaseModel):
    entity: Literal["product", "customer", "distributor"]
    tokens: list[str] = Field(min_length=1)
    dim_id: int = Field(gt=0)


class ApplyBody(BaseModel):
    confirm: bool = False


def _require_admin(x_user_role: str | None) -> None:
    if (x_user_role or "").strip().lower() != "admin":
        raise HTTPException(
            status_code=403,
            detail={"error": "admin_required", "message": "Admin required for historical CPOR import"},
        )


def _get_job_sync(db: Session, job_id: int) -> ImportJob:
    job = db.get(ImportJob, job_id)
    if job is None or (job.template_slug or "") != TEMPLATE_SLUG:
        raise HTTPException(status_code=404, detail={"error": "job_not_found"})
    return job


def _dispatch_cpor_historical_apply(job_id: int) -> tuple[bool, str | None]:
    settings = get_settings()
    task_name = "imports.cpor_historical_apply"
    try:
        result = celery_app.send_task(task_name, args=[job_id], ignore_result=True)
        task_run_id = str(result.id)
        create_queued_task_run(
            task_run_id=task_run_id,
            task_name=task_name,
            entity_type=ENTITY_IMPORT_JOB,
            entity_id=job_id,
            transport=TRANSPORT_BROKER,
        )
        return True, result.id
    except Exception:
        logger.exception("CPOR historical apply: Celery enqueue failed job_id=%s", job_id)
        if settings.cip_dev_celery_dispatch == "in_process_thread":
            task_run_id = f"thread-{uuid.uuid4().hex}"
            create_queued_task_run(
                task_run_id=task_run_id,
                task_name=task_name,
                entity_type=ENTITY_IMPORT_JOB,
                entity_id=job_id,
                transport=TRANSPORT_IN_PROCESS_THREAD,
            )

            def _in_process() -> None:
                run_cpor_historical_apply_sync(job_id)

            DEV_CELERY_LOGGER.warning(
                "ENQUEUE: CPOR historical apply job_id=%s — in-process thread after broker failure.",
                job_id,
            )
            spawn_in_process_thread_with_ledger(
                task_run_id=task_run_id,
                thread_name=f"cpor-hist-apply-{job_id}",
                target=_in_process,
            )
            return True, None

        task_run_id = f"inline-{uuid.uuid4().hex}"
        create_queued_task_run(
            task_run_id=task_run_id,
            task_name=task_name,
            entity_type=ENTITY_IMPORT_JOB,
            entity_id=job_id,
            transport=TRANSPORT_INLINE_SYNC,
        )
        run_inline_with_ledger(task_run_id, lambda: run_cpor_historical_apply_sync(job_id))
        return False, None


@router.get("/historical-import/profiles")
async def list_mapping_profiles(
    db: Annotated[AsyncSession, Depends(get_db)],
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
) -> dict[str, Any]:
    _require_admin(x_user_role)
    # Ensure default exists via sync (seed)
    with SessionLocal() as sdb:
        ensure_default_mapping_profile(sdb)
        sdb.commit()
    rows = (
        await db.scalars(select(CporHistoricalMappingProfile).order_by(CporHistoricalMappingProfile.id))
    ).all()
    return {
        "profiles": [
            {
                "id": r.id,
                "profile_code": r.profile_code,
                "display_name": r.display_name,
                "header_row_index": r.header_row_index,
                "sheet_roles_json": r.sheet_roles_json,
                "column_map_json": r.column_map_json,
                "value_maps_json": r.value_maps_json,
                "is_default": r.is_default,
            }
            for r in rows
        ]
    }


@router.get("/historical-import/jobs/{job_id}/summary")
def historical_job_summary(
    job_id: int,
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
) -> dict[str, Any]:
    _require_admin(x_user_role)
    with SessionLocal() as db:
        job = _get_job_sync(db, job_id)
        staging_count = (
            db.scalar(
                select(func.count())
                .select_from(ImportCporHistoricalStagingLine)
                .where(ImportCporHistoricalStagingLine.import_job_id == job_id)
            )
            or 0
        )
        unresolved = list_unresolved_candidates(db, job_id=job_id)
        rows = list(
            db.scalars(
                select(ImportCporHistoricalStagingLine).where(
                    ImportCporHistoricalStagingLine.import_job_id == job_id,
                    ImportCporHistoricalStagingLine.skip_apply.is_(False),
                )
            ).all()
        )
        by_case: dict[str, list[ImportCporHistoricalStagingLine]] = {}
        for r in rows:
            by_case.setdefault(r.case_code, []).append(r)
        ready = 0
        blocked = 0
        for code, case_rows in by_case.items():
            blockers: set[str] = set()
            for r in case_rows:
                blockers.update(case_apply_blockers(r))
            if blockers:
                blocked += 1
            else:
                ready += 1
        hist = (job.staged_metadata or {}).get("cpor_historical") or {}
        return {
            "id": job.id,
            "stage": job.stage,
            "status": job.status,
            "file_name": job.file_name,
            "staging_count": staging_count,
            "unresolved_counts": {k: len(v) for k, v in unresolved.items()},
            "plan_class_counts": plan_class_counts(unresolved),
            "cases_ready": ready,
            "cases_blocked": blocked,
            "cpor_historical": hist,
        }


@router.get("/historical-import/jobs/{job_id}/candidates")
def historical_candidates(
    job_id: int,
    entity: Annotated[Literal["product", "customer", "distributor"], Query()] = "product",
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
) -> dict[str, Any]:
    _require_admin(x_user_role)
    with SessionLocal() as db:
        _get_job_sync(db, job_id)
        all_c = list_unresolved_candidates(db, job_id=job_id)
        rows = all_c.get(entity) or []
        return {
            "entity": entity,
            "candidates": rows,
            "counts": {k: len(v) for k, v in all_c.items()},
            "plan_class_counts": plan_class_counts(all_c),
        }


@router.post("/historical-import/jobs/{job_id}/map-token")
def historical_map_token(
    job_id: int,
    body: MapTokenBody,
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
) -> dict[str, Any]:
    _require_admin(x_user_role)
    with SessionLocal() as db:
        _get_job_sync(db, job_id)
        updated = map_staging_token(
            db, job_id=job_id, entity=body.entity, token=body.token, dim_id=body.dim_id
        )
        db.commit()
        return {"updated": updated, "entity": body.entity, "token": body.token, "dim_id": body.dim_id}


@router.post("/historical-import/jobs/{job_id}/bulk-map-token")
def historical_bulk_map_token(
    job_id: int,
    body: BulkMapTokenBody,
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
) -> dict[str, Any]:
    _require_admin(x_user_role)
    tokens = [t.strip() for t in body.tokens if (t or "").strip()]
    if not tokens:
        raise HTTPException(status_code=400, detail={"error": "tokens_required"})
    with SessionLocal() as db:
        _get_job_sync(db, job_id)
        updated = map_staging_tokens(
            db, job_id=job_id, entity=body.entity, tokens=tokens, dim_id=body.dim_id
        )
        db.commit()
        return {
            "updated": updated,
            "entity": body.entity,
            "token_count": len(tokens),
            "dim_id": body.dim_id,
        }


@router.post("/historical-import/jobs/{job_id}/validate")
def historical_validate(
    job_id: int,
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
) -> dict[str, Any]:
    """Async validate (parse → stage → deterministic resolve) — same bar as DSI validate."""
    _require_admin(x_user_role)
    with SessionLocal() as db:
        _get_job_sync(db, job_id)
    claim_import_pipeline_dispatch(job_id, import_mode="validate")

    dispatched, task_id = enqueue_import_worker_task(
        job_id,
        task_name="imports.process_job",
        log_label="CPOR historical validate",
        in_process_thread_name=f"cpor-hist-validate-{job_id}",
        sync_work=process_import_job_sync,
    )
    if task_id:
        with SessionLocal() as db:
            job = db.get(ImportJob, job_id)
            if job is not None:
                set_task_slot_on_job(job, SLOT_MAIN, task_id=task_id)
                db.commit()
    return {
        "id": job_id,
        "async": dispatched,
        "task_id": task_id,
        "message": "Historical CPOR validate queued" if dispatched else "Historical CPOR validate completed inline",
    }


@router.post("/historical-import/jobs/{job_id}/apply")
def historical_apply(
    job_id: int,
    body: ApplyBody,
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
) -> dict[str, Any]:
    _require_admin(x_user_role)
    if not body.confirm:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "confirm_required",
                "message": "Pass confirm=true to apply historical CPOR cases",
            },
        )
    with SessionLocal() as db:
        job = _get_job_sync(db, job_id)
        if (job.stage or "") not in ("validated", "loaded"):
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "not_validated",
                    "message": f"Job stage must be validated before apply (got {job.stage})",
                },
            )
        job.status = "running"
        job.import_mode = "apply"
        from datetime import datetime, timezone

        meta = dict(job.staged_metadata or {})
        meta["pipeline_queued_at"] = datetime.now(timezone.utc).isoformat()
        job.staged_metadata = meta
        db.commit()

    dispatched, task_id = _dispatch_cpor_historical_apply(job_id)
    if task_id:
        with SessionLocal() as db:
            job = db.get(ImportJob, job_id)
            if job is not None:
                set_task_slot_on_job(job, SLOT_MAIN, task_id=task_id)
                db.commit()
    return {
        "id": job_id,
        "async": dispatched,
        "task_id": task_id,
        "message": "Historical CPOR apply queued" if dispatched else "Historical CPOR apply completed inline",
    }


@router.get("/historical-import/jobs/{job_id}/progress")
def historical_progress(
    job_id: int,
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
) -> dict[str, Any]:
    """Celery PROGRESS + DB fallback — same shape as DSI ``dsi-progress``."""
    _require_admin(x_user_role)
    from app.services.imports.background_tasks import read_celery_with_timeout
    from app.services.imports.import_job_background_metadata import (
        ACTIVE_CELERY_STATES,
        job_db_indicates_pipeline_finished,
    )

    with SessionLocal() as db:
        job = _get_job_sync(db, job_id)
        stage = (job.stage or "").strip()
        status = (job.status or "").strip()
        meta = dict(job.staged_metadata or {})
        hist = meta.get("cpor_historical") or {}
        task_id: str | None = meta.get("celery_task_id")
        if isinstance(task_id, dict):
            task_id = task_id.get("task_id")  # type: ignore[assignment]
        total_rows = int(hist.get("row_count") or hist.get("staging_upserted") or 0)

        progress: dict[str, Any] = {
            "job_id": job_id,
            "id": job_id,
            "stage": stage,
            "status": status,
            "phase": "idle",
            "phase_label": "Idle",
            "current_row": 0,
            "total_rows": total_rows,
            "pct": 0,
            "task_state": None,
            "pipeline_queued_at": meta.get("pipeline_queued_at"),
            "pipeline_started_at": meta.get("pipeline_started_at"),
            "error_summary": job.error_summary,
            "apply": hist.get("apply"),
            "cpor_historical": hist,
        }

        if job_db_indicates_pipeline_finished(job) and (job.import_mode or "") != "apply":
            # Validate finished
            progress["phase"] = "complete"
            progress["phase_label"] = "Validated" if stage == "validated" else stage or "Complete"
            progress["pct"] = 100
            progress["current_row"] = total_rows
            if status in ("failed", "interrupted") or stage in ("failed", "stage_failed"):
                progress["phase"] = "failed"
                progress["phase_label"] = "Failed"
            return progress

        if stage == "loaded" and status in ("completed", "completed_with_errors"):
            progress["phase"] = "complete"
            progress["phase_label"] = "Apply complete"
            progress["pct"] = 100
            return progress

    if task_id:
        try:
            task_state, info = read_celery_with_timeout(str(task_id), timeout_s=3.0)
            progress["task_state"] = task_state
            state_u = (str(task_state or "PENDING")).strip().upper()
            if isinstance(info, dict) and state_u in ACTIVE_CELERY_STATES:
                progress["phase"] = info.get("phase", "processing_rows")
                progress["phase_label"] = info.get("phase_label", "Processing")
                progress["current_row"] = info.get("current_row", 0)
                progress["total_rows"] = info.get("total_rows", 0) or total_rows
                progress["pct"] = info.get("pct", 0)
                progress["progress_at"] = info.get("progress_at")
                if state_u in ("PENDING", "STARTED") and not info:
                    progress["phase"] = "queued"
                    progress["phase_label"] = "Queued"
                return progress
        except Exception as exc:
            logger.debug("historical_progress: Celery read failed job_id=%s: %s", job_id, exc)

    if status == "running":
        progress["phase"] = "processing_rows"
        progress["phase_label"] = "Processing historical CPOR import"
    elif status in ("failed", "interrupted") or stage in ("failed", "stage_failed"):
        progress["phase"] = "failed"
        progress["phase_label"] = "Failed"
    return progress
