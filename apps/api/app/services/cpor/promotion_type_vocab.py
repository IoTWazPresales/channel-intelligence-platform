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

# --- promotion families (where a type fits) -----------------------------------------------------
# Warren (standing rule, 24 Nov 2026): "Promotions are sell-throughs. Sell-out is distributor (disti) to
# customer. They must not be mixed. The promotion planner shows customer promotions, never sell-out."
# Warren (t454u): "Correct, Sell through, sell out is disti to reseller and is still valuable but not here."
# This is the one place that says which stored type belongs to which family. A type that is in no family
# (for example "Stock PP (In-Direct)", SPIV) is shown by neither family filter; adding it to a family is a
# one-line change here. Storage is untouched: no type is renamed or deleted.
CUSTOMER_SELL_THROUGH = "customer_sell_through"
DISTRIBUTOR_SELL_OUT = "distributor_sell_out"

PROMOTION_FAMILIES: dict[str, tuple[str, ...]] = {
    CUSTOMER_SELL_THROUGH: ("Sell-Through PP",),
    DISTRIBUTOR_SELL_OUT: ("Sell out PP",),
}

# The customer promotion type a new planner case starts with: the first type of the family.
DEFAULT_CUSTOMER_PROMOTION_TYPE: str = PROMOTION_FAMILIES[CUSTOMER_SELL_THROUGH][0]


def _normalise_type(value: str | None) -> str:
    """Case and whitespace normalisation only (no punctuation folding, no substring)."""
    return " ".join((value or "").strip().lower().split())


_FAMILY_BY_NORMALISED_TYPE: dict[str, str] = {
    _normalise_type(t): family for family, types in PROMOTION_FAMILIES.items() for t in types
}


def promotion_family(promotion_type: str | None) -> str | None:
    """The family of a stored promotion type, by exact match after case/whitespace normalisation.

    Returns None for a type that belongs to no family. No substring or fuzzy matching.
    """
    return _FAMILY_BY_NORMALISED_TYPE.get(_normalise_type(promotion_type))


def promotion_family_types(family: str) -> tuple[str, ...]:
    """The stored types of one family. Raises KeyError for an unknown family."""
    return PROMOTION_FAMILIES[family]

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

# Open (not closed) for the planner's default view: still being planned, approved or running.
# Rejected, ended, settled and cancelled are history.
CPOR_OPEN_CASE_STATUSES: tuple[str, ...] = ("draft", "proposed", "approved", "active")

CPOR_CHANNELS: tuple[str, ...] = ("reseller",)
CPOR_CHANNEL_SET: frozenset[str] = frozenset(CPOR_CHANNELS)

CPOR_MARGIN_SOURCES: tuple[str, ...] = ("customer_default", "manual_override")
CPOR_COST_SOURCES: tuple[str, ...] = ("sellout_evidence", "manual", "cst_reported")
