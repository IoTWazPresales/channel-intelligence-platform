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
from types import SimpleNamespace
from typing import Any

from sqlalchemy import Select, func, or_, select
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


def _failed_read(obs: Any, flags: dict[str, Any]) -> bool:
    """A check whose fetch or parse failed proves nothing about the price (BACKLOG-226 item 1).

    The poller still evaluates activation on an error page that parsed to a price, so such a
    check must not count as "off the price" (or "at it").
    """
    http_status = getattr(obs, "http_status", None)
    if http_status is not None and int(http_status) != 200:
        return True
    if flags.get("snapshot_stored") == "fetch_failed":
        return True
    parse_status = getattr(obs, "parse_status", None)
    return parse_status is not None and str(parse_status) != "ok"


def activation_timing(observations: list[Any], *, alert_days: int) -> list[dict[str, Any]]:
    """Late activation / early deactivation per promotion window, from stored check results.

    ``observations`` are ordered by fetched_at, then id. Keep that order for transitions,
    including checks on the same day; calendar dates determine the day thresholds.
    Only stored ``price_basis="promo"`` results prove customer promotion timing.
    """
    windows: dict[tuple[Any, date, date], list[tuple[date, str]]] = {}
    meta: dict[tuple[Any, date, date], dict[str, Any]] = {}
    for obs in observations:
        flags = obs.parse_flags if isinstance(getattr(obs, "parse_flags", None), dict) else {}
        if _failed_read(obs, flags):
            continue
        act = flags.get("cpor_activation") if isinstance(flags.get("cpor_activation"), dict) else {}
        status = act.get("status")
        if act.get("price_basis") != "promo" or status not in (_AT_PRICE, _OFF_PRICE):
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
        first_at_index = next((i for i, (_on, st) in enumerate(reads) if st == _AT_PRICE), None)
        first_at = reads[first_at_index][0] if first_at_index is not None else None
        base = {
            **meta[key],
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "alert_days": alert_days,
        }
        late_proof = [
            on
            for on, st in reads[:first_at_index]
            if st == _OFF_PRICE and (on - start).days >= alert_days
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
        if first_at_index is not None:
            off_index = next(
                (i for i in range(first_at_index + 1, len(reads)) if reads[i][1] == _OFF_PRICE),
                None,
            )
            if off_index is None:
                continue
            off = reads[off_index][0]
            if (end - off).days >= alert_days:
                last_at = next(on for on, st in reversed(reads[:off_index]) if st == _AT_PRICE)
                back = next((on for on, st in reads[off_index + 1 :] if st == _AT_PRICE), None)
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


def _activation(obs: Any | None) -> dict[str, Any]:
    """The stored activation result on the last reading (``obs.activation`` or ``parse_flags``)."""
    if obs is None:
        return {"status": None, "message": None, "case_price": None}
    raw = getattr(obs, "activation", None)
    if raw is None and hasattr(obs, "parse_flags"):
        flags = obs.parse_flags if isinstance(obs.parse_flags, dict) else {}
        raw = flags.get("cpor_activation")
    act = raw if isinstance(raw, dict) else {}
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


# --- set-based reads (BACKLOG-226) -------------------------------------------------------------
# A fixed number of statements however many listings exist. None selects ``raw_snapshot`` (the
# stored page copy) or any other large column. Per-observation history is read only for the
# checks that can prove promotion timing (stored promo-basis results, small JSON fragments).

_LO = ListingObservation


def _listing_stmt() -> Select[Any]:
    return select(
        CustomerListing.id,
        CustomerListing.customer_id,
        CustomerListing.product_id,
        CustomerListing.marketplace,
        CustomerListing.url,
        CustomerListing.external_id,
    ).order_by(CustomerListing.id)


def _count_stmt() -> Select[Any]:
    return select(
        _LO.listing_id.label("listing_id"),
        func.count(_LO.id).label("n"),
        func.min(_LO.fetched_at).label("first_ts"),
        func.max(_LO.fetched_at).label("last_ts"),
    ).group_by(_LO.listing_id)


def _priced_ends_stmt() -> Select[Any]:
    """First and last priced reading per listing (fetched_at, then id)."""
    ranked = (
        select(
            _LO.listing_id.label("listing_id"),
            _LO.extracted_price.label("price"),
            func.row_number()
            .over(partition_by=_LO.listing_id, order_by=(_LO.fetched_at.asc(), _LO.id.asc()))
            .label("rn_first"),
            func.row_number()
            .over(partition_by=_LO.listing_id, order_by=(_LO.fetched_at.desc(), _LO.id.desc()))
            .label("rn_last"),
        )
        .where(_LO.extracted_price.is_not(None))
        .subquery("priced")
    )
    return select(ranked.c.listing_id, ranked.c.price, ranked.c.rn_first, ranked.c.rn_last).where(
        or_(ranked.c.rn_first == 1, ranked.c.rn_last == 1)
    )


def _latest_stmt() -> Select[Any]:
    """The last reading per listing (fetched_at, then id): only the columns the worklist shows."""
    ranked = select(
        _LO.listing_id.label("listing_id"),
        _LO.fetched_at.label("fetched_at"),
        _LO.buy_box_seller.label("buy_box_seller"),
        _LO.buy_box_own.label("buy_box_own"),
        _LO.extracted_availability.label("extracted_availability"),
        _LO.extracted_promo_badge.label("extracted_promo_badge"),
        _LO.parse_flags["cpor_activation"].label("activation"),
        func.row_number()
        .over(partition_by=_LO.listing_id, order_by=(_LO.fetched_at.desc(), _LO.id.desc()))
        .label("rn"),
    ).subquery("latest")
    return select(
        ranked.c.listing_id,
        ranked.c.fetched_at,
        ranked.c.buy_box_seller,
        ranked.c.buy_box_own,
        ranked.c.extracted_availability,
        ranked.c.extracted_promo_badge,
        ranked.c.activation,
    ).where(ranked.c.rn == 1)


def _timing_stmt() -> Select[Any]:
    """Stored promo-basis results that can prove timing, in the order the rule reads them.

    Failed fetches and parses are left out here (they prove nothing, ``_failed_read``); the rule
    still checks the stored ``snapshot_stored`` flag.
    """
    activation = _LO.parse_flags["cpor_activation"]
    return (
        select(
            _LO.id.label("id"),
            _LO.listing_id.label("listing_id"),
            _LO.fetched_at.label("fetched_at"),
            _LO.http_status.label("http_status"),
            _LO.parse_status.label("parse_status"),
            _LO.parse_flags["snapshot_stored"].astext.label("snapshot_stored"),
            activation.label("activation"),
        )
        .where(
            activation["price_basis"].astext == "promo",
            activation["status"].astext.in_((_AT_PRICE, _OFF_PRICE)),
            or_(_LO.http_status.is_(None), _LO.http_status == 200),
            _LO.parse_status == "ok",
        )
        .order_by(_LO.listing_id, _LO.fetched_at.asc(), _LO.id.asc())
    )


def build_listing_intelligence(
    session: Session, *, alert_days: int | None = None
) -> dict[str, Any]:
    days = _alert_days() if alert_days is None else int(alert_days)
    listings = list(session.execute(_listing_stmt()))
    counts = {int(r.listing_id): r for r in session.execute(_count_stmt())}
    first_prices: dict[int, float] = {}
    last_prices: dict[int, float] = {}
    for r in session.execute(_priced_ends_stmt()):
        if r.rn_first == 1:
            first_prices[int(r.listing_id)] = float(r.price)
        if r.rn_last == 1:
            last_prices[int(r.listing_id)] = float(r.price)
    latest = {int(r.listing_id): r for r in session.execute(_latest_stmt())}
    checks: dict[int, list[Any]] = {}
    for r in session.execute(_timing_stmt()):
        flags: dict[str, Any] = {
            "cpor_activation": r.activation if isinstance(r.activation, dict) else {}
        }
        if r.snapshot_stored is not None:
            flags["snapshot_stored"] = r.snapshot_stored
        checks.setdefault(int(r.listing_id), []).append(
            SimpleNamespace(
                id=r.id,
                fetched_at=r.fetched_at,
                http_status=r.http_status,
                parse_status=r.parse_status,
                parse_flags=flags,
            )
        )

    items: list[dict[str, Any]] = []
    for listing in listings:
        lid = int(listing.id)
        agg = counts.get(lid)
        n_obs = int(agg.n) if agg is not None else 0
        first_ts = agg.first_ts if agg is not None else None
        last_ts = agg.last_ts if agg is not None else None
        span_days = None
        if first_ts is not None and last_ts is not None:
            span_days = max(0, (last_ts - first_ts).days)
        ready = bool(span_days is not None and span_days >= MIN_SPAN_DAYS and n_obs >= 2)
        # Prices are the shopper's buy-box price (``extracted_price``). Needs do not read them.
        first_price = first_prices.get(lid)
        last_price = last_prices.get(lid)
        last_obs = latest.get(lid)
        own = last_obs.buy_box_own if last_obs is not None else None
        act = _activation(last_obs)
        row = {
            "listing_id": lid,
            "customer_id": int(listing.customer_id),
            "product_id": int(listing.product_id) if listing.product_id is not None else None,
            "marketplace": listing.marketplace,
            "url": listing.url,
            "external_id": listing.external_id,
            "observation_count": n_obs,
            "span_days": span_days,
            "ready": ready,
            "history_status": "ready" if ready else "accumulating",
            "first_price": first_price,
            "last_price": last_price,
            "shoppers_price": last_price,
            "buy_box_seller": last_obs.buy_box_seller if last_obs is not None else None,
            "buy_box_own": own,
            "buy_box_label": "Own" if own is True else "Competition" if own is False else None,
            "price_drift_pct": _drift(first_price, last_price),
            "activation_status": act.get("status"),
            "activation_message": act.get("message"),
            "case_price": act.get("case_price"),
            "case_id": act.get("case_id"),
            "last_availability": last_obs.extracted_availability if last_obs is not None else None,
            "last_promo_badge": last_obs.extracted_promo_badge if last_obs is not None else None,
            "last_fetched": last_obs.fetched_at.isoformat() if last_obs is not None else None,
            "worklist": bool(ready and act.get("status") == "not_activated"),
            "activation_timing": activation_timing(checks.get(lid, []), alert_days=days),
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
