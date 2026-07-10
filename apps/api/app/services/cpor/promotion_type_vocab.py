"""Config vocabulary for CPOR promotion_type (spec §2.4).

Steward-extendable later; seeded values match the Consumer CPOR workbook.
Not a DB enum — stored as varchar on cpor_case.promotion_type.
"""

from __future__ import annotations

CPOR_PROMOTION_TYPES: tuple[str, ...] = (
    "Sell out PP",
    "Sell-Through PP",
    "Stock PP (In-Direct)",
)

CPOR_PROMOTION_TYPE_SET: frozenset[str] = frozenset(CPOR_PROMOTION_TYPES)

CPOR_CASE_STATUSES: tuple[str, ...] = (
    "draft",
    "proposed",
    "approved",
    "rejected",
    "active",
    "ended",
    "settled",
    "cancelled",
)

CPOR_CASE_STATUS_SET: frozenset[str] = frozenset(CPOR_CASE_STATUSES)

CPOR_CHANNELS: tuple[str, ...] = ("reseller",)
CPOR_CHANNEL_SET: frozenset[str] = frozenset(CPOR_CHANNELS)

CPOR_MARGIN_SOURCES: tuple[str, ...] = ("customer_default", "manual_override")
CPOR_COST_SOURCES: tuple[str, ...] = ("sellout_evidence", "manual", "cst_reported")
