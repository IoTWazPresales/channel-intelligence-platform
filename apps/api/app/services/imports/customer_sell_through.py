"""Customer sell-through import pipeline (Phase 0 skeleton — parsers in Phase 1)."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.customer_report_config import CustomerReportConfig
from app.models.dimensions import CustomerLocation, DimCustomer
from app.models.import_customer_sellthrough_staging import ImportCustomerSellthroughStagingLine
from app.models.ingestion import ImportJob, ImportTemplate, RawFileMetadata
from app.services.imports.distributor_sales_inventory import (
    ProductResolutionIndex,
    _load_product_resolution_index,
    _product_token_key,
)
from app.core.config import get_settings
from app.services.imports.ai_import_resolver import detect_format_drift
from app.services.imports.ai_resolver_wiring import (
    stash_ai_suggestion_on_payload,
    try_ai_token_resolution,
)
from app.services.imports.parsers.customer_sell_through_flat import (
    EXPECTED_COLUMNS_META_KEY,
    parse_flat_report,
)
from app.services.imports.parsers.customer_sell_through_mtd_delta import (
    parse_mtd_delta_report,
)
from app.services.imports.parsers.customer_sell_through_multi_sheet import (
    parse_multi_sheet_report,
)
from app.services.imports.parsers.customer_sell_through_pivoted import (
    parse_pivoted_report,
)
from app.services.imports.parsers.customer_sell_through_wide_extract import (
    parse_wide_extract_report,
)
from app.storage.local import get_storage_backend
from app.utils.json_safe import to_jsonable

logger = logging.getLogger(__name__)

# Matches ``STAGE_FAILED`` in ``app.ingestion.pipeline`` (avoid circular import).
_STAGE_FAILED = "failed"

STRUCTURE_FLAT = "flat"
STRUCTURE_PIVOTED = "pivoted"
STRUCTURE_MULTI_SHEET = "multi_sheet"
STRUCTURE_MTD_DELTA = "mtd_delta"
STRUCTURE_WIDE_EXTRACT = "wide_extract"

def customer_sellthrough_source_key(
    *,
    customer_id: int,
    customer_location_id: int | None,
    product_id: int,
    period_start_date: date,
) -> str:
    """Natural upsert key: ``ct:{customer_id}:{location_id|0}:{product_id}:{period_start_date}``."""
    loc_part = int(customer_location_id) if customer_location_id is not None else 0
    return f"ct:{customer_id}:{loc_part}:{product_id}:{period_start_date.isoformat()}"


def new_customer_sellthrough_staging_line(
    *,
    import_job_id: int,
    source_row_number: int,
    raw_row_payload: dict[str, Any] | None = None,
) -> ImportCustomerSellthroughStagingLine:
    """Create a pending staging row (resolution applied in Phase 1)."""
    return ImportCustomerSellthroughStagingLine(
        import_job_id=import_job_id,
        source_row_number=source_row_number,
        raw_row_payload=raw_row_payload or {},
        resolution_status="pending",
    )


def customer_report_config_defaults(*, customer_id: int) -> CustomerReportConfig:
    """In-memory config row with Phase 0 defaults (not persisted)."""
    return CustomerReportConfig(
        customer_id=customer_id,
        reports_expected=False,
        expected_cadence="weekly",
        overdue_threshold_days=10,
    )


def _parser_not_implemented_message(structure_type: str) -> str:
    return f"Parser not yet implemented for structure type: {structure_type}"


def _write_parse_failed(job: ImportJob, message: str) -> None:
    meta = dict(job.staged_metadata or {}) if isinstance(job.staged_metadata, dict) else {}
    meta["customer_sellthrough_error"] = {
        "reason": "parse_failed",
        "message": message,
    }
    job.staged_metadata = to_jsonable(meta)
    job.stage = _STAGE_FAILED
    job.status = "completed_with_errors"
    job.error_summary = message[:500]


def resolve_customer_id_for_job(db: Session, job: ImportJob) -> int | None:
    """Resolve anchor customer for this import job (source-scoped, not row-derived)."""
    meta = job.staged_metadata if isinstance(job.staged_metadata, dict) else {}
    raw = meta.get("customer_id")
    if raw is not None:
        try:
            return int(raw)
        except (TypeError, ValueError):
            pass

    source = job.source
    if source and isinstance(source.expected_template, dict):
        cid = source.expected_template.get("customer_id")
        if cid is not None:
            try:
                return int(cid)
            except (TypeError, ValueError):
                pass

    if source and source.code:
        found = db.scalar(select(DimCustomer.id).where(DimCustomer.code == source.code.strip()))
        if found is not None:
            return int(found)

    return None


def resolve_product_id_for_sellthrough(idx: ProductResolutionIndex, token: str) -> int | None:
    """Item/material → EAN/UPC → sales model (single match only)."""
    key = _product_token_key(token)
    if not key:
        return None
    if key in idx.sku_to_id:
        return int(idx.sku_to_id[key])
    part_ids = idx.part_number_to_ids.get(key)
    if part_ids and len(part_ids) == 1:
        return int(part_ids[0])
    ean_ids = idx.ean_to_ids.get(key)
    if ean_ids and len(ean_ids) == 1:
        return int(ean_ids[0])
    upc_ids = idx.upc_to_ids.get(key)
    if upc_ids and len(upc_ids) == 1:
        return int(upc_ids[0])
    sm_ids = idx.sales_model_name_to_ids.get(key)
    if sm_ids and len(sm_ids) == 1:
        return int(sm_ids[0])
    return None


def _upsert_customer_report_config(
    db: Session,
    *,
    customer_id: int,
    period_start_date: date | None,
    report_structure_type: str,
) -> None:
    cfg = db.scalar(select(CustomerReportConfig).where(CustomerReportConfig.customer_id == customer_id))
    if cfg is None:
        cfg = customer_report_config_defaults(customer_id=customer_id)
        cfg.report_structure_type = report_structure_type
        db.add(cfg)
    if period_start_date is not None:
        cfg.last_report_received = period_start_date
    if not cfg.report_structure_type:
        cfg.report_structure_type = report_structure_type
    db.add(cfg)


def _build_parse_mapping(
    db: Session,
    job: ImportJob,
    mapping: dict[str, str],
    template: ImportTemplate | None,
) -> tuple[dict, list[str]]:
    from app.ingestion.pipeline import effective_mapping_template

    expected = effective_mapping_template(job.source) if job.source else {}
    if template and template.expected_columns:
        for k, v in template.expected_columns.items():
            if isinstance(v, dict):
                expected.setdefault(k, {"aliases": list(v.get("aliases", []))})

    parse_mapping = dict(mapping or {})
    parse_mapping[EXPECTED_COLUMNS_META_KEY] = expected
    return parse_mapping, []


def _sniff_file_headers(file_bytes: bytes, filename: str) -> list[str]:
    from app.services.imports.parsers.customer_sell_through_flat import _normalize_text, _read_workbook_sheets

    try:
        for _name, raw in _read_workbook_sheets(file_bytes, filename):
            if raw is not None and not raw.empty:
                return [str(_normalize_text(c) or "").strip() for c in raw.iloc[0].tolist()]
    except ValueError:
        return []
    return []


def _format_drift_warnings(job: ImportJob, current_headers: list[str]) -> list[str]:
    if not job.source or not isinstance(job.source.column_mapping_memory, dict):
        return []
    stored = job.source.column_mapping_memory
    stored_headers = list((stored.get("by_header_norm") or {}).keys())
    drift = detect_format_drift(current_headers, stored_headers, stored)
    if not drift or not drift.has_drift:
        return []
    return [
        f"Format drift detected: new={drift.new_columns} missing={drift.missing_columns}"
    ]


def _load_job_file_bytes(db: Session, job: ImportJob) -> tuple[bytes | None, str | None]:
    raw_meta = db.scalars(select(RawFileMetadata).where(RawFileMetadata.job_id == job.id)).first()
    if not raw_meta:
        return None, "No raw file metadata for this import job."
    storage = get_storage_backend()
    return storage.read(raw_meta.storage_key), None


def _product_candidates(idx: ProductResolutionIndex, token: str, limit: int = 10) -> list[dict[str, Any]]:
    key = _product_token_key(token)
    out: list[dict[str, Any]] = []
    if key:
        for sku, pid in idx.sku_to_id.items():
            if key in sku or sku in key:
                out.append({"id": int(pid), "sku": sku})
                if len(out) >= limit:
                    return out
    for sku, pid in list(idx.sku_to_id.items())[:limit]:
        out.append({"id": int(pid), "sku": sku})
    return out[:limit]


def _location_candidates(db: Session, customer_id: int, token: str, limit: int = 10) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(CustomerLocation).where(CustomerLocation.customer_id == customer_id).limit(limit * 3)
    ).all()
    key = (token or "").strip().lower()
    out: list[dict[str, Any]] = []
    for loc in rows:
        code = (loc.location_code or "").strip().lower()
        name = (loc.location_name or "").strip().lower()
        if not key or key in code or key in name or code in key:
            out.append(
                {
                    "id": int(loc.id),
                    "location_code": loc.location_code,
                    "location_name": loc.location_name,
                }
            )
        if len(out) >= limit:
            break
    if not out:
        for loc in rows[:limit]:
            out.append(
                {
                    "id": int(loc.id),
                    "location_code": loc.location_code,
                    "location_name": loc.location_name,
                }
            )
    return out[:limit]


def _apply_ai_resolution_to_line(
    db: Session,
    *,
    line: ImportCustomerSellthroughStagingLine,
    customer_id: int,
    prod_idx: ProductResolutionIndex,
    ai_assist_used: list[bool],
) -> tuple[bool, bool]:
    product_ok = line.resolved_product_id is not None
    job_id = int(getattr(line, "import_job_id", 0) or 0)

    # Deterministic-first is already done by the caller (resolved_product_id set on exact match);
    # this runs only on miss, and goes through the SHARED resolver wrapper (deterministic→AI≥0.90),
    # same as DSI / shipment — not the bespoke direct call. Wrapper no-ops when AI is disabled.
    if not product_ok and line.raw_product_token:
        ai_id, ai_tag, suggestion = try_ai_token_resolution(
            raw_token=line.raw_product_token,
            token_type="product",
            candidates=_product_candidates(prod_idx, line.raw_product_token),
            import_type="customer_sell_through",
            job_id=job_id,
            extra_context={"customer_id": customer_id},
        )
        if suggestion is not None:
            ai_assist_used[0] = True
            line.raw_row_payload = stash_ai_suggestion_on_payload(
                line.raw_row_payload, token_type="product", suggestion=suggestion
            )
            if ai_id is not None and ai_tag == "ai_auto_resolved":
                line.resolved_product_id = int(ai_id)
                line.resolution_status = "ai_auto_resolved"
                product_ok = True
            else:
                line.resolution_status = "ai_suggested"

    location_ok = True
    if line.raw_location_token:
        loc_id = db.scalar(
            select(CustomerLocation.id).where(
                CustomerLocation.customer_id == customer_id,
                CustomerLocation.location_code == line.raw_location_token,
            )
        )
        if loc_id is not None:
            line.resolved_location_id = int(loc_id)
        else:
            ai_id, ai_tag, suggestion = try_ai_token_resolution(
                raw_token=line.raw_location_token,
                token_type="location",
                candidates=_location_candidates(db, customer_id, line.raw_location_token),
                import_type="customer_sell_through",
                job_id=job_id,
                extra_context={"customer_id": customer_id},
            )
            if suggestion is not None:
                ai_assist_used[0] = True
                line.raw_row_payload = stash_ai_suggestion_on_payload(
                    line.raw_row_payload, token_type="location", suggestion=suggestion
                )
                if ai_id is not None and ai_tag == "ai_auto_resolved":
                    line.resolved_location_id = int(ai_id)
                else:
                    location_ok = False
                    if line.resolution_status == "pending":
                        line.resolution_status = "ai_suggested"
            else:
                location_ok = False

    return product_ok, location_ok


def _ingest_parse_result(
    db: Session,
    job: ImportJob,
    *,
    customer_id: int,
    result: Any,
    structure_type: str,
    summary_key: str,
    drift_warnings: list[str] | None = None,
) -> int:
    if result.error:
        _write_parse_failed(job, result.error)
        return 1

    db.execute(
        delete(ImportCustomerSellthroughStagingLine).where(
            ImportCustomerSellthroughStagingLine.import_job_id == job.id
        )
    )
    db.flush()

    prod_idx = _load_product_resolution_index(db)
    resolved_n = 0
    unresolved_n = 0
    ai_assist_used = [False]

    for row in result.rows:
        line = ImportCustomerSellthroughStagingLine(**row)
        line.resolved_customer_id = customer_id

        if line.raw_product_token:
            pid = resolve_product_id_for_sellthrough(prod_idx, line.raw_product_token)
            if pid is not None:
                line.resolved_product_id = pid

        product_ok, location_ok = _apply_ai_resolution_to_line(
            db,
            line=line,
            customer_id=customer_id,
            prod_idx=prod_idx,
            ai_assist_used=ai_assist_used,
        )

        if not product_ok and line.raw_product_token:
            pid = resolve_product_id_for_sellthrough(prod_idx, line.raw_product_token)
            if pid is not None:
                line.resolved_product_id = pid
                product_ok = True

        if product_ok and location_ok and line.resolution_status in ("pending", "unresolved"):
            line.resolution_status = "resolved"

        if product_ok and location_ok:
            if line.resolution_status in ("ai_auto_resolved", "pending"):
                line.resolution_status = "resolved"
            if line.resolution_status == "resolved":
                resolved_n += 1
            else:
                unresolved_n += 1
        else:
            if line.resolution_status == "pending":
                line.resolution_status = "unresolved"
            unresolved_n += 1

        db.add(line)

    db.flush()

    warnings = list(result.warnings or [])
    if drift_warnings:
        warnings = drift_warnings + warnings

    meta = dict(job.staged_metadata or {}) if isinstance(job.staged_metadata, dict) else {}
    summary: dict[str, Any] = {
        "period_start_date": str(result.period_start_date) if result.period_start_date else None,
        "total_rows": len(result.rows),
        "resolved": resolved_n,
        "unresolved": unresolved_n,
        "warnings": warnings,
    }
    if ai_assist_used[0]:
        summary["ai_assist_used"] = True
    meta[summary_key] = to_jsonable(summary)
    job.staged_metadata = to_jsonable(meta)

    _upsert_customer_report_config(
        db,
        customer_id=customer_id,
        period_start_date=result.period_start_date,
        report_structure_type=structure_type,
    )

    if (job.import_mode or "").strip().lower() == "apply":
        from app.services.imports.customer_sell_through_apply import apply_customer_sellthrough_staging

        apply_customer_sellthrough_staging(db, job.id)

    return 0 if result.rows else 0


def _run_structure_handler(
    db: Session,
    job: ImportJob,
    mapping: dict[str, str],
    template: ImportTemplate | None,
    *,
    structure_type: str,
    summary_key: str,
    parse_fn,
    needs_db: bool = False,
) -> int:
    customer_id = resolve_customer_id_for_job(db, job)
    if customer_id is None:
        _write_parse_failed(
            job,
            "Could not resolve customer_id for this import job (set staged_metadata.customer_id or source customer).",
        )
        return 1

    file_bytes, err = _load_job_file_bytes(db, job)
    if err or file_bytes is None:
        _write_parse_failed(job, err or "Missing file bytes")
        return 1

    parse_mapping, _ = _build_parse_mapping(db, job, mapping, template)
    if structure_type == STRUCTURE_MTD_DELTA:
        parse_mapping["__customer_id__"] = customer_id

    fname = job.file_name or "upload"
    drift_warnings = _format_drift_warnings(job, _sniff_file_headers(file_bytes, fname))
    jid = int(job.id)
    if needs_db:
        result = parse_fn(file_bytes, fname, parse_mapping, jid, db)
    else:
        result = parse_fn(file_bytes, fname, parse_mapping, jid)

    return _ingest_parse_result(
        db,
        job,
        customer_id=customer_id,
        result=result,
        structure_type=structure_type,
        summary_key=summary_key,
        drift_warnings=drift_warnings,
    )


def _handle_flat(
    db: Session,
    job: ImportJob,
    df: pd.DataFrame,
    mapping: dict[str, str],
    template: ImportTemplate | None,
) -> int:
    del df  # flat parser reads raw bytes (multi-sheet / header detection)

    customer_id = resolve_customer_id_for_job(db, job)
    if customer_id is None:
        _write_parse_failed(
            job,
            "Could not resolve customer_id for this import job (set staged_metadata.customer_id or source customer).",
        )
        return 1

    raw_meta = db.scalars(select(RawFileMetadata).where(RawFileMetadata.job_id == job.id)).first()
    if not raw_meta:
        _write_parse_failed(job, "No raw file metadata for this import job.")
        return 1

    storage = get_storage_backend()
    file_bytes = storage.read(raw_meta.storage_key)

    from app.ingestion.pipeline import effective_mapping_template

    expected = effective_mapping_template(job.source) if job.source else {}
    if template and template.expected_columns:
        for k, v in template.expected_columns.items():
            if isinstance(v, dict):
                expected.setdefault(k, {"aliases": list(v.get("aliases", []))})

    parse_mapping = dict(mapping or {})
    parse_mapping[EXPECTED_COLUMNS_META_KEY] = expected

    result = parse_flat_report(file_bytes, job.file_name or "upload", parse_mapping, int(job.id))
    if result.error:
        _write_parse_failed(job, result.error)
        return 1

    db.execute(
        delete(ImportCustomerSellthroughStagingLine).where(
            ImportCustomerSellthroughStagingLine.import_job_id == job.id
        )
    )
    db.flush()

    prod_idx = _load_product_resolution_index(db)
    resolved_n = 0
    unresolved_n = 0

    for row in result.rows:
        line = ImportCustomerSellthroughStagingLine(**row)
        line.resolved_customer_id = customer_id

        product_ok = False
        if line.raw_product_token:
            pid = resolve_product_id_for_sellthrough(prod_idx, line.raw_product_token)
            if pid is not None:
                line.resolved_product_id = pid
                product_ok = True

        location_ok = True
        if line.raw_location_token:
            loc_id = db.scalar(
                select(CustomerLocation.id).where(
                    CustomerLocation.customer_id == customer_id,
                    CustomerLocation.location_code == line.raw_location_token,
                )
            )
            if loc_id is not None:
                line.resolved_location_id = int(loc_id)
            else:
                location_ok = False

        if product_ok and location_ok:
            line.resolution_status = "resolved"
            resolved_n += 1
        else:
            line.resolution_status = "unresolved"
            unresolved_n += 1

        db.add(line)

    db.flush()

    meta = dict(job.staged_metadata or {}) if isinstance(job.staged_metadata, dict) else {}
    meta["customer_sellthrough_flat"] = to_jsonable(
        {
            "period_start_date": str(result.period_start_date) if result.period_start_date else None,
            "total_rows": len(result.rows),
            "resolved": resolved_n,
            "unresolved": unresolved_n,
            "warnings": list(result.warnings),
        }
    )
    job.staged_metadata = to_jsonable(meta)

    _upsert_customer_report_config(
        db,
        customer_id=customer_id,
        period_start_date=result.period_start_date,
        report_structure_type=STRUCTURE_FLAT,
    )

    if (job.import_mode or "").strip().lower() == "apply":
        from app.services.imports.customer_sell_through_apply import apply_customer_sellthrough_staging

        apply_customer_sellthrough_staging(db, job.id)

    return 0 if result.rows else 0


def _handle_pivoted(
    db: Session,
    job: ImportJob,
    df: pd.DataFrame,
    mapping: dict[str, str],
    template: ImportTemplate | None,
) -> int:
    del df
    return _run_structure_handler(
        db,
        job,
        mapping,
        template,
        structure_type=STRUCTURE_PIVOTED,
        summary_key="customer_sellthrough_pivoted",
        parse_fn=parse_pivoted_report,
    )


def _handle_multi_sheet(
    db: Session,
    job: ImportJob,
    df: pd.DataFrame,
    mapping: dict[str, str],
    template: ImportTemplate | None,
) -> int:
    del df
    return _run_structure_handler(
        db,
        job,
        mapping,
        template,
        structure_type=STRUCTURE_MULTI_SHEET,
        summary_key="customer_sellthrough_multi_sheet",
        parse_fn=parse_multi_sheet_report,
    )


def _handle_mtd_delta(
    db: Session,
    job: ImportJob,
    df: pd.DataFrame,
    mapping: dict[str, str],
    template: ImportTemplate | None,
) -> int:
    del df
    return _run_structure_handler(
        db,
        job,
        mapping,
        template,
        structure_type=STRUCTURE_MTD_DELTA,
        summary_key="customer_sellthrough_mtd_delta",
        parse_fn=parse_mtd_delta_report,
        needs_db=True,
    )


def _handle_wide_extract(
    db: Session,
    job: ImportJob,
    df: pd.DataFrame,
    mapping: dict[str, str],
    template: ImportTemplate | None,
) -> int:
    del df
    return _run_structure_handler(
        db,
        job,
        mapping,
        template,
        structure_type=STRUCTURE_WIDE_EXTRACT,
        summary_key="customer_sellthrough_wide_extract",
        parse_fn=parse_wide_extract_report,
    )


def _write_parser_not_implemented(job: ImportJob, structure_type: str, message: str) -> None:
    meta = dict(job.staged_metadata or {}) if isinstance(job.staged_metadata, dict) else {}
    meta["customer_sellthrough_error"] = {
        "reason": "parser_not_implemented",
        "structure_type": structure_type,
        "message": message,
    }
    job.staged_metadata = to_jsonable(meta)
    job.stage = _STAGE_FAILED
    job.status = "completed_with_errors"
    job.error_summary = message[:500]


def process_customer_sell_through(
    db: Session,
    job: ImportJob,
    df: pd.DataFrame,
    mapping: dict[str, str],
    template: ImportTemplate | None = None,
) -> int:
    """Dispatch on report structure type; Phase 0 handlers are not implemented yet.

    ``df`` is the parsed tabular file from the import pipeline (equivalent to decoded file bytes).
    Returns blocking error count (0 success path, 1 when parser skeleton stops the job).
    """
    meta = dict(job.staged_metadata or {}) if isinstance(job.staged_metadata, dict) else {}
    structure_type = meta.get("report_structure_type")
    if not isinstance(structure_type, str) or not structure_type.strip():
        structure_type = STRUCTURE_FLAT
        logger.warning(
            "customer_sell_through job_id=%s missing report_structure_type; defaulting to flat",
            job.id,
        )
    structure_type = structure_type.strip()

    handlers = {
        STRUCTURE_FLAT: _handle_flat,
        STRUCTURE_PIVOTED: _handle_pivoted,
        STRUCTURE_MULTI_SHEET: _handle_multi_sheet,
        STRUCTURE_MTD_DELTA: _handle_mtd_delta,
        STRUCTURE_WIDE_EXTRACT: _handle_wide_extract,
    }
    handler = handlers.get(structure_type)
    if handler is None:
        msg = f"Unknown structure type: {structure_type}"
        _write_parser_not_implemented(job, structure_type, msg)
        return 1

    try:
        return handler(db, job, df, mapping, template)
    except NotImplementedError as exc:
        _write_parser_not_implemented(job, structure_type, str(exc))
        return 1
