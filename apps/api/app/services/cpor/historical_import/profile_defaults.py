"""ASUS / generic CPOR historical mapping profile defaults (H1)."""

from __future__ import annotations

from typing import Any

# Canonical CIP fields ← tenant headers (ASUS Consumer CPOR Tracking Table).
# Profiles store this map; other tenants remap without code changes.
ASUS_COLUMN_MAP: dict[str, list[str]] = {
    "case_code": ["Case ID"],
    "case_name": ["Case Name"],
    "promotion_type": ["Promotion Type"],
    "window_start": ["Start From"],
    "window_end": ["End on"],
    "status": ["Status", "Case Status"],
    "pod_quarter": ["POD Quarter", "Quarter"],
    "product_line": ["Product Line"],
    "distributor_token": ["Distributor"],
    "customer_token": ["Dealer/Retailer"],
    "sales_model_token": ["Sales Model Name"],
    "soh_snapshot": ["SOH"],
    "estimate_qty": ["Estimate Qty"],
    "result_qty": ["Result"],
    "srp": ["SRP"],
    "vat_rate": ["VAT"],
    "dealer_margin_pct": ["Dealer/Store Margin", "Dealer Margin"],
    "rebate_pct": ["Rebate"],
    "disti_margin_pct": ["Disti Margin", "Margin"],
    "dealer_price": ["Dealer Price", "Dealer Net Price"],
    "cost_basis": ["Dealer System Cost", "Disti System Cost"],
    "disti_price": ["Disti Price"],
    "support_unit": ["Support  P/Unit ZAR", "Support P/Unit ZAR"],
    "ttl_support": ["Ttl Support"],
    "roe_snapshot": ["ROE"],
    "support_usd": ["Support P/Unit USD"],
    "ttl_support_usd": ["Ttl Support USD"],
    "ttl_result": ["Ttl Support Result ZAR", "Ttl Support Result Rand"],
    "ttl_result_usd": ["Ttl Support Result USD", "Ttl Support Result ($)"],
    "remark": ["Remark"],
    "dap_invoiced": ["DAP Invoiced"],
    "disti_roe": ["Disti ROE"],
    "new_dap": ["New DAP"],
    "new_disti_customer_cost": ["New Disti/Customer Cost"],
}

# status_raw (lower) → lifecycle decision before Result rule
ASUS_STATUS_VALUE_MAP: dict[str, str] = {
    "approved": "approved",
    "approve": "approved",
    "cancelled": "cancelled",
    "cancel": "cancelled",
    "under discussion": "under_discussion",
    "underdiscussion": "under_discussion",
}

ASUS_PROMOTION_TYPE_VALUE_MAP: dict[str, str] = {
    "sell out pp": "Sell out PP",
    "sell out (pp)": "Sell out PP",
    "sell out": "Sell out PP",
    "sell-through pp": "Sell-Through PP",
    "sell through": "Sell-Through PP",
    "sell through pp": "Sell-Through PP",
    "stock pp (in-direct)": "Stock PP (In-Direct)",
    "stock pp (indirect)": "Stock PP (In-Direct)",
    "stock pp (direct)": "Stock PP (Direct)",
    "spiv": "SPIV",
    "spiv (direct)": "SPIV (Direct)",
    "spiv (in-direct)": "SPIV (In-Direct)",
}

ASUS_SHEET_ROLES: dict[str, str] = {
    "Disti Sell out": "disti",
    "Reseller Sell out": "reseller",
    "Sell out Pivot": "ignore",
    "Reseller Sell out Pivot": "ignore",
}


def asus_default_profile_dict() -> dict[str, Any]:
    return {
        "profile_code": "asus_consumer_cpor_tracking_v1",
        "display_name": "ASUS Consumer CPOR Tracking Table",
        "header_row_index": 1,
        "sheet_roles_json": dict(ASUS_SHEET_ROLES),
        "column_map_json": {k: list(v) for k, v in ASUS_COLUMN_MAP.items()},
        "value_maps_json": {
            "status": dict(ASUS_STATUS_VALUE_MAP),
            "promotion_type": dict(ASUS_PROMOTION_TYPE_VALUE_MAP),
            "under_discussion_policy": "skip_with_flag",
        },
        "is_default": True,
        "notes": "Seeded from Consumer CPOR Tracking Table 20260623 layout (header row index 1).",
    }


def normalize_header(value: str | None) -> str:
    return (
        str(value or "")
        .replace("\xa0", " ")
        .strip()
        .lower()
        .replace("  ", " ")
    )
