"""DSI multi-sheet workbook load + per-sheet field mapping resolution."""

from __future__ import annotations

import io
from typing import Any

import pandas as pd
from sqlalchemy import select

from app.ingestion.infer import infer_schema, read_tabular
from app.models.ingestion import ImportJob, RawFileMetadata
from app.services.imports.distributor_sales_inventory import CANONICAL
from app.storage.local import get_storage_backend

DSI_SHEET_META_KEY = "dsi_workbook"
DSI_SINGLE_SHEET_KEY = "__single__"


def is_nested_dsi_field_mapping(field_mapping: dict[str, Any] | None) -> bool:
    fm = field_mapping or {}
    return any(isinstance(v, dict) for v in fm.values())


def flatten_dsi_field_mapping(field_mapping: dict[str, Any] | None) -> dict[str, str]:
    fm = dict(field_mapping or {})
    if not is_nested_dsi_field_mapping(fm):
        return {str(k): str(v) for k, v in fm.items() if isinstance(v, str)}
    flat: dict[str, str] = {}
    for val in fm.values():
        if isinstance(val, dict):
            for src, tgt in val.items():
                if isinstance(src, str) and isinstance(tgt, str):
                    flat[src] = tgt
    return flat


def load_dsi_workbook_sheet_frames(filename: str, raw_bytes: bytes) -> list[tuple[str | None, pd.DataFrame]]:
    lower = (filename or "").lower()
    if lower.endswith(".csv"):
        return [(None, pd.read_csv(io.BytesIO(raw_bytes)))]
    if lower.endswith((".xlsx", ".xlsm")):
        xls = pd.ExcelFile(io.BytesIO(raw_bytes), engine="openpyxl")
        out: list[tuple[str | None, pd.DataFrame]] = []
        for sheet in xls.sheet_names:
            sdf = pd.read_excel(xls, sheet_name=sheet)
            if sdf.empty or sdf.shape[1] == 0:
                continue
            out.append((sheet, sdf))
        return out or [(None, pd.DataFrame())]
    return [(None, read_tabular(filename, raw_bytes))]


def _sheet_looks_dsi_mappable(df: pd.DataFrame) -> bool:
    if df.empty:
        return False
    cols = {str(c).strip().lower() for c in df.columns}
    hints = (
        "distributor",
        "sku",
        "product",
        "model",
        "qty",
        "quantity",
        "soh",
        "stock",
        "customer",
        "dealer",
        "invoice",
        "date",
    )
    hits = sum(1 for c in cols if any(h in c for h in hints))
    return hits >= 2


def build_dsi_workbook_structure(
    filename: str,
    raw_bytes: bytes,
    *,
    field_mapping: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Detect workbook sheets; classify mappable vs skipped."""
    frames = load_dsi_workbook_sheet_frames(filename, raw_bytes)
    mapped_sheets = set()
    if is_nested_dsi_field_mapping(field_mapping):
        mapped_sheets = {k for k, v in (field_mapping or {}).items() if isinstance(v, dict) and v}

    sheets: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for sheet_name, df in frames:
        key = sheet_name or DSI_SINGLE_SHEET_KEY
        schema = infer_schema(df)
        entry = {
            "sheet_name": sheet_name,
            "sheet_key": key,
            "row_count": int(len(df)),
            "columns": [c["name"] for c in schema.get("columns", [])],
            "user_mapped": key in mapped_sheets,
            "dsi_mappable": _sheet_looks_dsi_mappable(df),
        }
        if key in mapped_sheets or (len(frames) == 1 and _sheet_looks_dsi_mappable(df)):
            sheets.append(entry)
        elif _sheet_looks_dsi_mappable(df):
            sheets.append(entry)
        else:
            skipped.append({"sheet_name": sheet_name or "(csv)", "reason": "not_dsi_mappable"})
    return {
        "multi_sheet": len(frames) > 1,
        "sheet_count": len(frames),
        "sheets": sheets,
        "skipped_sheets": skipped,
    }


def resolve_dsi_sheet_mappings(job: ImportJob) -> list[tuple[str | None, dict[str, str]]]:
    """Return (sheet_name, source→canonical mapping) pairs to process."""
    fm = dict(job.field_mapping or {})
    meta = job.staged_metadata if isinstance(job.staged_metadata, dict) else {}
    wb = meta.get(DSI_SHEET_META_KEY) if isinstance(meta.get(DSI_SHEET_META_KEY), dict) else {}

    if is_nested_dsi_field_mapping(fm):
        out: list[tuple[str | None, dict[str, str]]] = []
        for sheet_key, sheet_map in fm.items():
            if not isinstance(sheet_map, dict) or not sheet_map:
                continue
            sheet_name = None if sheet_key == DSI_SINGLE_SHEET_KEY else str(sheet_key)
            out.append((sheet_name, {str(k): str(v) for k, v in sheet_map.items()}))
        return out

    flat = {str(k): str(v) for k, v in fm.items() if isinstance(v, str)}
    if flat:
        return [(None, flat)]

    selected = wb.get("sheets") if isinstance(wb.get("sheets"), list) else []
    if len(selected) == 1 and isinstance(selected[0], dict):
        sn = selected[0].get("sheet_name")
        return [(sn if isinstance(sn, str) else None, flat)]
    return [(None, flat)]


def build_combined_dsi_dataframe(
    frames: list[tuple[str | None, pd.DataFrame, dict[str, str]]],
) -> tuple[pd.DataFrame, dict[str, str], list[dict[str, str]]]:
    """Normalize each mapped sheet to canonical columns and concatenate for one pass."""
    parts: list[pd.DataFrame] = []
    skipped: list[dict[str, str]] = []
    for sheet_name, sheet_df, sheet_map in frames:
        if not sheet_map or "distributor_token" not in sheet_map.values():
            skipped.append(
                {
                    "sheet_name": sheet_name or "(default)",
                    "reason": "not_mapped_or_missing_distributor",
                }
            )
            continue
        if "product_identifier" not in sheet_map.values():
            skipped.append(
                {
                    "sheet_name": sheet_name or "(default)",
                    "reason": "not_mapped_or_missing_product_identifier",
                }
            )
            continue
        norm = pd.DataFrame()
        for src, canon in sheet_map.items():
            if canon in CANONICAL and src in sheet_df.columns:
                norm[canon] = sheet_df[src]
        if sheet_name:
            norm["_dsi_source_sheet"] = sheet_name
        if norm.empty:
            skipped.append({"sheet_name": sheet_name or "(default)", "reason": "empty_after_normalize"})
            continue
        parts.append(norm)
    if not parts:
        return pd.DataFrame(), {}, skipped
    combined = pd.concat(parts, ignore_index=True)
    mapping = {c: c for c in CANONICAL if c in combined.columns}
    return combined, mapping, skipped


def iter_dsi_dataframes_for_job(
    db: Any,
    job: ImportJob,
    df_fallback: pd.DataFrame,
) -> list[tuple[str | None, pd.DataFrame, dict[str, str]]]:
    """Load raw file and yield per-sheet dataframes with resolved mappings."""
    mappings = resolve_dsi_sheet_mappings(job)
    if len(mappings) == 1 and mappings[0][0] is None and not is_nested_dsi_field_mapping(job.field_mapping):
        return [(None, df_fallback, mappings[0][1])]

    raw = db.scalars(select(RawFileMetadata).where(RawFileMetadata.job_id == job.id)).first()
    if raw is None:
        return [(None, df_fallback, mappings[0][1] if mappings else {})]

    storage = get_storage_backend()
    data = storage.read(raw.storage_key)
    frames_by_name = {sn: frame for sn, frame in load_dsi_workbook_sheet_frames(job.file_name or "", data)}

    out: list[tuple[str | None, pd.DataFrame, dict[str, str]]] = []
    for sheet_name, mapping in mappings:
        if sheet_name is None:
            if len(frames_by_name) == 1:
                only = next(iter(frames_by_name.values()))
                out.append((None, only, mapping))
            else:
                out.append((None, df_fallback, mapping))
            continue
        frame = frames_by_name.get(sheet_name)
        if frame is not None and not frame.empty:
            out.append((sheet_name, frame, mapping))
    if not out:
        return [(None, df_fallback, mappings[0][1] if mappings else {})]
    return out


def persist_dsi_workbook_on_job(job: ImportJob, structure: dict[str, Any]) -> None:
    meta = dict(job.staged_metadata or {})
    meta[DSI_SHEET_META_KEY] = structure
    job.staged_metadata = meta
