import asyncio
import json
import logging
import threading
import uuid
from typing import Annotated, Any, Callable

from fastapi import APIRouter, Body, Depends, File, Form, Header, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.dev_celery_logging import DEV_CELERY_LOGGER
from app.db.session_sync import SessionLocal
from app.ingestion.pipeline import process_import_job_sync
from app.services.imports.cst_mapping_candidates import (
    CstCandidateOpError,
    bulk_resolve_cst_candidates_sync,
    cst_mapping_state_dict,
    ignore_cst_candidate_sync,
    list_cst_mapping_candidates_sync,
    resolve_cst_candidate_sync,
)
from app.services.imports.dsi_mapping_workflow import (
    dsi_mapping_gate_errors,
    dsi_mapping_state_dict,
    infer_dsi_job_sync,
    merge_dsi_mapping_memory,
    sanitize_dsi_field_mapping,
)
from app.services.imports.import_dispatch import enqueue_import_worker_task
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
from app.services.imports.import_background_slots import (
    SLOT_CST_RESOLUTION_PLAN,
    SLOT_MAIN,
    clear_task_slot_on_job,
    set_task_slot_on_job,
)
from app.services.imports.import_job_background_metadata import ACTIVE_CELERY_STATES, read_main_celery_state
from app.services.imports.import_job_bulk_delete import bulk_delete_import_jobs, normalize_job_ids, preview_import_job_bulk_delete
from app.services.imports.db_transient_retry import is_readonly_db_error
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
    """Delegate to the shared dispatch helper (see ``import_dispatch.enqueue_import_worker_task``)."""
    return enqueue_import_worker_task(
        job_id,
        task_name=task_name,
        log_label=log_label,
        in_process_thread_name=in_process_thread_name,
        sync_work=sync_work,
    )


def _enqueue_import_pipeline_job(job_id: int, *, log_label: str, in_process_thread_name: str) -> tuple[bool, str | None]:
    """Enqueue full import pipeline (``imports.process_job``) — validate/apply processing."""
    return _enqueue_import_worker_task(
        job_id,
        task_name="imports.process_job",
        log_label=log_label,
        in_process_thread_name=in_process_thread_name,
        sync_work=process_import_job_sync,
    )


from app.services.imports.import_pipeline_dispatch_claim import (
    claim_import_pipeline_dispatch,
    raise_if_import_pipeline_busy as _raise_if_import_pipeline_busy,
)


def _prepare_dsi_pipeline_dispatch(job_id: int) -> None:
    """Mark job running and atomically claim pipeline dispatch before broker enqueue."""
    claim_import_pipeline_dispatch(job_id, import_mode="validate")


def _dispatch_dsi_apply(job_id: int) -> tuple[bool, str | None]:
    """Publish ``imports.dsi_apply`` to the broker; mirror the shipment apply dispatch semantics.

    Returns ``(dispatched, task_id)``. ``dispatched`` is ``True`` when apply should be treated as
    async (broker accepted, or a dev in-process thread started). On broker failure with no dev
    thread it runs the apply inline (``False``) so the operation still completes. DSI validate is
    already async; this brings apply to parity without the enqueue-helper dedup (parked in BACKLOG).
    """
    import uuid

    from app.services.imports.dsi_apply_sync import run_dsi_apply_sync
    from app.services.task_run_ledger import (
        ENTITY_IMPORT_JOB,
        TRANSPORT_BROKER,
        TRANSPORT_INLINE_SYNC,
        TRANSPORT_IN_PROCESS_THREAD,
        create_queued_task_run,
        run_inline_with_ledger,
        spawn_in_process_thread_with_ledger,
    )

    settings = get_settings()
    task_name = "imports.dsi_apply"
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
        logger.exception("DSI apply: Celery enqueue failed job_id=%s", job_id)
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
                try:
                    run_dsi_apply_sync(job_id)
                except Exception:
                    logger.exception(
                        "DSI apply: in-process thread failed job_id=%s "
                        "(CIP_DEV_CELERY_DISPATCH=in_process_thread after broker failure)",
                        job_id,
                    )
                    raise

            DEV_CELERY_LOGGER.warning(
                "ENQUEUE: DSI apply job_id=%s — in-process thread after broker failure (DEV ONLY).",
                job_id,
            )
            spawn_in_process_thread_with_ledger(
                task_run_id=task_run_id,
                thread_name=f"dsi-apply-{job_id}",
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
        run_inline_with_ledger(task_run_id, lambda: run_dsi_apply_sync(job_id))
        return False, None


def _persist_pipeline_celery_task_id(job_id: int, task_id: str | None) -> None:
    if not task_id:
        return
    with SessionLocal() as meta_db:
        j_meta = meta_db.get(ImportJob, job_id)
        if j_meta is None:
            return
        set_task_slot_on_job(j_meta, SLOT_MAIN, task_id=task_id)
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
        except OperationalError as exc:
            db.rollback()
            if is_readonly_db_error(exc):
                raise HTTPException(
                    status_code=503,
                    detail={
                        "error": "database_read_only",
                        "message": (
                            "Supabase rejected the delete (database is read-only). "
                            "In the Supabase dashboard open Disk settings, expand storage or "
                            "override read-only mode, then retry."
                        ),
                    },
                ) from exc
            raise
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
        mode = "validate" if tpl.slug in (
            "product_master",
            "distributor_inventory",
            "inbound_shipments",
            "cpor_historical_cases",
        ) else "apply"
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


@router.post("/jobs/{job_id}/dsi-file-exclusions")
async def set_dsi_file_exclusions(
    job_id: int,
    body: dict[str, Any] = Body(...),
):
    """Exclude files from a multi-file DSI batch before re-validate (clears staging)."""
    from app.services.imports.dsi_batch import set_dsi_file_exclusions_sync

    excluded = body.get("excluded_filenames")
    if not isinstance(excluded, list):
        raise HTTPException(status_code=400, detail="excluded_filenames must be a list of filenames")
    excluded_keys = body.get("excluded_mapping_keys")
    with SessionLocal() as sync_db:
        try:
            job = set_dsi_file_exclusions_sync(
                sync_db,
                job_id,
                excluded_filenames=[str(x) for x in excluded],
                excluded_mapping_keys=(
                    [str(x) for x in excluded_keys] if isinstance(excluded_keys, list) else None
                ),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        sm = job.staged_metadata if isinstance(job.staged_metadata, dict) else {}
        return {
            "id": job.id,
            "stage": job.stage,
            "status": job.status,
            "dsi_excluded_files": sm.get("dsi_excluded_files") or [],
            "dsi_excluded_mapping_keys": sm.get("dsi_excluded_mapping_keys") or [],
        }


@router.post("/jobs/{job_id}/dsi-file-distributors")
async def post_dsi_file_distributors(
    job_id: int,
    body: dict[str, Any] = Body(...),
):
    """Confirm or assign per-file distributor identity (banner/company stamp)."""
    from app.services.imports.dsi_file_distributor import (
        DSI_FILE_DISTRIBUTORS_KEY,
        confirm_dsi_file_distributor,
        file_distributors_all_confirmed,
    )

    filename = body.get("filename")
    if not isinstance(filename, str) or not filename.strip():
        raise HTTPException(status_code=400, detail="filename is required")
    distributor_id = body.get("distributor_id")
    if distributor_id is not None:
        try:
            distributor_id = int(distributor_id)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="distributor_id must be an integer") from exc
    confirm = bool(body.get("confirm", True))
    clear = bool(body.get("clear", False))

    with SessionLocal() as sync_db:
        job = sync_db.get(ImportJob, job_id)
        if not job or job.template_slug != "distributor_inventory":
            raise HTTPException(status_code=404, detail="Job not found")
        try:
            stamps = confirm_dsi_file_distributor(
                sync_db,
                job,
                filename=filename.strip(),
                distributor_id=distributor_id,
                confirm=confirm,
                clear=clear,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        sync_db.refresh(job)
        return {
            "id": job.id,
            DSI_FILE_DISTRIBUTORS_KEY: stamps,
            "dsi_file_distributors_all_confirmed": file_distributors_all_confirmed(job),
            **dsi_mapping_state_dict(job),
        }


@router.post("/jobs/{job_id}/dsi-file-snapshot-periods")
async def post_dsi_file_snapshot_periods(
    job_id: int,
    body: dict[str, Any] = Body(...),
):
    """Confirm or override per-file inventory snapshot period (Application Date banner)."""
    from app.services.imports.dsi_file_snapshot import (
        DSI_FILE_SNAPSHOT_PERIODS_KEY,
        confirm_dsi_file_snapshot_period,
        file_snapshot_periods_all_confirmed,
    )

    confirm_all = bool(body.get("confirm_all_sniffed", False))
    filename = body.get("filename")
    if not confirm_all and (not isinstance(filename, str) or not filename.strip()):
        raise HTTPException(status_code=400, detail="filename is required (or confirm_all_sniffed)")
    confirm = bool(body.get("confirm", True))
    clear = bool(body.get("clear", False))
    resolved_date = body.get("resolved_date")

    with SessionLocal() as sync_db:
        job = sync_db.get(ImportJob, job_id)
        if not job or job.template_slug != "distributor_inventory":
            raise HTTPException(status_code=404, detail="Job not found")
        try:
            stamps = confirm_dsi_file_snapshot_period(
                sync_db,
                job,
                filename=(filename or "").strip(),
                confirm=confirm,
                clear=clear,
                resolved_date=resolved_date,
                confirm_all_sniffed=confirm_all,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        sync_db.refresh(job)
        return {
            "id": job.id,
            DSI_FILE_SNAPSHOT_PERIODS_KEY: stamps,
            "dsi_file_snapshot_periods_all_confirmed": file_snapshot_periods_all_confirmed(job),
            **dsi_mapping_state_dict(job),
        }


@router.get("/dsi/coverage")
async def get_dsi_coverage(
    source_id: int | None = Query(None),
    weeks: int = Query(12, ge=4, le=26),
):
    """Read-only DSI weekly coverage — missed sell-out / SOH weeks (FLAG only)."""
    from app.services.imports.dsi_coverage import compute_dsi_coverage

    with SessionLocal() as sync_db:
        return compute_dsi_coverage(sync_db, source_id=source_id, weeks=weeks)


@router.post("/dsi/batch-propose")
async def dsi_batch_propose(
    files: list[UploadFile] = File(...),
):
    """Preview DSI batch groups (no DB writes).

    All DSI-capable files form one ``dsi_capable`` group (exact header equality not required).
    Unmappable files are listed separately and will not become jobs.
    """
    from app.services.imports.dsi_batch import (
        DSI_CAPABLE_GROUP_SIGNATURE,
        batch_groups_preview_to_dict,
        propose_dsi_batch_groups,
    )

    if not files:
        raise HTTPException(status_code=400, detail="At least one file is required")
    payload: list[tuple[str, bytes]] = []
    for f in files:
        raw = await f.read()
        payload.append((f.filename or "upload", raw))
    groups = propose_dsi_batch_groups(payload)
    job_groups = [g for g in groups if g.signature == DSI_CAPABLE_GROUP_SIGNATURE]
    return {
        "group_count": len(job_groups),
        "file_count": len(payload),
        "groups": batch_groups_preview_to_dict(groups),
    }


@router.post("/dsi/batch-jobs")
async def dsi_batch_create_jobs(
    source_id: int = Form(...),
    dsi_workflow_mode: str = Form(default="auto"),
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Create DSI import jobs from a multi-file upload.

    All DSI-capable files become **one** job (nested per-file mapping + distributor stamps).
    Unmappable files return an error outcome and are not attached to a job.
    """
    from app.services.imports.dsi_batch import (
        DSI_CAPABLE_GROUP_SIGNATURE,
        batch_groups_preview_to_dict,
        create_dsi_batch_job_sync,
        propose_dsi_batch_groups,
    )

    source = await db.scalar(
        select(SourceDefinition)
        .options(joinedload(SourceDefinition.import_template))
        .where(SourceDefinition.id == source_id)
    )
    if not source or not source.is_active:
        raise HTTPException(status_code=400, detail="Unknown or inactive source_id")
    tpl = source.import_template
    if not tpl or tpl.slug != "distributor_inventory":
        raise HTTPException(status_code=400, detail="DSI batch upload requires a distributor_inventory source")

    if not files:
        raise HTTPException(status_code=400, detail="At least one file is required")

    payload: list[tuple[str, bytes]] = []
    for f in files:
        raw = await f.read()
        payload.append((f.filename or "upload", raw))

    groups = propose_dsi_batch_groups(payload)
    name_to_bytes = dict(payload)
    created: list[dict[str, Any]] = []
    with SessionLocal() as sync_db:
        for group in groups:
            group_payload = [
                (p.filename, name_to_bytes[p.filename])
                for p in group.files
                if p.filename in name_to_bytes
            ]
            if not group_payload:
                continue
            if group.signature != DSI_CAPABLE_GROUP_SIGNATURE or any(p.unmappable for p in group.files):
                created.append(
                    {
                        "signature": group.signature,
                        "outcome": "error",
                        "error": "One or more files could not be mapped (no DSI-like columns)",
                        "filenames": [p.filename for p in group.files],
                    }
                )
                continue
            try:
                job = create_dsi_batch_job_sync(
                    sync_db,
                    source_id=source_id,
                    filenames_and_bytes=group_payload,
                    import_mode="validate",
                    dsi_workflow_mode=dsi_workflow_mode,
                )
                created.append(
                    {
                        "signature": group.signature,
                        "outcome": "created",
                        "import_job_id": job.id,
                        "stage": job.stage,
                        "filenames": [p.filename for p in group.files],
                        "file_count": len(group_payload),
                    }
                )
            except Exception as exc:
                created.append(
                    {
                        "signature": group.signature,
                        "outcome": "error",
                        "error": str(exc),
                        "filenames": [p.filename for p in group.files],
                    }
                )

    job_groups = [g for g in groups if g.signature == DSI_CAPABLE_GROUP_SIGNATURE]
    return {
        "group_count": len(job_groups),
        "groups_preview": batch_groups_preview_to_dict(groups),
        "jobs": created,
    }


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


def _dsi_terminal_progress_label(job: ImportJob) -> str:
    """Terminal progress label from job stage/mode (validate vs apply)."""
    stage = (job.stage or "").strip().lower()
    if stage == "loaded":
        return "Apply complete"
    if stage == "validated" or (job.import_mode or "").strip().lower() == "validate":
        return "Validation complete"
    return "Complete"


def _parse_iso_timestamp_ms(raw: Any) -> int | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        from datetime import datetime

        normalized = text.replace("Z", "+00:00")
        return int(datetime.fromisoformat(normalized).timestamp() * 1000)
    except (TypeError, ValueError):
        return None


def _dsi_validate_progress_label_from_metadata(meta: dict[str, Any]) -> str | None:
    from app.services.imports.distributor_sales_inventory import dsi_validate_sub_phase_label

    phase = str(meta.get("dsi_validate_phase") or "").strip()
    if not phase:
        return None
    sub = dsi_validate_sub_phase_label(meta.get("dsi_validate_sub_phase"))
    if phase == "loading_caches" and sub:
        return sub
    if phase == "processing_rows":
        return "Processing rows"
    if phase == "building_candidates":
        return "Building candidates"
    if phase == "complete":
        return "Validation complete"
    return phase.replace("_", " ").title()


def _dsi_validate_progress_from_metadata(meta: dict[str, Any]) -> dict[str, Any] | None:
    phase = str(meta.get("dsi_validate_phase") or "").strip()
    if not phase:
        return None
    total_rows = int(meta.get("dsi_validate_total_rows") or 0)
    current_row = int(meta.get("dsi_validate_rows_committed") or 0)
    pct = round(current_row / total_rows * 100) if total_rows else 0
    label = _dsi_validate_progress_label_from_metadata(meta) or "Processing rows"
    out: dict[str, Any] = {
        "phase": phase,
        "phase_label": label,
        "current_row": current_row,
        "total_rows": total_rows,
        "pct": pct,
        "progress_at": meta.get("dsi_validate_checkpoint_at"),
    }
    sub_phase = meta.get("dsi_validate_sub_phase")
    if isinstance(sub_phase, str) and sub_phase.strip():
        out["sub_phase"] = sub_phase.strip()
    return out


def _merge_dsi_validate_progress(
    progress: dict[str, Any],
    meta: dict[str, Any],
    celery_info: dict[str, Any] | None,
) -> None:
    """Prefer durable DB checkpoint metadata when fresher than Celery PROGRESS."""
    db_progress = _dsi_validate_progress_from_metadata(meta)
    if not db_progress:
        return
    db_at = _parse_iso_timestamp_ms(db_progress.get("progress_at"))
    celery_at = _parse_iso_timestamp_ms(
        celery_info.get("progress_at") if isinstance(celery_info, dict) else None
    )
    use_db = db_at is not None and (celery_at is None or db_at >= celery_at)
    if not use_db and celery_at is None:
        # Running validate with no Celery heartbeat — DB is authoritative.
        use_db = True
    if not use_db:
        return
    progress.update(db_progress)
    if not progress.get("total_rows"):
        progress["total_rows"] = int(meta.get("dsi_validate_total_rows") or 0)


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
        progress["phase_label"] = _dsi_terminal_progress_label(job)
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
                progress["progress_at"] = info.get("progress_at")
                if state_u in ("PENDING", "STARTED") and not info:
                    progress["phase"] = "queued"
                    progress["phase_label"] = "Queued"
                _merge_dsi_validate_progress(progress, meta, info if isinstance(info, dict) else None)
                return progress
        except Exception as exc:
            logger.debug("get_dsi_job_progress: Celery read failed job_id=%s: %s", job_id, exc)

    if status_l == "running" or stage_l not in ("validated", "loaded", "failed", "stage_failed"):
        _merge_dsi_validate_progress(progress, meta, None)

    if stage_l in ("failed", "stage_failed") or status_l in ("failed", "interrupted"):
        progress["phase"] = "failed"
        progress["phase_label"] = "Interrupted" if status_l == "interrupted" else "Failed"
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
            session.commit()
        claim_import_pipeline_dispatch(job_id)
        dispatched, task_id = _enqueue_import_pipeline_job(
            job_id,
            log_label="Import job retry",
            in_process_thread_name=f"import-retry-{job_id}",
        )
        if dispatched and task_id:
            with SessionLocal() as meta_db:
                j_meta = meta_db.get(ImportJob, job_id)
                if j_meta is not None:
                    set_task_slot_on_job(j_meta, SLOT_MAIN, task_id=task_id)
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

    claim_import_pipeline_dispatch(job_id, import_mode="validate")

    dispatched, shipment_task_id = _enqueue_import_pipeline_job(
        job_id,
        log_label="Shipment validate",
        in_process_thread_name=f"shipment-validate-{job_id}",
    )

    if dispatched and shipment_task_id:
        with SessionLocal() as meta_db:
            j_meta = meta_db.get(ImportJob, job_id)
            if j_meta is not None:
                set_task_slot_on_job(j_meta, SLOT_MAIN, task_id=shipment_task_id)
                meta_db.commit()

    job2 = await db.get(ImportJob, job_id)
    if job2 is not None:
        await db.refresh(job2)

    if dispatched:
        return {
            "async": True,
            "id": job_id,
            "task_id": shipment_task_id,
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
    from app.services.imports.dsi_workbook import is_nested_dsi_field_mapping

    raw = dict(job.field_mapping or {})
    # Nested multi-file/sheet maps use file::sheet keys — never flatten-sanitize them as headers
    # (that previously wiped automap to {} and committed it).
    if is_nested_dsi_field_mapping(raw):
        return dsi_mapping_state_dict(job)

    # Recovery: multi-file job whose nested mapping was wiped by the old GET path.
    meta = job.staged_metadata if isinstance(job.staged_metadata, dict) else {}
    wb = meta.get("dsi_workbook") if isinstance(meta.get("dsi_workbook"), dict) else {}
    if meta.get("dsi_multi_file") and not raw and (wb.get("sheets") or meta.get("dsi_batch_filenames")):

        def _reinfer() -> None:
            with SessionLocal() as sync_db:
                infer_dsi_job_sync(sync_db, job_id)

        await asyncio.to_thread(_reinfer)
        job = await _async_import_job_with_source(db, job_id)
        if not job or job.template_slug != "distributor_inventory":
            raise HTTPException(status_code=404, detail="DSI mapping state not found for this job")
        if is_nested_dsi_field_mapping(job.field_mapping):
            return dsi_mapping_state_dict(job)

    headers = list(job.file_headers or [])
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
    from app.services.imports.dsi_workbook import is_nested_dsi_field_mapping

    if is_nested_dsi_field_mapping(fm):
        nested_clean: dict[str, dict[str, str]] = {}
        for sheet_key, sheet_map in fm.items():
            if not isinstance(sheet_key, str) or not isinstance(sheet_map, dict):
                continue
            headers = list(job.file_headers or [])
            cleaned_input: dict[str, str] = {}
            for k, v in sheet_map.items():
                if isinstance(k, str) and isinstance(v, str) and v.strip():
                    cleaned_input[k] = v.strip()
            cleaned, _ = sanitize_dsi_field_mapping(headers, cleaned_input)
            if cleaned:
                nested_clean[sheet_key] = cleaned
        job.field_mapping = nested_clean
        if job.source_id is not None and nested_clean:
            with SessionLocal() as sync_db:
                first = next(iter(nested_clean.values()))
                merge_dsi_mapping_memory(sync_db, source_id=job.source_id, field_mapping=first)
                sync_db.commit()
    else:
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
    from app.services.imports.dsi_file_distributor import distributor_identity_satisfied
    from app.services.imports.dsi_file_snapshot import snapshot_identity_satisfied
    from app.services.imports.dsi_workbook import is_nested_dsi_field_mapping

    if is_nested_dsi_field_mapping(job.field_mapping):
        gate: list[dict[str, str]] = []
        for sheet_key, sheet_map in (job.field_mapping or {}).items():
            if isinstance(sheet_map, dict):
                ok = distributor_identity_satisfied(job, sheet_map, mapping_key=str(sheet_key))
                snap_ok = snapshot_identity_satisfied(job, sheet_map, mapping_key=str(sheet_key))
                gate.extend(
                    dsi_mapping_gate_errors(
                        sheet_map,
                        file_distributor_satisfied=ok,
                        file_snapshot_satisfied=snap_ok,
                    )
                )
    else:
        headers = list(job.file_headers or [])
        clean, _ = sanitize_dsi_field_mapping(headers, dict(job.field_mapping or {}))
        job.field_mapping = clean
        await db.commit()
        await db.refresh(job)
        ok = distributor_identity_satisfied(job, job.field_mapping or {})
        snap_ok = snapshot_identity_satisfied(job, job.field_mapping or {})
        gate = dsi_mapping_gate_errors(
            job.field_mapping or {},
            file_distributor_satisfied=ok,
            file_snapshot_satisfied=snap_ok,
        )
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
    from app.services.imports.dsi_file_distributor import distributor_identity_satisfied
    from app.services.imports.dsi_file_snapshot import snapshot_identity_satisfied
    from app.services.imports.dsi_workbook import is_nested_dsi_field_mapping

    if is_nested_dsi_field_mapping(job.field_mapping):
        gate = []
        for sheet_key, sheet_map in (job.field_mapping or {}).items():
            if isinstance(sheet_map, dict):
                ok = distributor_identity_satisfied(job, sheet_map, mapping_key=str(sheet_key))
                snap_ok = snapshot_identity_satisfied(job, sheet_map, mapping_key=str(sheet_key))
                gate.extend(
                    dsi_mapping_gate_errors(
                        sheet_map,
                        file_distributor_satisfied=ok,
                        file_snapshot_satisfied=snap_ok,
                    )
                )
    else:
        headers = list(job.file_headers or [])
        clean, _ = sanitize_dsi_field_mapping(headers, dict(job.field_mapping or {}))
        job.field_mapping = clean
        await db.commit()
        await db.refresh(job)
        ok = distributor_identity_satisfied(job, job.field_mapping or {})
        snap_ok = snapshot_identity_satisfied(job, job.field_mapping or {})
        gate = dsi_mapping_gate_errors(
            job.field_mapping or {},
            file_distributor_satisfied=ok,
            file_snapshot_satisfied=snap_ok,
        )
    if gate:
        raise HTTPException(status_code=422, detail={"blocking_mapping_errors": gate})
    # Mark running + record dispatch time + import_mode=apply in a sync session before handing off,
    # so progress/background UI are accurate the instant the request returns (mirrors validate +
    # the shipment apply dispatch). Reject a second apply while Celery work is still active.
    with SessionLocal() as sync_db:
        from app.services.imports.import_job_background_metadata import persist_pipeline_queued_at

        j = sync_db.get(ImportJob, job_id)
        if j is None:
            raise HTTPException(status_code=404, detail="Job not found")
        _raise_if_import_pipeline_busy(j)
        j.import_mode = "apply"
        j.status = "running"
        persist_pipeline_queued_at(sync_db, j)
        sync_db.commit()

    dispatched, task_id = _dispatch_dsi_apply(job_id)
    if dispatched and task_id:
        _persist_pipeline_celery_task_id(job_id, task_id)

    job2 = await _async_import_job_with_source(db, job_id)
    if dispatched:
        # Async: work runs in the worker (or dev thread). Poll
        # ``GET /api/v1/imports/jobs/{job_id}/dsi-progress`` + the job stage; no proxy-timeout risk.
        return {
            "async": True,
            "id": job_id,
            "status": job2.status if job2 else "running",
            "stage": job2.stage if job2 else None,
            "template_slug": "distributor_inventory",
            "import_mode": "apply",
            "task_id": task_id,
            "message": "DSI apply started in the background worker.",
        }

    # Broker unavailable and no dev thread: apply ran inline. Surface failures the way it used to.
    if job2 and job2.status == "failed":
        raise HTTPException(
            status_code=422,
            detail=job2.error_summary or "Import job failed during apply.",
        )
    return dsi_mapping_state_dict(job2) if job2 else {}


@router.post("/jobs/{job_id}/process")
async def process_job(job_id: int):
    import asyncio

    def _work() -> tuple[bool, str | None]:
        claim_import_pipeline_dispatch(job_id)
        return _enqueue_import_pipeline_job(
            job_id,
            log_label="process_job",
            in_process_thread_name=f"import-process-{job_id}",
        )

    dispatched, task_id = await asyncio.to_thread(_work)
    if dispatched and task_id:
        _persist_pipeline_celery_task_id(job_id, task_id)
    return {"async": dispatched, "task_id": task_id, "job_id": job_id}


@router.get("/jobs/{job_id}/cst-mapping-state")
async def get_cst_mapping_state(job_id: int, db: AsyncSession = Depends(get_db)):
    job = await _async_import_job_with_source(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Import job not found")
    return cst_mapping_state_dict(job)


@router.get("/jobs/{job_id}/cst-candidates")
async def list_cst_candidates(
    job_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=1000),
    entity: str = Query("all"),
    status: str = Query("all"),
):
    with SessionLocal() as sync_db:
        result = list_cst_mapping_candidates_sync(
            sync_db, job_id, skip=skip, limit=limit, entity=entity, status=status
        )
    return result


class CstResolveCandidateBody(BaseModel):
    entity_id: int = Field(..., ge=1)


class CstBulkResolveCandidatesBody(BaseModel):
    candidate_ids: list[int] = Field(..., min_length=1)
    entity_id: int = Field(..., ge=1)


@router.post("/jobs/{job_id}/cst-candidates/{candidate_id}/resolve", status_code=200)
async def resolve_cst_candidate(
    job_id: int,
    candidate_id: int,
    body: CstResolveCandidateBody,
):
    with SessionLocal() as sync_db:
        try:
            result = resolve_cst_candidate_sync(
                sync_db, job_id, candidate_id, body.entity_id
            )
            sync_db.commit()
            return result
        except CstCandidateOpError as exc:
            sync_db.rollback()
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/jobs/{job_id}/cst-candidates/{candidate_id}/ignore", status_code=200)
async def ignore_cst_candidate(job_id: int, candidate_id: int):
    with SessionLocal() as sync_db:
        try:
            result = ignore_cst_candidate_sync(sync_db, job_id, candidate_id)
            sync_db.commit()
            return result
        except CstCandidateOpError as exc:
            sync_db.rollback()
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/jobs/{job_id}/cst-candidates/bulk-resolve", status_code=200)
async def bulk_resolve_cst_candidates(job_id: int, body: CstBulkResolveCandidatesBody):
    with SessionLocal() as sync_db:
        try:
            result = bulk_resolve_cst_candidates_sync(
                sync_db, job_id, body.candidate_ids, body.entity_id
            )
            sync_db.commit()
            return result
        except CstCandidateOpError as exc:
            sync_db.rollback()
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


CST_TEMPLATE_SLUG = "customer_sell_through"


def _get_cst_job_sync(db: Session, job_id: int) -> ImportJob:
    job = db.get(ImportJob, job_id)
    if job is None or (job.template_slug or "") != CST_TEMPLATE_SLUG:
        raise HTTPException(status_code=404, detail="Import job not found")
    return job


def _cst_resolution_plan_task_id(job: ImportJob) -> str | None:
    meta = job.staged_metadata if isinstance(job.staged_metadata, dict) else {}
    slot = meta.get("cst_resolution_plan_task")
    if not isinstance(slot, dict):
        return None
    tid = slot.get("task_id")
    return tid.strip() if isinstance(tid, str) and tid.strip() else None


def _assert_cst_resolution_plan_dispatch_allowed(job: ImportJob) -> None:
    """409 guard — block plan compute/apply while pipeline (SLOT_MAIN) or another plan task runs."""
    if (job.status or "").strip().lower() == "running":
        state = read_main_celery_state(job)
        if state is not None and state in ACTIVE_CELERY_STATES:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "cst_pipeline_busy",
                    "message": f"CST import process is already running for job {job.id}.",
                },
            )

    tid = _cst_resolution_plan_task_id(job)
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
                    "error": "cst_resolution_plan_busy",
                    "message": f"A CST resolution plan task is already in flight for job {job.id}.",
                },
            )


def _write_cst_resolution_plan_slot(job_id: int, task_id: str, *, async_poll: bool, label: str) -> None:
    with SessionLocal() as meta_db:
        job = meta_db.get(ImportJob, job_id)
        if job is not None:
            set_task_slot_on_job(
                job, SLOT_CST_RESOLUTION_PLAN, task_id=task_id, async_poll=async_poll, label=label
            )
            meta_db.commit()


def _clear_cst_resolution_plan_slot(job_id: int) -> None:
    with SessionLocal() as sess:
        job = sess.get(ImportJob, job_id)
        if job is not None:
            clear_task_slot_on_job(job, SLOT_CST_RESOLUTION_PLAN)
            sess.commit()


class CstResolutionPlanGenerateBody(BaseModel):
    candidate_ids: list[int] | None = None


class CstResolutionPlanApplyBody(BaseModel):
    candidate_ids: list[int] = Field(min_length=1)


@router.post("/jobs/{job_id}/cst-resolution-plan", status_code=200)
def cst_resolution_plan_generate(job_id: int, body: CstResolutionPlanGenerateBody) -> dict[str, Any]:
    """Synchronous CST resolution-plan generation — small jobs / tests."""
    from app.services.imports.cst_resolution_plan import build_cst_resolution_plan_sync

    with SessionLocal() as db:
        try:
            _get_cst_job_sync(db, job_id)
            return build_cst_resolution_plan_sync(db, job_id, candidate_ids=body.candidate_ids)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/jobs/{job_id}/cst-resolution-plan/compute-async", status_code=202)
def cst_resolution_plan_compute_async(
    job_id: int,
    body: CstResolutionPlanGenerateBody,
) -> dict[str, Any]:
    with SessionLocal() as s:
        job = _get_cst_job_sync(s, job_id)
        _assert_cst_resolution_plan_dispatch_allowed(job)

    payload = {"candidate_ids": list(body.candidate_ids) if body.candidate_ids else None}
    from app.services.imports.cst_resolution_plan_enqueue import (
        TASK_CST_RESOLUTION_PLAN_COMPUTE,
        enqueue_cst_resolution_plan_task,
        run_cst_resolution_plan_compute_sync,
    )

    task_id, async_poll = enqueue_cst_resolution_plan_task(
        task_name=TASK_CST_RESOLUTION_PLAN_COMPUTE,
        job_id=job_id,
        payload=payload,
        run_sync=lambda: run_cst_resolution_plan_compute_sync(job_id, payload),
        dev_prefix="cst-plan-compute",
    )
    _write_cst_resolution_plan_slot(
        job_id, task_id, async_poll=async_poll, label="Computing CST resolution plan…"
    )
    return {"import_job_id": job_id, "task_id": task_id, "async_poll": async_poll, "async": True}


@router.post("/jobs/{job_id}/cst-resolution-plan/apply-async", status_code=202)
def cst_resolution_plan_apply_async(
    job_id: int,
    body: CstResolutionPlanApplyBody,
) -> dict[str, Any]:
    """Apply ready CST resolution-plan rows — per-candidate own target (never bulk single-target)."""
    with SessionLocal() as s:
        job = _get_cst_job_sync(s, job_id)
        _assert_cst_resolution_plan_dispatch_allowed(job)

    payload = {"candidate_ids": [int(x) for x in body.candidate_ids]}
    from app.services.imports.cst_resolution_plan_enqueue import (
        TASK_CST_RESOLUTION_PLAN_APPLY,
        enqueue_cst_resolution_plan_task,
        run_cst_resolution_plan_apply_sync,
    )

    task_id, async_poll = enqueue_cst_resolution_plan_task(
        task_name=TASK_CST_RESOLUTION_PLAN_APPLY,
        job_id=job_id,
        payload=payload,
        run_sync=lambda: run_cst_resolution_plan_apply_sync(job_id, payload),
        dev_prefix="cst-plan-apply",
    )
    _write_cst_resolution_plan_slot(
        job_id, task_id, async_poll=async_poll, label="Applying CST resolution plan…"
    )
    return {"import_job_id": job_id, "task_id": task_id, "async_poll": async_poll, "async": True}


@router.get("/jobs/{job_id}/cst-resolution-plan-task/{task_id}", status_code=200)
def cst_resolution_plan_task_status(job_id: int, task_id: str) -> dict[str, Any]:
    """Poll a CST resolution-plan Celery task (or dev in-process / sync fallback) state + result."""
    from app.services.imports.cst_resolution_plan_enqueue import dev_cst_resolution_plan_task_results

    dev_store = dev_cst_resolution_plan_task_results()
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
            _clear_cst_resolution_plan_slot(job_id)
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
        _clear_cst_resolution_plan_slot(job_id)

    return progress
