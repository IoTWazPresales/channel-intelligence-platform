# Plan (Phase 1e wide extract parser):
# - Header-first column selection; stream data in 500-row chunks.
# - Period columns trigger shared pivoted unpivot; else single-period flat rows.

from __future__ import annotations

from typing import Any

import pandas as pd

from app.core.config import get_settings
from app.services.imports.ai_import_resolver import suggest_column_mapping
from app.services.imports.parsers.customer_sell_through_flat import (
    EXPECTED_COLUMNS_META_KEY,
    ParseResult,
    _build_alias_index,
    _detect_header_row,
    _extract_period,
    _normalize_text,
    _parse_decimal,
    _read_workbook_sheets,
    _resolve_source_columns,
    _row_dict,
)
from app.services.imports.parsers.customer_sell_through_pivoted import _parse_pivoted_dataframe
from app.services.imports.parsers.customer_sell_through_period import detect_period_columns

_CHUNK_SIZE = 500
_REQUIRED_CANONICAL = ("raw_product_token", "units_sold")


def _apply_ai_mapping_if_needed(
    headers: list[str],
    field_mapping: dict,
    expected_columns: dict,
    sample_rows: list[dict],
) -> bool:
    resolved = _resolve_source_columns(headers, field_mapping, expected_columns)
    found = sum(1 for c in _REQUIRED_CANONICAL if resolved.get(c))
    if found >= 2 or not get_settings().ai_assist_enabled:
        return False

    suggestion = suggest_column_mapping(
        headers=headers[:50],
        sample_rows=sample_rows,
        canonical_fields=list(_REQUIRED_CANONICAL)
        + ["raw_location_token", "unit_cost", "reported_soh", "unit_sell_price"],
        existing_mapping=field_mapping,
    )
    if not suggestion:
        return False
    for src, canon in suggestion.mappings.items():
        field_mapping[src] = canon
    return True


def parse_wide_extract_report(
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
        sheets = _read_workbook_sheets(file_bytes, filename)
    except ValueError as exc:
        return ParseResult(error=str(exc))

    raw_df = None
    for _name, candidate in sheets:
        if candidate is not None and not candidate.empty:
            if _detect_header_row(candidate, alias_index) is not None:
                raw_df = candidate
                break

    if raw_df is None:
        return ParseResult(error="Could not detect header row in wide extract file")

    header_row_idx = _detect_header_row(raw_df, alias_index)
    assert header_row_idx is not None

    headers = [
        str(c).strip() if c is not None and str(c).strip() else f"col_{i}"
        for i, c in enumerate(raw_df.iloc[header_row_idx].tolist())
    ]

    sample_rows: list[dict] = []
    data_start = header_row_idx + 1
    for i in range(data_start, min(data_start + 3, len(raw_df))):
        row = {headers[j]: raw_df.iloc[i, j] if j < raw_df.shape[1] else None for j in range(len(headers))}
        sample_rows.append(row)

    warnings: list[str] = []
    ai_used = _apply_ai_mapping_if_needed(headers, fm, expected_columns, sample_rows)
    if ai_used:
        warnings.append("ai_column_mapping_used=true")

    resolved = _resolve_source_columns(headers, fm, expected_columns)
    found = sum(1 for c in _REQUIRED_CANONICAL if resolved.get(c))
    if found < 2:
        return ParseResult(
            error=(
                f"Fewer than 2 required fields mapped (need product + units). "
                f"Available columns: {headers[:30]}{'...' if len(headers) > 30 else ''}"
            ),
        )

    period_cols = detect_period_columns(headers)
    keep_cols: list[str] = []
    for src in resolved.values():
        if src and src not in keep_cols:
            keep_cols.append(src)
    for col_name, _, _ in period_cols:
        if col_name not in keep_cols:
            keep_cols.append(col_name)

    body = raw_df.iloc[data_start:].copy()
    ncol = min(body.shape[1], len(headers))
    body = body.iloc[:, :ncol]
    body.columns = headers[:ncol]
    slim = body[keep_cols] if keep_cols else body

    frames: list[pd.DataFrame] = []
    for chunk_start in range(0, len(slim), _CHUNK_SIZE):
        frames.append(slim.iloc[chunk_start : chunk_start + _CHUNK_SIZE])
    slim_df = pd.concat(frames, ignore_index=True) if frames else slim

    if period_cols:
        return _parse_pivoted_dataframe(
            slim_df,
            field_mapping=fm,
            expected_columns=expected_columns,
            job_id=job_id,
            first_data_row=header_row_idx + 2,
            filename=filename,
            warnings=warnings,
        )

    period_start = _extract_period(
        filename=filename,
        period_col=resolved.get("raw_period_ref"),
        df=slim_df,
        warnings=warnings,
    )
    rows: list[dict[str, Any]] = []
    for pos in range(len(slim_df)):
        series = slim_df.iloc[pos]
        units = _parse_decimal(series.get(resolved["units_sold"]))
        product_tok = _normalize_text(series.get(resolved["raw_product_token"]))
        if units is None or product_tok is None:
            continue
        loc_tok = (
            _normalize_text(series.get(resolved["raw_location_token"])) if resolved["raw_location_token"] else None
        )
        rows.append(
            {
                "import_job_id": int(job_id),
                "source_row_number": int(header_row_idx + 2 + pos),
                "raw_row_payload": _row_dict(series),
                "raw_customer_token": None,
                "raw_location_token": loc_tok,
                "raw_product_token": product_tok,
                "raw_period_ref": None,
                "period_start_date": period_start,
                "period_type": "weekly",
                "units_sold": units,
                "raw_mtd_units": None,
                "is_mtd_estimate": False,
                "unit_sell_price": _parse_decimal(series.get(resolved["unit_sell_price"]))
                if resolved["unit_sell_price"]
                else None,
                "unit_cost": _parse_decimal(series.get(resolved["unit_cost"])) if resolved["unit_cost"] else None,
                "reported_soh": _parse_decimal(series.get(resolved["reported_soh"]))
                if resolved["reported_soh"]
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
