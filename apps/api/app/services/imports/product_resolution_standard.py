"""Single-match product token resolution for non-DSI importers.

Documented tier order (one eligible id only):
  item_code (SKU) → part_number → EAN → UPC → sales_model_name

DSI steward / shipment evidence use ``distributor_sales_inventory._resolve_product``
(full lifecycle, shipment tie-break, steward-alias precedence). Do not route DSI through
this module — behaviour there is intentionally richer and frozen for steward parity.

N-0111 (Warren 2026-10-19): a file may carry each product identifier in its own column.
``resolve_product_by_identifiers`` resolves such a row over the same index and the same token keys
(``_product_token_key``), one identifier slot at a time in the platform order
Part number → Barcode → Sales model, then the customer's own product code through the customer's
aliases. Exact / normalised-exact only, never fuzzy; a slot wins only when it matches exactly one
Product Master row; identifiers that point at different products are reported as a conflict, never
guessed. Barcode matches Product Master EAN **or** UPC, as DSI and shipment evidence do.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

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


# --------------------------------------------------------------------------- identifier slots

#: Slot order of a row's Product Master identifiers (Warren 2026-10-19). The customer's own product
#: code is last: it resolves through the customer's aliases, not through Product Master.
SLOT_PART_NUMBER = "part_number"
SLOT_BARCODE = "barcode"
SLOT_SALES_MODEL = "sales_model"
SLOT_ANY = "any_identifier"  # older layouts: one column that may hold any identifier
SLOT_CUSTOMER_CODE = "customer_code"
SLOT_ORDER: tuple[str, ...] = (SLOT_PART_NUMBER, SLOT_BARCODE, SLOT_SALES_MODEL, SLOT_ANY, SLOT_CUSTOMER_CODE)

# Which Product Master fields each slot is matched against, in the order tried.
# Part number: item code (SKU) then part number, the standard's own order.
# Barcode: EAN or UPC. Sales model: sales model name, then model name, then marketing name (DSI's order).
_SLOT_TIERS: dict[str, tuple[str, ...]] = {
    SLOT_PART_NUMBER: ("sku", "part_number"),
    SLOT_BARCODE: ("barcode",),
    SLOT_SALES_MODEL: ("sales_model_name", "model_name", "marketing_name"),
    SLOT_ANY: ("sku", "part_number", "ean", "upc", "sales_model_name"),
}

STATUS_UNIQUE = "unique"
STATUS_AMBIGUOUS = "ambiguous"
STATUS_NO_MATCH = "no_match"

RESULT_RESOLVED = "resolved"
RESULT_CONFLICT = "conflict"
RESULT_AMBIGUOUS = "ambiguous"
RESULT_UNMATCHED = "unmatched"

TIER_CONFLICT = "identifier_conflict"


@dataclass(frozen=True)
class IdentifierOutcome:
    """What one identifier on a row matched."""

    slot: str
    token: str
    status: str
    tier: str | None = None
    product_ids: tuple[int, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "slot": self.slot,
            "token": self.token,
            "status": self.status,
            "tier": self.tier,
            "product_ids": list(self.product_ids),
        }


@dataclass(frozen=True)
class ProductIdentifierMatch:
    """The result for one row: the product (only when the identifiers agree) and why."""

    result: str
    product_id: int | None
    tier: str | None
    outcomes: tuple[IdentifierOutcome, ...] = field(default_factory=tuple)

    def to_json(self) -> dict[str, Any]:
        return {
            "result": self.result,
            "product_id": self.product_id,
            "tier": self.tier,
            "outcomes": [o.to_json() for o in self.outcomes],
        }


def _tier_ids(idx: ProductResolutionIndex, tier: str, key: str) -> tuple[int, ...]:
    if tier == "sku":
        pid = idx.sku_to_id.get(key)
        return (int(pid),) if pid is not None else ()
    if tier == "barcode":
        return tuple(sorted({int(i) for i in (*idx.ean_to_ids.get(key, ()), *idx.upc_to_ids.get(key, ()))}))
    maps = {
        "part_number": idx.part_number_to_ids,
        "ean": idx.ean_to_ids,
        "upc": idx.upc_to_ids,
        "sales_model_name": idx.sales_model_name_to_ids,
        "model_name": idx.model_name_to_ids,
        "marketing_name": idx.marketing_name_to_ids,
    }
    return tuple(int(i) for i in maps[tier].get(key, ()))


def _barcode_tier_name(idx: ProductResolutionIndex, key: str) -> str:
    in_ean, in_upc = key in idx.ean_to_ids, key in idx.upc_to_ids
    return "ean_upc" if in_ean and in_upc else ("ean" if in_ean else "upc")


def _match_slot(idx: ProductResolutionIndex, slot: str, token: str) -> IdentifierOutcome:
    """Match one identifier against its Product Master fields: the first field with exactly one product wins."""
    key = _product_token_key(token)
    if not key:
        return IdentifierOutcome(slot, token, STATUS_NO_MATCH)
    first_ambiguous: tuple[str, tuple[int, ...]] | None = None
    for tier in _SLOT_TIERS[slot]:
        ids = _tier_ids(idx, tier, key)
        if len(ids) == 1:
            name = _barcode_tier_name(idx, key) if tier == "barcode" else tier
            return IdentifierOutcome(slot, token, STATUS_UNIQUE, name, ids)
        if len(ids) > 1 and first_ambiguous is None:
            first_ambiguous = ("ean_upc" if tier == "barcode" else tier, ids)
    if first_ambiguous is not None:
        return IdentifierOutcome(slot, token, STATUS_AMBIGUOUS, first_ambiguous[0], first_ambiguous[1])
    return IdentifierOutcome(slot, token, STATUS_NO_MATCH)


def resolve_product_by_identifiers(
    idx: ProductResolutionIndex,
    identifiers: Mapping[str, str | None],
    *,
    customer_code_alias: Callable[[str], int | None] | None = None,
) -> ProductIdentifierMatch:
    """Resolve a row from every identifier it carries (``identifiers`` maps slot -> raw cell text).

    The product is the first slot, in ``SLOT_ORDER``, that matches exactly one Product Master row,
    provided no other identifier on the row points at a different product. A slot that matches more
    than one product is ambiguous: it is passed over, and if another slot picks a product outside its
    matches that is a disagreement too. Identifiers that disagree give no product (``conflict``); the
    steward decides. ``customer_code_alias`` maps the customer's own product code to a product through
    the customer's confirmed aliases (None when the customer has none).
    """
    outcomes: list[IdentifierOutcome] = []
    for slot in SLOT_ORDER:
        token = identifiers.get(slot)
        if token is None or not _product_token_key(token):
            continue
        token = str(token).strip()
        if slot == SLOT_CUSTOMER_CODE:
            pid = customer_code_alias(token) if customer_code_alias is not None else None
            if pid is None:
                outcomes.append(IdentifierOutcome(slot, token, STATUS_NO_MATCH))
            else:
                outcomes.append(IdentifierOutcome(slot, token, STATUS_UNIQUE, "customer_alias", (int(pid),)))
            continue
        outcomes.append(_match_slot(idx, slot, token))

    unique = [o for o in outcomes if o.status == STATUS_UNIQUE]
    winners = {o.product_ids[0] for o in unique}
    if len(winners) > 1:
        return ProductIdentifierMatch(RESULT_CONFLICT, None, TIER_CONFLICT, tuple(outcomes))
    if len(winners) == 1:
        winner = next(iter(winners))
        if any(o.status == STATUS_AMBIGUOUS and winner not in o.product_ids for o in outcomes):
            return ProductIdentifierMatch(RESULT_CONFLICT, None, TIER_CONFLICT, tuple(outcomes))
        first = unique[0]
        return ProductIdentifierMatch(RESULT_RESOLVED, winner, first.tier, tuple(outcomes))
    if any(o.status == STATUS_AMBIGUOUS for o in outcomes):
        return ProductIdentifierMatch(RESULT_AMBIGUOUS, None, None, tuple(outcomes))
    return ProductIdentifierMatch(RESULT_UNMATCHED, None, None, tuple(outcomes))
