"""Clash maths: a CPOR case window that overlaps a customer calendar event for the same customer.

Pure function. Dates are inclusive on both ends, so a window ending on the day an event starts is
a one-day clash and a window ending the day before is not.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from typing import Any


def _to_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def overlap_days(
    a_start: date, a_end: date, b_start: date, b_end: date
) -> tuple[date, date, int] | None:
    """The inclusive overlap of two date ranges as (start, end, days), or None when apart."""
    start = max(a_start, b_start)
    end = min(a_end, b_end)
    if start > end:
        return None
    return start, end, (end - start).days + 1


def compute_clashes(
    promotions: Iterable[dict[str, Any]], calendar_events: Iterable[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Every (promotion, event) pair of the same customer whose date ranges overlap.

    ``promotions``: dicts with ``case_id``, ``customer_id``, ``window_start``, ``window_end``.
    ``calendar_events``: dicts with ``id``, ``customer_id``, ``start_date``, ``end_date``.
    Events with no customer never clash. Output is ordered by customer, overlap start, case id,
    event id, and carries the promotion and the event so a caller can show both.
    """
    by_customer: dict[int, list[dict[str, Any]]] = {}
    for ev in calendar_events:
        cid = ev.get("customer_id")
        if cid is None:
            continue
        by_customer.setdefault(int(cid), []).append(ev)

    out: list[dict[str, Any]] = []
    for promo in promotions:
        cid = promo.get("customer_id")
        if cid is None:
            continue
        p_start, p_end = _to_date(promo["window_start"]), _to_date(promo["window_end"])
        for ev in by_customer.get(int(cid), []):
            found = overlap_days(
                p_start, p_end, _to_date(ev["start_date"]), _to_date(ev["end_date"])
            )
            if found is None:
                continue
            o_start, o_end, days = found
            out.append(
                {
                    "customer_id": int(cid),
                    "case_id": promo.get("case_id"),
                    "event_id": ev.get("id"),
                    "overlap_start": o_start,
                    "overlap_end": o_end,
                    "overlap_days": days,
                    "promotion": dict(promo),
                    "event": dict(ev),
                }
            )
    out.sort(
        key=lambda c: (
            c["customer_id"],
            c["overlap_start"],
            c["case_id"] if c["case_id"] is not None else -1,
            c["event_id"] if c["event_id"] is not None else -1,
        )
    )
    return out
