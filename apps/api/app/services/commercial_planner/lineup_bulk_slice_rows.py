"""Map bulk-backfill preview row slices to lineup_case_parser source_row_number identities."""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from sqlalchemy import select

from app.db.session_sync import SessionLocal
from app.models.dimensions import DimCustomer, DimDistributor, DimProduct
from app.services.commercial_planner.lineup_case_parser import _parse_file_to_row_dicts
from app.services.commercial_planner.lineup_customer_alias_resolution import (
    load_approved_customer_alias_id_by_token_sync,
)


def _clean_token(val: Any) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    return s if s and s.lower() not in ("nan", "none") else None


def _qty_key(val: Any) -> str | None:
    if val is None:
        return None
    try:
        return str(float(val))
    except (TypeError, ValueError):
        return _clean_token(val)


def row_match_key(row: dict[str, Any]) -> tuple[str | None, str | None, str | None, str | None, str | None]:
  """Stable identity for a lineup data row across preview + parse paths."""
  return (
      _clean_token(row.get("sku_raw")),
      _clean_token(row.get("part_number_raw")),
      _clean_token(row.get("model_raw")),
      _clean_token(row.get("customer_token")),
      _qty_key(row.get("quantity_units")),
  )


def load_lineup_parser_context_sync() -> dict[str, Any]:
    with SessionLocal() as session:
        products = list(session.scalars(select(DimProduct)).all())
        customers = list(session.scalars(select(DimCustomer)).all())
        distributors = list(session.scalars(select(DimDistributor)).all())
        customer_alias_map = load_approved_customer_alias_id_by_token_sync(session)

    product_map: dict[str, DimProduct] = {}
    for p in products:
        for val in (p.sku, p.part_number, p.model_name, p.sales_model_name):
            if val:
                key = val.lower().strip()
                if key and key not in product_map:
                    product_map[key] = p

    customer_map: dict[str, DimCustomer] = {}
    for c in customers:
        if c.name:
            customer_map[c.name.lower().strip()] = c
        if c.code:
            customer_map[c.code.lower().strip()] = c

    distributor_map: dict[str, DimDistributor] = {}
    for d in distributors:
        for val in (d.code, d.name):
            if val:
                key = val.lower().strip()
                if key and key not in distributor_map:
                    distributor_map[key] = d

    customers_by_id = {int(c.id): c for c in customers}
    return {
        "product_map": product_map,
        "customer_map": customer_map,
        "distributor_map": distributor_map,
        "customer_alias_map": customer_alias_map,
        "customers_by_id": customers_by_id,
    }


def parser_row_dicts_for_sheet(
    filename: str,
    file_bytes: bytes,
    *,
    sheet_name: str,
    parser_ctx: dict[str, Any],
) -> list[dict[str, Any]]:
    row_dicts, *_rest = _parse_file_to_row_dicts(
        filename,
        file_bytes,
        product_map=parser_ctx["product_map"],
        customer_map=parser_ctx["customer_map"],
        distributor_map=parser_ctx["distributor_map"],
        customer_alias_map=parser_ctx["customer_alias_map"],
        customers_by_id=parser_ctx["customers_by_id"],
        sheet_name=sheet_name,
    )
    return row_dicts


def map_slice_rows_to_source_row_numbers(
    slice_rows: list[dict[str, Any]],
    parser_row_dicts: list[dict[str, Any]],
) -> list[int]:
    """Resolve preview slice rows to parser ``source_row_number`` values (1:1, order preserved)."""
    buckets: dict[tuple, deque[int]] = defaultdict(deque)
    for rd in sorted(parser_row_dicts, key=lambda r: int(r["source_row_number"])):
        buckets[row_match_key(rd)].append(int(rd["source_row_number"]))

    out: list[int] = []
    missing: list[tuple] = []
    for row in slice_rows:
        key = row_match_key(row)
        if not buckets[key]:
            missing.append(key)
            continue
        out.append(buckets[key].popleft())

    if missing:
        raise ValueError(
            f"slice rows could not be aligned to parser source_row_number ({len(missing)} unmatched)"
        )
    return out


def filter_row_dicts_to_slice(
    row_dicts: list[dict[str, Any]],
    slice_source_rows: list[int],
) -> list[dict[str, Any]]:
    allowed = {int(x) for x in slice_source_rows}
    by_num = {int(rd["source_row_number"]): rd for rd in row_dicts}
    missing = sorted(allowed - set(by_num))
    if missing:
        raise ValueError(
            f"slice_source_rows not found in parsed sheet rows: missing source_row_number {missing}"
        )
    filtered = [by_num[n] for n in sorted(slice_source_rows)]
    if len(filtered) != len(slice_source_rows):
        raise ValueError("slice_source_rows produced duplicate parser row mapping")
    return filtered
