"""P5 listing intelligence v1 — ≥14d observation span, activation, price drift.

Activation itself is BACKLOG-130 (per-observation). This module rolls listings into a
worklist once they have two weeks of observations: promo activated vs not, plus
first→last price drift. FLAG ≠ BLOCK — short history stays ``accumulating``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.listing_capture import CustomerListing, ListingObservation

MIN_SPAN_DAYS = 14


def _activation(obs: ListingObservation | None) -> dict[str, Any]:
    if obs is None:
        return {"status": None, "message": None, "case_price": None}
    flags = obs.parse_flags if isinstance(obs.parse_flags, dict) else {}
    act = flags.get("cpor_activation") if isinstance(flags.get("cpor_activation"), dict) else {}
    return {
        "status": act.get("status"),
        "message": act.get("message"),
        "case_price": act.get("case_price"),
        "case_id": act.get("case_id"),
    }


def _drift(first: float | None, last: float | None) -> float | None:
    if first is None or last is None or first == 0:
        return None
    return (last - first) / first


def build_listing_intelligence(session: Session) -> dict[str, Any]:
    listings = list(session.scalars(select(CustomerListing).order_by(CustomerListing.id)).all())
    items: list[dict[str, Any]] = []
    for listing in listings:
        obs = list(
            session.scalars(
                select(ListingObservation)
                .where(ListingObservation.listing_id == int(listing.id))
                .order_by(ListingObservation.fetched_at.asc(), ListingObservation.id.asc())
            ).all()
        )
        priced = [o for o in obs if o.extracted_price is not None]
        first_ts = obs[0].fetched_at if obs else None
        last_ts = obs[-1].fetched_at if obs else None
        span_days = None
        if first_ts is not None and last_ts is not None:
            span_days = max(0, (last_ts - first_ts).days)
        ready = bool(span_days is not None and span_days >= MIN_SPAN_DAYS and len(obs) >= 2)
        first_price = float(priced[0].extracted_price) if priced else None
        last_price = float(priced[-1].extracted_price) if priced else None
        act = _activation(obs[-1] if obs else None)
        row = {
            "listing_id": int(listing.id),
            "customer_id": int(listing.customer_id),
            "product_id": int(listing.product_id) if listing.product_id is not None else None,
            "marketplace": listing.marketplace,
            "url": listing.url,
            "external_id": listing.external_id,
            "observation_count": len(obs),
            "span_days": span_days,
            "ready": ready,
            "history_status": "ready" if ready else "accumulating",
            "first_price": first_price,
            "last_price": last_price,
            "price_drift_pct": _drift(first_price, last_price),
            "activation_status": act.get("status"),
            "activation_message": act.get("message"),
            "case_price": act.get("case_price"),
            "worklist": bool(ready and act.get("status") == "not_activated"),
        }
        items.append(row)

    worklist = [r for r in items if r["worklist"]]
    ready_n = sum(1 for r in items if r["ready"])
    return {
        "min_span_days": MIN_SPAN_DAYS,
        "listings": len(items),
        "ready": ready_n,
        "accumulating": len(items) - ready_n,
        "not_activated_worklist": len(worklist),
        "items": items,
        "worklist": worklist,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "data_unavailable": False,
    }
