"""Customer sales import: header discovery + field_mapping (mirrors shipment infer flow)."""

from __future__ import annotations

from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.ingestion import ImportJob, RawFileMetadata, SourceDefinition
from app.services.imports.pm_mapping_memory import MEMORY_SCHEMA_VERSION, load_by_header_norm, norm_header_key
from app.storage.local import get_storage_backend


def _effective_mapping_template(source: SourceDefinition | None) -> dict[str, Any]:
    """Same merge rules as ``pipeline.effective_mapping_template`` (kept local to avoid import cycles)."""
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
    return merged


CUSTOMER_SALES_CANONICAL_TARGETS: tuple[str, ...] = (
    "report_week",
    "report_year",
    "report_period",
    "transaction_date",
    "product_identifier",
    "quantity_sold",
    "quantity_returned",
    "selling_price",
    "cost_price",
    "currency_code",
    "store_code",
    "channel_type",
    "reported_soh",
)

CUSTOMER_SALES_FIELD_LABELS: dict[str, str] = {
    "report_week": "Report week",
    "report_year": "Report year",
    "report_period": "Report period",
    "transaction_date": "Transaction date",
    "product_identifier": "Product identifier",
    "quantity_sold": "Quantity sold",
    "quantity_returned": "Quantity returned",
    "selling_price": "Selling price",
    "cost_price": "Cost price",
    "currency_code": "Currency code",
    "store_code": "Store code",
    "channel_type": "Channel type",
    "reported_soh": "Reported SOH",
}

CUSTOMER_SALES_FIELD_TARGET_DESCRIPTIONS: dict[str, str] = {
    "report_week": (
        "Numeric week of year (1-53) from the retailer's reporting calendar. "
        "Used together with report_year for weekly aggregation."
    ),
    "report_year": (
        "Calendar or fiscal year matching the report_week. "
        "Required when report_week is mapped to form a complete week/year date key."
    ),
    "report_period": (
        "Combined period label (e.g. '2024-W12', '202412', 'Wk12 2024'). "
        "Used as an alternative to separate week + year columns."
    ),
    "transaction_date": (
        "Individual sale/transaction date. Provides day-level granularity "
        "as an alternative to week-based reporting."
    ),
    "product_identifier": (
        "Primary product key from the retailer file: article code, SKU, barcode (EAN/UPC/GTIN), "
        "or retailer-specific item number. Used for matching to dim_product."
    ),
    "quantity_sold": (
        "Units sold in the reporting period (positive = sales out to consumer). "
        "Core metric for sell-out analysis."
    ),
    "quantity_returned": (
        "Units returned by consumers in the reporting period. "
        "Tracked separately from sold quantity for net-sales calculation."
    ),
    "selling_price": (
        "Retail selling price per unit (RSP/RRP/ASP). "
        "Used for revenue estimation and price-point analysis."
    ),
    "cost_price": (
        "Cost/buy price per unit (DLP/landed cost). "
        "Used for margin analysis where available."
    ),
    "currency_code": "ISO currency code for monetary values in this row.",
    "store_code": (
        "Retailer store/branch/outlet identifier. "
        "Enables store-level sell-out analysis and regional aggregation."
    ),
    "channel_type": (
        "Sales channel classification (e.g. online, in-store, marketplace). "
        "Used for channel-mix reporting."
    ),
    "reported_soh": (
        "Stock-on-hand / closing inventory as reported by the retailer at period end. "
        "Used for availability and weeks-of-cover calculations."
    ),
}


def _norm_header(h: str) -> str:
    return (h or "").strip().lower()


def build_initial_customer_sales_field_mapping(
    headers: list[str], source: SourceDefinition | None, job: ImportJob | None = None
) -> dict[str, str]:
    """Map file header -> canonical customer sales field using saved source memory, template aliases, and heuristics."""
    template = _effective_mapping_template(source)
    aliases_norm: dict[str, str] = {}
    for canonical, meta in template.items():
        if canonical not in CUSTOMER_SALES_CANONICAL_TARGETS:
            continue
        if not isinstance(meta, dict):
            continue
        for a in meta.get("aliases", []) or []:
            if isinstance(a, str) and a.strip():
                aliases_norm[norm_header_key(a)] = canonical

    allowed_targets = set(CUSTOMER_SALES_CANONICAL_TARGETS)
    memory = load_by_header_norm(source) if source else {}
    mapping: dict[str, str] = {}

    # Pass 1: saved memory
    for col in headers:
        if not isinstance(col, str) or not col.strip():
            continue
        nh = norm_header_key(col)
        if nh:
            entry = memory.get(nh)
            if isinstance(entry, dict):
                tgt = entry.get("target")
                if tgt and str(tgt).strip() in allowed_targets:
                    mapping[col] = str(tgt).strip()

    # Pass 2: template aliases (normalized to handle underscores/spaces uniformly)
    for col in headers:
        if not isinstance(col, str) or not col.strip():
            continue
        if col in mapping:
            continue
        nk = norm_header_key(col)
        if nk in aliases_norm:
            mapping[col] = aliases_norm[nk]
            continue

        # Pass 3: header heuristics for SA retail patterns
        key = nk
        # Product identifiers
        if key in (
            "article", "article_code", "article_no", "article_number", "article_id",
            "sku", "sku_code", "product_code", "item_code", "item_no", "item_number",
            "part_number", "part_no", "pn", "barcode", "ean", "upc", "gtin",
            "retailer_sku", "retailer_code", "vendor_code", "vendor_sku",
            "product_id", "material", "material_code", "material_no",
        ):
            mapping[col] = "product_identifier"
        # Quantity sold patterns
        elif key in (
            "qty_sold", "units_sold", "qty", "quantity", "units", "sales_qty",
            "sell_qty", "sellout_qty", "sell_out_qty", "sold_qty", "sold_units",
            "total_qty", "total_units", "volume",
        ):
            mapping[col] = "quantity_sold"
        # Quantity returned patterns
        elif key in (
            "qty_returned", "returns", "return_qty", "returned_qty", "returned_units",
            "units_returned", "return_units", "rtn_qty",
        ):
            mapping[col] = "quantity_returned"
        # Selling price patterns
        elif key in (
            "selling_price", "sell_price", "retail_price", "unit_price", "price",
            "sales_price", "rsp", "rrp", "srp", "asp", "avg_selling_price",
            "average_selling_price", "unit_sell_price",
        ):
            mapping[col] = "selling_price"
        # Cost price patterns
        elif key in (
            "cost_price", "cost", "unit_cost", "cogs", "cost_of_goods",
            "buy_price", "purchase_price", "landed_cost", "dlp",
        ):
            mapping[col] = "cost_price"
        # Week patterns
        elif key in ("week", "wk", "week_no", "week_number", "week_num", "reporting_week", "sales_week", "wk_no"):
            mapping[col] = "report_week"
        # Year patterns
        elif key in ("year", "yr", "reporting_year", "sales_year", "fiscal_year"):
            mapping[col] = "report_year"
        # Period patterns
        elif key in ("period", "reporting_period", "sales_period", "week_period", "date_period", "wk_yr", "week_year"):
            mapping[col] = "report_period"
        # Transaction date patterns
        elif key in ("date", "transaction_date", "sale_date", "sales_date", "trans_date", "sold_date", "order_date"):
            mapping[col] = "transaction_date"
        # Store patterns
        elif key in (
            "store", "store_code", "store_id", "store_no", "store_number",
            "branch", "branch_code", "branch_no", "branch_id",
            "outlet", "outlet_code", "location", "location_code", "site", "site_code",
        ):
            mapping[col] = "store_code"
        # Channel patterns
        elif key in (
            "channel", "channel_type", "sales_channel", "channel_code",
            "online_offline", "store_type", "fulfilment_channel",
        ):
            mapping[col] = "channel_type"
        # Currency
        elif key in ("currency", "currency_code", "curr", "ccy"):
            mapping[col] = "currency_code"
        # SOH patterns
        elif key in (
            "soh", "stock_on_hand", "on_hand", "oh", "closing_stock",
            "ending_stock", "ending_inventory", "stock_balance",
            "inventory_on_hand", "available_stock", "closing_soh",
        ):
            mapping[col] = "reported_soh"

    return mapping


def sanitize_customer_sales_field_mapping(
    mapping: dict[str, Any], headers: list[str]
) -> tuple[dict[str, str], list[dict[str, str]]]:
    """Drop unknown headers / targets; return (clean_mapping, notices)."""
    notices: list[dict[str, str]] = []
    header_set = {h for h in headers if isinstance(h, str) and h.strip()}
    allowed = set(CUSTOMER_SALES_CANONICAL_TARGETS)
    out: dict[str, str] = {}
    for k, v in mapping.items():
        if not isinstance(k, str) or k not in header_set:
            continue
        if not isinstance(v, str) or not v.strip():
            continue
        tgt = v.strip()
        if tgt not in allowed:
            notices.append({
                "code": "unknown_customer_sales_target",
                "message": f"Ignored unknown target {tgt!r} for column {k!r}.",
            })
            continue
        out[k] = tgt
    return out, notices


def customer_sales_mapping_gate_errors(mapping: dict[str, str]) -> list[dict[str, str]]:
    """Blocking issues before running customer sales validation."""
    inv = set(mapping.values())
    errs: list[dict[str, str]] = []

    if "product_identifier" not in inv:
        errs.append({
            "code": "missing_product_identifier",
            "message": "Map a product identifier column (article, SKU, barcode, etc.).",
        })

    if "quantity_sold" not in inv:
        errs.append({
            "code": "missing_quantity_sold",
            "message": "Map at least one quantity sold column.",
        })

    has_week_year = "report_week" in inv and "report_year" in inv
    has_period = "report_period" in inv
    has_date = "transaction_date" in inv
    if not (has_week_year or has_period or has_date):
        errs.append({
            "code": "missing_date_resolution",
            "message": (
                "Map at least one date resolution: "
                "report_week + report_year, report_period, or transaction_date."
            ),
        })

    return errs


def _union_frame_headers(frames: list[tuple[Any, Any, str, str]]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for _sn, frame, _rt, _ls in frames:
        if frame is None or not len(frame.columns):
            continue
        for c in frame.columns:
            s = str(c).strip() if c is not None else ""
            if not s or s in seen:
                continue
            seen.add(s)
            out.append(s)
    return out


def _load_frames_for_customer_sales(
    job: ImportJob, data: bytes
) -> list[tuple[str, pd.DataFrame | None, str, str]]:
    """Load raw file data into frames (simplified single-sheet handling for CSV/XLSX)."""
    import io

    file_name = (job.file_name or "").lower()
    frames: list[tuple[str, pd.DataFrame | None, str, str]] = []

    try:
        if file_name.endswith(".xlsx") or file_name.endswith(".xls"):
            xls = pd.ExcelFile(io.BytesIO(data))
            for sheet_name in xls.sheet_names:
                df = pd.read_excel(xls, sheet_name=sheet_name, dtype=str, nrows=500)
                frames.append((sheet_name, df, "customer_sales", "raw"))
        else:
            df = pd.read_csv(io.BytesIO(data), dtype=str, nrows=500)
            frames.append(("Sheet1", df, "customer_sales", "raw"))
    except Exception:
        frames.append(("Sheet1", None, "customer_sales", "error"))

    return frames


def infer_customer_sales_import_job_sync(db: Session, job: ImportJob) -> ImportJob:
    """Read stored raw file, infer headers, set initial field_mapping, set stage to customer_sales_mapping_ready."""
    if not job or (job.template_slug or "") != "customer_sales":
        raise ValueError("infer_customer_sales_import_job_sync requires a customer_sales import job")

    raw = db.scalars(select(RawFileMetadata).where(RawFileMetadata.job_id == job.id)).first()
    if not raw:
        raise ValueError("infer_customer_sales_import_job_sync requires raw file metadata")

    storage = get_storage_backend()
    data = storage.read(raw.storage_key)

    frames = _load_frames_for_customer_sales(job, data)
    headers = _union_frame_headers(frames)
    mapping = build_initial_customer_sales_field_mapping(headers, job.source, job)
    mapping, notices = sanitize_customer_sales_field_mapping(mapping, headers)

    meta_reports: list[dict[str, Any]] = []
    for sn, frame, rt, ls in frames:
        meta_reports.append({
            "sheet": sn,
            "columns": [str(c) for c in (frame.columns if frame is not None else [])],
            "report_type": rt,
            "line_state": ls,
            "row_count": int(len(frame)) if frame is not None else 0,
        })

    inferred: dict[str, Any] = {
        "kind": "customer_sales",
        "sheets": meta_reports,
        "mapping_notices": notices,
    }

    job.file_headers = headers
    job.field_mapping = mapping
    job.inferred_schema = inferred
    job.stage = "customer_sales_mapping_ready"
    job.status = "pending"
    job.error_summary = None
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def customer_sales_mapping_state_dict(
    job: ImportJob, headers: list[str] | None = None, source: SourceDefinition | None = None
) -> dict[str, Any]:
    """UI/API snapshot of current customer sales mapping state."""
    hdrs = list(headers or job.file_headers or [])
    raw_mapping = dict(job.field_mapping or {})
    mapping, notices = sanitize_customer_sales_field_mapping(raw_mapping, hdrs)
    gate = customer_sales_mapping_gate_errors(mapping)

    return {
        "id": job.id,
        "stage": job.stage,
        "status": job.status,
        "error_summary": job.error_summary,
        "file_headers": hdrs,
        "field_mapping": mapping,
        "canonical_targets": list(CUSTOMER_SALES_CANONICAL_TARGETS),
        "field_labels": dict(CUSTOMER_SALES_FIELD_LABELS),
        "blocking_mapping_errors": gate,
        "mapping_valid": len(gate) == 0,
        "mapping_adjustment_notices": notices,
        "field_target_descriptions": dict(CUSTOMER_SALES_FIELD_TARGET_DESCRIPTIONS),
    }


def merge_customer_sales_mapping_memory(
    source: SourceDefinition, confirmed_mapping: dict[str, str]
) -> None:
    """Persist confirmed customer sales column → canonical mappings on the source (by normalized header)."""
    allowed = set(CUSTOMER_SALES_CANONICAL_TARGETS)
    root: dict[str, Any] = dict(source.column_mapping_memory or {})
    bh: dict[str, Any] = dict(root.get("by_header_norm") or {})

    for header, tgt in confirmed_mapping.items():
        nh = norm_header_key(str(header))
        if not nh:
            continue
        if tgt not in allowed:
            continue
        prev = bh.get(nh) if isinstance(bh.get(nh), dict) else {}
        bh[nh] = {
            "target": tgt,
            "confirmations": int(prev.get("confirmations", 0)) + 1,
        }

    root["by_header_norm"] = bh
    root["schema_version"] = root.get("schema_version") or MEMORY_SCHEMA_VERSION
    root["customer_sales_mapping"] = True
    source.column_mapping_memory = root
