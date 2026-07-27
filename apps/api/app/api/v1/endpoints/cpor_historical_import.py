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
from app.services.cpor.historical_import.resolution_plan import build_cpor_historical_resolution_plan_sync
from app.services.cpor.historical_import.resolve import (
    case_apply_blockers,
    list_unresolved_candidates,
    map_staging_token,
    map_staging_tokens,
    plan_class_counts,
)
from app.services.imports.import_background_slots import (
    SLOT_CPOR_RESOLUTION_PLAN,
    SLOT_MAIN,
    clear_task_slot_on_job,
    set_task_slot_on_job,
)
from app.services.imports.import_dispatch import enqueue_import_worker_task
from app.services.imports.import_job_background_metadata import ACTIVE_CELERY_STATES, read_main_celery_state
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


class ResolutionPlanGenerateBody(BaseModel):
    candidate_ids: list[int] | None = None


class ResolutionPlanApplyBody(BaseModel):
    candidate_ids: list[int] = Field(min_length=1)


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


def _cpor_resolution_plan_task_id(job: ImportJob) -> str | None:
    meta = job.staged_metadata if isinstance(job.staged_metadata, dict) else {}
    slot = meta.get("cpor_resolution_plan_task")
    if not isinstance(slot, dict):
        return None
    tid = slot.get("task_id")
    return tid.strip() if isinstance(tid, str) and tid.strip() else None


def _assert_cpor_resolution_plan_dispatch_allowed(job: ImportJob) -> None:
    """409 guard (Unit C, D-013 dispatch-claim) — block a new plan compute/apply while case
    validate/apply (SLOT_MAIN) or another resolution-plan task (SLOT_CPOR_RESOLUTION_PLAN) is
    already in flight for this job. Concurrent writers to the same staging rows would race.
    """
    if (job.status or "").strip().lower() == "running":
        state = read_main_celery_state(job)
        if state is not None and state in ACTIVE_CELERY_STATES:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "cpor_pipeline_busy",
                    "message": f"Historical CPOR validate/apply is already running for job {job.id}.",
                },
            )

    tid = _cpor_resolution_plan_task_id(job)
    if tid:
        from app.services.imports.background_tasks import read_celery_with_timeout

        try:
            state, _info = read_celery_with_timeout(tid, timeout_s=2.0)
        except Exception:
            state = None
        if state in ACTIVE_CELERY_STATES:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "cpor_resolution_plan_busy",
                    "message": f"A CPOR resolution plan task is already in flight for job {job.id}.",
                },
            )


def _write_cpor_resolution_plan_slot(job_id: int, task_id: str, *, async_poll: bool, label: str) -> None:
    """Record the CPOR resolution-plan Celery task on the job (own slot, never SLOT_MAIN)."""
    with SessionLocal() as meta_db:
        job = meta_db.get(ImportJob, job_id)
        if job is not None:
            set_task_slot_on_job(
                job, SLOT_CPOR_RESOLUTION_PLAN, task_id=task_id, async_poll=async_poll, label=label
            )
            meta_db.commit()


def _clear_cpor_resolution_plan_slot(job_id: int) -> None:
    with SessionLocal() as sess:
        job = sess.get(ImportJob, job_id)
        if job is not None:
            clear_task_slot_on_job(job, SLOT_CPOR_RESOLUTION_PLAN)
            sess.commit()


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
        db.commit()  # persist any newly get-or-created token surrogate ids (D-014)
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
    plan_class: Annotated[
        Literal["ready_to_map", "ambiguous_eligible", "needs_review", "no_match"] | None, Query()
    ] = None,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int | None, Query(ge=1, le=5000)] = None,
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
) -> dict[str, Any]:
    """Steward candidates for one entity tab (Unit C S12 server pagination, S9 plan_class filter).

    ``plan_class`` filters the returned page server-side (avoids the queue-chip collision from
    client-side filtering a truncated page). ``counts`` / ``plan_class_counts`` always reflect
    the *full* unfiltered/unpaginated set so queue chips stay correct regardless of the current
    page. When ``limit`` is omitted, all matching rows are returned (byte-compatible with the
    pre-Unit-C response) — pass ``skip``/``limit`` to opt into pagination.
    """
    _require_admin(x_user_role)
    with SessionLocal() as db:
        _get_job_sync(db, job_id)
        all_c = list_unresolved_candidates(db, job_id=job_id)
        db.commit()  # persist any newly get-or-created token surrogate ids (D-014)
        counts = {k: len(v) for k, v in all_c.items()}
        pcc = plan_class_counts(all_c)
        rows = all_c.get(entity) or []
        if plan_class is not None:
            rows = [r for r in rows if r.get("plan_class") == plan_class]
        total = len(rows)
        limit_val = limit if limit is not None else (total or 1)
        page_rows = rows[skip : skip + limit_val]
        return {
            "entity": entity,
            "candidates": page_rows,
            "items": page_rows,
            "total": total,
            "skip": skip,
            "limit": limit_val,
            "counts": counts,
            "plan_class_counts": pcc,
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


# --- Resolution plan (Unit C, D-013) -------------------------------------------------------
#
# Transient steward resolution plan over the same unresolved token candidates as
# .../candidates (S9 plan engine). Own background-task slot (``SLOT_CPOR_RESOLUTION_PLAN``) —
# never ``SLOT_MAIN``, which stays reserved for validate/case-apply (``historical_validate`` /
# ``historical_apply`` above). Poll via .../resolution-plan-task/{task_id}, mirroring
# ``shipment_evidence.shipment_bulk_task_status`` — the shared .../progress endpoint above is
# scoped to SLOT_MAIN pipeline-stage tracking and does not read this slot.


@router.post("/historical-import/jobs/{job_id}/resolution-plan", status_code=200)
def historical_resolution_plan_generate(
    job_id: int,
    body: ResolutionPlanGenerateBody,
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
) -> dict[str, Any]:
    """Synchronous plan generation — small jobs / tests. Prefer compute-async for steward UI."""
    _require_admin(x_user_role)
    with SessionLocal() as db:
        try:
            out = build_cpor_historical_resolution_plan_sync(db, job_id, candidate_ids=body.candidate_ids)
            db.commit()  # persist any newly get-or-created token surrogate ids (D-014)
            return out
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/historical-import/jobs/{job_id}/resolution-plan/compute-async", status_code=202)
def historical_resolution_plan_compute_async(
    job_id: int,
    body: ResolutionPlanGenerateBody,
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
) -> dict[str, Any]:
    _require_admin(x_user_role)
    with SessionLocal() as s:
        job = _get_job_sync(s, job_id)
        _assert_cpor_resolution_plan_dispatch_allowed(job)

    payload = {"candidate_ids": list(body.candidate_ids) if body.candidate_ids else None}
    from app.services.cpor.historical_import.resolution_plan_enqueue import (
        TASK_CPOR_RESOLUTION_PLAN_COMPUTE,
        enqueue_cpor_resolution_plan_task,
        run_cpor_historical_resolution_plan_compute_sync,
    )

    task_id, async_poll = enqueue_cpor_resolution_plan_task(
        task_name=TASK_CPOR_RESOLUTION_PLAN_COMPUTE,
        job_id=job_id,
        payload=payload,
        run_sync=lambda: run_cpor_historical_resolution_plan_compute_sync(job_id, payload),
        dev_prefix="cpor-plan-compute",
    )
    _write_cpor_resolution_plan_slot(
        job_id, task_id, async_poll=async_poll, label="Computing CPOR resolution plan…"
    )
    return {"import_job_id": job_id, "task_id": task_id, "async_poll": async_poll, "async": True}


@router.post("/historical-import/jobs/{job_id}/resolution-plan/apply-async", status_code=202)
def historical_resolution_plan_apply_async(
    job_id: int,
    body: ResolutionPlanApplyBody,
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
) -> dict[str, Any]:
    """Apply ready resolution-plan rows — per-token map_staging_token (D-013; never bulk single-target)."""
    _require_admin(x_user_role)
    with SessionLocal() as s:
        job = _get_job_sync(s, job_id)
        _assert_cpor_resolution_plan_dispatch_allowed(job)

    payload = {"candidate_ids": [int(x) for x in body.candidate_ids]}
    from app.services.cpor.historical_import.resolution_plan_enqueue import (
        TASK_CPOR_RESOLUTION_PLAN_APPLY,
        enqueue_cpor_resolution_plan_task,
        run_cpor_historical_resolution_plan_apply_sync,
    )

    task_id, async_poll = enqueue_cpor_resolution_plan_task(
        task_name=TASK_CPOR_RESOLUTION_PLAN_APPLY,
        job_id=job_id,
        payload=payload,
        run_sync=lambda: run_cpor_historical_resolution_plan_apply_sync(job_id, payload),
        dev_prefix="cpor-plan-apply",
    )
    _write_cpor_resolution_plan_slot(
        job_id, task_id, async_poll=async_poll, label="Applying CPOR resolution plan…"
    )
    return {"import_job_id": job_id, "task_id": task_id, "async_poll": async_poll, "async": True}


@router.get("/historical-import/jobs/{job_id}/resolution-plan-task/{task_id}", status_code=200)
def historical_resolution_plan_task_status(job_id: int, task_id: str) -> dict[str, Any]:
    """Poll a CPOR resolution-plan Celery task (or dev in-process / sync fallback) state + result.

    Mirrors ``shipment_evidence.shipment_bulk_task_status``: clears the registered
    ``cpor_resolution_plan_task`` slot once the task is terminal.
    """
    from app.services.cpor.historical_import.resolution_plan_enqueue import (
        dev_cpor_resolution_plan_task_results,
    )

    dev_store = dev_cpor_resolution_plan_task_results()
    dev_hit = dev_store.get(task_id)
    if dev_hit is not None:
        state = dev_hit.get("state", "SUCCESS")
        if state in ("SUCCESS", "FAILURE"):
            dev_store.pop(task_id, None)
        out: dict[str, Any] = {"import_job_id": job_id, "task_id": task_id, "state": state}
        if state == "SUCCESS":
            out["result"] = dev_hit.get("result")
        else:
            out["error"] = dev_hit.get("error")
        if state in ("SUCCESS", "FAILURE"):
            _clear_cpor_resolution_plan_slot(job_id)
        return out

    from celery.result import AsyncResult

    result = AsyncResult(task_id, app=celery_app)
    task_state = result.state
    info = result.info
    progress: dict[str, Any] = {"import_job_id": job_id, "task_id": task_id, "state": task_state}
    if task_state == "PROGRESS" and isinstance(info, dict):
        progress["phase"] = info.get("phase")
        progress["phase_label"] = info.get("phase_label")
        progress["current_row"] = info.get("current_row", 0)
        progress["total_rows"] = info.get("total_rows", 0)
        progress["pct"] = info.get("pct", 0)
    elif task_state == "SUCCESS":
        progress["result"] = result.result if isinstance(result.result, dict) else None
    elif task_state == "FAILURE":
        progress["error"] = str(info)[:800] if info is not None else "Task failed"

    if task_state in ("SUCCESS", "FAILURE", "REVOKED"):
        _clear_cpor_resolution_plan_slot(job_id)

    return progress
