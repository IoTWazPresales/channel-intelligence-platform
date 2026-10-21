"""Addable filters for the Sell-through tab (Warren 2026-10-19).

Next to Customers and Product, a user adds filters from a list: product fields (business unit,
category, series, product line, lifecycle, price band), every spec in Product Master (CPU, RAM,
GPU, ... from ``dim_product.specs_json``), customer channel and region, and store. Each filter is a
searchable multi-select of the values that exist for products and customers with sell-through, so
new specs appear without a code change.

A filter is keyed ``prod:<field>``, ``spec:<name>``, ``cust:<field>`` or ``site``; values are matched
exactly. Picks resolve to product ids, customer ids and store labels for the overview.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.dimensions import DimChannel, DimCustomer, DimProduct, DimRegion
from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.services.commercial_planner.read_model import specs_json_flat_string_map

MAX_FILTERS = 6
MAX_VALUES = 400  # a spec with more distinct values than this is free text, not a filter

PRODUCT_FIELDS: dict[str, tuple[str, Any]] = {
    "business_unit": ("Business unit", DimProduct.business_unit),
    "category": ("Category", DimProduct.category),
    "series_name": ("Series", DimProduct.series_name),
    "product_line": ("Product line", DimProduct.product_line),
    "lifecycle_status": ("Lifecycle", DimProduct.lifecycle_status),
    "price_band": ("Price band", DimProduct.price_band),
}


def _products_with_sellthrough(session: Session, tenant_id: str) -> list[DimProduct]:
    ids = select(FactCustomerSellthrough.product_id).where(FactCustomerSellthrough.tenant_id == tenant_id).distinct()
    return list(session.scalars(select(DimProduct).where(DimProduct.id.in_(ids))))


def _customers_with_sellthrough(session: Session, tenant_id: str) -> list[DimCustomer]:
    ids = select(FactCustomerSellthrough.customer_id).where(FactCustomerSellthrough.tenant_id == tenant_id).distinct()
    return list(
        session.scalars(select(DimCustomer).where((DimCustomer.id.in_(ids)) | (DimCustomer.is_key_account.is_(True))))
    )


def _lookup_names(session: Session, model, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    return {int(r.id): r.name for r in session.execute(select(model.id, model.name).where(model.id.in_(ids)))}


def available_dimensions(session: Session, tenant_id: str) -> list[dict[str, Any]]:
    """Every filter that has at least one value, with its values sorted."""
    products = _products_with_sellthrough(session, tenant_id)
    dims: list[dict[str, Any]] = []
    for key, (label, col) in PRODUCT_FIELDS.items():
        vals = sorted({str(getattr(p, col.key)).strip() for p in products if getattr(p, col.key)} - {""})
        if vals:
            dims.append({"key": f"prod:{key}", "label": label, "group": "Product", "values": vals})

    spec_vals: dict[str, set[str]] = defaultdict(set)
    for p in products:
        for k, v in specs_json_flat_string_map(p.specs_json).items():
            spec_vals[k].add(v)
    for k in sorted(spec_vals, key=str.lower):
        vals = spec_vals[k]
        if 1 < len(vals) <= MAX_VALUES or (len(vals) == 1 and len(products) == 1):
            dims.append({"key": f"spec:{k}", "label": k, "group": "Specs", "values": sorted(vals, key=_natural)})

    customers = _customers_with_sellthrough(session, tenant_id)
    channels = _lookup_names(session, DimChannel, {c.channel_id for c in customers if c.channel_id})
    regions = _lookup_names(session, DimRegion, {c.region_id for c in customers if c.region_id})
    if channels:
        dims.append({"key": "cust:channel", "label": "Channel", "group": "Customer", "values": sorted(set(channels.values()))})
    if regions:
        dims.append({"key": "cust:region", "label": "Region", "group": "Customer", "values": sorted(set(regions.values()))})
    if any(c.is_key_account for c in customers):
        dims.append({"key": "cust:key_account", "label": "Key account", "group": "Customer", "values": ["Yes", "No"]})

    sites = sorted(
        {
            s
            for s in session.scalars(
                select(FactCustomerSellthrough.site_label)
                .where(FactCustomerSellthrough.tenant_id == tenant_id, FactCustomerSellthrough.site_label.is_not(None))
                .distinct()
            )
            if s and s.strip()
        }
    )
    if sites:
        dims.append({"key": "site", "label": "Store", "group": "Store", "values": sites})
    return dims


def _natural(v: str) -> tuple:
    """Sort 8GB before 16GB."""
    import re

    return tuple(int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", v))


def resolve_dimension_filters(
    session: Session, tenant_id: str, picks: dict[str, list[str]]
) -> tuple[set[int] | None, set[int] | None, list[str]]:
    """(product ids, customer ids, store labels) for the picked values. ``None`` means not filtered."""
    picks = {k: [v for v in vals if v] for k, vals in picks.items() if vals}
    if len(picks) > MAX_FILTERS:
        raise ValueError(f"at most {MAX_FILTERS} extra filters")
    product_ids: set[int] | None = None
    customer_ids: set[int] | None = None
    sites: list[str] = []

    prod_picks = {k: set(v) for k, v in picks.items() if k.startswith(("prod:", "spec:"))}
    if prod_picks:
        for k in prod_picks:
            if k.startswith("prod:") and k[5:] not in PRODUCT_FIELDS:
                raise ValueError(f"unknown filter {k}")
        matched: set[int] = set()
        for p in _products_with_sellthrough(session, tenant_id):
            flat = None
            ok = True
            for k, wanted in prod_picks.items():
                if k.startswith("prod:"):
                    v = getattr(p, PRODUCT_FIELDS[k[5:]][1].key)
                    if (str(v).strip() if v else "") not in wanted:
                        ok = False
                        break
                else:
                    if flat is None:
                        flat = specs_json_flat_string_map(p.specs_json)
                    if flat.get(k[5:]) not in wanted:
                        ok = False
                        break
            if ok:
                matched.add(int(p.id))
        product_ids = matched

    cust_picks = {k: set(v) for k, v in picks.items() if k.startswith("cust:")}
    if cust_picks:
        customers = _customers_with_sellthrough(session, tenant_id)
        channels = _lookup_names(session, DimChannel, {c.channel_id for c in customers if c.channel_id})
        regions = _lookup_names(session, DimRegion, {c.region_id for c in customers if c.region_id})
        matched_c: set[int] = set()
        for c in customers:
            ok = True
            for k, wanted in cust_picks.items():
                if k == "cust:channel":
                    v = channels.get(c.channel_id) if c.channel_id else None
                elif k == "cust:region":
                    v = regions.get(c.region_id) if c.region_id else None
                elif k == "cust:key_account":
                    v = "Yes" if c.is_key_account else "No"
                else:
                    raise ValueError(f"unknown filter {k}")
                if v not in wanted:
                    ok = False
                    break
            if ok:
                matched_c.add(int(c.id))
        customer_ids = matched_c

    if "site" in picks:
        sites = sorted(set(picks["site"]))
    unknown = [k for k in picks if not k.startswith(("prod:", "spec:", "cust:")) and k != "site"]
    if unknown:
        raise ValueError(f"unknown filter {unknown[0]}")
    return product_ids, customer_ids, sites
