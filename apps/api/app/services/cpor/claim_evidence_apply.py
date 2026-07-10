"""CPOR claim-evidence apply: parse flat file → upsert cpor_claim_evidence_line (U5)."""

from __future__ import annotations

import io
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.cpor import CporCase, CporClaimEvidenceLine
from app.services.cpor.claim_evidence import (
    claim_evidence_source_key,
    load_product_resolution_index,
    resolve_claim_product_id,
)

_CANONICAL_ALIASES: dict[str, tuple[str, ...]] = {
    "product_token": (
        "product_token",
        "source_model_token",
        "sku",
        "item",
        "item_code",
        "model",
        "sales_model",
        "sales_model_name",
    ),
    "sale_date": ("sale_date", "date", "transaction_date", "invoice_date"),
    "units": ("units", "qty", "quantity", "result_qty", "units_sold"),
    "unit_price": ("unit_price", "price", "unit_sell_price"),
    "ean": ("ean", "ean_code", "barcode"),
}


def _norm_col(c: str) -> str:
    return str(c or "").strip().lower().replace(" ", "_")


def _map_headers(columns: list[str]) -> dict[str, str]:
    """Map file header → canonical field."""
    by_norm = {_norm_col(c): c for c in columns}
    out: dict[str, str] = {}
    for canon, aliases in _CANONICAL_ALIASES.items():
        for a in aliases:
            if a in by_norm:
                out[canon] = by_norm[a]
                break
    return out


def _parse_date(val: Any) -> date | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    s = str(val).strip()
    if not s or s.lower() in ("nan", "none"):
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    try:
        return pd.to_datetime(s).date()
    except Exception:
        return None


def _parse_num(val: Any) -> Decimal | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        return Decimal(str(val).strip().replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def parse_claim_evidence_dataframe(df: pd.DataFrame) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Return (row dicts, blocking header errors)."""
    if df is None or df.empty:
        return [], [{"code": "empty_file", "message": "Claim evidence file has no rows"}]
    mapping = _map_headers([str(c) for c in df.columns])
    errors: list[dict[str, str]] = []
    if "product_token" not in mapping:
        errors.append({"code": "missing_product", "message": "Need a product/SKU/model column"})
    if "sale_date" not in mapping:
        errors.append({"code": "missing_date", "message": "Need a sale_date / date column"})
    if "units" not in mapping:
        errors.append({"code": "missing_units", "message": "Need a units / qty column"})
    if errors:
        return [], errors

    rows: list[dict[str, Any]] = []
    for i, ser in df.iterrows():
        raw = {str(k): (None if pd.isna(v) else v) for k, v in ser.items()}
        token = str(raw.get(mapping["product_token"]) or "").strip()
        sale_d = _parse_date(raw.get(mapping["sale_date"]))
        units = _parse_num(raw.get(mapping["units"]))
        price = _parse_num(raw.get(mapping["unit_price"])) if "unit_price" in mapping else None
        ean = None
        if "ean" in mapping:
            ean = str(raw.get(mapping["ean"]) or "").strip() or None
        if not token or sale_d is None or units is None:
            continue
        rows.append(
            {
                "source_model_token": token,
                "sale_date": sale_d,
                "units": float(units),
                "unit_price": float(price) if price is not None else None,
                "ean": ean,
                "raw_source_row": {str(k): (str(v) if v is not None else None) for k, v in raw.items()},
                "row_ordinal": int(i) if isinstance(i, int) else len(rows),
            }
        )
    return rows, []


def load_claim_evidence_frames(filename: str, raw_bytes: bytes) -> pd.DataFrame:
    lower = (filename or "").lower()
    if lower.endswith(".csv"):
        return pd.read_csv(io.BytesIO(raw_bytes))
    return pd.read_excel(io.BytesIO(raw_bytes), engine="openpyxl")


def apply_claim_evidence_to_case(
    session: Session,
    *,
    case_id: int,
    filename: str,
    raw_bytes: bytes,
    import_job_id: int | None = None,
    include_out_of_window: bool = False,
) -> dict[str, Any]:
    """Parse + upsert claim lines for a case. Unresolved products FLAG, never block."""
    case = session.get(CporCase, case_id)
    if case is None:
        raise ValueError(f"cpor_case id={case_id} not found")

    df = load_claim_evidence_frames(filename, raw_bytes)
    parsed, header_errors = parse_claim_evidence_dataframe(df)
    if header_errors:
        return {
            "ok": False,
            "case_id": case_id,
            "blocking_errors": header_errors,
            "rows_upserted": 0,
        }

    index = load_product_resolution_index(session)
    window_start = case.window_start
    window_end = case.window_end

    values: list[dict[str, Any]] = []
    unresolved = 0
    ambiguous = 0
    out_of_window = 0
    in_window = 0

    for row in parsed:
        sale_d: date = row["sale_date"]
        in_win = True
        if window_start and sale_d < window_start:
            in_win = False
        if window_end and sale_d > window_end:
            in_win = False
        if not in_win:
            out_of_window += 1
            if not include_out_of_window:
                # Still persist (spec: retain + flag); rollup excludes unless override.
                pass
        else:
            in_window += 1

        pid, _tok, status = resolve_claim_product_id(
            index,
            item_code=row["source_model_token"],
            ean=row.get("ean"),
            sales_model=row["source_model_token"],
        )
        if status == "unresolved":
            unresolved += 1
        elif status == "ambiguous":
            ambiguous += 1

        raw = dict(row["raw_source_row"] or {})
        raw["_cpor_flags"] = {
            "out_of_window": not in_win,
            "product_status": status,
            "include_out_of_window_override": bool(include_out_of_window and not in_win),
        }

        sk = claim_evidence_source_key(
            case_id=case_id,
            sale_date=sale_d,
            source_model_token=row["source_model_token"],
            units=row["units"],
            unit_price=row.get("unit_price"),
            row_ordinal=int(row.get("row_ordinal") or 0),
        )
        values.append(
            {
                "case_id": case_id,
                "import_job_id": import_job_id,
                "product_id": pid,
                "source_model_token": row["source_model_token"][:256],
                "sale_date": sale_d,
                "units": row["units"],
                "unit_price": row.get("unit_price"),
                "raw_source_row": raw,
                "source_key": sk,
            }
        )

    upserted = 0
    if values:
        # De-dup by source_key within chunk
        by_key: dict[str, dict[str, Any]] = {}
        for v in values:
            by_key[v["source_key"]] = v
        chunk = list(by_key.values())
        stmt = pg_insert(CporClaimEvidenceLine).values(chunk)
        stmt = stmt.on_conflict_do_update(
            index_elements=["source_key"],
            set_={
                "product_id": stmt.excluded.product_id,
                "source_model_token": stmt.excluded.source_model_token,
                "sale_date": stmt.excluded.sale_date,
                "units": stmt.excluded.units,
                "unit_price": stmt.excluded.unit_price,
                "raw_source_row": stmt.excluded.raw_source_row,
                "import_job_id": stmt.excluded.import_job_id,
                "case_id": stmt.excluded.case_id,
            },
        )
        session.execute(stmt)
        session.flush()
        upserted = len(chunk)

    return {
        "ok": True,
        "case_id": case_id,
        "rows_parsed": len(parsed),
        "rows_upserted": upserted,
        "in_window_rows": in_window,
        "out_of_window_rows": out_of_window,
        "unresolved_product_rows": unresolved,
        "ambiguous_product_rows": ambiguous,
        "blocking_errors": [],
    }


def list_claim_evidence_for_case(session: Session, case_id: int) -> list[CporClaimEvidenceLine]:
    return list(
        session.scalars(
            select(CporClaimEvidenceLine)
            .where(CporClaimEvidenceLine.case_id == case_id)
            .order_by(CporClaimEvidenceLine.sale_date, CporClaimEvidenceLine.id)
        ).all()
    )
