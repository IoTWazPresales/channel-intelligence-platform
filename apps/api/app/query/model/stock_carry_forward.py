"""D-0119: distributor reported stock carries forward across periods at read time.

Warren 9 Nov 2026: a period with no new count shows the last count and is flagged
as carried forward. A pair that has never been counted stays empty (not zero).
Channel Ops derived stock (channel_stock / weeks of cover) stays governed and still
refuses period — this module is only for the distributor_stock model measure.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Iterable, Sequence

from app.query.calendar_grain import bucket_end, bucket_start_to_key


@dataclass(frozen=True)
class StockObservation:
    distributor_id: int
    product_id: int
    as_of_date: date
    on_hand_units: float


def _month_floor(d: date) -> date:
    return date(d.year, d.month, 1)


def _quarter_floor(d: date) -> date:
    return date(d.year, ((d.month - 1) // 3) * 3 + 1, 1)


def _week_floor(d: date) -> date:
    # Monday-start week, matching date_trunc('week') on Postgres for ISO-like weeks.
    return d - timedelta(days=d.weekday())


def bucket_floor(d: date, grain: str) -> date:
    if grain == "day":
        return d
    if grain == "week":
        return _week_floor(d)
    if grain == "month":
        return _month_floor(d)
    if grain == "quarter":
        return _quarter_floor(d)
    if grain == "year":
        return date(d.year, 1, 1)
    raise ValueError(f"unsupported period grain for stock carry-forward: {grain!r}")


def next_bucket_start(start: date, grain: str) -> date:
    if grain == "day":
        return start + timedelta(days=1)
    if grain == "week":
        return start + timedelta(days=7)
    if grain == "month":
        if start.month == 12:
            return date(start.year + 1, 1, 1)
        return date(start.year, start.month + 1, 1)
    if grain == "quarter":
        m = start.month + 3
        if m > 12:
            return date(start.year + 1, m - 12, 1)
        return date(start.year, m, 1)
    if grain == "year":
        return date(start.year + 1, 1, 1)
    raise ValueError(f"unsupported period grain for stock carry-forward: {grain!r}")


def iter_bucket_starts(period_from: date, period_to: date, grain: str) -> list[date]:
    """Inclusive spine of bucket starts covering [period_from, period_to]."""
    if period_from > period_to:
        return []
    start = bucket_floor(period_from, grain)
    end_floor = bucket_floor(period_to, grain)
    out: list[date] = []
    cur = start
    # Guard against runaway spines: refuse (raise) rather than silently truncate.
    for _ in range(5000):
        out.append(cur)
        if cur >= end_floor:
            return out
        cur = next_bucket_start(cur, grain)
    raise ValueError(
        f"period spine exceeds 5000 {grain} buckets from {period_from} to {period_to}; narrow the window"
    )


def _coalesce_same_date(history: Sequence[StockObservation]) -> list[StockObservation]:
    """Sum on_hand for the same (distributor, product, as_of_date); keep one row per date."""
    by_date: dict[date, float] = {}
    dist_id = product_id = None
    for obs in history:
        dist_id = obs.distributor_id
        product_id = obs.product_id
        by_date[obs.as_of_date] = by_date.get(obs.as_of_date, 0.0) + float(obs.on_hand_units)
    assert dist_id is not None and product_id is not None
    return [
        StockObservation(dist_id, product_id, d, units)
        for d, units in sorted(by_date.items())
    ]


def _latest_on_or_before(
    history: Sequence[StockObservation],
    as_of: date,
) -> StockObservation | None:
    picked: StockObservation | None = None
    for obs in history:
        if obs.as_of_date <= as_of and (picked is None or obs.as_of_date >= picked.as_of_date):
            picked = obs
    return picked


def carry_forward_pair_series(
    observations: Sequence[StockObservation],
    *,
    buckets: Sequence[date],
    grain: str,
) -> list[dict[str, Any]]:
    """Carry one distributor×product series across ``buckets``.

    Returns one row per bucket that has a known count (fresh or carried). Buckets
    before the first count are omitted (stay empty, not zero-faked).
    """
    if not buckets:
        return []
    if not observations:
        return []
    history = _coalesce_same_date(observations)
    dist_id = history[0].distributor_id
    product_id = history[0].product_id
    rows: list[dict[str, Any]] = []
    for bs in buckets:
        if grain == "day":
            be = bs
        elif grain == "year":
            be = date(bs.year, 12, 31)
        else:
            be = bucket_end(bs, grain)
        picked = _latest_on_or_before(history, be)
        if picked is None:
            continue
        carried = picked.as_of_date < bs
        rows.append(
            {
                "distributor_id": dist_id,
                "product_id": product_id,
                "bucket_start": bs,
                "bucket_end": be,
                "bucket_key": bucket_start_to_key(bs, grain) if grain != "day" else bs.isoformat(),
                "on_hand": float(picked.on_hand_units),
                "carried_forward": carried,
                "source_as_of_date": picked.as_of_date,
            }
        )
    return rows


def carry_forward_all(
    observations: Iterable[StockObservation],
    *,
    period_from: date,
    period_to: date,
    grain: str,
) -> list[dict[str, Any]]:
    """Carry every distributor×product pair across the period spine."""
    buckets = iter_bucket_starts(period_from, period_to, grain)
    by_pair: dict[tuple[int, int], list[StockObservation]] = {}
    for obs in observations:
        by_pair.setdefault((obs.distributor_id, obs.product_id), []).append(obs)
    rows: list[dict[str, Any]] = []
    for pair_obs in by_pair.values():
        rows.extend(carry_forward_pair_series(pair_obs, buckets=buckets, grain=grain))
    rows.sort(key=lambda r: (r["bucket_start"], r["distributor_id"], r["product_id"]))
    return rows


def rollup_carry_rows(
    pair_rows: Sequence[dict[str, Any]],
    *,
    breakdowns: Sequence[str],
) -> list[dict[str, Any]]:
    """Sum on-hand across products/distributors within a bucket; keep period keys.

    ``carried_forward`` is true when every contributing pair value for that group
    is carried (no fresh count in the bucket for any member of the group).
    """
    want_period = "period" in breakdowns
    want_dist = "distributor" in breakdowns
    want_product = "product" in breakdowns
    groups: dict[tuple[Any, ...], dict[str, Any]] = {}
    for r in pair_rows:
        key_parts: list[Any] = []
        if want_period:
            key_parts.append(r["bucket_start"])
        if want_dist:
            key_parts.append(r["distributor_id"])
        if want_product:
            key_parts.append(r["product_id"])
        key = tuple(key_parts)
        g = groups.get(key)
        if g is None:
            g = {
                "on_hand": 0.0,
                "carried_forward": True,
                "fresh_count": 0,
                "pair_count": 0,
            }
            if want_period:
                g["bucket_start"] = r["bucket_start"]
                g["bucket_end"] = r["bucket_end"]
                g["bucket_key"] = r["bucket_key"]
            if want_dist:
                g["distributor_id"] = r["distributor_id"]
            if want_product:
                g["product_id"] = r["product_id"]
            groups[key] = g
        g["on_hand"] += float(r["on_hand"])
        g["pair_count"] += 1
        if not r["carried_forward"]:
            g["carried_forward"] = False
            g["fresh_count"] += 1
    out: list[dict[str, Any]] = []
    for g in groups.values():
        out.append(
            {
                **{k: v for k, v in g.items() if k not in {"fresh_count", "pair_count"}},
            }
        )
    out.sort(
        key=lambda r: (
            r.get("bucket_start") or date.min,
            r.get("distributor_id") or 0,
            r.get("product_id") or 0,
        )
    )
    return out
