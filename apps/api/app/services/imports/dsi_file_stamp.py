"""Shared DSI per-file stamp core (distributor identity, snapshot period, …).

File-level banner/filename metadata → staged_metadata JSON → steward confirm →
row inherit via ``_dsi_source_file``. No alembic — stamps fill existing columns.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from app.models.ingestion import ImportJob
from app.utils.json_safe import to_jsonable


def cell_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def load_banner_grid(filename: str, raw_bytes: bytes, *, header_row: int = 19) -> pd.DataFrame | None:
    """Read leading rows as an unlabeled grid for banner sniffing."""
    from app.services.imports.dsi_workbook import SNIFF_ROWS, _excel_engine_for_filename

    lower = (filename or "").lower()
    nrows = max(int(header_row) + 1, SNIFF_ROWS)
    try:
        if lower.endswith(".csv"):
            return pd.read_csv(
                io.BytesIO(raw_bytes),
                header=None,
                nrows=nrows,
                names=list(range(64)),
                encoding="utf-8-sig",
                skip_blank_lines=False,
            )
        engine = _excel_engine_for_filename(filename)
        if engine is None:
            return None
        return pd.read_excel(
            io.BytesIO(raw_bytes),
            header=None,
            nrows=nrows,
            engine=engine,
        )
    except Exception:
        return None


def sniff_banner_label_value(grid: pd.DataFrame | None, label_hints: tuple[str, ...]) -> str | None:
    """Find label/value pairs above the data table (Company Name, Application Date, …)."""
    if grid is None or grid.empty:
        return None
    hints = tuple(h.lower() for h in label_hints)
    for i in range(min(len(grid), 40)):
        row = [cell_text(v) for v in grid.iloc[i].tolist()]
        non_empty = [c for c in row if c]
        if not non_empty:
            continue
        label = non_empty[0].lower()
        if any(h == label or label.startswith(h) for h in hints):
            if len(non_empty) >= 2:
                token = non_empty[1]
                if token and token.lower() not in hints:
                    return token
        for cell in non_empty:
            low = cell.lower()
            for h in hints:
                prefix = f"{h}:"
                if low.startswith(prefix) or f"{h} :" in low:
                    if ":" in cell:
                        rhs = cell.split(":", 1)[1].strip()
                        if rhs:
                            return rhs
    return None


def get_file_stamps(job: ImportJob, metadata_key: str) -> dict[str, dict[str, Any]]:
    sm = job.staged_metadata if isinstance(job.staged_metadata, dict) else {}
    raw = sm.get(metadata_key)
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for k, v in raw.items():
        if isinstance(k, str) and isinstance(v, dict):
            out[k] = dict(v)
    return out


def set_file_stamps(job: ImportJob, metadata_key: str, stamps: dict[str, dict[str, Any]]) -> None:
    sm = dict(job.staged_metadata or {})
    sm[metadata_key] = to_jsonable(stamps)
    job.staged_metadata = to_jsonable(sm)


def included_batch_filenames(job: ImportJob) -> list[str]:
    sm = job.staged_metadata if isinstance(job.staged_metadata, dict) else {}
    names = sm.get("dsi_batch_filenames")
    if isinstance(names, list) and names:
        files = [str(x) for x in names if str(x).strip()]
    else:
        wb = sm.get("dsi_workbook") if isinstance(sm.get("dsi_workbook"), dict) else {}
        files = []
        for s in wb.get("sheets") or []:
            if isinstance(s, dict) and s.get("source_file"):
                files.append(str(s["source_file"]))
        if not files and job.file_name:
            files = [str(job.file_name)]
    from app.services.imports.dsi_batch import get_dsi_excluded_filenames

    excluded = get_dsi_excluded_filenames(job)
    return [f for f in dict.fromkeys(files) if f not in excluded]


def header_row_for_file(job: ImportJob, filename: str, *, default: int = 19) -> int:
    wb = (job.staged_metadata or {}).get("dsi_workbook") if isinstance(job.staged_metadata, dict) else {}
    if not isinstance(wb, dict):
        return default
    for s in wb.get("sheets") or []:
        if not isinstance(s, dict):
            continue
        if s.get("source_file") == filename or str(s.get("mapping_key") or "").startswith(filename):
            try:
                return int(s.get("header_row") or default)
            except (TypeError, ValueError):
                return default
    return default


def file_maps_canonical_target(job: ImportJob, filename: str, target: str) -> bool:
    """True when any sheet map for this file includes the canonical target."""
    fm = job.field_mapping if isinstance(job.field_mapping, dict) else {}
    from app.services.imports.dsi_workbook import is_nested_dsi_field_mapping

    if is_nested_dsi_field_mapping(fm):
        for key, sheet_map in fm.items():
            if not isinstance(sheet_map, dict):
                continue
            key_s = str(key)
            file_part = key_s.split("::", 1)[0] if "::" in key_s else None
            if file_part is not None and file_part != filename:
                continue
            if file_part is None and filename not in included_batch_filenames(job):
                continue
            if target in set(sheet_map.values()):
                return True
        return False
    return target in set(fm.values())


def stamps_covering_files(
    job: ImportJob,
    *,
    metadata_key: str,
    is_ready: Callable[[dict[str, Any]], bool],
    column_satisfies: Callable[[ImportJob, str], bool],
) -> bool:
    """Every included file is OK via mapped column OR a ready stamp."""
    stamps = get_file_stamps(job, metadata_key)
    files = included_batch_filenames(job)
    if not files:
        return False
    for name in files:
        if column_satisfies(job, name):
            continue
        if not is_ready(stamps.get(name) or {}):
            return False
    return True


def apply_stamps_to_column(
    job: ImportJob,
    df: pd.DataFrame,
    *,
    metadata_key: str,
    column: str,
    is_ready: Callable[[dict[str, Any]], bool],
    value_from_stamp: Callable[[dict[str, Any]], str],
) -> pd.DataFrame:
    """Fill ``column`` from confirmed stamps where empty/missing (keyed by ``_dsi_source_file``)."""
    if df is None or df.empty:
        return df
    stamps = get_file_stamps(job, metadata_key)
    if not stamps:
        return df
    out = df.copy()
    if column not in out.columns:
        out[column] = ""

    if "_dsi_source_file" in out.columns:
        values: list[str] = []
        for src in out["_dsi_source_file"].astype(str).tolist():
            st = stamps.get(src) or {}
            values.append(value_from_stamp(st) if is_ready(st) else "")
        stamped = pd.Series(values, index=out.index)
    else:
        files = included_batch_filenames(job)
        ready_val = ""
        for name in files:
            st = stamps.get(name) or {}
            if is_ready(st):
                ready_val = value_from_stamp(st)
                break
        if not ready_val and len(stamps) == 1:
            only = next(iter(stamps.values()))
            if is_ready(only):
                ready_val = value_from_stamp(only)
        if not ready_val:
            return out
        stamped = pd.Series(ready_val, index=out.index)

    existing = out[column].fillna("").astype(str).str.strip()
    # Treat pandas NaT / "NaT" / "None" as empty for date columns
    empty_mask = existing.eq("") | existing.str.lower().isin(["nat", "none", "nan"])
    out[column] = existing.where(~empty_mask, stamped)
    return out


def iter_raw_files_for_propose(db: Session, job: ImportJob) -> list[tuple[str, bytes, int]]:
    """(filename, bytes, header_row) for each raw file on the job."""
    from app.services.imports.dsi_batch import list_raw_files_for_job
    from app.services.imports.dsi_workbook import raw_file_display_name
    from app.storage.local import get_storage_backend

    storage = get_storage_backend()
    out: list[tuple[str, bytes, int]] = []
    for raw in list_raw_files_for_job(db, int(job.id)):
        filename = raw_file_display_name(raw.storage_key)
        data = storage.read(raw.storage_key)
        hr = header_row_for_file(job, filename)
        out.append((filename, data, hr))
    return out
