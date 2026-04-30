"""Shared column-header → canonical field mapping for commercial current lineup uploads.

Mirrors the proven rules in ``app.services.imports.historical_lineup`` (pattern MSRP roots,
promo disqualifiers, claimed-column exclusivity) for ``CommercialLineupLine`` field names.
"""
from __future__ import annotations

import re
from typing import Any

# Pattern-fallback roots for period-prefixed MSRP/SRP/RRP columns (e.g. "Q2 MSRP", "FY SRP", "2026 MSRP").
_MSRP_PATTERN_ROOTS: frozenset[str] = frozenset({"msrp", "srp", "rrp", "listprice", "retailprice"})
_PROMO_DISQUALIFIERS: frozenset[str] = frozenset({"promo", "deal", "special"})

# Order matters: first canonical match wins; promo aliases must claim "Promo SRP" before MSRP pattern fallback.
_COMMERCIAL_LINEUP_ALIASES: dict[str, list[str]] = {
    "sku_raw": ["sku", "item", "product_sku", "sku_raw"],
    "part_number_raw": ["part_number", "mpn", "part_no", "part no", "sales_part_number", "part number"],
    "model_raw": ["model", "model_name", "model name", "series"],
    "customer_token": ["customer", "customer_code", "account", "account_name", "end customer", "buyer", "sold to"],
    "distributor_token": ["distributor", "disti", "distributor_code", "partner", "channel", "channel_partner"],
    "quantity_units": ["qty", "quantity", "units", "forecast_qty"],
    "msrp_local": [
        "msrp",
        "srp",
        "rrp",
        "list_price",
        "retail_price",
        "new_msrp",
        "list price",
        "retail price",
    ],
    "promo_price_evidence_local": [
        "promo_price",
        "promo_srp",
        "promo",
        "deal_price",
        "deal price",
        "promo price",
        "suggested_promo_price",
        "special_price",
        "special price",
        "sell_price",
        "street_price",
    ],
    "dap_evidence_local": [
        "dap",
        "dap_local",
        "rand landed cost",
        "rand landed",
        "landed zar",
        "local dap",
    ],
    "rebate_pct_evidence": ["rebate", "rebate_pct"],
    "distributor_margin_pct_evidence": ["disti_margin", "distributor_margin", "disti_margin_pct"],
    "vat_pct_evidence": ["vat", "vat_pct", "tax_pct"],
    "base_unit_raw": ["base_unit", "baseunit", "base unit"],
}


def norm_lineup_column_token(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    return re.sub(r"[\s\-_]+", "", text)


def build_commercial_lineup_column_map(columns: list[str]) -> dict[str, str]:
    """Map workbook header labels to canonical CommercialLineupLine parser field names."""
    normalized_cols = {norm_lineup_column_token(c): c for c in columns}
    mapping: dict[str, str] = {}
    claimed_sources: set[str] = set()

    for target, opts in _COMMERCIAL_LINEUP_ALIASES.items():
        for alias in opts:
            actual = normalized_cols.get(norm_lineup_column_token(alias))
            if actual and actual not in claimed_sources:
                mapping[target] = actual
                claimed_sources.add(actual)
                break

    if "msrp_local" not in mapping:
        for norm_col, actual_col in normalized_cols.items():
            if actual_col not in claimed_sources:
                if any(norm_col.endswith(root) for root in _MSRP_PATTERN_ROOTS):
                    if not any(disq in norm_col for disq in _PROMO_DISQUALIFIERS):
                        mapping["msrp_local"] = actual_col
                        claimed_sources.add(actual_col)
                        break

    return mapping
