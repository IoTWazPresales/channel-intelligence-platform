import json
import logging
import threading
import uuid
from typing import Annotated, Any, Callable

from fastapi import APIRouter, Body, Depends, File, Form, Header, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.dev_celery_logging import DEV_CELERY_LOGGER
from app.db.session_sync import SessionLocal
from app.ingestion.pipeline import process_import_job_sync
from app.services.imports.dsi_mapping_workflow import (
    dsi_mapping_gate_errors,
    dsi_mapping_state_dict,
    infer_dsi_job_sync,
    merge_dsi_mapping_memory,
    sanitize_dsi_field_mapping,
)
from app.services.imports.shipment_field_mapping import (
    infer_shipment_import_job_sync,
    merge_shipment_mapping_memory,
    sanitize_shipment_field_mapping,
    shipment_mapping_gate_errors,
    shipment_mapping_state_dict,
)
from app.models.historical_lineup import HistoricalLineupImportHeader, HistoricalLineupImportLine
from app.models.ingestion import ImportJob, ImportRowResult, ImportTemplate, RawFileMetadata, SourceDefinition
from app.storage.local import get_storage_backend
from app.services.imports.import_job_bulk_delete import bulk_delete_import_jobs, normalize_job_ids, preview_import_job_bulk_delete
from app.services.imports.template_definitions import product_master_sample_csv
from app.utils.json_safe import to_jsonable
from app.worker.celery_app import celery_app

router = APIRouter()
logger = logging.getLogger(__name__)


async def _async_import_job_with_source(db: AsyncSession, job_id: int) -> ImportJob | None:
    """Load ``ImportJob`` with ``source`` + ``import_template`` eager (avoids lazy IO under ``AsyncSession``)."""
    return await db.scalar(
        select(ImportJob)
        .options(joinedload(ImportJob.source).joinedload(SourceDefinition.import_template))
        .where(ImportJob.id == job_id)
    )


def _wants_inline_import_processing(run_sync_raw: str) -> bool:
    """Parse the multipart ``run_sync`` form value into a boolean.

    Returns True when processing should run inline in the API process.
    Returns False when the caller wants deferred/async processing.
    """
    s0 = str(run_sync_raw).strip()
    if len(s0) >= 2 and s0[0] == s0[-1] and s0[0] in "'\"":
        s0 = s0[1:-1].strip()
    s = s0.lower()
    if s in ("0", "false", "no", "off", "n"):
        return False
    if s in ("1", "true", "yes", "on", "y"):
        return True
    return True


def _enqueue_import_worker_task(
    job_id: int,
    *,
    task_name: str,
    log_label: str,
    in_process_thread_name: str,
    sync_work: Callable[[Session, int], Any],
) -> tuple[bool, str | None]:
    """Publish ``task_name`` to the Celery broker; mirror upload/validate fallback semantics.

    Uses ``celery_app.send_task`` so dispatch matches the worker-registered task name regardless
    of import binding order. On broker failure: dev-only in-process thread when
    ``CIP_DEV_CELERY_DISPATCH=in_process_thread``, otherwise run ``sync_work`` inline in this process.

    Returns ``(dispatched, task_id)`` where dispatched is ``True`` when the HTTP layer should treat
    the operation as async (broker accepted the message, or a dev thread was started), and
    ``task_id`` is the Celery task ID when dispatched via the broker (``None`` otherwise).
    """
    settings = get_settings()
    try:
        result = celery_app.send_task(task_name, args=[job_id], ignore_result=True)
        return True, result.id
    except Exception:
        logger.exception("%s: Celery enqueue failed job_id=%s task=%s", log_label, job_id, task_name)
        if settings.cip_dev_celery_dispatch == "in_process_thread":

            def _in_process() -> None:
                try:
                    with SessionLocal() as s2:
                        sync_work(s2, job_id)
                except Exception:
                    logger.exception(
                        "%s: in-process thread failed job_id=%s "
                        "(CIP_DEV_CELERY_DISPATCH=in_process_thread after broker failure)",
                        log_label,
                        job_id,
                    )

            DEV_CELERY_LOGGER.warning(
                "ENQUEUE: %s job_id=%s — in-process thread after broker failure (DEV ONLY).",
                log_label,
                job_id,
            )
            threading.Thread(target=_in_process, name=in_process_thread_name, daemon=True).start()
            return True, None
        with SessionLocal() as sync_fallback:
            sync_work(sync_fallback, job_id)
        return False, None


def _enqueue_import_pipeline_job(job_id: int, *, log_label: str, in_process_thread_name: str) -> tuple[bool, str | None]:
    """Enqueue full import pipeline (``imports.process_job``) — validate/apply processing."""
    return _enqueue_import_worker_task(
        job_id,
        task_name="imports.process_job",
        log_label=log_label,
        in_process_thread_name=in_process_thread_name,
        sync_work=process_import_job_sync,
    )


def _raise_if_import_pipeline_busy(job: ImportJob) -> None:
    """Reject a second validate/revalidate while Celery work is still active."""
    from app.services.imports.import_job_background_metadata import (
        ACTIVE_CELERY_STATES,
        pipeline_dispatch_conflict_message,
        read_main_celery_state,
    )

    if (job.status or "").strip().lower() != "running":
        return
    state = read_main_celery_state(job)
    if state is not None and state in ACTIVE_CELERY_STATES:
        raise HTTPException(status_code=409, detail=pipeline_dispatch_conflict_message(int(job.id)))


def _prepare_dsi_pipeline_dispatch(job_id: int) -> None:
    """Mark job running before broker dispatch so progress/background UI stay accurate."""
    from app.services.imports.import_job_background_metadata import persist_pipeline_queued_at

    with SessionLocal() as sync_db:
        j = sync_db.get(ImportJob, job_id)
        if j is None:
            raise HTTPException(status_code=404, detail="Import job not found")
        _raise_if_import_pipeline_busy(j)
        j.import_mode = "validate"
        j.status = "running"
        persist_pipeline_queued_at(sync_db, j)
        sync_db.commit()


def _persist_pipeline_celery_task_id(job_id: int, task_id: str | None) -> None:
    if not task_id:
        return
    with SessionLocal() as meta_db:
        j_meta = meta_db.get(ImportJob, job_id)
        if j_meta is None:
            return
        m = dict(j_meta.staged_metadata or {})
        m["celery_task_id"] = task_id
        j_meta.staged_metadata = m
        meta_db.commit()


def _is_admin(x_user_role: str | None) -> bool:
    return (x_user_role or "").strip().lower() == "admin"


def _require_admin_import_maintenance(
    x_user_role: Annotated[str | None, Header(alias="X-User-Role")] = None,
) -> None:
    if not _is_admin(x_user_role):
        raise HTTPException(
            status_code=403,
            detail={"error": "admin_required", "message": "Admin maintenance requires X-User-Role: admin"},
        )


class ImportJobBulkIdsBody(BaseModel):
    job_ids: list[int] = Field(default_factory=list, max_length=200)


class ImportJobBulkDeleteConfirmBody(ImportJobBulkIdsBody):
    delete_semantic_artifacts: bool = False


def _template_to_api(t: ImportTemplate) -> dict[str, Any]:
    ec = t.expected_columns or {}
    required: list[str] = []
    optional: list[str] = []
    for key, meta in ec.items():
        if isinstance(meta, dict) and meta.get("required"):
            required.append(key)
        else:
            optional.append(key)
    return {
        "id": t.id,
        "slug": t.slug,
        "display_name": t.display_name,
        "description": t.description,
        "enabled": t.enabled,
        "hidden": t.hidden,
        "admin_only": t.admin_only,
        "requires_provider": t.requires_provider,
        "pipeline_handler": t.pipeline_handler,
        "destructive_apply_requires_confirm": t.destructive_apply_requires_confirm,
        "accepted_file_types": t.accepted_file_types or [".csv", ".xlsx"],
        "expected_columns": ec,
        "required_fields": required,
        "optional_fields": optional,
        "pipeline_ready": t.pipeline_handler not in ("stub_noop",),
    }


@router.get("/templates")
async def list_import_templates(
    db: AsyncSession = Depends(get_db),
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
):
    """First-class import types (product master, distributor inventory, …)."""
    admin = _is_admin(x_user_role)
    stmt = select(ImportTemplate).where(ImportTemplate.enabled.is_(True)).order_by(ImportTemplate.slug)
    if not admin:
        stmt = stmt.where(ImportTemplate.hidden.is_(False), ImportTemplate.admin_only.is_(False))
    res = await db.execute(stmt)
    rows = res.scalars().all()
    return [_template_to_api(t) for t in rows]


@router.get("/templates/{slug}")
async def get_import_template(
    slug: str,
    db: AsyncSession = Depends(get_db),
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
):
    admin = _is_admin(x_user_role)
    t = await db.scalar(select(ImportTemplate).where(ImportTemplate.slug == slug))
    if not t or not t.enabled:
        raise HTTPException(status_code=404, detail="Template not found")
    if (t.hidden or t.admin_only) and not admin:
        raise HTTPException(status_code=404, detail="Template not found")
    return _template_to_api(t)


@router.get("/templates/{slug}/sample")
async def download_sample_template(slug: str):
    if slug != "product_master":
        raise HTTPException(status_code=404, detail="Sample not available for this template yet")
    body = product_master_sample_csv()
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{slug}_sample.csv"'},
    )


@router.get("/sources")
async def list_sources(
    db: AsyncSession = Depends(get_db),
    template_slug: str | None = Query(default=None, description="Filter feeds for this import template"),
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
):
    """Provider / feed instances (dim on `import_template`)."""
    admin = _is_admin(x_user_role)
    stmt = (
        select(SourceDefinition)
        .options(joinedload(SourceDefinition.import_template))
        .join(ImportTemplate, SourceDefinition.import_template_id == ImportTemplate.id)
        .where(SourceDefinition.is_active.is_(True), ImportTemplate.enabled.is_(True))
    )
    if not admin:
        stmt = stmt.where(ImportTemplate.hidden.is_(False), ImportTemplate.admin_only.is_(False))
    # Admins: may still filter by template_slug; otherwise see feeds for hidden/admin templates too
    if template_slug:
        stmt = stmt.where(ImportTemplate.slug == template_slug.strip())
    res = await db.execute(stmt.order_by(SourceDefinition.code))
    rows = res.unique().scalars().all()
    return [
        {
            "id": s.id,
            "code": s.code,
            "name": s.name,
            "source_kind": s.source_kind,
            "parser_module": s.parser_module,
            "is_active": s.is_active,
            "import_template_slug": s.import_template.slug if s.import_template else None,
        }
        for s in rows
    ]


@router.get("/jobs")
async def list_jobs(
    db: AsyncSession = Depends(get_db),
    include_archived: bool = Query(default=False, description="When true, include jobs with archived_at set."),
    limit: int = Query(default=50, ge=1, le=200, description="Max jobs returned (newest first)."),
    offset: int = Query(default=0, ge=0, description="Pagination offset."),
):
    """Lightweight job list — omits large JSONB blobs (inferred_schema, field_mapping, staged_metadata)."""
    filters = [] if include_archived else [ImportJob.archived_at.is_(None)]

    count_stmt = select(func.count()).select_from(ImportJob)
    if filters:
        count_stmt = count_stmt.where(*filters)
    total = int((await db.execute(count_stmt)).scalar_one() or 0)

    list_cols = (
        ImportJob.id,
        ImportJob.source_id,
        ImportJob.template_slug,
        ImportJob.import_mode,
        ImportJob.status,
        ImportJob.stage,
        ImportJob.file_name,
        ImportJob.error_summary,
        ImportJob.archived_at,
        ImportJob.created_at,
    )
    stmt = select(*list_cols).order_by(ImportJob.id.desc()).limit(limit).offset(offset)
    if filters:
        stmt = stmt.where(*filters)

    rows = (await db.execute(stmt)).all()
    items = [
        {
            "id": r.id,
            "source_id": r.source_id,
            "template_slug": r.template_slug,
            "import_mode": r.import_mode,
            "status": r.status,
            "stage": r.stage,
            "file_name": r.file_name,
            "error_summary": r.error_summary,
            "archived_at": r.archived_at,
            "created_at": r.created_at,
        }
        for r in rows
    ]
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(items) < total,
    }


@router.post("/jobs/bulk-delete-preview")
async def post_import_jobs_bulk_delete_preview(
    body: ImportJobBulkIdsBody,
    _admin: None = Depends(_require_admin_import_maintenance),
):
    """Return artifact counts for selected import jobs (admin maintenance; preview before delete)."""
    if not normalize_job_ids(body.job_ids):
        raise HTTPException(
            status_code=400,
            detail={"error": "no_valid_job_ids", "message": "Provide at least one valid import job id."},
        )
    with SessionLocal() as db:
        return preview_import_job_bulk_delete(db, body.job_ids)


@router.post("/jobs/bulk-delete-confirm")
async def post_import_jobs_bulk_delete_confirm(
    body: ImportJobBulkDeleteConfirmBody,
    _admin: None = Depends(_require_admin_import_maintenance),
):
    """Transactionally delete import jobs and directly linked ingestion artifacts (admin only)."""
    if not normalize_job_ids(body.job_ids):
        raise HTTPException(
            status_code=400,
            detail={"error": "no_valid_job_ids", "message": "Provide at least one valid import job id."},
        )
    with SessionLocal() as db:
        try:
            out = bulk_delete_import_jobs(
                db,
                body.job_ids,
                delete_semantic_artifacts=body.delete_semantic_artifacts,
            )
            db.commit()
        except ValueError as exc:
            db.rollback()
            code = str(exc)
            if code == "not_all_jobs_found":
                raise HTTPException(
                    status_code=409,
                    detail={
                        "error": code,
                        "message": "One or more job ids no longer exist; refresh the list and try again.",
                    },
                )
            if code == "semantic_artifacts_present":
                raise HTTPException(
                    status_code=422,
                    detail={
                        "error": code,
                        "message": (
                            "Steward aliases linked to these jobs still exist. "
                            "Preview counts are in the risky section; either remove aliases elsewhere first, "
                            "or confirm with delete_semantic_artifacts=true."
                        ),
                    },
                )
            raise HTTPException(status_code=400, detail={"error": code}) from exc
    return out


@router.post("/jobs")
async def create_job(
    source_id: int = Form(...),
    file: UploadFile = File(...),
    run_sync: str = Form(default="true"),
    import_mode: str = Form(default=""),
    confirm_destructive: str = Form(default=""),
    mapping_override: str = Form(default=""),
    dsi_workflow_mode: str = Form(default="auto"),
    db: AsyncSession = Depends(get_db),
):
    run_inline = _wants_inline_import_processing(run_sync)
    source = await db.scalar(
        select(SourceDefinition)
        .options(joinedload(SourceDefinition.import_template))
        .where(SourceDefinition.id == source_id)
    )
    if not source or not source.is_active:
        raise HTTPException(status_code=400, detail="Unknown or inactive source_id")

    tpl = source.import_template
    if not tpl or not tpl.enabled:
        raise HTTPException(status_code=400, detail="Source has no active import template")

    mode = (import_mode or "").strip().lower()
    if not mode:
        mode = "validate" if tpl.slug in ("product_master", "distributor_inventory", "inbound_shipments") else "apply"
    if mode not in ("validate", "apply"):
        raise HTTPException(status_code=400, detail="import_mode must be validate or apply")

    if tpl.destructive_apply_requires_confirm and mode == "apply":
        ok = str(confirm_destructive).strip().lower() in ("1", "true", "yes", "on", "confirm")
        if not ok:
            raise HTTPException(
                status_code=400,
                detail="This import can overwrite catalog fields; pass confirm_destructive=true with import_mode=apply.",
            )

    raw_bytes = await file.read()
    storage = get_storage_backend()
    key = f"imports/{uuid.uuid4().hex}/{file.filename}"
    storage.save(key, raw_bytes, file.content_type)

    job = ImportJob(
        source_id=source_id,
        template_slug=tpl.slug,
        import_mode=mode,
        status="pending",
        stage="uploaded",
        file_name=file.filename or "upload",
        content_type=file.content_type,
    )
    db.add(job)
    await db.flush()

    if tpl.slug == "distributor_inventory":
        mode_explicit = (dsi_workflow_mode or "auto").strip().lower()
        if mode_explicit not in ("auto", "historical", "weekly"):
            mode_explicit = "auto"
        sm = dict(job.staged_metadata or {})
        sm["dsi_workflow_mode_explicit"] = mode_explicit
        job.staged_metadata = to_jsonable(sm)
        db.add(job)

    # Store column mapping override for historical_lineup before sync processing.
    # The service reads job.mapping_decisions and applies overrides during parsing.
    if mapping_override.strip() and tpl.slug == "historical_lineup":
        try:
            _override = json.loads(mapping_override)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="mapping_override must be valid JSON")
        if not isinstance(_override, dict):
            raise HTTPException(status_code=400, detail="mapping_override must be a JSON object")
        job.mapping_decisions = _override

    meta = RawFileMetadata(job_id=job.id, storage_key=key, byte_size=len(raw_bytes), checksum=None)
    db.add(meta)
    await db.commit()
    await db.refresh(job)

    # Product Master and DSI use constrained mapping workflows; never run legacy sync on create.
    effective_run_sync = run_inline and tpl.slug not in ("product_master", "distributor_inventory", "inbound_shipments")
    if effective_run_sync:
        with SessionLocal() as sync_db:
            process_import_job_sync(sync_db, job.id)
        await db.refresh(job)
    elif tpl.slug == "distributor_inventory":
        # Always infer inline — DSI infer is fast and the frontend has no polling for this step.
        # Celery dispatch for DSI infer was removed because the worker path was unreliable and
        # left jobs stuck at 'uploaded' with column mapping never loading.
        with SessionLocal() as sync_db:
            infer_dsi_job_sync(sync_db, job.id)
        await db.refresh(job)
    elif tpl.slug == "inbound_shipments":
        with SessionLocal() as sync_db:
            infer_shipment_import_job_sync(sync_db, job.id)
        await db.refresh(job)

    return {"id": job.id, "status": job.status, "stage": job.stage, "template_slug": job.template_slug, "import_mode": job.import_mode}


@router.get("/jobs/{job_id}/rows")
async def list_job_rows(job_id: int, db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        select(ImportRowResult).where(ImportRowResult.job_id == job_id).order_by(ImportRowResult.row_number)
    )
    rows = res.scalars().all()
    return [
        {
            "id": r.id,
            "row_number": r.row_number,
            "severity": r.severity,
            "code": r.code,
            "message": r.message,
            "raw_payload": r.raw_payload,
        }
        for r in rows
    ]


@router.get("/jobs/{job_id}/lineup-lines")
async def list_lineup_lines(job_id: int, db: AsyncSession = Depends(get_db)):
    """Return persisted HistoricalLineupImportLine records for a historical_lineup apply job.

    Returns an empty list for validate-only jobs that produced no applied header/lines.
    Multiple headers are supported (one per parsed sheet) but in practice there is
    usually one.  Line fields are denormalized with the parent header's period_label,
    customer_id, and sheet_name for frontend convenience.
    """
    headers_res = await db.execute(
        select(HistoricalLineupImportHeader)
        .where(HistoricalLineupImportHeader.import_job_id == job_id)
        .order_by(HistoricalLineupImportHeader.id)
    )
    headers = headers_res.scalars().all()
    if not headers:
        return []

    result: list[dict] = []
    for header in headers:
        lines_res = await db.execute(
            select(HistoricalLineupImportLine)
            .where(HistoricalLineupImportLine.header_id == header.id)
            .order_by(HistoricalLineupImportLine.source_row_number)
        )
        lines = lines_res.scalars().all()
        for ln in lines:
            result.append(
                {
                    "id": ln.id,
                    "header_id": ln.header_id,
                    "source_row_number": ln.source_row_number,
                    "product_id": ln.product_id,
                    "sku_raw": ln.sku_raw,
                    "part_number_raw": ln.part_number_raw,
                    "model_raw": ln.model_raw,
                    "base_unit_raw": ln.base_unit_raw,
                    "quantity_units": float(ln.quantity_units) if ln.quantity_units is not None else None,
                    "msrp_local": float(ln.msrp_local) if ln.msrp_local is not None else None,
                    "promo_price_local": float(ln.promo_price_local) if ln.promo_price_local is not None else None,
                    "dap_local": float(ln.dap_local) if ln.dap_local is not None else None,
                    "disti_margin_pct": float(ln.disti_margin_pct) if ln.disti_margin_pct is not None else None,
                    # Header-level fields denormalized for frontend convenience.
                    "period_label": header.period_label,
                    "header_customer_id": header.customer_id,
                    "sheet_name": header.sheet_name,
                    # Resolution status fields — read-only audit surface.
                    "diagnostic_codes": ln.diagnostic_codes or [],
                    "customer_token": (ln.raw_row_payload or {}).get("customer_token"),
                }
            )
    return result


@router.get("/jobs/{job_id}")
async def get_job(job_id: int, db: AsyncSession = Depends(get_db)):
    job = await db.get(ImportJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "id": job.id,
        "status": job.status,
        "stage": job.stage,
        "file_name": job.file_name,
        "error_summary": job.error_summary,
        "inferred_schema": job.inferred_schema,
        "field_mapping": job.field_mapping,
        "file_headers": job.file_headers,
        "template_slug": job.template_slug,
        "import_mode": job.import_mode,
        "archived_at": job.archived_at,
        "staged_metadata": job.staged_metadata,
    }


@router.get("/jobs/{job_id}/dsi-progress")
async def get_dsi_job_progress(job_id: int, db: AsyncSession = Depends(get_db)):
    """Return real-time import pipeline progress from Celery task state (Redis).

    Reads the Celery task ID stored in ``staged_metadata.celery_task_id`` (written at
    dispatch time) and queries the Celery result backend for the current PROGRESS meta.
    Falls back to stage/status from the job record when no task state is available.
    """
    import asyncio

    job = await db.get(ImportJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    stage = (job.stage or "").strip()
    status = (job.status or "").strip()
    stage_l = stage.lower()
    status_l = status.lower()
    meta = dict(job.staged_metadata or {})
    task_id: str | None = meta.get("celery_task_id")
    total_rows_from_meta: int = int(meta.get("dsi_validate_total_rows") or 0)

    progress: dict[str, Any] = {
        "job_id": job_id,
        "stage": stage,
        "status": status,
        "phase": "idle",
        "phase_label": "Idle",
        "current_row": 0,
        "total_rows": total_rows_from_meta,
        "pct": 0,
        "task_state": None,
        "pipeline_queued_at": meta.get("pipeline_queued_at"),
        "pipeline_started_at": meta.get("pipeline_started_at"),
    }

    from app.services.imports.background_tasks import read_celery_with_timeout
    from app.services.imports.import_job_background_metadata import (
        ACTIVE_CELERY_STATES,
        job_db_indicates_pipeline_finished,
    )

    # Trust DB when pipeline finished — do not read Celery (stale PROGRESS after completion).
    if job_db_indicates_pipeline_finished(job):
        progress["phase"] = "complete"
        progress["status"] = "complete"
        progress["phase_label"] = "Validation complete"
        progress["pct"] = 100
        progress["current_row"] = total_rows_from_meta
        return progress

    if task_id:
        try:

            def _read_celery_state() -> tuple[str, Any]:
                return read_celery_with_timeout(task_id, timeout_s=3.0)

            task_state, info = await asyncio.to_thread(_read_celery_state)
            progress["task_state"] = task_state
            state_u = (str(task_state or "PENDING")).strip().upper()
            if isinstance(info, dict) and state_u in ACTIVE_CELERY_STATES:
                progress["phase"] = info.get("phase", "processing_rows")
                progress["phase_label"] = info.get("phase_label", "Processing rows")
                progress["current_row"] = info.get("current_row", 0)
                total_from_celery = info.get("total_rows", 0)
                progress["total_rows"] = total_from_celery or total_rows_from_meta
                progress["pct"] = info.get("pct", 0)
                if state_u in ("PENDING", "STARTED") and not info:
                    progress["phase"] = "queued"
                    progress["phase_label"] = "Queued"
                return progress
        except Exception as exc:
            logger.debug("get_dsi_job_progress: Celery read failed job_id=%s: %s", job_id, exc)

    if stage_l in ("failed", "stage_failed") or status_l == "failed":
        progress["phase"] = "failed"
        progress["phase_label"] = "Failed"
    elif status_l == "running" or progress["phase"] == "idle":
        progress["phase"] = "processing_rows"
        progress["phase_label"] = "Processing rows"

    return progress


@router.get("/background-tasks")
async def list_background_tasks(
    limit: int = Query(default=40, ge=1, le=80),
):
    """Active Celery-backed import work for global nav progress (DSI validate, shipment import, bulk steward, etc.)."""
    from app.services.imports.background_tasks import list_import_background_tasks_for_ui

    return await list_import_background_tasks_for_ui(limit=limit)


@router.post("/jobs/{job_id}/cancel")
async def post_cancel_import_job(job_id: int, db: AsyncSession = Depends(get_db)):
    """Revoke Celery work, clear task metadata, mark job failed (works for stale queued refs too)."""
    import asyncio

    from app.services.imports.import_job_task_control import cancel_import_job_sync

    job = await db.get(ImportJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    def _cancel() -> dict[str, Any]:
        with SessionLocal() as session:
            return cancel_import_job_sync(session, job_id)

    try:
        return await asyncio.to_thread(_cancel)
    except ValueError as exc:
        if str(exc) == "job_not_found":
            raise HTTPException(status_code=404, detail="Job not found") from exc
        raise


@router.post("/jobs/{job_id}/retry")
async def post_retry_import_job(job_id: int, db: AsyncSession = Depends(get_db)):
    """Re-enqueue ``imports.process_job`` for a failed job (same pattern as validate/revalidate)."""
    import asyncio

    from app.services.imports.import_job_task_control import prepare_import_job_retry_sync

    job = await db.get(ImportJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if str(job.status or "").strip() != "failed":
        raise HTTPException(
            status_code=409,
            detail={"error": "job_not_failed", "message": "Retry is only available when job status is failed."},
        )

    def _work() -> dict[str, Any]:
        with SessionLocal() as session:
            prepare_import_job_retry_sync(session, job_id)
        dispatched, task_id = _enqueue_import_pipeline_job(
            job_id,
            log_label="Import job retry",
            in_process_thread_name=f"import-retry-{job_id}",
        )
        if dispatched and task_id:
            with SessionLocal() as meta_db:
                j_meta = meta_db.get(ImportJob, job_id)
                if j_meta is not None:
                    m = dict(j_meta.staged_metadata or {})
                    m["celery_task_id"] = task_id
                    j_meta.staged_metadata = m
                    meta_db.commit()
        if not dispatched:
            raise RuntimeError("Failed to enqueue import job retry")
        return {"queued": True, "job_id": job_id, "task_id": task_id}

    try:
        return await asyncio.to_thread(_work)
    except ValueError as exc:
        if str(exc) == "job_not_found":
            raise HTTPException(status_code=404, detail="Job not found") from exc
        if str(exc) == "job_not_failed":
            raise HTTPException(status_code=409, detail="Job is not in failed status") from exc
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/jobs/{job_id}/shipment-mapping-state")
async def get_shipment_mapping_state(job_id: int, db: AsyncSession = Depends(get_db)):
    job = await db.get(ImportJob, job_id)
    if not job or job.template_slug != "inbound_shipments":
        raise HTTPException(status_code=404, detail="Shipment mapping state not found for this job")
    headers = list(job.file_headers or [])
    raw = dict(job.field_mapping or {})
    clean, _ = sanitize_shipment_field_mapping(headers, raw)
    if clean != raw:
        job.field_mapping = clean
        await db.commit()
        await db.refresh(job)
    return shipment_mapping_state_dict(job)


@router.put("/jobs/{job_id}/shipment-field-mapping")
async def put_shipment_field_mapping(job_id: int, body: dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
    job = await db.get(ImportJob, job_id)
    if not job or job.template_slug != "inbound_shipments":
        raise HTTPException(status_code=404, detail="Job not found")
    fm = body.get("field_mapping")
    if not isinstance(fm, dict):
        raise HTTPException(status_code=400, detail="field_mapping must be an object")
    headers = list(job.file_headers or [])
    cleaned_input: dict[str, str] = {}
    for k, v in fm.items():
        if isinstance(k, str) and isinstance(v, str) and v.strip():
            cleaned_input[k] = v.strip()
    cleaned, _ = sanitize_shipment_field_mapping(headers, cleaned_input)
    job.field_mapping = cleaned
    await db.commit()
    await db.refresh(job)
    if job.source_id is not None:
        with SessionLocal() as sync_db:
            merge_shipment_mapping_memory(sync_db, source_id=int(job.source_id), field_mapping=cleaned)
            sync_db.commit()
    return shipment_mapping_state_dict(job)


@router.post("/jobs/{job_id}/shipment-validate")
async def post_shipment_validate(job_id: int, db: AsyncSession = Depends(get_db)):
    job = await db.get(ImportJob, job_id)
    if not job or job.template_slug != "inbound_shipments":
        raise HTTPException(status_code=404, detail="Job not found")
    headers = list(job.file_headers or [])
    clean, _ = sanitize_shipment_field_mapping(headers, dict(job.field_mapping or {}))
    job.field_mapping = clean
    await db.commit()
    gate = shipment_mapping_gate_errors(clean)
    if gate:
        raise HTTPException(status_code=422, detail={"blocking_mapping_errors": gate})

    with SessionLocal() as sync_db:
        j = sync_db.get(ImportJob, job_id)
        if j is None:
            raise HTTPException(status_code=404, detail="Job not found")
        j.import_mode = "validate"
        sync_db.commit()

    dispatched, shipment_task_id = _enqueue_import_pipeline_job(
        job_id,
        log_label="Shipment validate",
        in_process_thread_name=f"shipment-validate-{job_id}",
    )

    if dispatched and shipment_task_id:
        with SessionLocal() as meta_db:
            j_meta = meta_db.get(ImportJob, job_id)
            if j_meta is not None:
                m = dict(j_meta.staged_metadata or {})
                m["celery_task_id"] = shipment_task_id
                j_meta.staged_metadata = m
                meta_db.commit()

    job2 = await db.get(ImportJob, job_id)
    if job2 is not None:
        await db.refresh(job2)

    if dispatched:
        return {
            "async": True,
            "id": job_id,
            "status": job2.status if job2 else None,
            "stage": job2.stage if job2 else None,
            "message": "Validation started in the background worker.",
        }

    if job2 and job2.status == "failed":
        raise HTTPException(
            status_code=422,
            detail=job2.error_summary or "Import job failed during validation.",
        )
    return shipment_mapping_state_dict(job2) if job2 else {}


@router.get("/jobs/{job_id}/dsi-mapping-state")
async def get_dsi_mapping_state(job_id: int, db: AsyncSession = Depends(get_db)):
    job = await _async_import_job_with_source(db, job_id)
    if not job or job.template_slug != "distributor_inventory":
        raise HTTPException(status_code=404, detail="DSI mapping state not found for this job")
    headers = list(job.file_headers or [])
    raw = dict(job.field_mapping or {})
    clean, _ = sanitize_dsi_field_mapping(headers, raw)
    if clean != raw:
        job.field_mapping = clean
        await db.commit()
        job = await _async_import_job_with_source(db, job_id)
        if not job or job.template_slug != "distributor_inventory":
            raise HTTPException(status_code=404, detail="DSI mapping state not found for this job")
    return dsi_mapping_state_dict(job)


@router.put("/jobs/{job_id}/dsi-field-mapping")
async def put_dsi_field_mapping(job_id: int, body: dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
    job = await _async_import_job_with_source(db, job_id)
    if not job or job.template_slug != "distributor_inventory":
        raise HTTPException(status_code=404, detail="Job not found")
    fm = body.get("field_mapping")
    if not isinstance(fm, dict):
        raise HTTPException(status_code=400, detail="field_mapping must be an object")
    headers = list(job.file_headers or [])
    cleaned_input: dict[str, str] = {}
    for k, v in fm.items():
        if not isinstance(k, str) or not isinstance(v, str):
            continue
        if not v.strip():
            continue
        cleaned_input[k] = v.strip()
    cleaned, _ = sanitize_dsi_field_mapping(headers, cleaned_input)
    job.field_mapping = cleaned
    if job.source_id is not None:
        with SessionLocal() as sync_db:
            merge_dsi_mapping_memory(sync_db, source_id=job.source_id, field_mapping=cleaned)
            sync_db.commit()
    await db.commit()
    job = await _async_import_job_with_source(db, job_id)
    if not job or job.template_slug != "distributor_inventory":
        raise HTTPException(status_code=404, detail="Job not found")
    return dsi_mapping_state_dict(job)


@router.post("/jobs/{job_id}/dsi-validate")
async def post_dsi_validate(job_id: int, db: AsyncSession = Depends(get_db)):
    job = await db.get(ImportJob, job_id)
    if not job or job.template_slug != "distributor_inventory":
        raise HTTPException(status_code=404, detail="Job not found")
    headers = list(job.file_headers or [])
    clean, _ = sanitize_dsi_field_mapping(headers, dict(job.field_mapping or {}))
    job.field_mapping = clean
    await db.commit()
    await db.refresh(job)
    gate = dsi_mapping_gate_errors(job.field_mapping or {})
    if gate:
        raise HTTPException(status_code=422, detail={"blocking_mapping_errors": gate})

    _prepare_dsi_pipeline_dispatch(job_id)

    dispatched, dsi_task_id = _enqueue_import_pipeline_job(
        job_id,
        log_label="DSI validate",
        in_process_thread_name=f"dsi-validate-{job_id}",
    )

    if dispatched and dsi_task_id:
        _persist_pipeline_celery_task_id(job_id, dsi_task_id)

    job2 = await _async_import_job_with_source(db, job_id)
    if job2 is not None:
        await db.refresh(job2)

    if dispatched:
        return {
            "async": True,
            "job_id": job_id,
            "id": job_id,
            "task_id": dsi_task_id,
            "status": job2.status if job2 else "running",
            "stage": job2.stage if job2 else None,
            "message": "Validation started in the background worker.",
        }

    if job2 and job2.status == "failed":
        raise HTTPException(
            status_code=422,
            detail=job2.error_summary or "Import job failed during validation.",
        )
    return dsi_mapping_state_dict(job2) if job2 else {}


@router.post("/jobs/{job_id}/dsi-apply")
async def post_dsi_apply(
    job_id: int,
    confirm_destructive: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
):
    job = await db.get(ImportJob, job_id)
    if not job or job.template_slug != "distributor_inventory":
        raise HTTPException(status_code=404, detail="Job not found")
    tpl = await db.scalar(select(ImportTemplate).where(ImportTemplate.slug == job.template_slug))
    if tpl and tpl.destructive_apply_requires_confirm:
        ok = str(confirm_destructive).strip().lower() in ("1", "true", "yes", "on", "confirm")
        if not ok:
            raise HTTPException(
                status_code=400,
                detail="This import can change canonical facts; pass confirm_destructive=true.",
            )
    headers = list(job.file_headers or [])
    clean, _ = sanitize_dsi_field_mapping(headers, dict(job.field_mapping or {}))
    job.field_mapping = clean
    await db.commit()
    await db.refresh(job)
    gate = dsi_mapping_gate_errors(job.field_mapping or {})
    if gate:
        raise HTTPException(status_code=422, detail={"blocking_mapping_errors": gate})
    job.import_mode = "apply"
    await db.commit()
    with SessionLocal() as sync_db:
        process_import_job_sync(sync_db, job_id)
    job2 = await _async_import_job_with_source(db, job_id)
    if job2 and job2.status == "failed":
        raise HTTPException(
            status_code=422,
            detail=job2.error_summary or "Import job failed during apply.",
        )
    return dsi_mapping_state_dict(job2) if job2 else {}


@router.post("/jobs/{job_id}/process")
async def process_job(job_id: int):
    with SessionLocal() as sync_db:
        job = process_import_job_sync(sync_db, job_id)
    return {"id": job.id, "status": job.status, "stage": job.stage, "error_summary": job.error_summary}
