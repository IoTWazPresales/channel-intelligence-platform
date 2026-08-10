# Plan (Phase 1d MTD delta parser):
# - Detect MTD measure column by header keywords or explicit field_mapping.
# - Prior-week MTD from staging via raw_product_token + customer_id (handler passes __customer_id__).
# - derived_units = current_mtd - prior; first upload in month uses is_mtd_estimate=True.
# - D1 parity (Batch 1c): unit_mac, raw_article_token, listing_external_id,
#   listing_marketplace, and site_label emitted when mapped; otherwise None.

from __future__ import annotations

import re
from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.imports.ai_import_resolver import suggest_column_mapping
from app.models.import_customer_sellthrough_staging import ImportCustomerSellthroughStagingLine
from app.models.ingestion import ImportJob
from app.services.imports.parsers.customer_sell_through_flat import (
    EXPECTED_COLUMNS_META_KEY,
    ParseResult,
    _build_alias_index,
    _extract_period,
    _normalize_text,
    _parse_decimal,
    _resolve_source_columns,
    _row_dict,
    _select_sheet_with_header,
)
from app.services.imports.parsers.customer_sell_through_period import month_start

_MTD_HEADER_RE = re.compile(r"\b(mtd|month\s*to\s*date|cumulative|ytd)\b", re.IGNORECASE)
_CUSTOMER_ID_META = "__customer_id__"


def _detect_mtd_column(columns: list[str], field_mapping: dict, expected_columns: dict) -> str | None:
    col_lower = {str(c).strip().lower(): str(c) for c in columns}
    for src, canon in field_mapping.items():
        if src == EXPECTED_COLUMNS_META_KEY:
            continue
        if canon in ("raw_mtd_units", "mtd_units", "units_sold") and src.strip().lower() in col_lower:
            if canon in ("raw_mtd_units", "mtd_units"):
                return col_lower[src.strip().lower()]

    meta = expected_columns.get("raw_mtd_units") or expected_columns.get("mtd_units")
    if isinstance(meta, dict):
        for alias in meta.get("aliases") or []:
            if isinstance(alias, str) and alias.strip().lower() in col_lower:
                return col_lower[alias.strip().lower()]

    for col in columns:
        if _MTD_HEADER_RE.search(str(col)):
            return str(col)

    numeric_candidates = [
        c
        for c in columns
        if c
        and not _MTD_HEADER_RE.search(str(c))
        and str(c).strip().lower() not in ("sku", "product", "site", "store")
    ]
    if len(numeric_candidates) == 1:
        return str(numeric_candidates[0])
    return None


def _lookup_prior_mtd(
    db: Session,
    *,
    customer_id: int,
    raw_product_token: str,
    month_start_date: date,
    current_period_start: date,
) -> tuple[float | None, date | None]:
    stmt = (
        select(
            ImportCustomerSellthroughStagingLine.raw_mtd_units,
            ImportCustomerSellthroughStagingLine.period_start_date,
        )
        .join(ImportJob, ImportJob.id == ImportCustomerSellthroughStagingLine.import_job_id)
        .where(ImportJob.template_slug == "customer_sell_through")
        # Validate-mode weekly cadence leaves stage=validated; apply uses loaded.
        .where(ImportJob.stage.in_(("validated", "loaded")))
        .where(ImportCustomerSellthroughStagingLine.resolved_customer_id == customer_id)
        .where(ImportCustomerSellthroughStagingLine.raw_product_token == raw_product_token)
        .where(ImportCustomerSellthroughStagingLine.period_start_date >= month_start_date)
        .where(ImportCustomerSellthroughStagingLine.period_start_date < current_period_start)
        .where(ImportCustomerSellthroughStagingLine.raw_mtd_units.is_not(None))
        .order_by(ImportCustomerSellthroughStagingLine.period_start_date.desc())
        .limit(1)
    )
    row = db.execute(stmt).first()
    if not row:
        return None, None
    prior_mtd, prior_date = row[0], row[1]
    try:
        return float(prior_mtd), prior_date
    except (TypeError, ValueError):
        return None, prior_date


def parse_mtd_delta_report(
    file_bytes: bytes,
    filename: str,
    field_mapping: dict,
    job_id: int,
    db: Session,
) -> ParseResult:
    fm = dict(field_mapping or {})
    expected_columns = fm.pop(EXPECTED_COLUMNS_META_KEY, None)
    if not isinstance(expected_columns, dict):
        expected_columns = {}

    customer_id_raw = fm.pop(_CUSTOMER_ID_META, None)
    customer_id: int | None = None
    if customer_id_raw is not None:
        try:
            customer_id = int(customer_id_raw)
        except (TypeError, ValueError):
            customer_id = None

    alias_index = _build_alias_index(fm, expected_columns)
    try:
        df, first_data_row = _select_sheet_with_header(file_bytes, filename, alias_index)
    except ValueError as exc:
        return ParseResult(error=str(exc))

    if df is None:
        return ParseResult(error="Could not detect header row")

    headers = [str(c) for c in df.columns]
    mtd_col = _detect_mtd_column(headers, fm, expected_columns)

    if mtd_col is None and get_settings().ai_assist_enabled:
        sample = [_row_dict(df.iloc[i]) for i in range(min(3, len(df)))]
        suggestion = suggest_column_mapping(
            headers=headers,
            sample_rows=sample,
            canonical_fields=["raw_mtd_units", "raw_product_token", "raw_location_token"],
            existing_mapping=fm,
        )
        if suggestion:
            for src, canon in suggestion.mappings.items():
                if canon in ("raw_mtd_units", "mtd_units") and src in headers:
                    mtd_col = src
                    break

    if mtd_col is None:
        return ParseResult(
            error=f"MTD units column could not be detected. Available columns: {headers}",
        )

    col_map = _resolve_source_columns(headers, fm, expected_columns)
    if col_map["raw_product_token"] is None:
        return ParseResult(
            error=f"Required product identifier could not be mapped. Available columns: {headers}",
        )

    warnings: list[str] = []
    period_start = _extract_period(
        filename=filename,
        period_col=col_map["raw_period_ref"],
        df=df,
        warnings=warnings,
    )
    if period_start is None:
        period_start = date.today()
        warnings.append("Using current week as reporting period for MTD delta file")

    m_start = month_start(period_start)
    rows: list[dict[str, Any]] = []

    for pos in range(len(df)):
        series = df.iloc[pos]
        product_tok = _normalize_text(series.get(col_map["raw_product_token"]))
        current_mtd = _parse_decimal(series.get(mtd_col))
        if not product_tok or current_mtd is None:
            continue

        derived = current_mtd
        is_estimate = True
        prior_mtd, _prior_date = (None, None)
        if customer_id is not None:
            prior_mtd, _prior_date = _lookup_prior_mtd(
                db,
                customer_id=customer_id,
                raw_product_token=product_tok,
                month_start_date=m_start,
                current_period_start=period_start,
            )

        if prior_mtd is not None:
            derived = current_mtd - prior_mtd
            is_estimate = False
            if derived < 0:
                derived = 0.0
                warnings.append(
                    f"Negative delta detected for product token {product_tok} — MTD may have reset. Storing as 0."
                )
        else:
            warnings.append(
                f"No prior week found for product token {product_tok} — storing MTD as weekly estimate"
            )

        loc_tok = None
        if col_map["raw_location_token"]:
            loc_tok = _normalize_text(series.get(col_map["raw_location_token"]))

        rows.append(
            {
                "import_job_id": int(job_id),
                "source_row_number": int((first_data_row or 2) + pos),
                "raw_row_payload": _row_dict(series),
                "raw_customer_token": None,
                "raw_location_token": loc_tok,
                "site_label": loc_tok,
                "raw_product_token": product_tok,
                "raw_period_ref": _normalize_text(series.get(col_map["raw_period_ref"]))
                if col_map["raw_period_ref"]
                else None,
                "period_start_date": period_start,
                "period_type": "weekly",
                "units_sold": derived,
                "raw_mtd_units": current_mtd,
                "is_mtd_estimate": is_estimate,
                "unit_sell_price": _parse_decimal(series.get(col_map["unit_sell_price"]))
                if col_map["unit_sell_price"]
                else None,
                "unit_cost": _parse_decimal(series.get(col_map["unit_cost"])) if col_map["unit_cost"] else None,
                "unit_mac": _parse_decimal(series.get(col_map["unit_mac"])) if col_map.get("unit_mac") else None,
                "reported_soh": _parse_decimal(series.get(col_map["reported_soh"]))
                if col_map["reported_soh"]
                else None,
                "raw_article_token": _normalize_text(series.get(col_map["raw_article_token"]))
                if col_map.get("raw_article_token")
                else None,
                "listing_external_id": _normalize_text(series.get(col_map["listing_external_id"]))
                if col_map.get("listing_external_id")
                else None,
                "listing_marketplace": _normalize_text(series.get(col_map["listing_marketplace"]))
                if col_map.get("listing_marketplace")
                else None,
                "resolution_status": "pending",
            }
        )

    return ParseResult(
        rows=rows,
        period_start_date=period_start,
        period_type="weekly",
        warnings=warnings,
    )
