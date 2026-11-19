"""P5 listing intelligence v1 on cip_test (BACKLOG-226): the set-based read equals the old result.

The reference below is the previous per-listing implementation (one ORM load of every observation,
page copy included). The service now answers from a fixed number of aggregate statements; for the
same seeded rows every field must come out identical. Rows roll back; cip_test only.
"""

# ruff: noqa: F811 - pytest fixture import pattern
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.models.dimensions import DimCustomer, DimProduct
from app.models.listing_capture import CustomerListing, ListingObservation
from app.services.listing_capture import intelligence_v1 as mod
from app.services.listing_capture.intelligence_v1 import build_listing_intelligence
from sqlalchemy import event, select
from sqlalchemy.orm import Session
from test_listing_coverage import db_session  # noqa: F401 - shared cip_test-only fixture

AT, OFF = "price_consistent", "not_activated"
T0 = datetime(2026, 8, 1, 9, tzinfo=UTC)
PAGE_COPY = b"<html>" + b"x" * 4096 + b"</html>"


def _reference(session: Session, listing: CustomerListing, *, days: int) -> dict[str, Any]:
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
    span = (
        max(0, (last_ts - first_ts).days) if first_ts is not None and last_ts is not None else None
    )
    ready = bool(span is not None and span >= mod.MIN_SPAN_DAYS and len(obs) >= 2)
    first_price = float(priced[0].extracted_price) if priced else None
    last_price = float(priced[-1].extracted_price) if priced else None
    last = obs[-1] if obs else None
    own = last.buy_box_own if last is not None else None
    act = mod._activation(last)
    return {
        "listing_id": int(listing.id),
        "customer_id": int(listing.customer_id),
        "product_id": int(listing.product_id) if listing.product_id is not None else None,
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
        "buy_box_seller": last.buy_box_seller if last is not None else None,
        "buy_box_own": own,
        "buy_box_label": "Own" if own is True else "Competition" if own is False else None,
        "price_drift_pct": mod._drift(first_price, last_price),
        "activation_status": act.get("status"),
        "activation_message": act.get("message"),
        "case_price": act.get("case_price"),
        "case_id": act.get("case_id"),
        "last_availability": last.extracted_availability if last is not None else None,
        "last_promo_badge": last.extracted_promo_badge if last is not None else None,
        "last_fetched": last.fetched_at.isoformat() if last is not None else None,
        "worklist": bool(ready and act.get("status") == "not_activated"),
        "activation_timing": mod.activation_timing(obs, alert_days=days),
    }


def _seed_listing(session: Session, tag: str, n: int) -> CustomerListing:
    tenant = f"intel-{tag}"
    customer = DimCustomer(
        code=f"intel-{tag}-{n}",
        name=f"Account {tag} {n}",
        customer_status="active",
        is_key_account=False,
        tenant_id=tenant,
    )
    product = DimProduct(
        tenant_id=tenant, sku=f"sku-{tag}-{n}", name=f"Item {tag} {n}", is_active=True
    )
    session.add_all([customer, product])
    session.flush()
    listing = CustomerListing(
        customer_id=customer.id,
        product_id=None if n % 4 == 0 else product.id,
        url=f"https://shop-a.example.test/{tag}/{n}",
        marketplace="shop-a",
        status="active",
        source="manual",
        external_id=f"ext-{n}",
    )
    session.add(listing)
    session.flush()
    return listing


def _obs(
    session: Session,
    listing: CustomerListing,
    *,
    day: int,
    price: float | None,
    status: str | None = None,
    hour: int = 9,
    http_status: int | None = 200,
    parse_status: str = "ok",
    own: bool | None = None,
    extra_flags: dict[str, Any] | None = None,
) -> ListingObservation:
    when = T0 + timedelta(days=day, hours=hour - 9)
    flags: dict[str, Any] = dict(extra_flags or {})
    if status:
        flags["cpor_activation"] = {
            "status": status,
            "message": f"m-{status}",
            "case_price": 999,
            "case_id": 7,
            "case_code": "CASE-7",
            "price_basis": "promo",
            "as_of": when.date().isoformat(),
            "line_window_start": "2026-08-01",
            "line_window_end": "2026-08-30",
        }
    row = ListingObservation(
        listing_id=listing.id,
        fetched_at=when,
        extracted_price=price,
        extracted_availability="in_stock" if price else None,
        extracted_promo_badge="sale" if day % 2 else None,
        parser_version="test",
        http_status=http_status,
        parse_status=parse_status,
        parse_flags=flags,
        raw_snapshot=PAGE_COPY,
        buy_box_seller=f"seller-{listing.id}-{day}",
        buy_box_own=own,
    )
    session.add(row)
    session.flush()
    return row


def _seed_all(session: Session) -> list[CustomerListing]:
    tag = uuid.uuid4().hex[:10]
    listings = [_seed_listing(session, tag, n) for n in range(1, 10)]
    a, b, c, d, e, f, g, h, i = listings
    # a: short history (accumulating). The original unit scenario.
    _obs(session, a, day=0, price=900, status=OFF)
    _obs(session, a, day=3, price=910, status=OFF)
    # b: ready, last check off price (worklist). The original unit scenario.
    _obs(session, b, day=0, price=900, status=AT, own=True)
    _obs(session, b, day=14, price=1200, status=OFF, own=False)
    # c: no readings at all.
    # d: unpriced readings only.
    _obs(session, d, day=0, price=None)
    _obs(session, d, day=15, price=None)
    # e: late activation then at price, then off price early (both timing alerts).
    for day, price, status in [
        (0, 900, OFF),
        (4, 910, OFF),
        (6, 999, AT),
        (20, 1200, OFF),
        (25, 999, AT),
    ]:
        _obs(session, e, day=day, price=price, status=status)
    # f: a failed fetch that parsed to a price proves nothing (not a late-activation alert).
    _obs(session, f, day=0, price=999, status=AT)
    _obs(session, f, day=10, price=700, status=OFF, http_status=503)
    _obs(session, f, day=12, price=700, status=OFF, parse_status="parse_failed")
    _obs(session, f, day=14, price=700, status=OFF, extra_flags={"snapshot_stored": "fetch_failed"})
    # g: three readings with the same fetched_at: order falls back to id; null price in between.
    _obs(session, g, day=3, price=100, status=OFF)
    _obs(session, g, day=3, price=None, status=AT)
    _obs(session, g, day=3, price=120, status=None)
    # h: inserted out of fetched_at order; non-promo basis and a stray non-dict flag value.
    late = _obs(session, h, day=20, price=1500, status=AT)
    _obs(session, h, day=1, price=1000, status=OFF)
    late.parse_flags = {**late.parse_flags, "extra": [1, 2]}
    sell_out = _obs(session, h, day=10, price=1100, status=OFF)
    sell_out.parse_flags = {
        "cpor_activation": {**sell_out.parse_flags["cpor_activation"], "price_basis": "sell_out"}
    }
    # i: zero first price (drift undefined) and a non-dict activation value on the latest reading.
    _obs(session, i, day=0, price=0)
    newest = _obs(session, i, day=16, price=50)
    newest.parse_flags = {"cpor_activation": "not-an-object"}
    session.flush()
    return listings


def test_results_equal_the_per_listing_implementation(db_session: Session) -> None:
    listings = _seed_all(db_session)
    db_session.flush()
    db_session.expire_all()
    expected = {int(x.id): _reference(db_session, x, days=3) for x in listings}
    db_session.expire_all()

    out = build_listing_intelligence(db_session, alert_days=3)

    assert out["data_unavailable"] is False
    got = {r["listing_id"]: r for r in out["items"] if r["listing_id"] in expected}
    assert set(got) == set(expected)
    for lid, row in got.items():
        assert row == expected[lid], f"listing {lid}"
    assert any(r["worklist"] for r in expected.values())
    assert any(r["activation_timing"] for r in expected.values())
    assert any(r["observation_count"] == 0 for r in expected.values())
    # Roll-ups agree with the rows (other rows may exist on cip_test, so compare the whole output).
    items = out["items"]
    assert out["listings"] == len(items)
    assert out["ready"] == sum(1 for r in items if r["ready"])
    assert out["accumulating"] == out["listings"] - out["ready"]
    assert out["not_activated_worklist"] == sum(1 for r in items if r["worklist"])
    assert [r["listing_id"] for r in out["worklist"]] == [
        r["listing_id"] for r in items if r["worklist"]
    ]
    assert [a for a in out["timing_alerts"] if a["listing_id"] in expected] == [
        {
            **alert,
            "listing_id": lid,
            "customer_id": expected[lid]["customer_id"],
            "product_id": expected[lid]["product_id"],
            "marketplace": expected[lid]["marketplace"],
            "url": expected[lid]["url"],
        }
        for lid in sorted(expected)
        for alert in expected[lid]["activation_timing"]
    ]


def test_runs_a_fixed_number_of_statements_and_never_reads_the_page_copy(
    db_session: Session,
) -> None:
    _seed_all(db_session)
    db_session.flush()
    seen: list[str] = []

    def _record(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        seen.append(statement)

    bind = db_session.get_bind()
    event.listen(bind, "before_cursor_execute", _record)
    try:
        build_listing_intelligence(db_session, alert_days=3)
    finally:
        event.remove(bind, "before_cursor_execute", _record)
    selects = [s for s in seen if s.lstrip().upper().startswith(("SELECT", "WITH"))]
    assert 1 <= len(selects) <= 6
    assert not any("raw_snapshot" in s.lower() for s in seen)
