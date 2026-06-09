"""Detect multi-entity approved alias conflicts without changing resolution outcomes."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.imports.distributor_sales_inventory import DSIResolutionCache

MULTIPLE_DISTRIBUTOR_ALIASES = "multiple_approved_distributor_aliases_for_token"
MULTIPLE_CUSTOMER_ALIASES = "multiple_approved_customer_aliases_for_token"


def distributor_alias_conflict_reason_from_cache(
    res_cache: "DSIResolutionCache",
    *,
    source_definition_id: int | None,
    normalized_token: str,
) -> str | None:
    """Return a diagnostic when >1 distinct distributor_id matches an approved alias token."""
    nt = (normalized_token or "").strip()
    if not nt:
        return None
    matches: list[int] = []
    for a in res_cache.dist_aliases:
        if a.normalized_token != nt:
            continue
        if (
            source_definition_id is not None
            and a.source_definition_id is not None
            and a.source_definition_id != source_definition_id
        ):
            continue
        matches.append(int(a.distributor_id))
    unique = list(dict.fromkeys(matches))
    if len(unique) > 1:
        return MULTIPLE_DISTRIBUTOR_ALIASES
    return None


def customer_alias_conflict_reason_from_cache(
    res_cache: "DSIResolutionCache",
    *,
    source_definition_id: int | None,
    distributor_id: int | None,
    normalized_token: str,
) -> str | None:
    """Return a diagnostic when >1 distinct customer_id matches an approved alias token."""
    nt = (normalized_token or "").strip()
    if not nt:
        return None
    matches: list[int] = []
    for a in res_cache.cust_aliases:
        if a.normalized_token != nt:
            continue
        if (
            source_definition_id is not None
            and a.source_definition_id is not None
            and a.source_definition_id != source_definition_id
        ):
            continue
        if (
            distributor_id is not None
            and a.distributor_id is not None
            and a.distributor_id != distributor_id
        ):
            continue
        matches.append(int(a.customer_id))
    unique = list(dict.fromkeys(matches))
    if len(unique) > 1:
        return MULTIPLE_CUSTOMER_ALIASES
    return None
