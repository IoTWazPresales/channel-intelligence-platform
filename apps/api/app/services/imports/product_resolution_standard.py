"""Single-match product token resolution for non-DSI importers.

Documented tier order (one eligible id only):
  item_code (SKU) → part_number → EAN → UPC → sales_model_name

DSI steward / shipment evidence use ``distributor_sales_inventory._resolve_product``
(full lifecycle, shipment tie-break, steward-alias precedence). Do not route DSI through
this module — behaviour there is intentionally richer and frozen for steward parity.
"""

from __future__ import annotations

from app.services.imports.distributor_sales_inventory import (
    ProductResolutionIndex,
    _product_token_key,
)


def resolve_product_id_single_match(idx: ProductResolutionIndex, token: str) -> int | None:
    """Resolve a raw product token to dim_product.id when exactly one PM row matches a tier."""
    key = _product_token_key(token)
    if not key:
        return None
    if key in idx.sku_to_id:
        return int(idx.sku_to_id[key])
    part_ids = idx.part_number_to_ids.get(key)
    if part_ids and len(part_ids) == 1:
        return int(part_ids[0])
    ean_ids = idx.ean_to_ids.get(key)
    if ean_ids and len(ean_ids) == 1:
        return int(ean_ids[0])
    upc_ids = idx.upc_to_ids.get(key)
    if upc_ids and len(upc_ids) == 1:
        return int(upc_ids[0])
    sm_ids = idx.sales_model_name_to_ids.get(key)
    if sm_ids and len(sm_ids) == 1:
        return int(sm_ids[0])
    return None
