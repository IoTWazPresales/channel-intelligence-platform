"""Deterministic CST steward suggestions (product + location). No fuzzy engine."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.dimensions import CustomerLocation
from app.services.imports.cst_d1 import resolve_customer_article_alias
from app.services.imports.distributor_sales_inventory import (
    ProductResolutionIndex,
    ProductResolutionProductRow,
    _load_product_resolution_index,
    _product_token_key,
)

_MAX_SUGGESTIONS = 3
CST_PRODUCT_ENTITY = "cst_product_token"
CST_LOCATION_ENTITY = "cst_location_token"


def _location_token_key(raw: str | None) -> str:
    if raw is None:
        return ""
    t = str(raw).strip().lower()
    return t if t and t != "nan" else ""

_CST_PRODUCT_TIERS: tuple[tuple[str, str], ...] = (
    ("item_code", "sku_to_id"),
    ("part_number", "part_number_to_ids"),
    ("ean", "ean_to_ids"),
    ("upc", "upc_to_ids"),
    ("sales_model_name", "sales_model_name_to_ids"),
)


def _suggestion(dim_id: int, label: str, score: float, reason: str) -> dict[str, Any]:
    return {
        "dim_id": int(dim_id),
        "label": label,
        "score": round(float(score), 4),
        "reason": reason,
    }


def _product_label(row: ProductResolutionProductRow | None, dim_id: int) -> str:
    if row is None:
        return str(dim_id)
    return (
        (row.sales_model_name or "").strip()
        or (row.marketing_name or "").strip()
        or (row.model_name or "").strip()
        or (row.sku or "").strip()
        or str(dim_id)
    )


def _location_label(loc: CustomerLocation) -> str:
    return (
        (loc.location_name or "").strip()
        or (loc.location_code or "").strip()
        or str(loc.id)
    )


def _ids_for_cst_product_tier(
    product_index: ProductResolutionIndex, token_key: str, tier: str, attr: str
) -> list[int]:
    if tier == "item_code":
        pid = product_index.sku_to_id.get(token_key)
        return [int(pid)] if pid is not None else []
    raw = getattr(product_index, attr, {}).get(token_key) or ()
    return [int(x) for x in raw]


def suggest_cst_product_token(
    token_key: str,
    *,
    product_index: ProductResolutionIndex,
    session: Session | None = None,
    customer_id: int | None = None,
    article_token: str | None = None,
) -> list[dict[str, Any]]:
    """CST product tiers (item_code→part→EAN→UPC→sales_model_name), then article alias."""
    token_key = _product_token_key(token_key) or token_key
    labels = {
        pid: _product_label(row, pid) for pid, row in product_index.products_by_id.items()
    }

    for tier, attr in _CST_PRODUCT_TIERS:
        ids = _ids_for_cst_product_tier(product_index, token_key, tier, attr)
        if len(ids) == 1:
            did = ids[0]
            return [_suggestion(did, labels.get(did, str(did)), 1.0, tier)]
        if len(ids) > 1:
            return [
                _suggestion(did, labels.get(did, str(did)), 1.0, f"exact_key_collision:{tier}")
                for did in ids[:_MAX_SUGGESTIONS]
            ]

    if session is not None and customer_id is not None:
        for candidate in (article_token, token_key):
            alias_pid = resolve_customer_article_alias(
                session, customer_id=customer_id, article_token=candidate
            )
            if alias_pid is not None:
                return [
                    _suggestion(
                        alias_pid,
                        labels.get(alias_pid, str(alias_pid)),
                        1.0,
                        "customer_article_alias",
                    )
                ]

    return []


def suggest_cst_location_token(
    token_key: str,
    *,
    locations: list[CustomerLocation],
) -> list[dict[str, Any]]:
    """Exact location_code or location_name match (case-insensitive normalized keys)."""
    code_matches: list[CustomerLocation] = []
    name_matches: list[CustomerLocation] = []
    for loc in locations:
        code_key = _location_token_key(loc.location_code)
        name_key = _location_token_key(loc.location_name)
        if code_key and code_key == token_key:
            code_matches.append(loc)
        elif name_key and name_key == token_key:
            name_matches.append(loc)

    if len(code_matches) == 1:
        loc = code_matches[0]
        return [_suggestion(int(loc.id), _location_label(loc), 1.0, "location_code_exact")]
    if len(code_matches) > 1:
        return [
            _suggestion(int(loc.id), _location_label(loc), 1.0, "exact_key_collision:location_code")
            for loc in code_matches[:_MAX_SUGGESTIONS]
        ]

    if len(name_matches) == 1:
        loc = name_matches[0]
        return [_suggestion(int(loc.id), _location_label(loc), 1.0, "location_name_exact")]
    if len(name_matches) > 1:
        return [
            _suggestion(int(loc.id), _location_label(loc), 1.0, "exact_key_collision:location_name")
            for loc in name_matches[:_MAX_SUGGESTIONS]
        ]

    return []


def load_customer_locations(session: Session, customer_id: int) -> list[CustomerLocation]:
    return list(
        session.scalars(
            select(CustomerLocation).where(CustomerLocation.customer_id == customer_id)
        ).all()
    )


def build_cst_suggestions_for_candidate(
    session: Session,
    *,
    entity_type: str,
    normalized_key: str,
    product_index: ProductResolutionIndex,
    customer_id: int | None,
    sample_raw_values: list[str] | None = None,
) -> list[dict[str, Any]]:
    if entity_type == CST_PRODUCT_ENTITY:
        article_token = None
        if sample_raw_values:
            article_token = str(sample_raw_values[0]) if sample_raw_values[0] else None
        return suggest_cst_product_token(
            normalized_key,
            product_index=product_index,
            session=session,
            customer_id=customer_id,
            article_token=article_token,
        )
    if entity_type == CST_LOCATION_ENTITY:
        if customer_id is None:
            return []
        locations = load_customer_locations(session, customer_id)
        return suggest_cst_location_token(normalized_key, locations=locations)
    return []


def load_product_index(session: Session) -> ProductResolutionIndex:
    return _load_product_resolution_index(session)
