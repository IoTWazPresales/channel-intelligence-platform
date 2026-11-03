"""Store map. One dot per store per customer. No geocoding and no baked-in coordinates."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer_report_config import CustomerReportConfig
from app.models.dimensions import CustomerLocation, DimCustomer, DimProduct
from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.models.store_dc import SiteCandidate
from app.services.store_dc.candidates import served_customer_ids
from app.services.store_dc.rules import (
    cover_weeks,
    is_weekly,
    norm_label,
    sell_through_ratio,
    weeks_of_cover,
)


def _confirmed_dc_labels(db: Session, tenant_id: str) -> dict[int, set[str]]:
    """customer id -> confirmed DC labels that customer is served by."""
    rows = db.execute(
        select(SiteCandidate).where(SiteCandidate.tenant_id == tenant_id, SiteCandidate.status == "confirmed")
    ).scalars().all()
    out: dict[int, set[str]] = defaultdict(set)
    for row in rows:
        if row.blocked_as_distributor_site:
            continue
        for cid in served_customer_ids(db, tenant_id, row):
            out[cid].add(row.site_label_norm)
    return out


def build_store_map(db: Session, tenant_id: str, customer_ids: list[int] | None = None) -> dict[str, Any]:
    stmt = select(
        FactCustomerSellthrough.customer_id,
        FactCustomerSellthrough.product_id,
        FactCustomerSellthrough.period_start_date,
        FactCustomerSellthrough.period_grain,
        FactCustomerSellthrough.period_type,
        FactCustomerSellthrough.units_sold,
        FactCustomerSellthrough.reported_soh,
        FactCustomerSellthrough.site_label,
    ).where(
        FactCustomerSellthrough.tenant_id == tenant_id,
        FactCustomerSellthrough.site_label.is_not(None),
    )
    if customer_ids:
        stmt = stmt.where(FactCustomerSellthrough.customer_id.in_(customer_ids))
    facts = db.execute(stmt).all()
    dc_labels = _confirmed_dc_labels(db, tenant_id)
    grouped: dict[tuple[int, str], list] = defaultdict(list)
    display: dict[tuple[int, str], str] = {}
    for customer_id, product_id, period, grain, kind, units, soh, site in facts:
        label = (site or "").strip()
        key_norm = norm_label(label)
        if not key_norm or key_norm in dc_labels.get(int(customer_id), set()):
            continue
        key = (int(customer_id), key_norm)
        grouped[key].append((product_id, period, grain, kind, float(units or 0), None if soh is None else float(soh)))
        display.setdefault(key, label)
    if not grouped and not customer_ids:
        return {
            "customers": [],
            "stores": [],
            "legend": _legend(),
        }
    customer_id_set = {cid for cid, _ in grouped}
    # Customers for the filter are everyone with a store label, even when the response is filtered.
    if customer_ids:
        all_ids = set(
            db.execute(
                select(FactCustomerSellthrough.customer_id)
                .where(
                    FactCustomerSellthrough.tenant_id == tenant_id,
                    FactCustomerSellthrough.site_label.is_not(None),
                )
                .distinct()
            ).scalars().all()
        )
    else:
        all_ids = set(customer_id_set)
    customers = []
    if all_ids:
        for cid, code, name in db.execute(
            select(DimCustomer.id, DimCustomer.code, DimCustomer.name)
            .where(DimCustomer.tenant_id == tenant_id, DimCustomer.id.in_(all_ids))
            .order_by(DimCustomer.code)
        ).all():
            customers.append({"id": int(cid), "code": code, "name": name})
    names = {c["id"]: c["name"] for c in customers}
    configs = {}
    if customer_id_set:
        for row in db.execute(
            select(CustomerReportConfig).where(CustomerReportConfig.customer_id.in_(customer_id_set))
        ).scalars().all():
            configs[int(row.customer_id)] = row
    locations = db.execute(
        select(CustomerLocation).where(CustomerLocation.customer_id.in_(customer_id_set or {0}))
    ).scalars().all()
    by_customer_label: dict[tuple[int, str], CustomerLocation] = {}
    for loc in locations:
        for part in (loc.location_name, loc.location_code):
            key = (int(loc.customer_id), norm_label(part))
            current = by_customer_label.get(key)
            if current is None or (loc.latitude is not None and current.latitude is None):
                by_customer_label[key] = loc
    product_ids = {row[0] for rows in grouped.values() for row in rows}
    products = {}
    if product_ids:
        products = {
            int(p.id): p
            for p in db.execute(select(DimProduct).where(DimProduct.id.in_(product_ids))).scalars().all()
        }
    stores = []
    for key, rows in sorted(grouped.items()):
        customer_id, _ = key
        weekly = [r for r in rows if is_weekly(r[2], r[3])]
        pool = weekly or rows
        last_period = max(r[1] for r in pool)
        last_rows = [r for r in pool if r[1] == last_period]
        units = sum(r[4] for r in last_rows)
        soh_rows = [r[5] for r in last_rows if r[5] is not None]
        soh = None if not soh_rows else sum(soh_rows)
        rate = units if units > 0 else None
        loc = by_customer_label.get(key)
        pinned = loc is not None and loc.latitude is not None and loc.longitude is not None
        lines = []
        by_product: dict[int, list] = defaultdict(list)
        for row in last_rows:
            by_product[int(row[0])].append(row)
        for pid, group in sorted(by_product.items(), key=lambda item: -sum(r[4] for r in item[1])):
            p_units = sum(r[4] for r in group)
            p_soh_vals = [r[5] for r in group if r[5] is not None]
            p_soh = None if not p_soh_vals else sum(p_soh_vals)
            prod = products.get(pid)
            lines.append(
                {
                    "product_id": pid,
                    "sku": prod.sku if prod else None,
                    "product_name": prod.name if prod else None,
                    "units": round(p_units, 2),
                    "stock_on_hand": None if p_soh is None else round(p_soh, 2),
                    "weeks_of_cover": None
                    if weeks_of_cover(p_soh, p_units if p_units > 0 else None) is None
                    else round(weeks_of_cover(p_soh, p_units) or 0, 2),
                }
            )
        woc = weeks_of_cover(soh, rate)
        ratio = sell_through_ratio(units, soh)
        stores.append(
            {
                "customer_id": customer_id,
                "customer_name": names.get(customer_id),
                "site_label": display[key],
                "latitude": float(loc.latitude) if pinned else None,
                "longitude": float(loc.longitude) if pinned else None,
                "pinned": pinned,
                "location_id": loc.id if loc is not None else None,
                "last_week_start": last_period.isoformat() if last_period else None,
                "last_week_units": round(units, 2),
                "stock_on_hand": None if soh is None else round(soh, 2),
                "weeks_of_cover": None if woc is None else round(woc, 2),
                "sell_through": None if ratio is None else round(ratio, 4),
                "lines": lines[:50],
                "cover_target_weeks": cover_weeks(configs.get(customer_id))["target_weeks"],
            }
        )
    return {"customers": customers, "stores": stores, "legend": _legend()}


def _legend() -> dict[str, str]:
    return {
        "metric": "last_week_sell_through",
        "formula": "last week's units / (last week's units + stock on hand)",
        "best": "higher",
        "worst": "lower",
    }


def drop_pin(
    db: Session,
    *,
    tenant_id: str,
    customer_id: int,
    site_label: str,
    latitude: float,
    longitude: float,
    actor: str,
) -> dict[str, Any]:
    if latitude is None or longitude is None:
        raise ValueError("Both coordinates are required")
    lat = float(latitude)
    lon = float(longitude)
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError("Coordinates are out of range")
    customer = db.get(DimCustomer, customer_id)
    if customer is None or customer.tenant_id != tenant_id:
        raise LookupError(str(customer_id))
    label = site_label.strip()
    key = norm_label(label)
    if not key:
        raise ValueError("A store label is required")
    known = db.execute(
        select(FactCustomerSellthrough.site_label)
        .where(
            FactCustomerSellthrough.tenant_id == tenant_id,
            FactCustomerSellthrough.customer_id == customer_id,
            FactCustomerSellthrough.site_label.is_not(None),
        )
    ).scalars().all()
    if key not in {norm_label(item) for item in known}:
        raise LookupError("store")
    existing = db.execute(
        select(CustomerLocation).where(CustomerLocation.customer_id == customer_id)
    ).scalars().all()
    match = next((loc for loc in existing if norm_label(loc.location_name) == key or norm_label(loc.location_code) == key), None)
    if match is None:
        digest = hashlib.sha256(f"{tenant_id}:{customer_id}:{key}".encode()).hexdigest()[:12]
        match = CustomerLocation(
            customer_id=customer_id,
            location_code=f"pin-{digest}",
            location_name=label,
            location_type="store",
            site_level="store",
            site_owner="customer",
            confirmed_at=datetime.now(timezone.utc),
            confirmed_by=actor,
            is_active=True,
        )
        db.add(match)
    match.latitude = lat
    match.longitude = lon
    db.flush()
    payload = build_store_map(db, tenant_id, [customer_id])
    store = next((s for s in payload["stores"] if s["customer_id"] == customer_id and norm_label(s["site_label"]) == key), None)
    if store is None:
        raise LookupError("store")
    return store
