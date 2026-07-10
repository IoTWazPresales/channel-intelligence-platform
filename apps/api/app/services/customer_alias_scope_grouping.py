"""Group approved customer aliases by canonical scope key (matches DSI resolution)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.services.imports.provisional_entity_identity import customer_source_token_alias_key


def canonical_customer_alias_token(raw_or_normalized_token: str | None) -> str:
    """Lookup key shared with DSI validate and steward alias writes."""
    return customer_source_token_alias_key(raw_or_normalized_token)


def scope_bucket_ids(
    source_definition_id: int | None,
    distributor_id: int | None,
) -> tuple[int, int]:
    return (
        int(source_definition_id) if source_definition_id is not None else -1,
        int(distributor_id) if distributor_id is not None else -1,
    )


def scope_from_bucket(scope_src: int, scope_dist: int) -> dict[str, Any]:
    return {
        "normalized_token": "",  # filled by caller
        "source_definition_id": None if int(scope_src) < 0 else int(scope_src),
        "distributor_id": None if int(scope_dist) < 0 else int(scope_dist),
    }


def group_approved_customer_alias_scope_conflicts(
    rows: list[tuple[str, int, int | None, int | None]],
    *,
    canonical_token_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Group approved alias rows where one canonical token + scope maps to 2+ customers.

    Each row is ``(normalized_token, customer_id, source_definition_id, distributor_id)``.
    """
    filter_key = canonical_customer_alias_token(canonical_token_filter) if canonical_token_filter else None
    buckets: dict[tuple[str, int, int], dict[str, Any]] = {}

    for normalized_token, customer_id, source_definition_id, distributor_id in rows:
        canonical = canonical_customer_alias_token(normalized_token)
        if not canonical:
            continue
        if filter_key is not None and canonical != filter_key:
            continue
        scope_src, scope_dist = scope_bucket_ids(source_definition_id, distributor_id)
        key = (canonical, scope_src, scope_dist)
        bucket = buckets.get(key)
        if bucket is None:
            bucket = {
                "canonical_token": canonical,
                "scope_src": scope_src,
                "scope_dist": scope_dist,
                "customer_ids": set(),
                "alias_rows": 0,
                "token_variants": set(),
            }
            buckets[key] = bucket
        bucket["customer_ids"].add(int(customer_id))
        bucket["alias_rows"] += 1
        bucket["token_variants"].add(str(normalized_token))

    groups: list[dict[str, Any]] = []
    for bucket in buckets.values():
        if len(bucket["customer_ids"]) < 2:
            continue
        groups.append(
            {
                "canonical_token": bucket["canonical_token"],
                "scope_src": bucket["scope_src"],
                "scope_dist": bucket["scope_dist"],
                "customer_ids": sorted(bucket["customer_ids"]),
                "alias_rows": int(bucket["alias_rows"]),
                "token_variants": sorted(bucket["token_variants"]),
            }
        )
    groups.sort(key=lambda g: (g["canonical_token"], g["scope_src"], g["scope_dist"]))
    return groups


def customer_ids_for_canonical_scope_conflict(
    rows: list[tuple[str, int, int | None, int | None]],
    *,
    normalized_token: str,
    source_definition_id: int | None,
    distributor_id: int | None,
) -> list[int]:
    """Distinct customer_ids for a canonical token in one alias scope."""
    lookup = canonical_customer_alias_token(normalized_token)
    if not lookup:
        return []
    scope_src, scope_dist = scope_bucket_ids(source_definition_id, distributor_id)
    ids: set[int] = set()
    for row_token, customer_id, row_src, row_dist in rows:
        if scope_bucket_ids(row_src, row_dist) != (scope_src, scope_dist):
            continue
        if canonical_customer_alias_token(row_token) != lookup:
            continue
        ids.add(int(customer_id))
    return sorted(ids) if len(ids) >= 2 else []
