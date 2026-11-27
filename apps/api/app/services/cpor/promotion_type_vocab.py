"""CPOR vocabulary.

Case statuses, margin sources and cost sources stay in code. They name the
workflow engine's own states and where a number came from. They are not a
tenant's commercial names.

Promotion types, channels and the stock-promote type are tenant profile keys
(``cpor_promotion_types``, ``cpor_channels``, ``cpor_stock_promote_type``).
Unset means not configured. There is no built-in list and no code fallback.
"""

from __future__ import annotations

# Families classify stored promotion-type names (Warren, 24 Nov). They are not the tenant's
# selectable list. That list is the profile key, and unset means not configured.
# Warren (standing rule, 24 Nov 2026): "Promotions are sell-throughs. Sell-out is distributor (disti) to
# customer. They must not be mixed. The promotion planner shows customer promotions, never sell-out."
# Warren (t454u): "Correct, Sell through, sell out is disti to reseller and is still valuable but not here."
# A type that is in no family (for example "Stock PP (In-Direct)") is shown by neither family filter.
# Storage is untouched: no type is renamed or deleted.
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
# Rejected, ended, settled and cancelled are history. These are workflow states, not tenant names.
CPOR_OPEN_CASE_STATUSES: tuple[str, ...] = ("draft", "proposed", "approved", "active")

# Provenance of a margin or a cost on a case line: the system's own source, not a tenant name.
CPOR_MARGIN_SOURCES: tuple[str, ...] = ("customer_default", "manual_override")
CPOR_COST_SOURCES: tuple[str, ...] = ("sellout_evidence", "manual", "cst_reported")


def promotion_types(tenant_id: str = "default") -> tuple[str, ...]:
    from app.services.commercial_tenant_profile import cpor_promotion_types

    return cpor_promotion_types(tenant_id)


def promotion_type_set(tenant_id: str = "default") -> frozenset[str]:
    return frozenset(promotion_types(tenant_id))


def channels(tenant_id: str = "default") -> tuple[str, ...]:
    from app.services.commercial_tenant_profile import cpor_channels

    return cpor_channels(tenant_id)


def channel_set(tenant_id: str = "default") -> frozenset[str]:
    return frozenset(channels(tenant_id))


def stock_promote_type(tenant_id: str = "default") -> str | None:
    from app.services.commercial_tenant_profile import cpor_stock_promote_type

    return cpor_stock_promote_type(tenant_id)


def require_promotion_type(tenant_id: str, requested: str | None) -> str:
    """The type to write. A single saved type fills an omitted request. Otherwise the caller must name one."""
    allowed = promotion_types(tenant_id)
    if not allowed:
        raise ValueError("promotion_type_not_configured")
    raw = (requested or "").strip()
    if not raw:
        if len(allowed) == 1:
            return allowed[0]
        raise ValueError("promotion_type_required")
    if raw not in allowed:
        raise ValueError(f"unknown_promotion_type={raw}")
    return raw


def require_channel(tenant_id: str, requested: str | None) -> str:
    """The channel to write. A single saved channel fills an omitted request. Otherwise the caller must name one."""
    allowed = channels(tenant_id)
    if not allowed:
        raise ValueError("channel_not_configured")
    raw = (requested or "").strip()
    if not raw:
        if len(allowed) == 1:
            return allowed[0]
        raise ValueError("channel_required")
    if raw not in allowed:
        raise ValueError(f"unknown_channel={raw}")
    return raw
