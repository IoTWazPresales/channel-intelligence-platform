# Plan (Phase 1c multi-sheet parser):
# - Data sheets detected by period-like sheet names OR header alias match (not retailer names).
# - Summary/index sheets excluded via generic keyword list.
# - Per-sheet flat row parsing with period from sheet name; dedupe keeps latest period wins.
# - D1 parity (Batch 1c): unit_mac, raw_article_token, listing_external_id,
#   listing_marketplace, and site_label emitted per sheet row when mapped; otherwise None.

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from app.core.config import get_settings
from app.services.imports.ai_import_resolver import suggest_column_mapping
from app.services.imports.parsers.customer_sell_through_flat import (
    EXPECTED_COLUMNS_META_KEY,
    ParseResult,
    _build_alias_index,
    _detect_header_row,
    _normalize_text,
    _parse_decimal,
    _parse_date_value,
    _resolve_source_columns,
    _read_workbook_sheets,
    _row_dict,
)
from app.services.imports.parsers.customer_sell_through_period import (
    is_summary_sheet_name,
    parse_sheet_name_period,
    sheet_has_data_header,
)


def _parse_sheet_rows(
    raw_df: pd.DataFrame,
    *,
    field_mapping: dict,
    expected_columns: dict,
    alias_index: dict[str, set[str]],
    job_id: int,
    period_start: date | None,
    period_type: str,
    sheet_name: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    header_row = _detect_header_row(raw_df, alias_index)
    if header_row is None:
        return [], [f"Could not detect header in sheet: {sheet_name}"]

    headers = [_normalize_text(c) or f"col_{i}" for i, c in enumerate(raw_df.iloc[header_row].tolist())]
    body = raw_df.iloc[header_row + 1 :].copy()
    body.columns = headers
    body = body.reset_index(drop=True)
    first_data_row = header_row + 2

    col_map = _resolve_source_columns(list(body.columns), field_mapping, expected_columns)
    if col_map["units_sold"] is None or col_map["raw_product_token"] is None:
        return [], [f"Required columns not mapped in sheet: {sheet_name}"]

    rows: list[dict[str, Any]] = []
    for pos in range(len(body)):
        series = body.iloc[pos]
        units = _parse_decimal(series.get(col_map["units_sold"]))
        product_tok = _normalize_text(series.get(col_map["raw_product_token"]))
        if units is None or product_tok is None:
            continue

        row_period = period_start
        if col_map["raw_period_ref"]:
            row_period = _parse_date_value(series.get(col_map["raw_period_ref"])) or row_period

        loc_tok = None
        if col_map["raw_location_token"]:
            loc_tok = _normalize_text(series.get(col_map["raw_location_token"]))

        rows.append(
            {
                "import_job_id": int(job_id),
                "source_row_number": int(first_data_row + pos),
                "raw_row_payload": {**_row_dict(series), "_sheet": sheet_name},
                "raw_customer_token": None,
                "raw_location_token": loc_tok,
                "site_label": loc_tok,
                "raw_product_token": product_tok,
                "raw_period_ref": sheet_name,
                "period_start_date": row_period,
                "period_type": period_type,
                "units_sold": units,
                "raw_mtd_units": None,
                "is_mtd_estimate": False,
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
    return rows, warnings


def parse_multi_sheet_report(
    file_bytes: bytes,
    filename: str,
    field_mapping: dict,
    job_id: int,
) -> ParseResult:
    fm = dict(field_mapping or {})
    expected_columns = fm.pop(EXPECTED_COLUMNS_META_KEY, None)
    if not isinstance(expected_columns, dict):
        expected_columns = {}

    alias_index = _build_alias_index(fm, expected_columns)
    warnings: list[str] = []

    try:
        sheets = _read_workbook_sheets(file_bytes, filename)
    except ValueError as exc:
        return ParseResult(error=str(exc))

    sheet_plan: list[tuple[str, pd.DataFrame, date | None, str]] = []
    for name, raw_df in sheets:
        if is_summary_sheet_name(name):
            continue
        period_start, period_type, warn = parse_sheet_name_period(name)
        if warn:
            if get_settings().ai_assist_enabled and raw_df is not None and not raw_df.empty:
                headers = [_normalize_text(c) or "" for c in raw_df.iloc[0].tolist()]
                suggestion = suggest_column_mapping(
                    headers=[name, *headers[:5]],
                    sample_rows=[],
                    canonical_fields=["raw_period_ref"],
                    existing_mapping=fm,
                )
                if suggestion and suggestion.notes:
                    warnings.append(f"{warn} (AI note: {suggestion.notes})")
                else:
                    warnings.append(warn)
            else:
                warnings.append(warn)
        if sheet_has_data_header(raw_df, alias_index) or period_start is not None:
            sheet_plan.append((name, raw_df, period_start, period_type))

    sheet_plan.sort(key=lambda x: (x[2] or date.min, x[0]))

    all_rows: list[dict[str, Any]] = []
    for name, raw_df, period_start, period_type in sheet_plan:
        sheet_rows, sheet_warnings = _parse_sheet_rows(
            raw_df,
            field_mapping=fm,
            expected_columns=expected_columns,
            alias_index=alias_index,
            job_id=job_id,
            period_start=period_start,
            period_type=period_type,
            sheet_name=name,
        )
        all_rows.extend(sheet_rows)
        warnings.extend(sheet_warnings)

    if not all_rows:
        return ParseResult(error="No data sheets found in multi-sheet workbook", warnings=warnings)

    deduped: dict[tuple[Any, ...], dict[str, Any]] = {}
    dup_count = 0
    for row in all_rows:
        key = (
            row.get("raw_product_token"),
            row.get("raw_location_token"),
            row.get("period_start_date"),
        )
        if key in deduped:
            dup_count += 1
        deduped[key] = row

    if dup_count:
        warnings.append(f"Deduplicated {dup_count} duplicate product/location/period row(s); kept latest sheet")

    final_rows = list(deduped.values())
    latest_period = max((r.get("period_start_date") for r in final_rows if r.get("period_start_date")), default=None)

    return ParseResult(
        rows=final_rows,
        period_start_date=latest_period,
        period_type="weekly",
        warnings=warnings,
    )
