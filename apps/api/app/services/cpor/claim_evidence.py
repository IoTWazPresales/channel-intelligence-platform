"""CPOR claim-evidence source_key + product resolution (U5)."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.services.imports.distributor_sales_inventory import ProductResolutionIndex


def claim_evidence_source_key(
    *,
    case_id: int,
    sale_date: date,
    source_model_token: str,
    units: float,
    unit_price: float | None = None,
    row_ordinal: int = 0,
) -> str:
    """Stable upsert key: case + date + token + units/price + ordinal (dedupe within file)."""
    tok = (source_model_token or "").strip().upper()[:120]
    price_part = "" if unit_price is None else f"|p={unit_price}"
    return f"cpor-claim|{case_id}|{sale_date.isoformat()}|{tok}|u={units}{price_part}|r={row_ordinal}"[:256]


def resolve_claim_product_id(
    index: ProductResolutionIndex,
    *,
    item_code: str | None = None,
    ean: str | None = None,
    sales_model: str | None = None,
) -> tuple[int | None, str | None, str]:
    """Spec §3 tier order for claims: item → EAN → sales model. Never auto-create.

    Returns (product_id|None, matched_token, status) where status is
    resolved | unresolved | ambiguous.
    """
    from app.services.imports.distributor_sales_inventory import _product_token_key

    sku = (item_code or "").strip()
    if sku:
        key = _product_token_key(sku)
        if key in index.sku_to_id:
            return int(index.sku_to_id[key]), sku, "resolved"
        part_ids = index.part_number_to_ids.get(key) or []
        if len(part_ids) == 1:
            return int(part_ids[0]), sku, "resolved"
        if len(part_ids) > 1:
            return None, sku, "ambiguous"

    ean_s = (ean or "").strip()
    if ean_s:
        key = _product_token_key(ean_s)
        ids = index.ean_to_ids.get(key) or []
        if len(ids) == 1:
            return int(ids[0]), ean_s, "resolved"
        if len(ids) > 1:
            return None, ean_s, "ambiguous"

    sm = (sales_model or "").strip()
    if sm:
        key = _product_token_key(sm)
        ids = index.sales_model_name_to_ids.get(key) or []
        if len(ids) == 1:
            return int(ids[0]), sm, "resolved"
        if len(ids) > 1:
            return None, sm, "ambiguous"

    token = sku or ean_s or sm or ""
    return None, token or None, "unresolved"


def load_product_resolution_index(session: Session) -> ProductResolutionIndex:
    from app.services.imports.product_resolution_index_cache import get_product_resolution_index

    return get_product_resolution_index(session)
