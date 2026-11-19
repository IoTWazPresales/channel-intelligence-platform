"""Listing intelligence is set-based (BACKLOG-226): no per-listing query, no raw_snapshot. No DB.

The session is a recording fake: it has no ``scalars``/``get``/``query``, so any ORM-entity load
or per-listing round trip fails loudly. Each statement is compiled for PostgreSQL and kept, so the
tests can count statements and read the SQL that would have been sent.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from app.services.listing_capture import intelligence_v1 as mod
from app.services.listing_capture.intelligence_v1 import (
    activation_timing,
    build_listing_intelligence,
)
from sqlalchemy.dialects import postgresql

AT, OFF = "price_consistent", "not_activated"
T0 = datetime(2026, 11, 1, 9, tzinfo=UTC)


def _sql(stmt: Any) -> str:
    return str(stmt.compile(dialect=postgresql.dialect()))


class RecordingSession:
    """Answers each statement from in-memory listings and observations, as the SQL would."""

    def __init__(self, listings: list[Any], observations: list[Any]) -> None:
        self.listings = listings
        self.observations = observations
        self.statements: list[str] = []

    def _by_listing(self, lid: int) -> list[Any]:
        rows = [o for o in self.observations if o.listing_id == lid]
        return sorted(rows, key=lambda o: (o.fetched_at, o.id))

    def execute(self, stmt: Any) -> list[Any]:
        sql = _sql(stmt)
        self.statements.append(sql)
        low = sql.lower()
        if "listing_observation" not in low:
            return list(self.listings)
        if "count(" in low:
            out = []
            for lst in self.listings:
                rows = self._by_listing(lst.id)
                if rows:
                    out.append(
                        SimpleNamespace(
                            listing_id=lst.id,
                            n=len(rows),
                            first_ts=rows[0].fetched_at,
                            last_ts=rows[-1].fetched_at,
                        )
                    )
            return out
        if "snapshot_stored" in low:  # the timing read (the SQL carries the keys as bind values)
            out = []
            for lst in self.listings:
                for o in self._by_listing(lst.id):
                    flags = o.parse_flags if isinstance(o.parse_flags, dict) else {}
                    act = flags.get("cpor_activation")
                    if not isinstance(act, dict):
                        continue
                    if act.get("price_basis") != "promo" or act.get("status") not in (AT, OFF):
                        continue
                    if (
                        o.http_status is not None and o.http_status != 200
                    ) or o.parse_status != "ok":
                        continue
                    out.append(
                        SimpleNamespace(
                            id=o.id,
                            listing_id=lst.id,
                            fetched_at=o.fetched_at,
                            http_status=o.http_status,
                            parse_status=o.parse_status,
                            snapshot_stored=flags.get("snapshot_stored"),
                            activation=act,
                        )
                    )
            return out
        if "buy_box_seller" in low:
            out = []
            for lst in self.listings:
                rows = self._by_listing(lst.id)
                if not rows:
                    continue
                last = rows[-1]
                flags = last.parse_flags if isinstance(last.parse_flags, dict) else {}
                out.append(
                    SimpleNamespace(
                        listing_id=lst.id,
                        fetched_at=last.fetched_at,
                        buy_box_seller=last.buy_box_seller,
                        buy_box_own=last.buy_box_own,
                        extracted_availability=last.extracted_availability,
                        extracted_promo_badge=last.extracted_promo_badge,
                        activation=flags.get("cpor_activation"),
                    )
                )
            return out
        out = []
        for lst in self.listings:
            priced = [o for o in self._by_listing(lst.id) if o.extracted_price is not None]
            if not priced:
                continue
            for i, o in enumerate(priced):
                rn_first, rn_last = i + 1, len(priced) - i
                if rn_first == 1 or rn_last == 1:
                    out.append(
                        SimpleNamespace(
                            listing_id=lst.id,
                            price=o.extracted_price,
                            rn_first=rn_first,
                            rn_last=rn_last,
                        )
                    )
        return out


def _listing(i: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=i,
        customer_id=100 + i,
        product_id=None if i % 3 == 0 else 500 + i,
        marketplace="shop-a" if i % 2 else "shop-b",
        url=f"https://shop.example.test/{i}",
        external_id=f"x{i}",
    )


def _obs(
    oid: int,
    listing_id: int,
    *,
    day: int,
    price: float | None,
    status: str | None = None,
    hour: int = 9,
    http_status: int | None = 200,
    parse_status: str = "ok",
    own: bool | None = None,
    window: tuple[str, str] = ("2026-11-01", "2026-11-30"),
) -> SimpleNamespace:
    when = T0 + timedelta(days=day, hours=hour - 9)
    flags: dict[str, Any] = {}
    if status:
        flags["cpor_activation"] = {
            "status": status,
            "message": f"m-{status}",
            "case_price": 999,
            "case_id": 7,
            "case_code": "CASE-7",
            "price_basis": "promo",
            "as_of": when.date().isoformat(),
            "line_window_start": window[0],
            "line_window_end": window[1],
        }
    return SimpleNamespace(
        id=oid,
        listing_id=listing_id,
        fetched_at=when,
        extracted_price=None if price is None else Decimal(str(price)),
        extracted_availability="in_stock" if price else None,
        extracted_promo_badge="sale" if day % 2 else None,
        http_status=http_status,
        parse_status=parse_status,
        parse_flags=flags,
        buy_box_seller=f"seller-{oid}",
        buy_box_own=own,
    )


def _seed(n_listings: int) -> tuple[list[Any], list[Any]]:
    listings = [_listing(i) for i in range(1, n_listings + 1)]
    observations: list[Any] = []
    oid = 1
    for lst in listings:
        for day, price, status in [
            (0, 900.0, OFF),
            (4, None, OFF),
            (8, 910.0, AT),
            (20, 1200.0, OFF),
        ]:
            observations.append(
                _obs(oid, lst.id, day=day, price=price, status=status, own=lst.id % 2 == 0)
            )
            oid += 1
    return listings, observations


def test_statement_count_does_not_grow_with_listings() -> None:
    counts = {}
    for n in (1, 3, 60):
        listings, observations = _seed(n)
        session = RecordingSession(listings, observations)
        out = build_listing_intelligence(session, alert_days=3)  # type: ignore[arg-type]
        assert out["listings"] == n
        counts[n] = len(session.statements)
    assert counts[1] == counts[3] == counts[60]
    assert counts[60] <= 6


def test_no_statement_selects_the_page_copy_or_a_whole_entity() -> None:
    listings, observations = _seed(5)
    session = RecordingSession(listings, observations)
    build_listing_intelligence(session, alert_days=3)  # type: ignore[arg-type]
    assert session.statements
    for sql in session.statements:
        assert "raw_snapshot" not in sql.lower()
        # Whole-entity loads would select every column of listing_observation / customer_listing.
        assert "parser_version" not in sql.lower()
        assert "meta_json" not in sql.lower()


def test_an_empty_registry_costs_the_same_fixed_statements() -> None:
    session = RecordingSession([], [])
    out = build_listing_intelligence(session, alert_days=3)  # type: ignore[arg-type]
    assert out["listings"] == 0 and out["items"] == [] and out["timing_alerts"] == []
    assert out["data_unavailable"] is False


def _reference(listings: list[Any], observations: list[Any], *, days: int) -> list[dict[str, Any]]:
    """The previous per-listing implementation, kept here as the meaning of every field."""
    rows = []
    for listing in listings:
        obs = sorted(
            (o for o in observations if o.listing_id == listing.id),
            key=lambda o: (o.fetched_at, o.id),
        )
        priced = [o for o in obs if o.extracted_price is not None]
        first_ts = obs[0].fetched_at if obs else None
        last_ts = obs[-1].fetched_at if obs else None
        span = max(0, (last_ts - first_ts).days) if first_ts and last_ts else None
        ready = bool(span is not None and span >= mod.MIN_SPAN_DAYS and len(obs) >= 2)
        first_price = float(priced[0].extracted_price) if priced else None
        last_price = float(priced[-1].extracted_price) if priced else None
        last = obs[-1] if obs else None
        own = last.buy_box_own if last else None
        act = mod._activation(last)
        rows.append(
            {
                "listing_id": listing.id,
                "customer_id": listing.customer_id,
                "product_id": listing.product_id,
                "marketplace": listing.marketplace,
                "url": listing.url,
                "external_id": listing.external_id,
                "observation_count": len(obs),
                "span_days": span,
                "ready": ready,
                "history_status": "ready" if ready else "accumulating",
                "first_price": first_price,
                "last_price": last_price,
                "shoppers_price": last_price,
                "buy_box_seller": last.buy_box_seller if last else None,
                "buy_box_own": own,
                "buy_box_label": "Own" if own is True else "Competition" if own is False else None,
                "price_drift_pct": mod._drift(first_price, last_price),
                "activation_status": act.get("status"),
                "activation_message": act.get("message"),
                "case_price": act.get("case_price"),
                "case_id": act.get("case_id"),
                "last_availability": last.extracted_availability if last else None,
                "last_promo_badge": last.extracted_promo_badge if last else None,
                "last_fetched": last.fetched_at.isoformat() if last else None,
                "worklist": bool(ready and act.get("status") == "not_activated"),
                "activation_timing": activation_timing(obs, alert_days=days),
            }
        )
    return rows


def test_every_field_equals_the_per_listing_result() -> None:
    listings, observations = _seed(7)
    nid = len(observations) + 1
    # A listing with no readings, one with unpriced readings only, one whose latest read failed,
    # one whose off-price check was a failed fetch (proves nothing), one with ties on fetched_at.
    listings += [_listing(8), _listing(9), _listing(10), _listing(11), _listing(12)]
    observations += [
        _obs(nid, 9, day=0, price=None, status=None),
        _obs(nid + 1, 9, day=15, price=None, status=None),
        _obs(nid + 2, 10, day=0, price=500.0, status=AT),
        _obs(nid + 3, 10, day=20, price=None, status=OFF, http_status=503),
        _obs(nid + 4, 11, day=0, price=800.0, status=AT),
        _obs(nid + 5, 11, day=15, price=700.0, status=OFF, parse_status="parse_failed"),
        _obs(nid + 6, 12, day=3, price=100.0, status=OFF, hour=9),
        _obs(nid + 7, 12, day=3, price=110.0, status=AT, hour=9),
        _obs(nid + 8, 12, day=3, price=120.0, status=None, hour=9),
    ]
    expected = _reference(listings, observations, days=3)
    session = RecordingSession(listings, observations)
    out = build_listing_intelligence(session, alert_days=3)  # type: ignore[arg-type]
    assert out["items"] == expected
    assert out["listings"] == len(listings)
    assert out["ready"] == sum(1 for r in expected if r["ready"])
    assert out["accumulating"] == len(listings) - out["ready"]
    assert out["not_activated_worklist"] == sum(1 for r in expected if r["worklist"])
    assert [r["listing_id"] for r in out["worklist"]] == [
        r["listing_id"] for r in expected if r["worklist"]
    ]
    assert out["min_span_days"] == 14 and out["activation_alert_days"] == 3
    assert out["late_activation_count"] + out["early_deactivation_count"] == len(
        out["timing_alerts"]
    )
    flat = [a for r in expected for a in r["activation_timing"]]
    assert len(out["timing_alerts"]) == len(flat) and flat


def test_the_configured_threshold_is_used(monkeypatch: pytest.MonkeyPatch) -> None:
    listings, observations = _seed(2)
    monkeypatch.setattr(mod, "_alert_days", lambda: 100)
    out = build_listing_intelligence(RecordingSession(listings, observations))  # type: ignore[arg-type]
    assert out["activation_alert_days"] == 100
    assert out["timing_alerts"] == []
