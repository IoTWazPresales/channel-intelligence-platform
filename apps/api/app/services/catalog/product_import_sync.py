"""Synchronous product upserts for ingestion pipeline (Session, not AsyncSession)."""

from __future__ import annotations

from collections import OrderedDict
from datetime import date, datetime
from typing import Any

import pandas as pd
from sqlalchemy import Boolean, Date, Integer, String, case, func, literal_column, select, true
from sqlalchemy import values as sql_values
from sqlalchemy import column as sql_column
from sqlalchemy.dialects.postgresql import insert as pg_insert
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


def _dedupe_rows_by_sku_last_wins(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep one row per stripped SKU; last occurrence in `rows` wins."""
    out: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for r in rows:
        sku = _strip_optional(r.get("sku"))
        if not sku:
            continue
        out[sku] = r
    return list(out.values())


def _staging_tuple(
    r: dict[str, Any],
    channels: dict[str, int],
) -> tuple[Any, ...] | None:
    """Parse one input row into a VALUES tuple (flags + raw fields). Returns None to skip."""

    def take_str(key: str) -> tuple[str | None, bool]:
        if key not in r:
            return None, False
        return _strip_optional(r.get(key)), True

    sku = _strip_optional(r.get("sku"))
    name = _strip_optional(r.get("name"))
    if not sku or not name:
        return None
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

    str_dim_flags: list[tuple[bool, str | None]] = []
    for k in _STR_DIM_KEYS:
        if k == "part_number":
            continue
        if k in r:
            v = _bounded_str(k, _strip_optional(r.get(k)), sku)
            str_dim_flags.append((True, v))
        else:
            str_dim_flags.append((False, None))

    return (
        sku,
        name,
        has_pn,
        pn,
        has_cat,
        cat,
        has_ch,
        channel_id,
        has_ld,
        launch_d,
        has_eol,
        eol_d,
        has_ff,
        ff,
        has_pb,
        pb,
        *str_dim_flags,
    )


def _build_staging_values_clause():
    """SQLAlchemy VALUES(...) construct for bulk upsert staging rows."""
    cols = [
        sql_column("sku", String(128)),
        sql_column("name", String(512)),
        sql_column("has_pn", Boolean),
        sql_column("part_number", String(128)),
        sql_column("has_cat", Boolean),
        sql_column("category", String(256)),
        sql_column("has_ch", Boolean),
        sql_column("channel_id", Integer),
        sql_column("has_ld", Boolean),
        sql_column("launch_date", Date),
        sql_column("has_eol", Boolean),
        sql_column("retired_date", Date),
        sql_column("has_ff", Boolean),
        sql_column("form_factor", String(128)),
        sql_column("has_pb", Boolean),
        sql_column("price_band", String(64)),
        sql_column("has_sales_model_name", Boolean),
        sql_column("sales_model_name", String(512)),
        sql_column("has_model_name", Boolean),
        sql_column("model_name", String(512)),
        sql_column("has_marketing_name", Boolean),
        sql_column("marketing_name", String(512)),
        sql_column("has_series_name", Boolean),
        sql_column("series_name", String(256)),
        sql_column("has_product_line", Boolean),
        sql_column("product_line", String(256)),
        sql_column("has_ean", Boolean),
        sql_column("ean", String(32)),
        sql_column("has_upc", Boolean),
        sql_column("upc", String(32)),
        sql_column("has_business_unit", Boolean),
        sql_column("business_unit", String(128)),
        sql_column("has_lifecycle_status", Boolean),
        sql_column("lifecycle_status", String(64)),
        sql_column("has_country_code", Boolean),
        sql_column("country_code", String(8)),
    ]
    return sql_values(*cols, name="pm_stage")


def _merge_select(st, d):
    """SELECT that merges staging flags with existing dim_product (LEFT JOIN)."""
    tbl = DimProduct.__table__

    def opt_str(has_col, st_col, d_col):
        return case((has_col, st_col), else_=d_col)

    part_number = case(
        (st.c.has_pn, func.coalesce(st.c.part_number, st.c.sku)),
        else_=func.coalesce(d.c.part_number, st.c.sku),
    )
    return select(
        st.c.sku,
        st.c.name,
        part_number.label("part_number"),
        opt_str(st.c.has_cat, st.c.category, d.c.category).label("category"),
        opt_str(st.c.has_ff, st.c.form_factor, d.c.form_factor).label("form_factor"),
        d.c.specs_json.label("specs_json"),
        opt_str(st.c.has_pb, st.c.price_band, d.c.price_band).label("price_band"),
        opt_str(st.c.has_sales_model_name, st.c.sales_model_name, d.c.sales_model_name).label("sales_model_name"),
        opt_str(st.c.has_model_name, st.c.model_name, d.c.model_name).label("model_name"),
        opt_str(st.c.has_marketing_name, st.c.marketing_name, d.c.marketing_name).label("marketing_name"),
        opt_str(st.c.has_series_name, st.c.series_name, d.c.series_name).label("series_name"),
        opt_str(st.c.has_product_line, st.c.product_line, d.c.product_line).label("product_line"),
        opt_str(st.c.has_ean, st.c.ean, d.c.ean).label("ean"),
        opt_str(st.c.has_upc, st.c.upc, d.c.upc).label("upc"),
        opt_str(st.c.has_business_unit, st.c.business_unit, d.c.business_unit).label("business_unit"),
        opt_str(st.c.has_lifecycle_status, st.c.lifecycle_status, d.c.lifecycle_status).label("lifecycle_status"),
        opt_str(st.c.has_country_code, st.c.country_code, d.c.country_code).label("country_code"),
        opt_str(st.c.has_ld, st.c.launch_date, d.c.launch_date).label("launch_date"),
        opt_str(st.c.has_eol, st.c.retired_date, d.c.retired_date).label("retired_date"),
        func.coalesce(d.c.is_active, true()).label("is_active"),
        opt_str(st.c.has_ch, st.c.channel_id, d.c.channel_id).label("channel_id"),
        func.coalesce(d.c.created_at, func.now()).label("created_at"),
        func.now().label("updated_at"),
    ).select_from(st.outerjoin(d, d.c.sku == st.c.sku))


def sync_bulk_upsert_products_from_rows(session: Session, rows: list[dict[str, Any]]) -> dict[str, int]:
    """Upsert dim_product rows by canonical technical key (`sku` column in DB).

    Incoming rows are deduplicated by stripped SKU (last occurrence wins, earlier dropped silently).
    One PostgreSQL ``INSERT .. ON CONFLICT (sku) DO UPDATE`` per chunk (no per-row SELECT).

    Each dict requires: sku (technical id), name.
    Optional: part_number (defaults to sku), category, channel_code, form_factor, price_band,
    sales_model_name, model_name, marketing_name, series_name, product_line, ean, upc,
    business_unit, lifecycle_status, country_code, launch_date, end_of_life_date (→ retired_date).
    """
    bind = session.get_bind()
    if bind is None or bind.dialect.name != "postgresql":
        raise RuntimeError("sync_bulk_upsert_products_from_rows requires PostgreSQL")

    channels = {c.code.strip().lower(): c.id for c in session.scalars(select(DimChannel)).all()}
    deduped = _dedupe_rows_by_sku_last_wins(rows)
    staging_rows: list[tuple[Any, ...]] = []
    for r in deduped:
        tup = _staging_tuple(r, channels)
        if tup is not None:
            staging_rows.append(tup)

    if not staging_rows:
        return {"created": 0, "updated": 0, "total": len(rows), "deduped": len(deduped), "merged": 0}

    tbl = DimProduct.__table__
    d = tbl.alias("d")
    insert_cols = [
        tbl.c.sku,
        tbl.c.name,
        tbl.c.part_number,
        tbl.c.category,
        tbl.c.form_factor,
        tbl.c.specs_json,
        tbl.c.price_band,
        tbl.c.sales_model_name,
        tbl.c.model_name,
        tbl.c.marketing_name,
        tbl.c.series_name,
        tbl.c.product_line,
        tbl.c.ean,
        tbl.c.upc,
        tbl.c.business_unit,
        tbl.c.lifecycle_status,
        tbl.c.country_code,
        tbl.c.launch_date,
        tbl.c.retired_date,
        tbl.c.is_active,
        tbl.c.channel_id,
        tbl.c.created_at,
        tbl.c.updated_at,
    ]

    created = 0
    updated = 0
    chunk_size = 400
    for start in range(0, len(staging_rows), chunk_size):
        chunk = staging_rows[start : start + chunk_size]
        st = _build_staging_values_clause().data(chunk).alias("st")
        merged = _merge_select(st, d).subquery("m")

        insert_stmt = pg_insert(tbl).from_select(insert_cols, select(*merged.c).select_from(merged))
        upsert_stmt = (
            insert_stmt.on_conflict_do_update(
                index_elements=[tbl.c.sku],
                set_={
                    tbl.c.name: insert_stmt.excluded.name,
                    tbl.c.part_number: insert_stmt.excluded.part_number,
                    tbl.c.category: insert_stmt.excluded.category,
                    tbl.c.form_factor: insert_stmt.excluded.form_factor,
                    tbl.c.price_band: insert_stmt.excluded.price_band,
                    tbl.c.sales_model_name: insert_stmt.excluded.sales_model_name,
                    tbl.c.model_name: insert_stmt.excluded.model_name,
                    tbl.c.marketing_name: insert_stmt.excluded.marketing_name,
                    tbl.c.series_name: insert_stmt.excluded.series_name,
                    tbl.c.product_line: insert_stmt.excluded.product_line,
                    tbl.c.ean: insert_stmt.excluded.ean,
                    tbl.c.upc: insert_stmt.excluded.upc,
                    tbl.c.business_unit: insert_stmt.excluded.business_unit,
                    tbl.c.lifecycle_status: insert_stmt.excluded.lifecycle_status,
                    tbl.c.country_code: insert_stmt.excluded.country_code,
                    tbl.c.launch_date: insert_stmt.excluded.launch_date,
                    tbl.c.retired_date: insert_stmt.excluded.retired_date,
                    tbl.c.channel_id: insert_stmt.excluded.channel_id,
                    tbl.c.updated_at: insert_stmt.excluded.updated_at,
                },
            )
            .returning(literal_column("(xmax = 0)").label("was_insert"))
        )

        for row in session.execute(upsert_stmt):
            if row.was_insert:
                created += 1
            else:
                updated += 1

    session.flush()
    merged = created + updated
    return {
        "created": created,
        "updated": updated,
        "total": len(rows),
        "deduped": len(deduped),
        "merged": merged,
    }
