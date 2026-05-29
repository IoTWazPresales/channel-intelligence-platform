# Plan (Phase 1b pivoted parser):
# - Period columns detected by regex patterns in customer_sell_through_period (no fixed week names).
# - Unpivot: one output row per product/location per period with units_sold > 0.
# - SOH snapshot applied on the latest period column row only per identity group.
# - AI column mapping only when AI_ASSIST_ENABLED and zero period columns detected.

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
    _resolve_source_columns,
    _row_dict,
    _select_sheet_with_header,
)
from app.services.imports.parsers.customer_sell_through_period import (
    classify_period_header,
    detect_period_columns,
    is_period_column_header,
    sort_period_columns,
)

_IDENTITY_CANONICAL = (
    "raw_product_token",
    "raw_location_token",
    "unit_cost",
    "reported_soh",
    "unit_sell_price",
)


def _parse_pivoted_dataframe(
    df: pd.DataFrame,
    *,
    field_mapping: dict,
    expected_columns: dict,
    job_id: int,
    first_data_row: int,
    filename: str,
    warnings: list[str],
) -> ParseResult:
    headers = [str(c) for c in df.columns]
    period_cols = detect_period_columns(headers)
    ai_used = False

    if not period_cols and get_settings().ai_assist_enabled:
        sample = []
        for i in range(min(3, len(df))):
            sample.append(_row_dict(df.iloc[i]))
        suggestion = suggest_column_mapping(
            headers=headers,
            sample_rows=sample,
            canonical_fields=list(_IDENTITY_CANONICAL) + ["units_sold"],
            existing_mapping=field_mapping,
        )
        if suggestion and suggestion.mappings:
            ai_used = True
            for src, canon in suggestion.mappings.items():
                if canon in ("units_sold",) or is_period_column_header(src):
                    if is_period_column_header(src) and src in headers:
                        kind, pdate, ptype = classify_period_header(src)
                        if pdate is not None:
                            period_cols.append((src, pdate, ptype))
                    field_mapping[src] = canon
            period_cols = sort_period_columns(period_cols)
            warnings.append("AI column mapping used to identify period columns")

    if not period_cols:
        if get_settings().ai_assist_enabled and not ai_used:
            warnings.append("Could not detect period columns; AI assist did not return a mapping")
        return ParseResult(
            error="Could not detect period columns in pivoted report",
            warnings=warnings,
        )

    period_cols = sort_period_columns(period_cols)
    period_names = {name for name, _, _ in period_cols}
    non_period_headers = [h for h in headers if h not in period_names]

    col_map = _resolve_source_columns(non_period_headers, field_mapping, expected_columns)
    if col_map["raw_product_token"] is None:
        return ParseResult(
            error=f"Required product identifier could not be mapped. Available columns: {non_period_headers}",
            warnings=warnings,
        )

    latest_period_date = max((p[1] for p in period_cols if p[1]), default=None)
    rows: list[dict[str, Any]] = []
    skipped_periods: list[str] = []

    for pos in range(len(df)):
        series = df.iloc[pos]
        source_row_number = first_data_row + pos
        product_tok = (
            _normalize_text(series.get(col_map["raw_product_token"])) if col_map["raw_product_token"] else None
        )
        if not product_tok:
            continue

        loc_tok = None
        if col_map["raw_location_token"]:
            loc_tok = _normalize_text(series.get(col_map["raw_location_token"]))

        unit_cost = _parse_decimal(series.get(col_map["unit_cost"])) if col_map["unit_cost"] else None
        unit_sell = _parse_decimal(series.get(col_map["unit_sell_price"])) if col_map["unit_sell_price"] else None
        soh_val = _parse_decimal(series.get(col_map["reported_soh"])) if col_map["reported_soh"] else None

        for col_name, period_date, period_type in period_cols:
            if period_date is None:
                skipped_periods.append(str(col_name))
                continue
            units = _parse_decimal(series.get(col_name))
            if units is None or units <= 0:
                continue

            reported_soh = soh_val if latest_period_date and period_date == latest_period_date else None

            rows.append(
                {
                    "import_job_id": int(job_id),
                    "source_row_number": int(source_row_number),
                    "raw_row_payload": _row_dict(series),
                    "raw_customer_token": None,
                    "raw_location_token": loc_tok,
                    "raw_product_token": product_tok,
                    "raw_period_ref": str(col_name),
                    "period_start_date": period_date,
                    "period_type": period_type,
                    "units_sold": units,
                    "raw_mtd_units": None,
                    "is_mtd_estimate": False,
                    "unit_sell_price": unit_sell,
                    "unit_cost": unit_cost,
                    "reported_soh": reported_soh,
                    "resolution_status": "pending",
                }
            )

    for col in sorted(set(skipped_periods)):
        warnings.append(f"Period column could not be parsed to a date: {col}")

    if ai_used:
        warnings.append("ai_column_mapping_used=true")

    return ParseResult(
        rows=rows,
        period_start_date=latest_period_date,
        period_type="weekly",
        warnings=warnings,
    )


def parse_pivoted_report(
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
    try:
        df, first_data_row = _select_sheet_with_header(file_bytes, filename, alias_index)
    except ValueError as exc:
        return ParseResult(error=str(exc))

    if df is None:
        return ParseResult(error="Could not detect header row")

    return _parse_pivoted_dataframe(
        df,
        field_mapping=fm,
        expected_columns=expected_columns,
        job_id=job_id,
        first_data_row=first_data_row or 2,
        filename=filename,
        warnings=[],
    )
