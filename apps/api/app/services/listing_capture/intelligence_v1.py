"""P5 listing intelligence v1 — ≥14d observation span, activation, price drift, activation timing.

Activation itself is BACKLOG-130 (per-observation). This module rolls listings into a
worklist once they have two weeks of observations: promo activated vs not, plus
first→last price drift. FLAG ≠ BLOCK — short history stays ``accumulating``.

Activation timing (W1-B, Warren 2026-11-18) reads the same per-observation results for each
promotion window a listing was checked in. Threshold: ``cip_listing_activation_alert_days``
(default 3). Only what a check proves is reported; nothing is guessed between checks:

- late activation: a check on or after window start + N days still found the listing not at
  the promotion price (it may have gone live later, or never);
- early deactivation: after a check found it at the price, a later check at least N days
  before window end found it off the price.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.listing_capture import CustomerListing, ListingObservation

MIN_SPAN_DAYS = 14

_AT_PRICE = "price_consistent"
_OFF_PRICE = "not_activated"


def _alert_days() -> int:
    from app.core.config import get_settings

    return int(get_settings().cip_listing_activation_alert_days)


def _iso_date(raw: Any) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


def activation_timing(observations: list[Any], *, alert_days: int) -> list[dict[str, Any]]:
    """Late activation / early deactivation per promotion window, from stored check results.

    ``observations`` are in fetch order. Each one's ``parse_flags.cpor_activation`` says
    whether that check was at the covering line's price and which window covered it.
    """
    windows: dict[tuple[Any, date, date], list[tuple[date, str]]] = {}
    meta: dict[tuple[Any, date, date], dict[str, Any]] = {}
    for obs in observations:
        flags = obs.parse_flags if isinstance(getattr(obs, "parse_flags", None), dict) else {}
        act = flags.get("cpor_activation") if isinstance(flags.get("cpor_activation"), dict) else {}
        status = act.get("status")
        if status not in (_AT_PRICE, _OFF_PRICE):
            continue
        start = _iso_date(act.get("line_window_start") or act.get("case_window_start"))
        end = _iso_date(act.get("line_window_end") or act.get("case_window_end"))
        on = _iso_date(act.get("as_of"))
        if start is None or end is None or on is None or not (start <= on <= end):
            continue
        key = (act.get("case_id"), start, end)
        windows.setdefault(key, []).append((on, str(status)))
        meta.setdefault(key, {"case_id": act.get("case_id"), "case_code": act.get("case_code")})
    alerts: list[dict[str, Any]] = []
    for key, reads in windows.items():
        _case_id, start, end = key
        reads.sort(key=lambda item: item[0])
        first_at = next((on for on, st in reads if st == _AT_PRICE), None)
        base = {
            **meta[key],
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "alert_days": alert_days,
        }
        late_proof = [
            on
            for on, st in reads
            if st == _OFF_PRICE
            and (first_at is None or on < first_at)
            and (on - start).days >= alert_days
        ]
        if late_proof:
            seen = max(late_proof)
            alerts.append(
                {
                    **base,
                    "kind": "late_activation",
                    "not_at_price_on": seen.isoformat(),
                    "at_price_from": first_at.isoformat() if first_at else None,
                    "days_late_at_least": (seen - start).days,
                }
            )
        if first_at is not None:
            off = next((on for on, st in reads if st == _OFF_PRICE and on > first_at), None)
            if off is not None and (end - off).days >= alert_days:
                last_at = max(on for on, st in reads if st == _AT_PRICE and on < off)
                back = next((on for on, st in reads if st == _AT_PRICE and on > off), None)
                alerts.append(
                    {
                        **base,
                        "kind": "early_deactivation",
                        "last_at_price_on": last_at.isoformat(),
                        "off_price_on": off.isoformat(),
                        "back_at_price_on": back.isoformat() if back else None,
                        "days_early_at_least": (end - off).days,
                    }
                )
    alerts.sort(key=lambda a: (a["window_start"], str(a.get("case_code") or ""), a["kind"]))
    return alerts


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


def build_listing_intelligence(
    session: Session, *, alert_days: int | None = None
) -> dict[str, Any]:
    days = _alert_days() if alert_days is None else int(alert_days)
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
        # Prices are the shopper's buy-box price (``extracted_price``). Needs do not read them.
        first_price = float(priced[0].extracted_price) if priced else None
        last_price = float(priced[-1].extracted_price) if priced else None
        last_obs = obs[-1] if obs else None
        own = getattr(last_obs, "buy_box_own", None) if last_obs is not None else None
        act = _activation(last_obs)
        last_fetched = getattr(last_obs, "fetched_at", None) if last_obs is not None else None
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
            "shoppers_price": last_price,
            "buy_box_seller": getattr(last_obs, "buy_box_seller", None) if last_obs is not None else None,
            "buy_box_own": own,
            "buy_box_label": "Own" if own is True else "Competition" if own is False else None,
            "price_drift_pct": _drift(first_price, last_price),
            "activation_status": act.get("status"),
            "activation_message": act.get("message"),
            "case_price": act.get("case_price"),
            "case_id": act.get("case_id"),
            "last_availability": getattr(last_obs, "extracted_availability", None) if last_obs else None,
            "last_promo_badge": getattr(last_obs, "extracted_promo_badge", None) if last_obs else None,
            "last_fetched": last_fetched.isoformat() if last_fetched is not None else None,
            "worklist": bool(ready and act.get("status") == "not_activated"),
            "activation_timing": activation_timing(obs, alert_days=days),
        }
        items.append(row)

    worklist = [r for r in items if r["worklist"]]
    ready_n = sum(1 for r in items if r["ready"])
    timing = [
        {
            **alert,
            "listing_id": row["listing_id"],
            "customer_id": row["customer_id"],
            "product_id": row["product_id"],
            "marketplace": row["marketplace"],
            "url": row["url"],
        }
        for row in items
        for alert in row["activation_timing"]
    ]
    return {
        "activation_alert_days": days,
        "timing_alerts": timing,
        "late_activation_count": sum(1 for a in timing if a["kind"] == "late_activation"),
        "early_deactivation_count": sum(1 for a in timing if a["kind"] == "early_deactivation"),
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
