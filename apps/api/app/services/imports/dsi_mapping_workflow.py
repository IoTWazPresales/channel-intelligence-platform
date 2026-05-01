"""Distributor sales & inventory: header infer, initial field mapping, gate checks, source mapping memory."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.ingestion.infer import infer_schema, read_tabular
from app.ingestion.pipeline import default_field_mapping, effective_mapping_template
from app.models.ingestion import ImportJob, RawFileMetadata, SourceDefinition
from app.services.imports.distributor_sales_inventory import CANONICAL as DSI_CANONICAL
from app.services.imports.pm_mapping_memory import load_by_header_norm, norm_header_key
from app.storage.local import get_storage_backend

# Targets persisted in column_mapping_memory (same JSON shape as PM: {target, confirmations}).
DSI_MEMORY_TARGETS = frozenset(DSI_CANONICAL)


def build_initial_dsi_field_mapping(
    db: Session,
    headers: list[str],
    source: SourceDefinition | None,
    template: dict[str, Any],
) -> dict[str, str]:
    """Template + default_field_mapping, overlaid with saved per-header targets for this source."""
    memory = load_by_header_norm(source) if source else {}
    mapping: dict[str, str] = {}
    for h in headers:
        nh = norm_header_key(h)
        entry = memory.get(nh) if nh else None
        if isinstance(entry, dict):
            tgt = entry.get("target")
            if tgt and str(tgt).strip() and str(tgt) in DSI_MEMORY_TARGETS:
                mapping[h] = str(tgt)
    defaults = default_field_mapping(headers, template)
    for h, tgt in defaults.items():
        if h not in mapping:
            mapping[h] = tgt
    return mapping


def dsi_mapping_gate_errors(mapping: dict[str, str]) -> list[dict[str, str]]:
    """Blocking issues before running DSI pipeline (column mapping completeness)."""
    vals = set(mapping.values())
    errs: list[dict[str, str]] = []
    if "distributor_token" not in vals:
        errs.append(
            {
                "code": "missing_column_mapping_distributor",
                "message": "No source column is mapped to Distributor.",
            }
        )
    if "product_identifier" not in vals:
        errs.append(
            {
                "code": "missing_column_mapping_product",
                "message": "No source column is mapped to a product identifier (SKU / catalog key).",
            }
        )
    has_date = "transaction_date" in vals or "snapshot_date" in vals
    if not has_date:
        errs.append(
            {
                "code": "missing_column_mapping_date",
                "message": "Map at least one date column to Transaction date or Snapshot / stock date.",
            }
        )
    has_qty = "quantity_sold" in vals or "stock_on_hand" in vals
    if not has_qty:
        errs.append(
            {
                "code": "missing_column_mapping_quantity",
                "message": "Map at least one of Quantity sold or Stock on hand.",
            }
        )
    return errs


def merge_dsi_mapping_memory(db: Session, *, source_id: int, field_mapping: dict[str, str]) -> None:
    """Persist confirmed DSI column → canonical mappings on the source (by normalized header)."""
    src = db.get(SourceDefinition, source_id)
    if src is None:
        return
    root: dict[str, Any] = dict(src.column_mapping_memory or {})
    bh: dict[str, Any] = dict(root.get("by_header_norm") or {})

    for header, tgt in field_mapping.items():
        nh = norm_header_key(str(header))
        if not nh:
            continue
        if tgt not in DSI_MEMORY_TARGETS:
            continue
        prev = bh.get(nh) if isinstance(bh.get(nh), dict) else {}
        bh[nh] = {
            "target": tgt,
            "confirmations": int(prev.get("confirmations", 0)) + 1,
        }

    root["by_header_norm"] = bh
    root["schema_version"] = root.get("schema_version") or "1"
    root["dsi_mapping"] = True
    src.column_mapping_memory = root
    db.add(src)


def infer_dsi_job_sync(db: Session, job_id: int) -> ImportJob:
    """Read stored raw file, infer headers, set initial field_mapping + file_headers (no DSI pipeline run)."""
    job = db.scalar(
        select(ImportJob)
        .options(joinedload(ImportJob.source).joinedload(SourceDefinition.import_template))
        .where(ImportJob.id == job_id)
    )
    if not job or job.template_slug != "distributor_inventory":
        raise ValueError("infer_dsi_job_sync requires a distributor_inventory import job")

    raw = db.scalars(select(RawFileMetadata).where(RawFileMetadata.job_id == job_id)).one()
    storage = get_storage_backend()
    data = storage.read(raw.storage_key)

    df = read_tabular(job.file_name, data)
    schema = infer_schema(df)
    cols = [c["name"] for c in schema["columns"]]

    source = job.source
    template = effective_mapping_template(source)
    mapping = build_initial_dsi_field_mapping(db, cols, source, template)

    job.inferred_schema = schema
    job.file_headers = cols
    job.field_mapping = mapping
    job.stage = "dsi_mapping_ready"
    job.status = "pending"
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def dsi_mapping_state_dict(job: ImportJob) -> dict[str, Any]:
    """Serializable mapping UI payload."""
    mapping = job.field_mapping or {}
    gate = dsi_mapping_gate_errors(mapping)
    headers = list(job.file_headers or [])
    return {
        "id": job.id,
        "stage": job.stage,
        "status": job.status,
        "file_headers": headers,
        "field_mapping": mapping,
        "canonical_targets": sorted(DSI_MEMORY_TARGETS),
        "blocking_mapping_errors": gate,
        "mapping_valid": len(gate) == 0,
    }
