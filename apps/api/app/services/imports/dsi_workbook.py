"""DSI multi-sheet workbook load + per-sheet field mapping resolution."""

from __future__ import annotations

import io
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.infer import infer_schema, read_tabular
from app.models.ingestion import ImportJob, ImportRowResult, RawFileMetadata
from app.services.imports.distributor_sales_inventory import CANONICAL
from app.storage.local import get_storage_backend
from app.utils.json_safe import to_jsonable

DSI_SHEET_META_KEY = "dsi_workbook"
DSI_SINGLE_SHEET_KEY = "__single__"
DSI_FILE_SHEET_SEP = "::"


def flag_dsi_cross_file_raw_overlaps(
    db: Session,
    job: ImportJob,
    combined: pd.DataFrame,
    *,
    max_detail_flags: int = 20,
) -> int:
    """FLAG (warning) when the same raw business grain appears in >1 source file.

    Uses raw-token grain (pre-resolution): distributor_token + product_identifier +
    customer_dealer_token + transaction/snapshot date + invoice. Does not block apply.
    Returns number of detail warning rows written (summary always written when overlaps exist).
    """
    if combined is None or combined.empty or "_dsi_source_file" not in combined.columns:
        return 0
    needed = ["distributor_token", "product_identifier"]
    if any(c not in combined.columns for c in needed):
        return 0

    work = combined.copy()
    for col in (
        "distributor_token",
        "product_identifier",
        "customer_dealer_token",
        "transaction_date",
        "snapshot_date",
        "invoice_no",
    ):
        if col not in work.columns:
            work[col] = ""
        work[col] = work[col].fillna("").astype(str).str.strip()

    date_col = work["transaction_date"].where(work["transaction_date"] != "", work["snapshot_date"])
    work["_raw_grain"] = (
        work["distributor_token"]
        + "|"
        + work["product_identifier"]
        + "|"
        + work["customer_dealer_token"]
        + "|"
        + date_col
        + "|"
        + work["invoice_no"]
    )
    files_by_grain: dict[str, set[str]] = {}
    counts_by_grain: dict[str, int] = {}
    for grain, src in zip(work["_raw_grain"].tolist(), work["_dsi_source_file"].astype(str).tolist()):
        if not grain or grain.startswith("||"):
            continue
        files_by_grain.setdefault(grain, set()).add(src)
        counts_by_grain[grain] = counts_by_grain.get(grain, 0) + 1

    overlaps = [
        (g, sorted(files), counts_by_grain[g])
        for g, files in files_by_grain.items()
        if len(files) > 1
    ]
    if not overlaps:
        return 0

    summary = {
        "overlap_grain_count": len(overlaps),
        "samples": [
            {"grain": g[:200], "files": files, "row_count": n} for g, files, n in overlaps[:10]
        ],
    }
    sm = dict(job.staged_metadata or {})
    sm["dsi_cross_file_overlap"] = summary
    job.staged_metadata = to_jsonable(sm)
    db.add(job)
    db.add(
        ImportRowResult(
            job_id=job.id,
            row_number=0,
            severity="warning",
            code="dsi_cross_file_duplicate",
            message=(
                f"Cross-file overlap: {len(overlaps)} raw business key(s) appear in more than one "
                f"file in this batch. Latest-wins upsert still applies at fact grain; review before apply."
            ),
        )
    )
    written = 0
    for g, files, n in overlaps[:max_detail_flags]:
        db.add(
            ImportRowResult(
                job_id=job.id,
                row_number=0,
                severity="warning",
                code="dsi_cross_file_duplicate",
                message=f"Overlap grain {g[:160]!r} in files {files} ({n} rows).",
            )
        )
        written += 1
    return written


def raw_file_display_name(storage_key: str) -> str:
    return storage_key.rsplit("/", 1)[-1]


def is_dsi_file_sheet_mapping_key(key: str) -> bool:
    return DSI_FILE_SHEET_SEP in key


def make_dsi_file_sheet_key(filename: str, sheet_key: str) -> str:
    return f"{filename}{DSI_FILE_SHEET_SEP}{sheet_key}"


def parse_dsi_mapping_key(key: str) -> tuple[str | None, str]:
    if DSI_FILE_SHEET_SEP in key:
        file_part, sheet_part = key.split(DSI_FILE_SHEET_SEP, 1)
        return file_part, sheet_part
    return None, key


def job_has_multi_file_mapping(field_mapping: dict[str, Any] | None) -> bool:
    fm = field_mapping or {}
    return any(is_dsi_file_sheet_mapping_key(str(k)) for k in fm.keys())


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


# Corrective header sniff: only runs when default header=0 fails the DSI mappable bar.
# ASUS weekly sellout workbooks put a contact/form block above the table (~row 19).
SNIFF_ROWS = 40
HEADER_MIN_HINTS = 2
# CSV exports of those workbooks can exceed 200 delimiter fields (sparse trailing commas).
CSV_SNIFF_WIDTH = 300
# Propose/signature + infer must not fully parse multi‑10MB inventory workbooks.
DSI_SIGNATURE_MAX_ROWS = 5
DSI_INFER_SAMPLE_ROWS = 100

_DSI_HEADER_HINTS = (
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


def _cell_as_header_label(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if not text or text.lower().startswith("unnamed"):
        return ""
    return text


def _header_hint_hits(labels: list[str] | Any) -> int:
    cols = {_cell_as_header_label(c).lower() for c in labels}
    cols.discard("")
    return sum(1 for c in cols if any(h in c for h in _DSI_HEADER_HINTS))


def _sheet_looks_dsi_mappable(df: pd.DataFrame) -> bool:
    if df is None or df.empty:
        return False
    return _header_hint_hits(list(df.columns)) >= HEADER_MIN_HINTS


def _score_header_row(row_values: Any) -> int:
    return _header_hint_hits(list(row_values))


def _detect_header_row(grid: pd.DataFrame) -> int | None:
    """Pick best header row in a raw (header=None) grid. Must clear hint bar and beat row 0."""
    if grid is None or grid.empty:
        return None
    limit = min(int(len(grid)), SNIFF_ROWS)
    row0_score = _score_header_row(grid.iloc[0].tolist()) if limit else 0
    best_row: int | None = None
    best_score = -1
    for i in range(limit):
        score = _score_header_row(grid.iloc[i].tolist())
        if score >= HEADER_MIN_HINTS and score > best_score:
            best_score = score
            best_row = i
    if best_row is None:
        return None
    if best_row == 0:
        return None  # caller already tried header=0; no better offset
    if best_score > row0_score:
        return best_row
    return None


DSI_HEADER_ROW_OVERRIDES_KEY = "dsi_header_row_overrides"


def _has_meaningful_headers(df: pd.DataFrame) -> bool:
    return any(_cell_as_header_label(c) for c in df.columns)


def _drop_blank_unnamed_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Drop leading/stray columns with no header and no values (e.g. an empty column A)."""
    if df is None or df.shape[1] == 0:
        return df
    keep = [
        i
        for i, c in enumerate(df.columns)
        if _cell_as_header_label(c) or not df.iloc[:, i].isna().all()
    ]
    return df if len(keep) == df.shape[1] else df.iloc[:, keep]


def _fallback_header_row_in_grid(raw: pd.DataFrame) -> int | None:
    """Header row when no row carries the DSI hint words: the CST layout reader's fullest-of-first-rows."""
    from app.services.imports.cst_layouts import _fallback_header_row

    return _fallback_header_row(raw)


def header_row_overrides_for_file(job: ImportJob, filename: str) -> dict[str, int]:
    """Uploader-set header rows for one file: ``{sheet_key: 0-based row}``."""
    meta = job.staged_metadata if isinstance(job.staged_metadata, dict) else {}
    raw = meta.get(DSI_HEADER_ROW_OVERRIDES_KEY)
    if not isinstance(raw, dict):
        return {}
    prefix = f"{filename}{DSI_FILE_SHEET_SEP}"
    out: dict[str, int] = {}
    for key, value in raw.items():
        if isinstance(key, str) and key.startswith(prefix):
            try:
                out[key[len(prefix) :]] = max(0, int(value))
            except (TypeError, ValueError):
                continue
    return out


def _framed_sheet_read_csv(
    raw_bytes: bytes,
    *,
    max_data_rows: int | None = None,
    header_override: int | None = None,
) -> tuple[pd.DataFrame, int]:
    """Return (dataframe, header_row). Corrective sniff only when header=0 is not DSI-mappable."""
    data_nrows = max_data_rows  # None = full file; int includes header row semantics in pandas

    def _read_typed(*, header: int) -> pd.DataFrame:
        kwargs: dict[str, Any] = {
            "header": header,
            "encoding": "utf-8-sig",
            "skip_blank_lines": False,
        }
        if data_nrows is not None:
            kwargs["nrows"] = data_nrows
        try:
            return pd.read_csv(io.BytesIO(raw_bytes), **kwargs)
        except Exception:
            kwargs.pop("encoding", None)
            return pd.read_csv(io.BytesIO(raw_bytes), **kwargs)

    if header_override is not None:
        try:
            return _drop_blank_unnamed_columns(_read_typed(header=int(header_override))), int(header_override)
        except Exception:
            return pd.DataFrame(), int(header_override)

    df0: pd.DataFrame | None = None
    try:
        df0 = _read_typed(header=0)
        if _sheet_looks_dsi_mappable(df0):
            return _drop_blank_unnamed_columns(df0), 0
    except Exception:
        df0 = None

    # Banner CSVs often have 1-cell title rows; force a wide column set so the C parser
    # does not refuse later wider header/data rows during the sniff pass.
    # Keep blank lines — ASUS weekly sellout forms use empty rows before the table header.
    raw: pd.DataFrame | None = None
    for width in (CSV_SNIFF_WIDTH, 128, 64):
        try:
            raw = pd.read_csv(
                io.BytesIO(raw_bytes),
                header=None,
                nrows=SNIFF_ROWS,
                names=list(range(width)),
                encoding="utf-8-sig",
                skip_blank_lines=False,
            )
            break
        except Exception:
            raw = None
    if raw is None:
        try:
            raw = pd.read_csv(
                io.BytesIO(raw_bytes),
                header=None,
                nrows=SNIFF_ROWS,
                engine="python",
                on_bad_lines="skip",
                encoding="utf-8-sig",
                skip_blank_lines=False,
            )
        except Exception:
            return (df0 if df0 is not None else pd.DataFrame()), 0

    detected = _detect_header_row(raw)
    if detected is None and df0 is not None and not _has_meaningful_headers(df0):
        # Row 1 is blank and no row carries the DSI hint words: take the fullest of the first rows.
        fallback = _fallback_header_row_in_grid(raw)
        if fallback:
            try:
                return _drop_blank_unnamed_columns(_read_typed(header=int(fallback))), int(fallback)
            except Exception:
                pass
    if detected is None:
        return (_drop_blank_unnamed_columns(df0) if df0 is not None else pd.DataFrame()), 0
    try:
        typed = _read_typed(header=int(detected))
    except Exception:
        return (_drop_blank_unnamed_columns(df0) if df0 is not None else pd.DataFrame()), 0
    if _sheet_looks_dsi_mappable(typed):
        return _drop_blank_unnamed_columns(typed), int(detected)
    return (_drop_blank_unnamed_columns(df0) if df0 is not None else pd.DataFrame()), 0


def _framed_sheet_read_excel(
    xls: pd.ExcelFile,
    sheet_name: str,
    *,
    max_data_rows: int | None = None,
    header_override: int | None = None,
) -> tuple[pd.DataFrame, int] | None:
    """Return (dataframe, header_row) or None if sheet is empty."""
    read_kw: dict[str, Any] = {}
    if max_data_rows is not None:
        read_kw["nrows"] = max_data_rows

    if header_override is not None:
        forced = pd.read_excel(xls, sheet_name=sheet_name, header=int(header_override), **read_kw)
        if forced.shape[1] == 0:
            return None
        return _drop_blank_unnamed_columns(forced), int(header_override)

    sdf0 = pd.read_excel(xls, sheet_name=sheet_name, **read_kw)
    if sdf0.empty or sdf0.shape[1] == 0:
        return None
    if _sheet_looks_dsi_mappable(sdf0):
        return _drop_blank_unnamed_columns(sdf0), 0
    try:
        raw = pd.read_excel(xls, sheet_name=sheet_name, header=None, nrows=SNIFF_ROWS)
    except Exception:
        return _drop_blank_unnamed_columns(sdf0), 0
    detected = _detect_header_row(raw)
    if detected is None and not _has_meaningful_headers(sdf0):
        # Row 1 is blank and no row carries the DSI hint words: take the fullest of the first rows.
        detected = _fallback_header_row_in_grid(raw) or None
        if detected:
            typed = pd.read_excel(xls, sheet_name=sheet_name, header=detected, **read_kw)
            if not typed.empty and typed.shape[1] > 0:
                return _drop_blank_unnamed_columns(typed), int(detected)
        return _drop_blank_unnamed_columns(sdf0), 0
    if detected is None:
        return _drop_blank_unnamed_columns(sdf0), 0
    typed = pd.read_excel(xls, sheet_name=sheet_name, header=detected, **read_kw)
    if typed.empty or typed.shape[1] == 0:
        return _drop_blank_unnamed_columns(sdf0), 0
    if _sheet_looks_dsi_mappable(typed):
        return _drop_blank_unnamed_columns(typed), int(detected)
    return _drop_blank_unnamed_columns(sdf0), 0


def _excel_engine_for_filename(filename: str) -> str | None:
    """Return pandas Excel engine for DSI workbooks, or None if not Excel."""
    lower = (filename or "").lower()
    if lower.endswith((".xlsx", ".xlsm")):
        return "openpyxl"
    if lower.endswith(".xls"):
        return "xlrd"
    return None


def load_dsi_workbook_sheet_frames(
    filename: str,
    raw_bytes: bytes,
    *,
    max_data_rows: int | None = None,
    header_row_overrides: dict[str, int] | None = None,
) -> list[tuple[str | None, pd.DataFrame, int]]:
    """Load sheets as (sheet_name, dataframe, header_row).

    header_row is 0 for clean files; >0 when corrective sniff found a banner-offset header.
    ``header_row_overrides`` ({sheet_key: 0-based row}) is what the uploader set for this file; it
    wins over detection. Pass max_data_rows for propose/infer (bounded) — omit for validate.
    """
    overrides = header_row_overrides or {}
    lower = (filename or "").lower()
    if lower.endswith(".csv"):
        df, header_row = _framed_sheet_read_csv(
            raw_bytes,
            max_data_rows=max_data_rows,
            header_override=overrides.get(DSI_SINGLE_SHEET_KEY),
        )
        return [(None, df, header_row)]
    engine = _excel_engine_for_filename(filename)
    if engine is not None:
        xls = pd.ExcelFile(io.BytesIO(raw_bytes), engine=engine)
        out: list[tuple[str | None, pd.DataFrame, int]] = []
        for sheet in xls.sheet_names:
            framed = _framed_sheet_read_excel(
                xls,
                sheet,
                max_data_rows=max_data_rows,
                header_override=overrides.get(sheet),
            )
            if framed is None:
                continue
            sdf, header_row = framed
            out.append((sheet, sdf, header_row))
        return out or [(None, pd.DataFrame(), 0)]
    # Other tabular types: no sniff (preserve prior behavior).
    return [(None, read_tabular(filename, raw_bytes), 0)]


def build_dsi_workbook_structure(
    filename: str,
    raw_bytes: bytes,
    *,
    field_mapping: dict[str, Any] | None = None,
    max_data_rows: int | None = None,
    frames: list[tuple[str | None, pd.DataFrame, int]] | None = None,
    header_row_overrides: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Detect workbook sheets; classify mappable vs skipped."""
    frames = frames or load_dsi_workbook_sheet_frames(
        filename,
        raw_bytes,
        max_data_rows=max_data_rows,
        header_row_overrides=header_row_overrides,
    )
    mapped_sheets = set()
    if is_nested_dsi_field_mapping(field_mapping):
        mapped_sheets = {k for k, v in (field_mapping or {}).items() if isinstance(v, dict) and v}

    sheets: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for sheet_name, df, header_row in frames:
        key = sheet_name or DSI_SINGLE_SHEET_KEY
        schema = infer_schema(df)
        from app.services.imports.dsi_mapping_workflow import column_samples_from_schema_dict

        entry = {
            "sheet_name": sheet_name,
            "sheet_key": key,
            "row_count": int(len(df)),
            "columns": [c["name"] for c in schema.get("columns", [])],
            "column_samples": column_samples_from_schema_dict(schema),
            "user_mapped": key in mapped_sheets,
            "dsi_mappable": _sheet_looks_dsi_mappable(df),
            "header_row": int(header_row),
            "header_row_user_set": key in (header_row_overrides or {}),
        }
        # A lone sheet is always listed (even when no header row was found) so the uploader can
        # point at the header row; ``dsi_mappable`` says whether the headers look right.
        if key in mapped_sheets or len(frames) == 1:
            sheets.append(entry)
        elif _sheet_looks_dsi_mappable(df) or key in (header_row_overrides or {}):
            sheets.append(entry)
        else:
            skipped.append({"sheet_name": sheet_name or "(csv)", "reason": "not_dsi_mappable"})
    return {
        "multi_sheet": len(frames) > 1,
        "sheet_count": len(frames),
        "sheets": sheets,
        "skipped_sheets": skipped,
    }


def resolve_dsi_sheet_mappings(
    job: ImportJob,
) -> list[tuple[str | None, dict[str, str], str | None]]:
    """Return (sheet_name, source→canonical mapping, source_file) triples."""
    fm = dict(job.field_mapping or {})
    meta = job.staged_metadata if isinstance(job.staged_metadata, dict) else {}
    wb = meta.get(DSI_SHEET_META_KEY) if isinstance(meta.get(DSI_SHEET_META_KEY), dict) else {}

    if is_nested_dsi_field_mapping(fm):
        from app.services.imports.dsi_batch import get_dsi_excluded_filenames, get_dsi_excluded_mapping_keys

        excluded = get_dsi_excluded_filenames(job)
        excluded_keys = get_dsi_excluded_mapping_keys(job)
        out: list[tuple[str | None, dict[str, str], str | None]] = []
        for sheet_key, sheet_map in fm.items():
            if not isinstance(sheet_map, dict) or not sheet_map:
                continue
            if str(sheet_key) in excluded_keys:
                continue
            source_file, inner_key = parse_dsi_mapping_key(str(sheet_key))
            if source_file and source_file in excluded:
                continue
            sheet_name = None if inner_key == DSI_SINGLE_SHEET_KEY else inner_key
            out.append(
                (
                    sheet_name,
                    {str(k): str(v) for k, v in sheet_map.items()},
                    source_file,
                )
            )
        return out

    flat = {str(k): str(v) for k, v in fm.items() if isinstance(v, str)}
    if flat:
        return [(None, flat, None)]

    selected = wb.get("sheets") if isinstance(wb.get("sheets"), list) else []
    if len(selected) == 1 and isinstance(selected[0], dict):
        sn = selected[0].get("sheet_name")
        return [(sn if isinstance(sn, str) else None, flat, None)]
    return [(None, flat, None)]


def build_combined_dsi_dataframe(
    frames: list[tuple[str | None, pd.DataFrame, dict[str, str], str | None] | tuple[str | None, pd.DataFrame, dict[str, str]]],
    *,
    require_distributor_column: bool = True,
) -> tuple[pd.DataFrame, dict[str, str], list[dict[str, str]]]:
    """Normalize each mapped sheet to canonical columns and concatenate for one pass.

    When ``require_distributor_column`` is False (confirmed per-file distributor stamps),
    sheets may omit a mapped distributor column — stamps fill ``distributor_token`` after combine.
    """
    parts: list[pd.DataFrame] = []
    skipped: list[dict[str, str]] = []
    for frame in frames:
        if len(frame) == 4:
            sheet_name, sheet_df, sheet_map, source_file = frame
        else:
            sheet_name, sheet_df, sheet_map = frame  # type: ignore[misc]
            source_file = None
        label = sheet_name or "(default)"
        if source_file:
            label = f"{source_file} / {label}"
        if not sheet_map:
            skipped.append(
                {
                    "sheet_name": label,
                    "reason": "not_mapped_or_missing_distributor",
                }
            )
            continue
        if require_distributor_column and "distributor_token" not in sheet_map.values():
            skipped.append(
                {
                    "sheet_name": label,
                    "reason": "not_mapped_or_missing_distributor",
                }
            )
            continue
        if "product_identifier" not in sheet_map.values():
            skipped.append(
                {
                    "sheet_name": label,
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
        if source_file:
            norm["_dsi_source_file"] = source_file
        if norm.empty:
            skipped.append({"sheet_name": label, "reason": "empty_after_normalize"})
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
) -> list[tuple[str | None, pd.DataFrame, dict[str, str], str | None]]:
    """Load raw file(s) and yield per-sheet dataframes with resolved mappings."""
    mappings = resolve_dsi_sheet_mappings(job)
    if (
        len(mappings) == 1
        and mappings[0][0] is None
        and mappings[0][2] is None
        and not is_nested_dsi_field_mapping(job.field_mapping)
    ):
        return [(None, df_fallback, mappings[0][1], None)]

    raws = list(
        db.scalars(
            select(RawFileMetadata)
            .where(RawFileMetadata.job_id == job.id)
            .order_by(RawFileMetadata.id.asc())
        ).all()
    )
    if not raws:
        return [(None, df_fallback, mappings[0][1] if mappings else {}, None)]

    storage = get_storage_backend()
    file_frames: dict[str, dict[str | None, pd.DataFrame]] = {}
    for raw in raws:
        filename = raw_file_display_name(raw.storage_key)
        data = storage.read(raw.storage_key)
        sheets = load_dsi_workbook_sheet_frames(
            filename, data, header_row_overrides=header_row_overrides_for_file(job, filename)
        )
        file_frames[filename] = {sn: frame for sn, frame, _header_row in sheets}

    multi_file = len(raws) > 1 or job_has_multi_file_mapping(job.field_mapping)
    out: list[tuple[str | None, pd.DataFrame, dict[str, str], str | None]] = []
    for sheet_name, mapping, source_file in mappings:
        if source_file:
            sheets_map = file_frames.get(source_file)
            if sheets_map is None:
                continue
            frame = sheets_map.get(sheet_name) if sheet_name is not None else sheets_map.get(None)
            if frame is None and sheet_name is None and len(sheets_map) == 1:
                frame = next(iter(sheets_map.values()))
            if frame is not None and not frame.empty:
                out.append((sheet_name, frame, mapping, source_file))
            continue

        if multi_file and len(raws) == 1:
            filename = raw_file_display_name(raws[0].storage_key)
            sheets_map = file_frames.get(filename, {})
            frame = sheets_map.get(sheet_name) if sheet_name is not None else sheets_map.get(None)
            if frame is None and sheet_name is None and len(sheets_map) == 1:
                frame = next(iter(sheets_map.values()))
            if frame is not None and not frame.empty:
                out.append((sheet_name, frame, mapping, filename))
            continue

        if len(raws) == 1:
            filename = raw_file_display_name(raws[0].storage_key)
            data_frames = file_frames.get(filename, {})
            if sheet_name is None:
                if len(data_frames) == 1:
                    only = next(iter(data_frames.values()))
                    out.append((None, only, mapping, None))
                else:
                    out.append((None, df_fallback, mapping, None))
                continue
            frame = data_frames.get(sheet_name)
            if frame is not None and not frame.empty:
                out.append((sheet_name, frame, mapping, None))
            continue

    if not out and mappings:
        return [(None, df_fallback, mappings[0][1], mappings[0][2])]
    return out


def load_dsi_single_file_frame(job: ImportJob, filename: str, raw_bytes: bytes) -> pd.DataFrame:
    """The one sheet of a single-file job, read the way the mapping step read it (header row and all)."""
    sheets = load_dsi_workbook_sheet_frames(
        filename, raw_bytes, header_row_overrides=header_row_overrides_for_file(job, filename)
    )
    return sheets[0][1] if sheets else pd.DataFrame()


def describe_header_read(job: ImportJob, *, max_headers: int = 12) -> str:
    """Plain-words account of which header row was read per file/sheet, for zero-row failures."""
    meta = job.staged_metadata if isinstance(job.staged_metadata, dict) else {}
    wb = meta.get(DSI_SHEET_META_KEY) if isinstance(meta.get(DSI_SHEET_META_KEY), dict) else {}
    parts: list[str] = []
    for s in wb.get("sheets") or []:
        if not isinstance(s, dict):
            continue
        where = str(s.get("source_file") or job.file_name or "the file")
        if s.get("sheet_name"):
            where += f" (sheet {s['sheet_name']})"
        cols = [str(c) for c in (s.get("columns") or []) if _cell_as_header_label(c)]
        if not cols:
            parts.append(f"No header row found in {where}.")
            continue
        shown = ", ".join(cols[:max_headers]) + (f" and {len(cols) - max_headers} more" if len(cols) > max_headers else "")
        try:
            row_no = int(s.get("header_row") or 0) + 1
        except (TypeError, ValueError):
            row_no = 1
        how = "set by you" if s.get("header_row_user_set") else "found automatically"
        parts.append(f"Headers read from row {row_no} of {where} ({how}): {shown}.")
    return " ".join(parts)


def no_header_row_message(job: ImportJob) -> str | None:
    """Plain-words reason when no sheet of the job has a readable header row; ``None`` otherwise."""
    meta = job.staged_metadata if isinstance(job.staged_metadata, dict) else {}
    wb = meta.get(DSI_SHEET_META_KEY) if isinstance(meta.get(DSI_SHEET_META_KEY), dict) else {}
    sheets = [s for s in (wb.get("sheets") or []) if isinstance(s, dict)]
    if not sheets or any(_cell_as_header_label(c) for s in sheets for c in (s.get("columns") or [])):
        return None
    return (
        f"{describe_header_read(job)} Set \"Headers found on row\" to the row that holds the column names, "
        "then map the columns again."
    )


def persist_dsi_workbook_on_job(job: ImportJob, structure: dict[str, Any]) -> None:
    meta = dict(job.staged_metadata or {})
    meta[DSI_SHEET_META_KEY] = structure
    job.staged_metadata = meta
