"""PR #106 regressions on cip_test only; reuse the identity-checking rollback fixture."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy.orm import Session

from app.models.cpor import CporCase, CporCaseLine
from app.models.dimensions import DimCustomer, DimProduct
from app.models.listing_capture import CustomerListing, ListingObservation
from app.services.listing_capture.cpor_activation import evaluate_cpor_activation
from app.services.listing_capture.intelligence_v1 import build_listing_intelligence
from test_listing_coverage import db_session  # noqa: F401 - shared cip_test-only fixture

START, END = date(2026, 11, 1), date(2026, 11, 30)


def _setup(session: Session, promotion_type: str) -> CustomerListing:
    tag = uuid.uuid4().hex[:12]
    tenant = f"activation-{tag}"
    customer = DimCustomer(
        code=f"activation-{tag}",
        name=f"Account {tag}",
        customer_status="active",
        is_key_account=False,
        tenant_id=tenant,
    )
    product = DimProduct(tenant_id=tenant, sku=f"sku-{tag}", name=f"Item {tag}", is_active=True)
    session.add_all([customer, product])
    session.flush()
    listing = CustomerListing(
        customer_id=customer.id,
        product_id=product.id,
        url=f"https://shop-a.example.test/{tag}",
        marketplace="shop-a",
        status="active",
        source="manual",
    )
    case = CporCase(
        tenant_id=tenant,
        customer_id=customer.id,
        case_code=f"ACT-{tag}",
        promotion_type=promotion_type,
        window_start=START,
        window_end=END,
        status="active",
        origin="native",
    )
    session.add_all([listing, case])
    session.flush()
    session.add(
        CporCaseLine(
            case_id=case.id,
            product_id=product.id,
            window_start=START,
            window_end=END,
            srp=999,
            vat_rate=0,
            dealer_margin_pct=0,
            estimate_qty=1,
        )
    )
    session.flush()
    return listing


def _record(session: Session, listing: CustomerListing, when: datetime, price: float):
    activation = evaluate_cpor_activation(session, listing, listing_price=price, as_of=when.date())
    observation = ListingObservation(
        listing_id=listing.id,
        fetched_at=when,
        extracted_price=price,
        parser_version="test",
        http_status=200,
        parse_status="ok",
        parse_flags={"cpor_activation": activation},
    )
    session.add(observation)
    session.flush()
    return observation


def _timing(session: Session, listing: CustomerListing):
    # Reload JSONB and timestamps rather than relying on the identity map.
    listing_id = int(listing.id)
    session.expire_all()
    out = build_listing_intelligence(session, alert_days=3)
    row = next(row for row in out["items"] if row["listing_id"] == listing_id)
    alerts = [a for a in out["timing_alerts"] if a["listing_id"] == listing_id]
    assert out["data_unavailable"] is False
    identity_fields = {"listing_id", "customer_id", "product_id", "marketplace", "url"}
    assert row["activation_timing"] == [
        {key: value for key, value in alert.items() if key not in identity_fields}
        for alert in alerts
    ]
    return row, alerts


@pytest.mark.parametrize("equal_timestamps", [False, True])
def test_stored_same_day_transitions_and_recovery(db_session: Session, equal_timestamps: bool):
    listing = _setup(db_session, "Sell-Through PP")
    hours = [9] * 4 if equal_timestamps else [9, 12, 15, 18]
    checks = list(zip(hours, [1200, 900, 1200, 900]))
    if not equal_timestamps:
        # Insertion order differs from fetch order; the read query must order by fetched_at.
        checks.reverse()
    for hour, price in checks:
        observation = _record(db_session, listing, datetime(2026, 11, 4, hour, tzinfo=UTC), price)
        assert observation.parse_flags["cpor_activation"]["price_basis"] == "promo"

    _, alerts = _timing(db_session, listing)
    assert {a["kind"] for a in alerts} == {"late_activation", "early_deactivation"}
    assert len(alerts) == 2
    late = next(a for a in alerts if a["kind"] == "late_activation")
    early = next(a for a in alerts if a["kind"] == "early_deactivation")
    assert late["not_at_price_on"] == late["at_price_from"] == "2026-11-04"
    assert late["days_late_at_least"] == 3
    assert early["last_at_price_on"] == early["off_price_on"] == "2026-11-04"
    assert early["back_at_price_on"] == "2026-11-04"
    assert early["days_early_at_least"] == 26


@pytest.mark.parametrize(
    "promotion_type, basis", [("Sell out PP", "sell_out"), ("Sell-Through PP", "promo")]
)
@pytest.mark.parametrize("first_price, kind", [(1200, "late_activation"), (900, "early_deactivation")])
def test_only_promotion_bars_produce_timing_alerts(
    db_session: Session, promotion_type: str, basis: str, first_price: float, kind: str
):
    listing = _setup(db_session, promotion_type)
    first = _record(db_session, listing, datetime(2026, 11, 1, 9, tzinfo=UTC), first_price)
    last = _record(db_session, listing, datetime(2026, 11, 4, 9, tzinfo=UTC), 1200)
    assert first.parse_flags["cpor_activation"]["price_basis"] == basis
    assert last.parse_flags["cpor_activation"]["price_basis"] == basis

    row, alerts = _timing(db_session, listing)
    assert row["activation_status"] == "not_activated"  # Point-in-time fallback still works.
    assert [a["kind"] for a in alerts] == ([kind] if basis == "promo" else [])
