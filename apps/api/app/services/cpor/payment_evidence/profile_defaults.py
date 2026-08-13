"""Canonical CPOR payment-evidence profile defaults.

Tenant workbooks remap via column_map / sheet_roles / value_maps.
The ASUS Pending Report layout is one seeded profile — not the schema.
"""

from __future__ import annotations

from typing import Any

# Canonical CIP fields ← header aliases (first match wins, case-insensitive).
PAYMENT_COLUMN_MAP: dict[str, list[str]] = {
    "external_case_code": ["Case ID", "Case Id", "case_id", "Case Code"],
    "credit_note_id": [
        "Credit Note ID",
        "Credit Note Id",
        "CN ID",
        "CN No",
        "Deduction No",
        "Application No",
    ],
    "case_status_raw": ["Case Status", "Status"],
    "payment_status_raw": ["Payment Status", "CN Status", "Paid Status"],
    "payment_date": [
        "Payment Date",
        "CN Date",
        "Deduction Apply Date",
        "Last Action Date",
        "Rebate Apply Date",
    ],
    "amount": [
        "Amount",
        "CN Amount",
        "Paid Amount",
        "Payment Amount",
        "Sales Rebate Amount(Updated)",
        "Sales Rebate Amount(1st Submit)",
    ],
    "currency_code": ["Currency", "Currency Code"],
    "customer_token": [
        "Customer",
        "Dealer/Retailer",
        "Target Audience Name",
        "Dealer",
        "Retailer",
    ],
    "distributor_token": ["Distributor", "Disti", "Target Audience Distributor"],
    "description": ["Description", "Subject", "Purpose", "Remark", "Latest Comment"],
    "window_start": [
        "Window Start",
        "Start From",
        "Activity Duration From",
        "Promo Start",
    ],
    "window_end": [
        "Window End",
        "End on",
        "Activity Duration To",
        "Promo End",
    ],
    "promotion_type_raw": [
        "Promotion Type",
        "Rebate Reason Code",
        "Rebate Type",
        "Purpose",
    ],
    # Optional — tenant files that already carry an owed/outstanding column.
    # Shown vs CIP owed; never replaces ttl_support.
    "owed_amount_file": [
        "Owed",
        "Owed Amount",
        "Outstanding",
        "Outstanding Amount",
        "Balance",
        "Amount Owed",
        "Claim Amount",
    ],
}

# Normalized payment_status vocabulary (tenant value-maps land here).
PAYMENT_STATUS_VALUE_MAP: dict[str, str] = {
    "closed": "closed",
    "processed": "processed",
    "paid": "paid",
    "to_be_applied": "to_be_applied",
    "to be applied": "to_be_applied",
    "to_be_clarified": "to_be_clarified",
    "to be clarified": "to_be_clarified",
    "cancel": "cancelled",
    "cancelled": "cancelled",
    "11. closed": "closed",
    "7. cn sent": "cn_sent",
    "4. cn approved": "cn_approved",
}

# Prefer payment_status_raw from Payment Status; CN Status is fallback alias only.
ASUS_PENDING_SHEET_ROLES: dict[str, str] = {
    "Detail": "payment_evidence",
    # Pivot / summary sheets ignored
    "PendingQuarter": "ignore",
    "PendingStatus": "ignore",
    "PendingSales": "ignore",
    "PendingManager": "ignore",
    "PendingSA": "ignore",
}


def asus_pending_report_profile_dict() -> dict[str, Any]:
    """Seed profile for ASUS NewCPOR Pending Report — one tenant layout only."""
    return {
        "profile_code": "asus_cpor_pending_report_v1",
        "display_name": "ASUS CPOR Pending Report (payment / CN)",
        "header_row_index": 1,
        "sheet_roles_json": dict(ASUS_PENDING_SHEET_ROLES),
        "column_map_json": {k: list(v) for k, v in PAYMENT_COLUMN_MAP.items()},
        "value_maps_json": {
            "payment_status": dict(PAYMENT_STATUS_VALUE_MAP),
            # Prefer Payment Status column over CN Status when both present — handled in parser
            "payment_status_preference": ["Payment Status", "CN Status"],
        },
        "is_default": True,
        "notes": (
            "Generic payment-evidence profile seeded for ASUS Pending Report Detail sheet. "
            "Other tenants remap headers without code changes."
        ),
    }


def normalize_header(value: str | None) -> str:
    return (
        str(value or "")
        .replace("\xa0", " ")
        .replace("\n", " ")
        .strip()
        .lower()
        .replace("  ", " ")
    )
