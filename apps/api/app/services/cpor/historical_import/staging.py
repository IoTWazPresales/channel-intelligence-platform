"""Upsert historical CPOR staging lines by source_key (H2)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.cpor_historical import ImportCporHistoricalStagingLine
from app.utils.json_safe import to_jsonable

_STAGING_UPSERT_COLS = (
    "import_job_id",
    "source_row_number",
    "sheet_name",
    "channel",
    "case_code",
    "case_name",
    "promotion_type_raw",
    "promotion_type",
    "window_start",
    "window_end",
    "status_raw",
    "lifecycle_status",
    "pod_quarter",
    "product_line",
    "distributor_token",
    "customer_token",
    "sales_model_token",
    "resolved_customer_id",
    "resolved_distributor_id",
    "resolved_product_id",
    "soh_snapshot",
    "estimate_qty",
    "result_qty",
    "srp",
    "vat_rate",
    "dealer_margin_pct",
    "cost_basis",
    "dealer_price",
    "support_unit",
    "ttl_support",
    "roe_snapshot",
    "support_usd",
    "ttl_support_usd",
    "ttl_result",
    "ttl_result_usd",
    "remark",
    "skip_apply",
    "flags_json",
    "source_snapshot_json",
    "raw_source_row",
)


def _row_to_values(job_id: int, row: dict[str, Any]) -> dict[str, Any]:
    flags = row.get("flags_json")
    if isinstance(flags, list):
        flags = {"flags": flags}
    return {
        "import_job_id": job_id,
        "source_key": str(row["source_key"]),
        "source_row_number": int(row.get("source_row_number") or 0),
        "sheet_name": str(row.get("sheet_name") or ""),
        "channel": str(row.get("channel") or "reseller"),
        "case_code": str(row.get("case_code") or "").strip(),
        "case_name": row.get("case_name"),
        "promotion_type_raw": row.get("promotion_type_raw"),
        "promotion_type": row.get("promotion_type") or row.get("promotion_type_raw"),
        "window_start": row.get("window_start"),
        "window_end": row.get("window_end"),
        "status_raw": row.get("status_raw"),
        "lifecycle_status": row.get("lifecycle_status"),
        "pod_quarter": row.get("pod_quarter"),
        "product_line": row.get("product_line"),
        "distributor_token": row.get("distributor_token"),
        "customer_token": row.get("customer_token"),
        "sales_model_token": row.get("sales_model_token"),
        "resolved_customer_id": row.get("resolved_customer_id"),
        "resolved_distributor_id": row.get("resolved_distributor_id"),
        "resolved_product_id": row.get("resolved_product_id"),
        "soh_snapshot": row.get("soh_snapshot"),
        "estimate_qty": row.get("estimate_qty"),
        "result_qty": row.get("result_qty"),
        "srp": row.get("srp"),
        "vat_rate": row.get("vat_rate"),
        "dealer_margin_pct": row.get("dealer_margin_pct"),
        "cost_basis": row.get("cost_basis"),
        "dealer_price": row.get("dealer_price"),
        "support_unit": row.get("support_unit"),
        "ttl_support": row.get("ttl_support"),
        "roe_snapshot": row.get("roe_snapshot"),
        "support_usd": row.get("support_usd"),
        "ttl_support_usd": row.get("ttl_support_usd"),
        "ttl_result": row.get("ttl_result"),
        "ttl_result_usd": row.get("ttl_result_usd"),
        "remark": row.get("remark"),
        "skip_apply": bool(row.get("skip_apply") or False),
        "flags_json": to_jsonable(flags) if flags is not None else None,
        "source_snapshot_json": to_jsonable(row.get("source_snapshot_json")),
        "raw_source_row": to_jsonable(row.get("raw_source_row") or {}),
    }


def upsert_historical_staging_lines(
    db: Session,
    *,
    job_id: int,
    rows: list[dict[str, Any]],
    chunk_size: int = 500,
) -> int:
    """Chunked INSERT … ON CONFLICT (source_key) DO UPDATE. Returns row count written."""
    if not rows:
        return 0
    written = 0
    # Dedup within chunk by source_key (Postgres rejects same key twice in one statement).
    by_key: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str(row.get("source_key") or "").strip()
        if not key:
            continue
        by_key[key] = _row_to_values(job_id, row)

    values_list = list(by_key.values())
    for i in range(0, len(values_list), chunk_size):
        chunk = values_list[i : i + chunk_size]
        stmt = pg_insert(ImportCporHistoricalStagingLine).values(chunk)
        update_cols = {c: stmt.excluded[c] for c in _STAGING_UPSERT_COLS}
        db.execute(stmt.on_conflict_do_update(constraint="uq_import_cpor_historical_staging_source_key", set_=update_cols))
        written += len(chunk)
    db.flush()
    return written
