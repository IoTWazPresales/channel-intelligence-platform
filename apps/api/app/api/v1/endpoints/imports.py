import json
import uuid
from typing import Any

from fastapi import APIRouter, Body, Depends, File, Form, Header, HTTPException, Query, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.api.deps import get_db
from app.db.session_sync import SessionLocal
from app.ingestion.pipeline import process_import_job_sync
from app.services.imports.dsi_mapping_workflow import (
    dsi_mapping_gate_errors,
    dsi_mapping_state_dict,
    infer_dsi_job_sync,
    merge_dsi_mapping_memory,
    sanitize_dsi_field_mapping,
)
from app.models.historical_lineup import HistoricalLineupImportHeader, HistoricalLineupImportLine
from app.models.ingestion import ImportJob, ImportRowResult, ImportTemplate, RawFileMetadata, SourceDefinition
from app.storage.local import get_storage_backend
from app.services.imports.template_definitions import product_master_sample_csv

router = APIRouter()


def _is_admin(x_user_role: str | None) -> bool:
    return (x_user_role or "").strip().lower() == "admin"


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
async def list_jobs(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(ImportJob).order_by(ImportJob.id.desc()))
    rows = res.scalars().all()
    return [
        {
            "id": j.id,
            "source_id": j.source_id,
            "template_slug": j.template_slug,
            "import_mode": j.import_mode,
            "status": j.status,
            "stage": j.stage,
            "file_name": j.file_name,
            "error_summary": j.error_summary,
            "inferred_schema": j.inferred_schema,
            "field_mapping": j.field_mapping,
        }
        for j in rows
    ]


@router.post("/jobs")
async def create_job(
    source_id: int = Form(...),
    file: UploadFile = File(...),
    run_sync: bool = Form(default=True),
    import_mode: str = Form(default=""),
    confirm_destructive: str = Form(default=""),
    mapping_override: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
):
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
        mode = "validate" if tpl.slug in ("product_master", "distributor_inventory") else "apply"
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
    effective_run_sync = bool(run_sync) and tpl.slug not in ("product_master", "distributor_inventory")
    if effective_run_sync:
        with SessionLocal() as sync_db:
            process_import_job_sync(sync_db, job.id)
        await db.refresh(job)
    elif tpl.slug == "distributor_inventory":
        with SessionLocal() as sync_db:
            infer_dsi_job_sync(sync_db, job.id)
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
    }


@router.get("/jobs/{job_id}/dsi-mapping-state")
async def get_dsi_mapping_state(job_id: int, db: AsyncSession = Depends(get_db)):
    job = await db.get(ImportJob, job_id)
    if not job or job.template_slug != "distributor_inventory":
        raise HTTPException(status_code=404, detail="DSI mapping state not found for this job")
    headers = list(job.file_headers or [])
    raw = dict(job.field_mapping or {})
    clean, _ = sanitize_dsi_field_mapping(headers, raw)
    if clean != raw:
        job.field_mapping = clean
        await db.commit()
        await db.refresh(job)
    return dsi_mapping_state_dict(job)


@router.put("/jobs/{job_id}/dsi-field-mapping")
async def put_dsi_field_mapping(job_id: int, body: dict[str, Any] = Body(...), db: AsyncSession = Depends(get_db)):
    job = await db.get(ImportJob, job_id)
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
    await db.refresh(job)
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
    job.import_mode = "validate"
    await db.commit()
    with SessionLocal() as sync_db:
        process_import_job_sync(sync_db, job_id)
    job2 = await db.get(ImportJob, job_id)
    if job2 is not None:
        await db.refresh(job2)
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
    job2 = await db.get(ImportJob, job_id)
    if job2 is not None:
        await db.refresh(job2)
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
