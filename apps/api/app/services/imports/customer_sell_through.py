"""Customer sell-through import pipeline (Phase 0 skeleton — parsers in Phase 1)."""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy import delete, func, select, update
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
from app.services.imports.product_resolution_standard import resolve_product_id_single_match
from app.services.imports.cst_d1 import (
    apply_listing_seed_fields,
    corroborate_period,
    feed_profile_vat_basis,
    mark_cst_report_slot_received,
    propose_customer_article_alias,
    resolve_customer_article_alias,
    upsert_cst_listing_seed,
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

_SITE_LABEL_KEY_RE = re.compile(r"[^A-Z0-9]+")


def _source_key_site_part(
    *,
    customer_location_id: int | None,
    site_label: str | None,
) -> str:
    """Store grain: mapped location id, else verbatim site_label, else chain-level 0.

    Unmapped Game (and similar) site codes must not share loc=0 — that last-write-wins
    the week down to one store. FLAG ≠ BLOCK: we do not auto-create customer_location.
    """
    if customer_location_id is not None:
        return str(int(customer_location_id))
    raw = str(site_label or "").strip()
    if not raw:
        return "0"
    norm = _SITE_LABEL_KEY_RE.sub("_", raw.upper()).strip("_")
    if not norm:
        return "0"
    if len(norm) > 80:
        digest = hashlib.sha1(norm.encode("utf-8")).hexdigest()[:12]
        return f"sl:{digest}"
    return f"sl:{norm}"


def customer_sellthrough_source_key(
    *,
    customer_id: int,
    customer_location_id: int | None,
    product_id: int,
    period_start_date: date,
    site_label: str | None = None,
) -> str:
    """Natural upsert key: ``ct:{customer}:{loc|sl:SITE|0}:{product}:{period}``.

    Siteless reports (Amazon ASIN) stay ``…:0:…``. Site-named reports (Game G007)
    persist one fact per site×product×week without requiring a location master.
    """
    loc_part = _source_key_site_part(
        customer_location_id=customer_location_id,
        site_label=site_label,
    )
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
    from app.services.merge_redirect import follow_customer_merge_redirect_sync

    meta = job.staged_metadata if isinstance(job.staged_metadata, dict) else {}
    raw = meta.get("customer_id")
    if raw is not None:
        try:
            return follow_customer_merge_redirect_sync(db, int(raw))
        except (TypeError, ValueError):
            pass

    source = job.source
    if source and isinstance(source.expected_template, dict):
        cid = source.expected_template.get("customer_id")
        if cid is not None:
            try:
                return follow_customer_merge_redirect_sync(db, int(cid))
            except (TypeError, ValueError):
                pass

    if source and source.code:
        found = db.scalar(select(DimCustomer.id).where(DimCustomer.code == source.code.strip()))
        if found is not None:
            return follow_customer_merge_redirect_sync(db, int(found))

    return None


# Extra product identifiers often present beside the mapped primary column.
# Order is preference among *tokens* (each token still runs full PM single-match tiers).
# Sales-model / SKU before barcode so feeds without EAN (and polluted EAN masters) still resolve.
_CST_PAYLOAD_PRODUCT_HEADER_PREFERENCE: tuple[str, ...] = (
    "supplier code",
    "sales model name",
    "sales model",
    "sales_model_name",
    "sku",
    "item code",
    "item_code",
    "product code",
    "product_code",
    "article",
    "model name",
    "model_name",
    "barcode",
    "ean",
    "upc",
)


def collect_cst_product_lookup_tokens(
    *,
    primary: str | None,
    article_token: str | None = None,
    raw_row_payload: dict[str, Any] | None = None,
) -> list[str]:
    """Deduped product lookup tokens for one CST line (primary + article + payload IDs).

    Not every retailer ships barcodes — payload may only have sales model / SKU / article.
    """
    ordered: list[str] = []
    seen: set[str] = set()

    def _add(raw: Any) -> None:
        if raw is None:
            return
        text = str(raw).strip()
        if not text or text.lower() == "nan":
            return
        key = _product_token_key(text)
        if not key or key in seen:
            return
        seen.add(key)
        ordered.append(text)

    _add(primary)
    _add(article_token)

    if isinstance(raw_row_payload, dict) and raw_row_payload:
        by_fold: dict[str, Any] = {}
        for hdr, val in raw_row_payload.items():
            fold = str(hdr).strip().lower().replace("_", " ")
            if fold and fold not in by_fold:
                by_fold[fold] = val
        for pref in _CST_PAYLOAD_PRODUCT_HEADER_PREFERENCE:
            fold = pref.replace("_", " ")
            if fold in by_fold:
                _add(by_fold[fold])
            underscored = pref.replace(" ", "_")
            if underscored in raw_row_payload:
                _add(raw_row_payload[underscored])

    return ordered


def resolve_product_id_for_sellthrough(
    idx: ProductResolutionIndex,
    token: str | None,
    *,
    session: Session | None = None,
    customer_id: int | None = None,
    article_token: str | None = None,
    raw_row_payload: dict[str, Any] | None = None,
    as_of: date | None = None,
) -> int | None:
    """PM single-match tiers on each candidate token, then customer_article_alias (confirmed only).

    Candidate tokens = mapped primary + article + common payload product columns
    (supplier code / sales model / sku / barcode / …). First single-match wins.
    Article alias resolve is as-of ``period_start_date`` when provided.
    """
    tokens = collect_cst_product_lookup_tokens(
        primary=token,
        article_token=article_token,
        raw_row_payload=raw_row_payload,
    )
    for candidate in tokens:
        pid = resolve_product_id_single_match(idx, candidate)
        if pid is not None:
            return pid
    if session is not None and customer_id is not None:
        for candidate in tokens:
            alias_pid = resolve_customer_article_alias(
                session,
                customer_id=customer_id,
                article_token=candidate,
                as_of=as_of,
            )
            if alias_pid is not None:
                return alias_pid
    return None


def _steward_resolved_product_id(
    resolved_products: dict[str, int],
    *,
    primary: str | None,
    article_token: str | None = None,
    raw_row_payload: dict[str, Any] | None = None,
) -> int | None:
    for candidate in collect_cst_product_lookup_tokens(
        primary=primary,
        article_token=article_token,
        raw_row_payload=raw_row_payload,
    ):
        key = _product_token_key(candidate)
        if key and key in resolved_products:
            return int(resolved_products[key])
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
    from app.services.imports.parsers.customer_sell_through_flat import normalize_cst_expected_columns

    expected = effective_mapping_template(job.source) if job.source else {}
    if template and template.expected_columns:
        for k, v in template.expected_columns.items():
            if isinstance(v, dict):
                expected.setdefault(k, {"aliases": list(v.get("aliases", []))})

    parse_mapping = dict(mapping or {})
    parse_mapping[EXPECTED_COLUMNS_META_KEY] = normalize_cst_expected_columns(expected)
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


def _list_job_raw_files(db: Session, job: ImportJob) -> list[RawFileMetadata]:
    from app.services.imports.cst_batch import list_raw_files_for_job

    return list_raw_files_for_job(db, int(job.id))


def _raw_display_name(raw: RawFileMetadata) -> str:
    from app.services.imports.dsi_workbook import raw_file_display_name

    return raw_file_display_name(raw.storage_key)


def _load_job_file_bytes(db: Session, job: ImportJob) -> tuple[bytes | None, str | None]:
    raws = _list_job_raw_files(db, job)
    if not raws:
        return None, "No raw file metadata for this import job."
    storage = get_storage_backend()
    return storage.read(raws[0].storage_key), None


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
    on_progress: Any = None,
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

    from app.services.imports.cst_mapping_candidates import (
        load_resolved_cst_candidates,
        upsert_cst_mapping_candidates,
    )

    resolved_products, resolved_locations = load_resolved_cst_candidates(db, job.id)
    prod_idx = _load_product_resolution_index(db)
    cfg = db.scalar(select(CustomerReportConfig).where(CustomerReportConfig.customer_id == customer_id))
    vat_basis = feed_profile_vat_basis(cfg)
    feed_profile = cfg.feed_profile_json if cfg and isinstance(cfg.feed_profile_json, dict) else None
    resolved_n = 0
    unresolved_n = 0
    ai_assist_used = [False]
    total_rows = len(result.rows or [])
    if on_progress is not None:
        on_progress("resolving_tokens", "Resolving CST tokens", 0, total_rows or 1)

    for idx, row in enumerate(result.rows):
        if isinstance(row, dict):
            apply_listing_seed_fields(row, feed_profile)
        line = ImportCustomerSellthroughStagingLine(**row)
        line.resolved_customer_id = customer_id
        # D1: site_label first-class (verbatim); siteless reports stay NULL.
        if not getattr(line, "site_label", None) and line.raw_location_token:
            line.site_label = str(line.raw_location_token).strip() or None
        if not getattr(line, "vat_basis", None):
            line.vat_basis = vat_basis

        article_tok = getattr(line, "raw_article_token", None)
        payload = line.raw_row_payload if isinstance(line.raw_row_payload, dict) else None
        if line.raw_product_token or payload:
            pid = resolve_product_id_for_sellthrough(
                prod_idx,
                line.raw_product_token,
                session=db,
                customer_id=customer_id,
                article_token=article_tok,
                raw_row_payload=payload,
                as_of=getattr(line, "period_start_date", None),
            )
            if pid is not None:
                line.resolved_product_id = pid

        product_ok, location_ok = _apply_ai_resolution_to_line(
            db,
            line=line,
            customer_id=customer_id,
            prod_idx=prod_idx,
            ai_assist_used=ai_assist_used,
        )

        if not product_ok and (line.raw_product_token or payload):
            pid = resolve_product_id_for_sellthrough(
                prod_idx,
                line.raw_product_token,
                session=db,
                customer_id=customer_id,
                article_token=article_tok,
                raw_row_payload=payload,
                as_of=getattr(line, "period_start_date", None),
            )
            if pid is not None:
                line.resolved_product_id = pid
                product_ok = True

        # Candidate resolution fallback (steward-resolved tokens from a prior validate pass)
        if not product_ok:
            pid = _steward_resolved_product_id(
                resolved_products,
                primary=line.raw_product_token,
                article_token=article_tok,
                raw_row_payload=payload,
            )
            if pid is not None:
                line.resolved_product_id = pid
                product_ok = True
        if not location_ok and line.raw_location_token:
            loc_key = (line.raw_location_token or "").strip().lower()
            if loc_key and loc_key in resolved_locations:
                line.resolved_location_id = resolved_locations[loc_key]
                location_ok = True

        # FLAG ≠ BLOCK for unmapped sites: product alone is enough to resolve for apply.
        # Unmapped location stays on worklist via cst_location_token; site_label still carried.
        if product_ok and line.resolution_status in ("pending", "unresolved", "ai_auto_resolved"):
            line.resolution_status = "resolved"

        if product_ok:
            if line.resolution_status == "resolved":
                resolved_n += 1
            else:
                unresolved_n += 1
            # Learn article alias on co-occurrence (proposed only — steward confirms later).
            if article_tok and line.resolved_product_id is not None:
                propose_customer_article_alias(
                    db,
                    customer_id=customer_id,
                    article_token=article_tok,
                    product_id=int(line.resolved_product_id),
                    evidence={
                        "co_occurred_with": line.raw_product_token,
                        "import_job_id": job.id,
                    },
                )
        else:
            if line.resolution_status == "pending":
                line.resolution_status = "unresolved"
            unresolved_n += 1

        # Listing seed side-channel (LC-U1) — emit whenever marketplace+external_id present.
        upsert_cst_listing_seed(
            db,
            customer_id=customer_id,
            marketplace=getattr(line, "listing_marketplace", None),
            external_id=getattr(line, "listing_external_id", None),
            product_id=int(line.resolved_product_id) if line.resolved_product_id else None,
            import_job_id=job.id,
            raw=line.raw_row_payload if isinstance(line.raw_row_payload, dict) else None,
        )

        db.add(line)
        if on_progress is not None and total_rows and ((idx + 1) % 50 == 0 or (idx + 1) == total_rows):
            on_progress("resolving_tokens", "Resolving CST tokens", idx + 1, total_rows)

    db.flush()
    if on_progress is not None:
        on_progress("building_candidates", "Building CST mapping candidates", total_rows or 1, total_rows or 1)
    upsert_cst_mapping_candidates(db, job.id)

    warnings = list(result.warnings or [])
    if drift_warnings:
        warnings = drift_warnings + warnings

    # Period: steward-declared (staged_metadata) + file-corroborated.
    meta = dict(job.staged_metadata or {}) if isinstance(job.staged_metadata, dict) else {}
    steward_period = None
    raw_declared = meta.get("declared_period_start") or meta.get("steward_period_start")
    if isinstance(raw_declared, str) and raw_declared.strip():
        try:
            steward_period = date.fromisoformat(raw_declared.strip()[:10])
        except ValueError:
            warnings.append(f"invalid declared_period_start={raw_declared!r}")
    period_report = corroborate_period(
        steward_declared=steward_period,
        file_inferred=result.period_start_date,
        filename=getattr(job, "original_filename", None),
    )
    if period_report["flags"]:
        warnings.extend(period_report["flags"])
    if period_report["period_start_date"] is not None:
        # Prefer corroborated/steward choice for config last_report_received.
        effective_period = period_report["period_start_date"]
    else:
        effective_period = result.period_start_date

    # Stamp steward/corroborated period onto staging lines.
    # Preserve pivoted / wide-week multi-period dates; overwrite single-period
    # file_inferred (week-only filenames use date.today().year) when steward wins.
    if effective_period is not None:
        distinct_periods = db.scalar(
            select(func.count(func.distinct(ImportCustomerSellthroughStagingLine.period_start_date))).where(
                ImportCustomerSellthroughStagingLine.import_job_id == job.id,
                ImportCustomerSellthroughStagingLine.period_start_date.is_not(None),
            )
        )
        if distinct_periods is None or int(distinct_periods) <= 1:
            db.execute(
                update(ImportCustomerSellthroughStagingLine)
                .where(ImportCustomerSellthroughStagingLine.import_job_id == job.id)
                .values(period_start_date=effective_period)
            )
        else:
            db.execute(
                update(ImportCustomerSellthroughStagingLine)
                .where(
                    ImportCustomerSellthroughStagingLine.import_job_id == job.id,
                    ImportCustomerSellthroughStagingLine.period_start_date.is_(None),
                )
                .values(period_start_date=effective_period)
            )
        db.flush()

    summary: dict[str, Any] = {
        "period_start_date": str(effective_period) if effective_period else None,
        "period_corroboration": to_jsonable(period_report),
        "total_rows": len(result.rows),
        "resolved": resolved_n,
        "unresolved": unresolved_n,
        "warnings": warnings,
        "vat_basis": vat_basis,
    }
    if ai_assist_used[0]:
        summary["ai_assist_used"] = True
    meta[summary_key] = to_jsonable(summary)
    job.staged_metadata = to_jsonable(meta)

    _upsert_customer_report_config(
        db,
        customer_id=customer_id,
        period_start_date=effective_period,
        report_structure_type=structure_type,
    )
    mark_cst_report_slot_received(
        db,
        customer_id=customer_id,
        period_start_date=effective_period,
        import_job_id=job.id,
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
    on_progress: Any = None,
) -> int:
    customer_id = resolve_customer_id_for_job(db, job)
    if customer_id is None:
        _write_parse_failed(
            job,
            "Could not resolve customer_id for this import job (set staged_metadata.customer_id or source customer).",
        )
        return 1

    if on_progress is not None:
        on_progress("parsing", f"Parsing CST ({structure_type})", 0, 1)

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
        on_progress=on_progress,
    )


def _handle_flat(
    db: Session,
    job: ImportJob,
    df: pd.DataFrame,
    mapping: dict[str, str],
    template: ImportTemplate | None,
    on_progress: Any = None,
) -> int:
    del df  # flat parser reads raw bytes (multi-sheet / header detection)

    customer_id = resolve_customer_id_for_job(db, job)
    if customer_id is None:
        _write_parse_failed(
            job,
            "Could not resolve customer_id for this import job (set staged_metadata.customer_id or source customer).",
        )
        return 1

    if on_progress is not None:
        on_progress("parsing", "Parsing CST flat report(s)", 0, 1)

    raws = _list_job_raw_files(db, job)
    if not raws:
        _write_parse_failed(job, "No raw file metadata for this import job.")
        return 1

    from app.services.imports.cst_batch import get_cst_excluded_filenames, get_cst_file_period_stamps

    excluded = get_cst_excluded_filenames(job)
    period_stamps = get_cst_file_period_stamps(job)
    storage = get_storage_backend()
    parse_mapping, _ = _build_parse_mapping(db, job, mapping, template)
    cfg = db.scalar(select(CustomerReportConfig).where(CustomerReportConfig.customer_id == customer_id))
    feed_profile = cfg.feed_profile_json if cfg and isinstance(cfg.feed_profile_json, dict) else None
    vat_basis = feed_profile_vat_basis(cfg)

    # Job-level steward declare (fallback when a file has no inference).
    meta = dict(job.staged_metadata or {}) if isinstance(job.staged_metadata, dict) else {}
    job_steward_period: date | None = None
    raw_declared = meta.get("declared_period_start") or meta.get("steward_period_start")
    if isinstance(raw_declared, str) and raw_declared.strip():
        try:
            job_steward_period = date.fromisoformat(raw_declared.strip()[:10])
        except ValueError:
            pass

    db.execute(
        delete(ImportCustomerSellthroughStagingLine).where(
            ImportCustomerSellthroughStagingLine.import_job_id == job.id
        )
    )
    db.flush()

    from app.services.imports.cst_mapping_candidates import (
        load_resolved_cst_candidates,
        upsert_cst_mapping_candidates,
    )

    resolved_products, resolved_locations = load_resolved_cst_candidates(db, job.id)
    prod_idx = _load_product_resolution_index(db)
    resolved_n = 0
    unresolved_n = 0
    all_warnings: list[str] = []
    file_period_reports: list[dict[str, Any]] = []
    total_rows = 0
    periods_marked: set[date] = set()
    parse_errors: list[str] = []

    for file_idx, raw in enumerate(raws):
        fname = _raw_display_name(raw)
        if fname in excluded:
            file_period_reports.append(
                {
                    "filename": fname,
                    "excluded": True,
                    "period_start_date": None,
                    "flags": ["excluded"],
                }
            )
            continue

        file_bytes = storage.read(raw.storage_key)
        result = parse_flat_report(
            file_bytes,
            fname,
            parse_mapping,
            int(job.id),
            feed_profile=feed_profile,
        )
        if result.error:
            parse_errors.append(f"{fname}: {result.error}")
            file_period_reports.append(
                {
                    "filename": fname,
                    "excluded": False,
                    "period_start_date": None,
                    "flags": ["parse_error"],
                    "error": result.error,
                }
            )
            continue

        drift_warnings = _format_drift_warnings(job, _sniff_file_headers(file_bytes, fname))
        if drift_warnings:
            all_warnings.extend(f"{fname}: {w}" for w in drift_warnings)
        if result.warnings:
            all_warnings.extend(f"{fname}: {w}" for w in result.warnings)

        # Per-file steward stamp wins over job-level declare for corroboration.
        steward_period = job_steward_period
        stamp_raw = period_stamps.get(fname)
        if stamp_raw:
            try:
                steward_period = date.fromisoformat(stamp_raw[:10])
            except ValueError:
                all_warnings.append(f"{fname}: invalid cst_file_period_stamps={stamp_raw!r}")

        period_report = corroborate_period(
            steward_declared=steward_period,
            file_inferred=result.period_start_date,
            filename=fname,
        )
        effective_period = period_report["period_start_date"] or result.period_start_date
        if period_report["flags"]:
            all_warnings.extend(f"{fname}: {f}" for f in period_report["flags"])

        file_period_reports.append(
            {
                "filename": fname,
                "excluded": False,
                "period_start_date": str(effective_period) if effective_period else None,
                "file_inferred": (
                    result.period_start_date.isoformat() if result.period_start_date else None
                ),
                "source": period_report.get("source"),
                "flags": list(period_report.get("flags") or []),
            }
        )

        # Wide-week unpivot emits multiple period dates — keep them. Single-period
        # files often guess week year via date.today(); steward/corroborated wins.
        row_periods = {
            r.get("period_start_date")
            for r in result.rows
            if r.get("period_start_date") is not None
        }
        is_wide_week = len(row_periods) >= 2

        for row in result.rows:
            # Keep source_row_number unique across files in one job.
            row["source_row_number"] = int(file_idx) * 1_000_000 + int(row["source_row_number"])
            payload = dict(row.get("raw_row_payload") or {})
            payload["_cst_source_file"] = fname
            row["raw_row_payload"] = payload
            if effective_period is not None:
                if is_wide_week:
                    if row.get("period_start_date") is None:
                        row["period_start_date"] = effective_period
                else:
                    row["period_start_date"] = effective_period
            apply_listing_seed_fields(row, feed_profile)

            line = ImportCustomerSellthroughStagingLine(**row)
            line.resolved_customer_id = customer_id
            if not getattr(line, "site_label", None) and line.raw_location_token:
                line.site_label = str(line.raw_location_token).strip() or None
            if not getattr(line, "vat_basis", None):
                line.vat_basis = vat_basis

            product_ok = False
            article_tok = getattr(line, "raw_article_token", None)
            payload_dict = line.raw_row_payload if isinstance(line.raw_row_payload, dict) else None
            if line.raw_product_token or payload_dict:
                pid = resolve_product_id_for_sellthrough(
                    prod_idx,
                    line.raw_product_token,
                    session=db,
                    customer_id=customer_id,
                    article_token=article_tok,
                    raw_row_payload=payload_dict,
                    as_of=getattr(line, "period_start_date", None),
                )
                if pid is None:
                    pid = _steward_resolved_product_id(
                        resolved_products,
                        primary=line.raw_product_token,
                        article_token=article_tok,
                        raw_row_payload=payload_dict,
                    )
                if pid is not None:
                    line.resolved_product_id = pid
                    product_ok = True

            if line.raw_location_token:
                loc_id = db.scalar(
                    select(CustomerLocation.id).where(
                        CustomerLocation.customer_id == customer_id,
                        CustomerLocation.location_code == line.raw_location_token,
                    )
                )
                if loc_id is None:
                    loc_key = (line.raw_location_token or "").strip().lower()
                    loc_id = resolved_locations.get(loc_key)
                if loc_id is not None:
                    line.resolved_location_id = int(loc_id)

            if product_ok:
                line.resolution_status = "resolved"
                resolved_n += 1
                if article_tok and line.resolved_product_id is not None:
                    propose_customer_article_alias(
                        db,
                        customer_id=customer_id,
                        article_token=article_tok,
                        product_id=int(line.resolved_product_id),
                        evidence={"co_occurred_with": line.raw_product_token, "import_job_id": job.id},
                    )
            else:
                line.resolution_status = "unresolved"
                unresolved_n += 1

            # Listing seed side-channel even when product unresolved (proposed, product_id null).
            upsert_cst_listing_seed(
                db,
                customer_id=customer_id,
                marketplace=getattr(line, "listing_marketplace", None),
                external_id=getattr(line, "listing_external_id", None),
                product_id=int(line.resolved_product_id) if line.resolved_product_id else None,
                import_job_id=job.id,
                raw=line.raw_row_payload if isinstance(line.raw_row_payload, dict) else None,
            )

            db.add(line)
            total_rows += 1
            if on_progress is not None and total_rows % 50 == 0:
                on_progress("resolving_tokens", "Resolving CST tokens", total_rows, max(total_rows, 1))

        if effective_period is not None and effective_period not in periods_marked:
            mark_cst_report_slot_received(
                db,
                customer_id=customer_id,
                period_start_date=effective_period,
                import_job_id=job.id,
            )
            periods_marked.add(effective_period)

    if parse_errors and total_rows == 0:
        _write_parse_failed(job, "; ".join(parse_errors))
        return 1

    db.flush()
    upsert_cst_mapping_candidates(db, job.id)

    # Primary period for config last_report = latest file period (or sole).
    primary_period: date | None = None
    dated = [date.fromisoformat(r["period_start_date"]) for r in file_period_reports if r.get("period_start_date")]
    if dated:
        primary_period = max(dated)

    meta = dict(job.staged_metadata or {}) if isinstance(job.staged_metadata, dict) else {}
    meta.pop("customer_sellthrough_error", None)
    meta["customer_sellthrough_flat"] = to_jsonable(
        {
            "period_start_date": str(primary_period) if primary_period else None,
            "total_rows": total_rows,
            "resolved": resolved_n,
            "unresolved": unresolved_n,
            "warnings": all_warnings + ([f"file_errors: {parse_errors}"] if parse_errors else []),
            "vat_basis": vat_basis,
            "file_count": len(raws),
        }
    )
    meta["cst_file_periods"] = to_jsonable(file_period_reports)
    meta["cst_multi_file"] = len(raws) > 1
    job.staged_metadata = to_jsonable(meta)
    # Drop stale parse-failed banner from a prior attempt once rows staged.
    if total_rows > 0:
        job.error_summary = None

    _upsert_customer_report_config(
        db,
        customer_id=customer_id,
        period_start_date=primary_period,
        report_structure_type=STRUCTURE_FLAT,
    )

    if (job.import_mode or "").strip().lower() == "apply":
        from app.services.imports.customer_sell_through_apply import apply_customer_sellthrough_staging

        apply_customer_sellthrough_staging(db, job.id)

    return 0 if total_rows else 0


def _handle_pivoted(
    db: Session,
    job: ImportJob,
    df: pd.DataFrame,
    mapping: dict[str, str],
    template: ImportTemplate | None,
    on_progress: Any = None,
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
        on_progress=on_progress,
    )


def _handle_multi_sheet(
    db: Session,
    job: ImportJob,
    df: pd.DataFrame,
    mapping: dict[str, str],
    template: ImportTemplate | None,
    on_progress: Any = None,
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
        on_progress=on_progress,
    )


def _handle_mtd_delta(
    db: Session,
    job: ImportJob,
    df: pd.DataFrame,
    mapping: dict[str, str],
    template: ImportTemplate | None,
    on_progress: Any = None,
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
        on_progress=on_progress,
    )


def _handle_wide_extract(
    db: Session,
    job: ImportJob,
    df: pd.DataFrame,
    mapping: dict[str, str],
    template: ImportTemplate | None,
    on_progress: Any = None,
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
        on_progress=on_progress,
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
    on_progress: Any = None,
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
        return handler(db, job, df, mapping, template, on_progress=on_progress)
    except NotImplementedError as exc:
        _write_parser_not_implemented(job, structure_type, str(exc))
        return 1
