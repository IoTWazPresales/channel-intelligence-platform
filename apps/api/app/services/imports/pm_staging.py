"""Product Master staging helpers (no per-row JSONB blob; file is source of truth)."""

from __future__ import annotations

from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.dimensions import DimProduct
from app.services.imports.pm_dataframe_sanitize import normalize_scalar_for_pm
from app.utils.json_safe import to_jsonable

PM_STAGED_ROW_COUNT_KEY = "pm_staged_row_count"
_PM_SKU_BATCH_SIZE = 500


def stage_raw_columns_from_decisions(mapping_decisions: dict[str, Any] | None) -> list[str]:
    if not mapping_decisions:
        return []
    out: list[str] = []
    for h, m in mapping_decisions.items():
        if isinstance(m, dict) and str(m.get("disposition") or "").strip() == "stage_raw":
            out.append(str(h))
    return out


def attribute_candidate_columns_from_decisions(mapping_decisions: dict[str, Any] | None) -> list[str]:
    if not mapping_decisions:
        return []
    out: list[str] = []
    for h, m in mapping_decisions.items():
        if isinstance(m, dict) and str(m.get("disposition") or "").strip() == "attribute_candidate":
            out.append(str(h))
    return out


def row_stage_fragment_from_row(row: Any, stage_cols: list[str]) -> dict[str, Any]:
    """Build stage_raw cell map for one file row (JSON-safe values)."""
    if not stage_cols:
        return {}
    frag: dict[str, Any] = {}
    for sc in stage_cols:
        v = normalize_scalar_for_pm(row.get(sc))
        if v is not None and str(v).strip() != "":
            frag[sc] = to_jsonable(v)
    return frag


def row_has_stage_raw_data(row: Any, stage_cols: list[str]) -> bool:
    return bool(row_stage_fragment_from_row(row, stage_cols))


def _is_legacy_pm_row_staging_key(key: str, value: Any) -> bool:
    return key.isdigit() and isinstance(value, dict)


def scrub_pm_row_staging_keys(meta: dict[str, Any]) -> dict[str, Any]:
    """Remove legacy per-row index maps; preserve DSI/task slots and pm_staged_row_count."""
    return {k: v for k, v in meta.items() if not _is_legacy_pm_row_staging_key(k, v)}


def pm_staged_row_count_from_metadata(staged_metadata: Any) -> int:
    if not isinstance(staged_metadata, dict):
        return 0
    raw = staged_metadata.get(PM_STAGED_ROW_COUNT_KEY)
    if isinstance(raw, int):
        return raw
    if isinstance(raw, (float, str)) and str(raw).strip().isdigit():
        return int(raw)
    # Legacy jobs: count row-index dict keys
    return sum(1 for k, v in staged_metadata.items() if _is_legacy_pm_row_staging_key(k, v))


def persist_pm_staged_row_count(job: Any, count: int) -> None:
    """Set scalar staged row count on import_job.staged_metadata without row-index blobs."""
    meta = scrub_pm_row_staging_keys(
        dict(job.staged_metadata or {}) if isinstance(job.staged_metadata, dict) else {}
    )
    if count > 0:
        meta[PM_STAGED_ROW_COUNT_KEY] = int(count)
    else:
        meta.pop(PM_STAGED_ROW_COUNT_KEY, None)
    job.staged_metadata = to_jsonable(meta) if meta else None


def batch_load_dim_products_by_sku(
    db: Session,
    skus: list[str],
    *,
    chunk_size: int = _PM_SKU_BATCH_SIZE,
) -> dict[str, DimProduct]:
    """Load dim_product rows for many SKUs in chunked IN queries."""
    unique = list(dict.fromkeys(s for s in skus if s))
    out: dict[str, DimProduct] = {}
    if not unique:
        return out
    for offset in range(0, len(unique), chunk_size):
        chunk = unique[offset : offset + chunk_size]
        rows = db.scalars(select(DimProduct).where(DimProduct.sku.in_(chunk))).all()
        for prod in rows:
            if prod.sku:
                out[str(prod.sku)] = prod
    return out


def collect_technical_ids_from_df(
    df: pd.DataFrame,
    tech_col: str,
) -> list[str]:
    from app.services.imports.pm_dataframe_sanitize import scalar_to_clean_str

    ids: list[str] = []
    for _, row in df.iterrows():
        tid = scalar_to_clean_str(row.get(tech_col)) or ""
        if tid:
            ids.append(tid)
    return ids
