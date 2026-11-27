"""CPOR vocabulary.

Case statuses, margin sources and cost sources stay in code. They name the
workflow engine's own states and where a number came from. They are not a
tenant's commercial names.

Promotion types, channels and the stock-promote type are tenant profile keys
(``cpor_promotion_types``, ``cpor_channels``, ``cpor_stock_promote_type``).
Unset means not configured. There is no built-in list and no code fallback.
"""

from __future__ import annotations

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
