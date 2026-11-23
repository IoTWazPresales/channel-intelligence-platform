"""Stock-based listing scope: which products get monitored, and how often.

Tiers (per tenant, per product):

* ``active``: in stock at a distributor or customer, on order, or inbound (open order or
  shipped, not yet delivered). Full discovery and price checks on the normal schedule.
* ``recent``: no longer live, but stock evidence or the product's ``retired_date`` falls
  within the recently-gone window. Price checks at a low frequency, to catch clearance pricing.
  Not searched for by discovery.
* ``historical``: older. Not crawled. Stored history stays; ``fetch now`` polls on demand.

Hysteresis: a product stays ``active`` until it has had no stock evidence for the absence
period, measured from the tenant's newest stock date (not today), so a stale or single zero
feed does not drop products. A tenant with no stock data at all is not scoped.

Everything is one tenant setting, ``listing_scope.settings``. With no row, scoping is off.
Settings suggests 180 / 7 / 14 days as hints (Warren, 24 Nov 2026) but stores nothing itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.customer_stock_position import CustomerStockPosition
from app.models.dimensions import DimCustomer, DimProduct
from app.models.facts import FactInboundShipment, FactInventoryCustomer, FactInventoryDistributor
from app.services import tenant_settings as ts

KEY_SCOPE = ts.KEY_LISTING_SCOPE

TIER_ACTIVE = "active"
TIER_RECENT = "recent"
TIER_HISTORICAL = "historical"

INBOUND_OPEN_STATES = ("open_order", "shipped")


@dataclass(frozen=True)
class ScopeSettings:
    enabled: bool = False
    recent_window_days: int = 0
    recent_interval_days: int = 0
    absent_days: int = 0


def load_scope(session: Session, tenant_id: str) -> ScopeSettings:
    raw = ts.get_setting(session, tenant_id, KEY_SCOPE, None)
    if not isinstance(raw, dict):
        return ScopeSettings()
    try:
        return ScopeSettings(**ts.SETTING_VALIDATORS[KEY_SCOPE](raw))
    except ValueError:
        return ScopeSettings()


def tier_for(
    last_live: date | None,
    retired: date | None,
    reference: date,
    settings: ScopeSettings,
    *,
    inbound_open: bool = False,
) -> str:
    """Pure tier rule. ``reference`` is the tenant's newest stock date."""
    retired_now = retired is not None and retired <= reference
    if inbound_open and not retired_now:
        return TIER_ACTIVE
    if not retired_now and last_live is not None and last_live >= reference - timedelta(days=settings.absent_days):
        return TIER_ACTIVE
    window_start = reference - timedelta(days=settings.recent_window_days)
    if last_live is not None and last_live >= window_start:
        return TIER_RECENT
    if retired_now and retired >= window_start:
        return TIER_RECENT
    return TIER_HISTORICAL


def _max_by_product(session: Session, column, product_col, *where) -> dict[int, date]:
    rows = session.execute(select(product_col, func.max(column)).where(*where).group_by(product_col)).all()
    return {int(pid): day for pid, day in rows if pid is not None and day is not None}


def product_tiers(
    session: Session, tenant_id: str, product_ids: Iterable[int], settings: ScopeSettings | None = None
) -> dict[int, str] | None:
    """Tier per product id, or ``None`` when scoping does not apply (off, or no stock data)."""
    settings = settings or load_scope(session, tenant_id)
    ids = sorted({int(p) for p in product_ids if p is not None})
    if not settings.enabled:
        return None
    if not ids:
        return {}
    evidence: list[dict[int, date]] = [
        _max_by_product(
            session, FactInventoryDistributor.as_of_date, FactInventoryDistributor.product_id,
            FactInventoryDistributor.tenant_id == tenant_id, FactInventoryDistributor.on_hand_units > 0,
            FactInventoryDistributor.product_id.in_(ids),
        ),
        _max_by_product(
            session, FactInventoryCustomer.as_of_date, FactInventoryCustomer.product_id,
            FactInventoryCustomer.tenant_id == tenant_id,
            or_(FactInventoryCustomer.on_hand_units > 0, FactInventoryCustomer.on_order_units > 0),
            FactInventoryCustomer.product_id.in_(ids),
        ),
        _max_by_product(
            session, CustomerStockPosition.period_end_date, CustomerStockPosition.product_id,
            CustomerStockPosition.tenant_id == tenant_id,
            or_(
                CustomerStockPosition.reported_on_hand > 0,
                CustomerStockPosition.in_transit_units > 0,
                CustomerStockPosition.on_order_units > 0,
            ),
            CustomerStockPosition.product_id.in_(ids),
        ),
        _max_by_product(
            session, FactInboundShipment.pod_date, FactInboundShipment.product_id,
            FactInboundShipment.tenant_id == tenant_id, FactInboundShipment.pod_date.is_not(None),
            FactInboundShipment.product_id.in_(ids),
        ),
    ]
    newest = [
        session.scalar(select(func.max(FactInventoryDistributor.as_of_date)).where(FactInventoryDistributor.tenant_id == tenant_id)),
        session.scalar(select(func.max(FactInventoryCustomer.as_of_date)).where(FactInventoryCustomer.tenant_id == tenant_id)),
        session.scalar(select(func.max(CustomerStockPosition.period_end_date)).where(CustomerStockPosition.tenant_id == tenant_id)),
    ]
    newest = [d for d in newest if d is not None]
    if not newest:
        return None  # no stock data for this tenant: do not scope
    reference = max(newest)
    inbound = {
        int(pid)
        for pid in session.scalars(
            select(FactInboundShipment.product_id).where(
                FactInboundShipment.tenant_id == tenant_id,
                FactInboundShipment.product_id.in_(ids),
                FactInboundShipment.line_state.in_(INBOUND_OPEN_STATES),
                FactInboundShipment.pod_date.is_(None),
                FactInboundShipment.superseded_by_fact_id.is_(None),
            ).distinct()
        ).all()
        if pid is not None
    }
    retired = {
        int(pid): day
        for pid, day in session.execute(
            select(DimProduct.id, DimProduct.retired_date).where(DimProduct.id.in_(ids))
        ).all()
    }
    out: dict[int, str] = {}
    for pid in ids:
        days = [source[pid] for source in evidence if pid in source]
        last_live = max(days) if days else None
        out[pid] = tier_for(last_live, retired.get(pid), reference, settings, inbound_open=pid in inbound)
    return out


def scope_due_listings(
    session: Session, listings: list[Any], *, now: datetime, last_seen: dict[int, datetime | None]
) -> tuple[list[Any], dict[str, int]]:
    """Drop listings outside their tier's schedule. Listings without a product are kept."""
    by_tenant: dict[str, list[Any]] = {}
    customer_tenant = {
        int(cid): str(tid)
        for cid, tid in session.execute(
            select(DimCustomer.id, DimCustomer.tenant_id).where(
                DimCustomer.id.in_({int(l.customer_id) for l in listings})
            )
        ).all()
    } if listings else {}
    for listing in listings:
        by_tenant.setdefault(customer_tenant.get(int(listing.customer_id), "default"), []).append(listing)
    skipped = {TIER_RECENT: 0, TIER_HISTORICAL: 0}
    keep_ids: set[int] = set()
    for tenant_id, group in by_tenant.items():
        settings = load_scope(session, tenant_id)
        tiers = product_tiers(session, tenant_id, [l.product_id for l in group if l.product_id], settings)
        for listing in group:
            tier = TIER_ACTIVE if tiers is None or listing.product_id is None else tiers.get(int(listing.product_id), TIER_ACTIVE)
            if tier == TIER_HISTORICAL:
                skipped[TIER_HISTORICAL] += 1
                continue
            if tier == TIER_RECENT:
                seen = last_seen.get(int(listing.id))
                if seen is not None:
                    if seen.tzinfo is None:
                        seen = seen.replace(tzinfo=timezone.utc)
                    if now - seen < timedelta(days=settings.recent_interval_days):
                        skipped[TIER_RECENT] += 1
                        continue
            keep_ids.add(int(listing.id))
    return [l for l in listings if int(l.id) in keep_ids], skipped
