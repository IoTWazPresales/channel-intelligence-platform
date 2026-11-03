"""Process-level TTL cache for DSI ProductResolutionIndex with a narrow dim_product load."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session, load_only

from app.models.dimensions import DimProduct
from app.models.mapping import ProductAlias
from app.services.imports.tenant_mapping_scope import effective_tenant_id, tenant_scope_predicate

if TYPE_CHECKING:
    from app.services.imports.distributor_sales_inventory import ProductResolutionIndex

logger = logging.getLogger(__name__)

# Shared across plan build, apply, validate passes within a steward session.
_CACHE_TTL_SECONDS = 300.0

_lock = threading.Lock()
_cache_by_tenant: dict[str, tuple["ProductResolutionIndex", float]] = {}

# Identity + eligibility columns only — excludes specs_json and other heavy JSONB.
_PRODUCT_LOAD_COLUMNS = (
    DimProduct.id,
    DimProduct.tenant_id,
    DimProduct.sku,
    DimProduct.part_number,
    DimProduct.sales_model_name,
    DimProduct.model_name,
    DimProduct.marketing_name,
    DimProduct.ean,
    DimProduct.upc,
    DimProduct.is_active,
    DimProduct.lifecycle_status,
    DimProduct.launch_date,
    DimProduct.retired_date,
)

_ALIAS_LOAD_COLUMNS = (
    ProductAlias.alias_value,
    ProductAlias.product_id,
    ProductAlias.confidence,
    ProductAlias.tenant_id,
)


def invalidate_product_resolution_index_cache(tenant_id: str | None = None) -> None:
    """Drop cached index after Product Master commit or steward alias writes."""
    global _cache_by_tenant
    with _lock:
        if tenant_id is None:
            _cache_by_tenant = {}
        else:
            _cache_by_tenant.pop(effective_tenant_id(tenant_id), None)


def get_product_resolution_index(
    db: Session,
    *,
    tenant_id: str | None = None,
    force_refresh: bool = False,
) -> "ProductResolutionIndex":
    """Return a cached ProductResolutionIndex or load a fresh narrow index from the DB."""
    tid = effective_tenant_id(tenant_id)
    now = time.monotonic()
    if not force_refresh:
        with _lock:
            cached = _cache_by_tenant.get(tid)
            if cached is not None:
                idx, loaded_at = cached
                if now - loaded_at < _CACHE_TTL_SECONDS:
                    return idx

    idx = _load_product_resolution_index_narrow(db, tenant_id=tid)
    with _lock:
        _cache_by_tenant[tid] = (idx, now)
    return idx


def _load_product_resolution_index_narrow(db: Session, *, tenant_id: str) -> "ProductResolutionIndex":
    """Build ProductResolutionIndex without loading specs_json or other heavy columns."""
    from app.services.imports.distributor_sales_inventory import (
        ProductResolutionIndex,
        _multimap_from_pairs,
        _product_resolution_row_from_dim,
        _product_token_key,
    )

    tid = effective_tenant_id(tenant_id)
    products = list(
        db.scalars(
            select(DimProduct)
            .where(DimProduct.tenant_id == tid)
            .options(load_only(*_PRODUCT_LOAD_COLUMNS))
        ).all()
    )
    products_by_id = {
        int(p.id): _product_resolution_row_from_dim(p) for p in products
    }
    sku_to_id: dict[str, int] = {}
    part_pairs: list[tuple[str, int]] = []
    sm_pairs: list[tuple[str, int]] = []
    model_pairs: list[tuple[str, int]] = []
    mkt_pairs: list[tuple[str, int]] = []
    ean_pairs: list[tuple[str, int]] = []
    upc_pairs: list[tuple[str, int]] = []
    for p in products:
        sk = _product_token_key(p.sku)
        if sk:
            sku_to_id[sk] = int(p.id)
        pk = _product_token_key(p.part_number)
        if pk:
            part_pairs.append((pk, int(p.id)))
        sm = _product_token_key(p.sales_model_name)
        if sm:
            sm_pairs.append((sm, int(p.id)))
        mn = _product_token_key(p.model_name)
        if mn:
            model_pairs.append((mn, int(p.id)))
        mk = _product_token_key(p.marketing_name)
        if mk:
            mkt_pairs.append((mk, int(p.id)))
        ean = _product_token_key(p.ean)
        if ean:
            ean_pairs.append((ean, int(p.id)))
        upc = _product_token_key(p.upc)
        if upc:
            upc_pairs.append((upc, int(p.id)))

    alias_pairs: list[tuple[str, int]] = []
    steward_alias_by_key: dict[str, int] = {}
    for a in db.scalars(
        select(ProductAlias)
        .where(tenant_scope_predicate(ProductAlias, tid))
        .options(load_only(*_ALIAS_LOAD_COLUMNS))
    ).all():
        av = _product_token_key(a.alias_value)
        if av:
            alias_pairs.append((av, int(a.product_id)))
            if (getattr(a, "confidence", None) or "") == "steward_approved":
                pid_a = int(a.product_id)
                if pid_a in products_by_id:
                    steward_alias_by_key[av] = pid_a

    return ProductResolutionIndex(
        sku_to_id=sku_to_id,
        part_number_to_ids=_multimap_from_pairs(part_pairs),
        sales_model_name_to_ids=_multimap_from_pairs(sm_pairs),
        model_name_to_ids=_multimap_from_pairs(model_pairs),
        marketing_name_to_ids=_multimap_from_pairs(mkt_pairs),
        ean_to_ids=_multimap_from_pairs(ean_pairs),
        upc_to_ids=_multimap_from_pairs(upc_pairs),
        alias_value_to_ids=_multimap_from_pairs(alias_pairs),
        products_by_id=products_by_id,
        steward_alias_by_key=steward_alias_by_key,
    )
