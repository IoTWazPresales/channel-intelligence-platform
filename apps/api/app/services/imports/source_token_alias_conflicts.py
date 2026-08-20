"""Detect multi-entity approved alias conflicts without changing resolution outcomes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.services.imports.provisional_entity_identity import customer_source_token_alias_key

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
    from app.services.merge_redirect import collapse_ids

    unique = collapse_ids(matches, getattr(res_cache, "distributor_redirect", {}) or {})
    if len(unique) > 1:
        return MULTIPLE_DISTRIBUTOR_ALIASES
    return None


def customer_alias_conflict_reason_from_db(
    db: "Session",
    *,
    source_definition_id: int | None,
    distributor_id: int | None,
    raw_or_normalized_token: str,
) -> str | None:
    """DB-backed alias-scope conflict check (apply refresh / single-line paths)."""
    from sqlalchemy import select

    from app.models.import_distributor_si import CustomerSourceTokenAlias

    lookup_key = customer_source_token_alias_key(raw_or_normalized_token)
    if not lookup_key:
        return None
    matches: list[int] = []
    for row in db.scalars(
        select(CustomerSourceTokenAlias).where(
            CustomerSourceTokenAlias.status == "approved",
        )
    ).all():
        row_key = customer_source_token_alias_key(row.normalized_token or "")
        if row_key != lookup_key:
            continue
        if (
            source_definition_id is not None
            and row.source_definition_id is not None
            and row.source_definition_id != source_definition_id
        ):
            continue
        if (
            distributor_id is not None
            and row.distributor_id is not None
            and row.distributor_id != distributor_id
        ):
            continue
        matches.append(int(row.customer_id))
    from app.services.merge_redirect import collapse_ids, load_customer_redirect_map

    unique = collapse_ids(matches, load_customer_redirect_map(db))
    if len(unique) > 1:
        return MULTIPLE_CUSTOMER_ALIASES
    return None


def customer_alias_conflict_reason_from_cache(
    res_cache: "DSIResolutionCache",
    *,
    source_definition_id: int | None,
    distributor_id: int | None,
    normalized_token: str,
) -> str | None:
    """Return a diagnostic when >1 distinct customer_id matches an approved alias token."""
    lookup_key = customer_source_token_alias_key(normalized_token)
    if not lookup_key:
        return None
    matches: list[int] = []
    for a in res_cache.cust_aliases:
        if a.match_key != lookup_key:
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
    from app.services.merge_redirect import collapse_ids

    unique = collapse_ids(matches, getattr(res_cache, "customer_redirect", {}) or {})
    if len(unique) > 1:
        return MULTIPLE_CUSTOMER_ALIASES
    return None
