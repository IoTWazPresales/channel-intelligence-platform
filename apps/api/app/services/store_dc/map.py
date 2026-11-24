"""Store map. One dot per store per customer.

A suggestion comes from the bundled place list. A coordinate is written only by
``drop_pin``, after a steward confirms or types the pin. No online geocoding.
"""

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
from app.services import tenant_settings
from app.services.store_dc.candidates import served_customer_ids
from app.services.store_dc.place_name import (
    place_name_from_raw,
    place_table_for_country,
    suggest_store_location,
)
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


def build_store_map(
    db: Session,
    tenant_id: str,
    customer_ids: list[int] | None = None,
    *,
    include_proposals: bool = True,
) -> dict[str, Any]:
    """One row per store per customer. ``location_suggestion`` is the offline pin proposal for an
    unpinned store; it is computed here and never saved (``include_proposals=False`` skips it).
    Proposals use the gazetteer of the tenant's ``tenant.country`` setting (Opus R-05)."""
    place_table = None
    if include_proposals:
        country = tenant_settings.get_setting(db, tenant_id, tenant_settings.KEY_TENANT_COUNTRY)
        place_table = place_table_for_country(country.get("code") if isinstance(country, dict) else None)
    stmt = select(
        FactCustomerSellthrough.customer_id,
        FactCustomerSellthrough.product_id,
        FactCustomerSellthrough.period_start_date,
        FactCustomerSellthrough.period_grain,
        FactCustomerSellthrough.period_type,
        FactCustomerSellthrough.units_sold,
        FactCustomerSellthrough.reported_soh,
        FactCustomerSellthrough.site_label,
        FactCustomerSellthrough.raw_source_row,
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
    places: dict[tuple[int, str], str] = {}
    for customer_id, product_id, period, grain, kind, units, soh, site, raw in facts:
        label = (site or "").strip()
        key_norm = norm_label(label)
        if not key_norm or key_norm in dc_labels.get(int(customer_id), set()):
            continue
        key = (int(customer_id), key_norm)
        grouped[key].append((product_id, period, grain, kind, float(units or 0), None if soh is None else float(soh)))
        display.setdefault(key, label)
        place = place_name_from_raw(raw if isinstance(raw, dict) else None)
        if place and key not in places:
            places[key] = place
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
    # The store's own customer words are removed before the place is looked up.
    customer_words = {c["id"]: [c["name"], c["code"]] for c in customers}
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
        place_name = places.get(key)
        stores.append(
            {
                "customer_id": customer_id,
                "customer_name": names.get(customer_id),
                "site_label": display[key],
                "place_name": place_name,
                "latitude": float(loc.latitude) if pinned else None,
                "longitude": float(loc.longitude) if pinned else None,
                "pinned": pinned,
                "location_suggestion": None
                if pinned or not include_proposals
                else suggest_store_location(
                    display[key],
                    place_name=place_name,
                    customer_names=customer_words.get(customer_id),
                    table=place_table,
                ),
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


class _CustomerPinScope:
    """What a pin write needs about one customer. Read once, reused for a bulk confirm."""

    def __init__(self, db: Session, tenant_id: str, customer_id: int) -> None:
        customer = db.get(DimCustomer, customer_id)
        if customer is None or customer.tenant_id != tenant_id:
            raise LookupError(str(customer_id))
        self.known = {
            norm_label(item)
            for item in db.execute(
                select(FactCustomerSellthrough.site_label)
                .where(
                    FactCustomerSellthrough.tenant_id == tenant_id,
                    FactCustomerSellthrough.customer_id == customer_id,
                    FactCustomerSellthrough.site_label.is_not(None),
                )
                .distinct()
            ).scalars().all()
        }
        self.existing = list(
            db.execute(select(CustomerLocation).where(CustomerLocation.customer_id == customer_id)).scalars().all()
        )


def _write_pin(
    db: Session,
    *,
    tenant_id: str,
    customer_id: int,
    site_label: str,
    latitude: float,
    longitude: float,
    actor: str,
    scope: _CustomerPinScope | None = None,
) -> str:
    """Validate and write one coordinate. Returns the normalised store key. The only coordinate write."""
    if latitude is None or longitude is None:
        raise ValueError("Both coordinates are required")
    lat = float(latitude)
    lon = float(longitude)
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError("Coordinates are out of range")
    scope = scope or _CustomerPinScope(db, tenant_id, customer_id)
    label = site_label.strip()
    key = norm_label(label)
    if not key:
        raise ValueError("A store label is required")
    if key not in scope.known:
        raise LookupError("store")
    existing = scope.existing
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
        existing.append(match)
    match.latitude = lat
    match.longitude = lon
    db.flush()
    return key


def _store_row(payload: dict[str, Any], customer_id: int, key: str) -> dict[str, Any] | None:
    return next(
        (s for s in payload["stores"] if s["customer_id"] == customer_id and norm_label(s["site_label"]) == key),
        None,
    )


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
    key = _write_pin(
        db,
        tenant_id=tenant_id,
        customer_id=customer_id,
        site_label=site_label,
        latitude=latitude,
        longitude=longitude,
        actor=actor,
    )
    # The saved store has no proposal to show, so the whole customer's proposals are not recomputed.
    payload = build_store_map(db, tenant_id, [customer_id], include_proposals=False)
    store = _store_row(payload, customer_id, key)
    if store is None:
        raise LookupError("store")
    return store


MAX_BULK_CONFIRM = 500


def confirm_pins(
    db: Session,
    *,
    tenant_id: str,
    items: list[dict[str, Any]],
    actor: str,
) -> dict[str, Any]:
    """Save pins a steward confirmed, each through the one write path (``_write_pin``).

    An item with ``latitude`` and ``longitude`` is an edited pin and is saved as given. An item
    without coordinates confirms the proposal the map shows for that store; it is recomputed
    here, so the client cannot confirm a place the matcher did not propose. A store with no
    proposal, a store that is already pinned (without coordinates), an unknown store or bad
    coordinates is reported in ``failed`` and writes nothing. The other items still save.
    """
    if len(items) > MAX_BULK_CONFIRM:
        raise ValueError(f"At most {MAX_BULK_CONFIRM} pins per request")
    by_customer: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        by_customer[int(item["customer_id"])].append(item)
    saved: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []

    def fail(item: dict[str, Any], message: str) -> None:
        failed.append(
            {"customer_id": int(item["customer_id"]), "site_label": item.get("site_label"), "error": message}
        )

    for customer_id, group in by_customer.items():
        try:
            scope = _CustomerPinScope(db, tenant_id, customer_id)
        except LookupError:
            for item in group:
                fail(item, "Customer not found")
            continue
        proposals: dict[str, dict[str, Any]] | None = None
        written: list[str] = []
        for item in group:
            label = str(item.get("site_label") or "")
            key = norm_label(label)
            lat, lon = item.get("latitude"), item.get("longitude")
            try:
                if (lat is None) != (lon is None):
                    raise ValueError("Both coordinates are required")
                if lat is None:
                    if proposals is None:
                        current = build_store_map(db, tenant_id, [customer_id])
                        proposals = {
                            norm_label(s["site_label"]): s
                            for s in current["stores"]
                            if s["customer_id"] == customer_id
                        }
                    store = proposals.get(key)
                    if store is None:
                        raise LookupError("store")
                    if store["pinned"]:
                        raise ValueError("This store already has a pin; send coordinates to move it")
                    suggestion = store.get("location_suggestion") or {}
                    if suggestion.get("outcome") != "suggest":
                        raise ValueError("No proposal for this store; send coordinates")
                    lat, lon = suggestion["latitude"], suggestion["longitude"]
                _write_pin(
                    db,
                    tenant_id=tenant_id,
                    customer_id=customer_id,
                    site_label=label,
                    latitude=lat,
                    longitude=lon,
                    actor=actor,
                    scope=scope,
                )
                written.append(key)
            except LookupError:
                fail(item, "Store not found for this customer")
            except ValueError as exc:
                fail(item, str(exc))
        if written:
            payload = build_store_map(db, tenant_id, [customer_id], include_proposals=False)
            for key in written:
                row = _store_row(payload, customer_id, key)
                if row is not None:
                    saved.append(row)
    return {"saved": saved, "failed": failed}
