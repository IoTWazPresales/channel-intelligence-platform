"""Import pipeline orchestration (MVP: synchronous, explainable stages)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.infer import infer_schema, read_tabular
from app.models.dimensions import DimChannel, DimProduct
from app.models.ingestion import ImportJob, ImportRowResult, RawFileMetadata, SourceDefinition
from app.models.mapping import EntityMappingQueue
from app.services.catalog.product_import_sync import sync_bulk_upsert_products_from_rows
from app.storage.local import get_storage_backend


STAGE_UPLOADED = "uploaded"
STAGE_RAW_STORED = "raw_stored"
STAGE_INFERRED = "schema_inferred"
STAGE_MAPPED = "fields_mapped"
STAGE_VALIDATED = "validated"
STAGE_LOADED = "loaded"
STAGE_FAILED = "failed"


def effective_mapping_template(source: SourceDefinition | None) -> dict[str, Any]:
    """Merge ImportTemplate.expected_columns with per-source overrides (alias shape)."""
    merged: dict[str, Any] = {}
    tpl = source.import_template if source else None
    if tpl and tpl.expected_columns:
        for k, v in tpl.expected_columns.items():
            if isinstance(v, dict):
                merged[k] = {"aliases": list(v.get("aliases", []))}
    if source and source.expected_template:
        for k, v in source.expected_template.items():
            if isinstance(v, dict):
                merged.setdefault(k, {"aliases": list(v.get("aliases", []))})
            else:
                merged.setdefault(k, {"aliases": []})
    return merged


def default_field_mapping(inferred_columns: list[str], template: dict[str, Any] | None) -> dict[str, str]:
    """Map source column names to canonical fields using template aliases or heuristics."""
    template = template or {}
    aliases: dict[str, str] = {}
    for canonical, meta in template.items():
        for alias in meta.get("aliases", []) if isinstance(meta, dict) else []:
            aliases[alias.lower()] = canonical

    mapping: dict[str, str] = {}
    for col in inferred_columns:
        key = col.strip().lower()
        if key in aliases:
            mapping[col] = aliases[key]
            continue
        if "sku" in key or ("item" in key and "name" not in key):
            mapping[col] = "sku"
        elif "qty" in key or "quantity" in key or "on_hand" in key:
            mapping[col] = "quantity"
        elif "price" in key:
            mapping[col] = "price"
        elif key in ("name", "title", "product_name", "description") or ("name" in key and "sku" not in key):
            mapping[col] = "name"
        elif "category" in key or key == "cat":
            mapping[col] = "category"
        elif "channel" in key and "customer" not in key:
            mapping[col] = "channel_code"
        elif "form" in key or "factor" in key:
            mapping[col] = "form_factor"
        elif "price_band" in key or ("band" in key and "price" in key):
            mapping[col] = "price_band"
    return mapping


def _process_inventory_sku_gate(db: Session, job: ImportJob, df: pd.DataFrame, mapping: dict[str, str]) -> int:
    errors = 0
    if "sku" not in mapping.values():
        db.add(
            ImportRowResult(
                job_id=job.id,
                row_number=0,
                severity="error",
                code="missing_sku_mapping",
                message="Could not infer SKU column; manual mapping required.",
            )
        )
        return 1

    sku_col = next(k for k, v in mapping.items() if v == "sku")
    products = {p.sku.lower(): p for p in db.scalars(select(DimProduct)).all()}

    for idx, row in df.iterrows():
        raw_sku = str(row.get(sku_col, "")).strip()
        if not raw_sku:
            db.add(
                ImportRowResult(
                    job_id=job.id,
                    row_number=int(idx) + 1,
                    severity="warning",
                    code="blank_sku",
                    message="Blank SKU in row",
                    raw_payload=row.where(pd.notnull(row), None).to_dict(),
                )
            )
            continue
        match = products.get(raw_sku.lower())
        if not match:
            db.add(
                ImportRowResult(
                    job_id=job.id,
                    row_number=int(idx) + 1,
                    severity="error",
                    code="unmatched_product",
                    message=f"No master match for SKU '{raw_sku}'",
                    raw_payload=row.where(pd.notnull(row), None).to_dict(),
                )
            )
            db.add(
                EntityMappingQueue(
                    entity_type="product",
                    raw_value=raw_sku,
                    normalized_value=raw_sku.lower(),
                    suggested_entity_id=None,
                    match_method="none",
                    confidence_score=0,
                    status="review_required",
                    job_id=job.id,
                    context={"row": int(idx) + 1},
                )
            )
            errors += 1
    return errors


def _process_stub(db: Session, job: ImportJob, df: pd.DataFrame, mapping: dict[str, str]) -> int:
    db.add(
        ImportRowResult(
            job_id=job.id,
            row_number=0,
            severity="info",
            code="stub_pipeline",
            message="This import template is not wired to a full loader yet; file is stored and schema inferred only.",
        )
    )
    return 0


def _process_product_master(db: Session, job: ImportJob, df: pd.DataFrame, mapping: dict[str, str]) -> int:
    errors = 0
    if "sku" not in mapping.values():
        db.add(
            ImportRowResult(
                job_id=job.id,
                row_number=0,
                severity="error",
                code="missing_sku_mapping",
                message="Could not infer SKU column; check headers against the template.",
            )
        )
        return 1
    if "name" not in mapping.values():
        db.add(
            ImportRowResult(
                job_id=job.id,
                row_number=0,
                severity="error",
                code="missing_name_mapping",
                message="Could not infer product name column; expected name / product_name / title.",
            )
        )
        return 1

    sku_col = next(k for k, v in mapping.items() if v == "sku")
    name_col = next(k for k, v in mapping.items() if v == "name")
    cat_col = next((k for k, v in mapping.items() if v == "category"), None)
    ch_col = next((k for k, v in mapping.items() if v == "channel_code"), None)

    channels = {c.code.strip().lower(): c.id for c in db.scalars(select(DimChannel)).all()}
    payloads: list[dict[str, Any]] = []
    for idx, row in df.iterrows():
        sku = str(row.get(sku_col, "")).strip()
        name = str(row.get(name_col, "")).strip()
        if not sku:
            db.add(
                ImportRowResult(
                    job_id=job.id,
                    row_number=int(idx) + 1,
                    severity="warning",
                    code="blank_sku",
                    message="Blank SKU in row",
                    raw_payload=row.where(pd.notnull(row), None).to_dict(),
                )
            )
            continue
        if not name:
            db.add(
                ImportRowResult(
                    job_id=job.id,
                    row_number=int(idx) + 1,
                    severity="error",
                    code="blank_name",
                    message="Blank product name in row",
                    raw_payload=row.where(pd.notnull(row), None).to_dict(),
                )
            )
            errors += 1
            continue
        cat = None
        if cat_col:
            v = row.get(cat_col)
            if v is not None and str(v).strip():
                cat = str(v).strip()
        ch_raw = None
        if ch_col:
            v = row.get(ch_col)
            if v is not None and str(v).strip():
                ch_raw = str(v).strip()
        if ch_raw and ch_raw.lower() not in channels:
            db.add(
                ImportRowResult(
                    job_id=job.id,
                    row_number=int(idx) + 1,
                    severity="error",
                    code="unknown_channel",
                    message=f"Unknown channel_code {ch_raw!r}",
                    raw_payload=row.where(pd.notnull(row), None).to_dict(),
                )
            )
            errors += 1
            continue
        payloads.append({"sku": sku, "name": name, "category": cat, "channel_code": ch_raw})

    if errors:
        return errors

    if job.import_mode == "apply":
        stats = sync_bulk_upsert_products_from_rows(db, payloads)
        db.add(
            ImportRowResult(
                job_id=job.id,
                row_number=0,
                severity="info",
                code="product_master_applied",
                message=f"Applied product upsert: created={stats['created']}, updated={stats['updated']}, rows={stats['total']}.",
            )
        )
        job.stage = STAGE_LOADED
    else:
        db.add(
            ImportRowResult(
                job_id=job.id,
                row_number=0,
                severity="info",
                code="product_master_validated",
                message=f"Validated {len(payloads)} product row(s); import_mode=validate — no catalog writes performed.",
            )
        )

    return 0


def process_import_job_sync(db: Session, job_id: int) -> ImportJob:
    job = db.get(ImportJob, job_id)
    if not job:
        raise ValueError("job not found")

    # Product Master jobs using the mapping workflow store file_headers; do not run legacy one-shot pipeline.
    if job.template_slug == "product_master" and job.file_headers is not None:
        db.refresh(job)
        return job

    storage = get_storage_backend()
    raw = db.scalars(select(RawFileMetadata).where(RawFileMetadata.job_id == job_id)).one()
    data = storage.read(raw.storage_key)

    try:
        job.stage = STAGE_RAW_STORED
        job.started_at = datetime.now(timezone.utc)
        job.status = "running"
        db.flush()

        df = read_tabular(job.file_name, data)
        schema = infer_schema(df)
        job.inferred_schema = schema
        job.stage = STAGE_INFERRED

        cols = [c["name"] for c in schema["columns"]]
        source = job.source
        template = effective_mapping_template(source)
        mapping = job.field_mapping or default_field_mapping(cols, template)
        job.field_mapping = mapping
        job.stage = STAGE_MAPPED

        tpl = source.import_template if source else None
        handler = tpl.pipeline_handler if tpl else "inventory_sku_gate"

        if handler == "stub_noop":
            errors = _process_stub(db, job, df, mapping)
        elif handler == "product_master_upsert":
            errors = _process_product_master(db, job, df, mapping)
        else:
            errors = _process_inventory_sku_gate(db, job, df, mapping)

        job.stage = STAGE_VALIDATED
        job.status = "completed_with_errors" if errors else "completed"
        job.completed_at = datetime.now(timezone.utc)
        job.error_summary = f"{errors} rows require attention" if errors else None
        db.commit()
        db.refresh(job)
        return job
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        job = db.get(ImportJob, job_id)
        if job:
            job.status = "failed"
            job.stage = STAGE_FAILED
            job.error_summary = str(exc)
            job.completed_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(job)
        return job
