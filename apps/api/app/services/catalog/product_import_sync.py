"""Synchronous product upserts for ingestion pipeline (Session, not AsyncSession)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.dimensions import DimChannel, DimProduct

_STR_DIM_KEYS = (
    "part_number",
    "sales_model_name",
    "model_name",
    "marketing_name",
    "series_name",
    "product_line",
    "ean",
    "upc",
    "business_unit",
    "lifecycle_status",
    "country_code",
)

# Max lengths aligned with DimProduct (app.models.dimensions).
_STR_DIM_MAX: dict[str, int] = {
    "part_number": 128,
    "sales_model_name": 512,
    "model_name": 512,
    "marketing_name": 512,
    "series_name": 256,
    "product_line": 256,
    "ean": 32,
    "upc": 32,
    "business_unit": 128,
    "lifecycle_status": 64,
    "country_code": 8,
}


def _strip_optional(v: Any) -> str | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    if not s:
        return None
    low = s.lower()
    if low in ("nan", "nat", "none", "<na>", "null", "#n/a", "n/a"):
        return None
    return s


def _bounded_str(key: str, val: str | None, sku: str) -> str | None:
    if val is None:
        return None
    mx = _STR_DIM_MAX.get(key)
    if mx is not None and len(val) > mx:
        raise ValueError(
            f"Field {key!r} exceeds database limit ({mx} chars) for SKU {sku!r} (got {len(val)})."
        )
    return val


def _parse_date_val(v: Any) -> date | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, pd.Timestamp):
        return v.date()
    ts = pd.to_datetime(v, errors="coerce")
    if pd.isna(ts):
        return None
    return ts.date()


def sync_bulk_upsert_products_from_rows(session: Session, rows: list[dict[str, Any]]) -> dict[str, int]:
    """Upsert dim_product rows by canonical technical key (`sku` column in DB).

    Each dict requires: sku (technical id), name.
    Optional: part_number (defaults to sku), category, channel_code, form_factor, price_band,
    sales_model_name, model_name, marketing_name, series_name, product_line, ean, upc,
    business_unit, lifecycle_status, country_code, launch_date, end_of_life_date (→ retired_date).
    """
    channels = {c.code.strip().lower(): c.id for c in session.scalars(select(DimChannel)).all()}
    created = 0
    updated = 0

    for r in rows:
        def take_str(key: str) -> tuple[str | None, bool]:
            """Return (stripped value or None, whether key was present)."""
            if key not in r:
                return None, False
            return _strip_optional(r.get(key)), True

        sku = _strip_optional(r.get("sku"))
        name = _strip_optional(r.get("name"))
        if not sku or not name:
            continue
        if len(sku) > 128:
            raise ValueError(f"sku exceeds database limit (128 chars) for value {sku[:80]!r}…")
        if len(name) > 512:
            raise ValueError(f"name exceeds database limit (512 chars) for SKU {sku!r}.")

        pn, has_pn = take_str("part_number")
        if pn is not None:
            pn = _bounded_str("part_number", pn, sku)

        cat, has_cat = take_str("category")
        if cat is not None and len(cat) > 256:
            raise ValueError(f"category exceeds database limit (256 chars) for SKU {sku!r}.")
        ff, has_ff = take_str("form_factor")
        if ff is not None and len(ff) > 128:
            raise ValueError(f"form_factor exceeds database limit (128 chars) for SKU {sku!r}.")
        pb, has_pb = take_str("price_band")
        if pb is not None and len(pb) > 64:
            raise ValueError(f"price_band exceeds database limit (64 chars) for SKU {sku!r}.")

        channel_id = None
        has_ch = False
        if "channel_code" in r:
            has_ch = True
            ch_raw = _strip_optional(r.get("channel_code"))
            if ch_raw:
                channel_id = channels.get(ch_raw.lower())
                if channel_id is None:
                    raise ValueError(f"Unknown channel_code {ch_raw!r} for SKU {sku!r}")

        has_ld = "launch_date" in r
        launch_d = _parse_date_val(r.get("launch_date")) if has_ld else None
        has_eol = "end_of_life_date" in r
        eol_d = _parse_date_val(r.get("end_of_life_date")) if has_eol else None

        existing = session.execute(select(DimProduct).where(DimProduct.sku == sku)).scalar_one_or_none()
        if existing:
            existing.name = name
            if has_pn:
                existing.part_number = pn or sku
            else:
                existing.part_number = existing.part_number or sku
            if has_cat:
                existing.category = cat
            if has_ch:
                existing.channel_id = channel_id
            if has_ld:
                existing.launch_date = launch_d
            if has_eol:
                existing.retired_date = eol_d
            if has_ff:
                existing.form_factor = ff
            if has_pb:
                existing.price_band = pb
            for k in _STR_DIM_KEYS:
                if k == "part_number":
                    continue
                if k in r:
                    v = _bounded_str(k, _strip_optional(r.get(k)), sku)
                    setattr(existing, k, v)
            updated += 1
        else:
            kwargs: dict[str, Any] = {
                "sku": sku,
                "name": name,
                "part_number": (pn or sku) if has_pn else sku,
                "category": cat if has_cat else None,
                "form_factor": ff if has_ff else None,
                "price_band": pb if has_pb else None,
                "channel_id": channel_id if has_ch else None,
                "launch_date": launch_d if has_ld else None,
                "retired_date": eol_d if has_eol else None,
            }
            for k in _STR_DIM_KEYS:
                if k == "part_number":
                    continue
                if k in r:
                    kwargs[k] = _bounded_str(k, _strip_optional(r.get(k)), sku)
            session.add(DimProduct(**kwargs))
            created += 1
    session.flush()
    return {"created": created, "updated": updated, "total": len(rows)}
