"""Price matrix end to end on cip_test (step 1, N-0121).

Mock-only tests let the listed_products UnboundLocalError through (fixed in 5ef007ae), so this runs
the real SQL on a tiny sample inside the shared rollback fixture: 2 customers, 3 products, a line-up
case with MSRP lines, listings with observations, one Sell out PP case and one Sell-Through PP case.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupLine
from app.models.cpor import CporCase, CporCaseLine
from app.models.dimensions import DimCustomer, DimProduct
from app.models.listing_capture import CustomerListing, ListingObservation
from app.services.listing_capture.price_matrix import SRP_REASON_PENDING, build_price_matrix
from sqlalchemy.orm import Session
from test_listing_coverage import db_session  # noqa: F401 - shared cip_test-only fixture


def _sample(session: Session) -> dict:
    tag = uuid.uuid4().hex[:10]
    tenant = f"matrix-{tag}"
    cust_a = DimCustomer(
        code=f"ma-{tag}",
        name=f"Shop A {tag}",
        customer_status="active",
        is_key_account=False,
        tenant_id=tenant,
    )
    cust_b = DimCustomer(
        code=f"mb-{tag}",
        name=f"Shop B {tag}",
        customer_status="active",
        is_key_account=False,
        tenant_id=tenant,
    )
    products = [
        DimProduct(
            tenant_id=tenant,
            sku=f"sku{i}-{tag}",
            name=f"Item {i} {tag}",
            sales_model_name=f"MODEL-{i}-{tag}",
            is_active=True,
        )
        for i in range(3)
    ]
    session.add_all([cust_a, cust_b, *products])
    session.flush()
    p0, p1, p2 = products

    # Line-up MSRPs, including a high one: the matrix must not take the highest MSRP ever as SRP.
    lineup = CommercialLineupCase(
        period_label="sample", inferred_period_start=date.today().replace(day=1)
    )
    session.add(lineup)
    session.flush()
    session.add_all(
        [
            CommercialLineupLine(
                case_id=lineup.id, product_id=p0.id, customer_id=cust_a.id, msrp_local=1500
            ),
            CommercialLineupLine(
                case_id=lineup.id, product_id=p0.id, customer_id=cust_b.id, msrp_local=9999
            ),
            CommercialLineupLine(
                case_id=lineup.id, product_id=p1.id, customer_id=cust_a.id, msrp_local=800
            ),
        ]
    )

    def listing(customer: DimCustomer, product: DimProduct, status: str) -> CustomerListing:
        row = CustomerListing(
            customer_id=customer.id,
            product_id=product.id,
            url=f"https://shop.example.test/{customer.code}/{product.sku}",
            marketplace="shop",
            status=status,
            source="manual",
        )
        session.add(row)
        return row

    l_a0 = listing(cust_a, p0, "active")
    l_b0 = listing(cust_b, p0, "out_of_stock")
    l_a1 = listing(cust_a, p1, "active")
    listing(cust_b, p2, "active")  # listed, no observation yet
    session.flush()

    now = datetime.now(UTC)
    old = now - timedelta(days=20)
    session.add_all(
        [
            ListingObservation(
                listing_id=l_a0.id,
                fetched_at=old,
                extracted_price=1300,
                parser_version="t",
                parse_status="ok",
            ),
            ListingObservation(
                listing_id=l_a0.id,
                fetched_at=now - timedelta(days=3),
                extracted_price=1200,
                parser_version="t",
                parse_status="ok",
            ),
            # A newer failed read must not replace the last good price.
            ListingObservation(
                listing_id=l_a0.id,
                fetched_at=now,
                extracted_price=None,
                parser_version="t",
                parse_status="parse_failed",
            ),
            ListingObservation(
                listing_id=l_b0.id,
                fetched_at=old,
                extracted_price=1100,
                parser_version="t",
                parse_status="ok",
            ),
            ListingObservation(
                listing_id=l_a1.id,
                fetched_at=now,
                extracted_price=700,
                parser_version="t",
                parse_status="ok",
            ),
        ]
    )

    today = date.today()
    for code, ptype, customer, product in (
        (f"SO-{tag}", "Sell out PP", cust_a, p0),
        (f"ST-{tag}", "Sell-Through PP", cust_a, p1),
    ):
        case = CporCase(
            tenant_id=tenant,
            customer_id=customer.id,
            case_code=code,
            case_name=f"{ptype} {tag}",
            promotion_type=ptype,
            window_start=today - timedelta(days=5),
            window_end=today + timedelta(days=5),
            status="active",
            origin="native",
        )
        session.add(case)
        session.flush()
        session.add(
            CporCaseLine(
                case_id=case.id,
                product_id=product.id,
                window_start=case.window_start,
                window_end=case.window_end,
                srp=999,
                vat_rate=0,
                dealer_margin_pct=0,
                estimate_qty=1,
            )
        )
    session.flush()
    return {"tenant": tenant, "a": cust_a, "b": cust_b, "p": products, "old": old}


def test_price_matrix_end_to_end(db_session: Session) -> None:  # noqa: F811 - fixture
    s = _sample(db_session)
    a, b = s["a"], s["b"]
    p0, p1, p2 = s["p"]

    out = build_price_matrix(db_session, tenant_id=s["tenant"], customer_ids=[a.id, b.id])

    assert [c["id"] for c in out["customers"]] == sorted([a.id, b.id])
    assert "cheapest_at" not in out["summary"]
    assert out["summary"]["product_count"] == 3
    # No SRP source is chosen, so there is no below-SRP comparison at all (None, not 0).
    assert out["summary"]["below_srp_count"] is None
    assert out["srp_source"] is None

    products = {p["id"]: p for p in out["products"]}
    assert products[p0.id]["sales_model_name"] == p0.sales_model_name
    assert products[p0.id]["sku"] == p0.sku
    assert products[p0.id]["name"] == p0.name
    for row in products.values():
        # Never the highest line-up MSRP ever (9999 for p0); pending until Warren picks a source.
        assert row["srp"] is None
        assert row["srp_reason"] == SRP_REASON_PENDING

    cells = {(c["product_id"], c["customer_id"]): c for c in out["cells"]}
    assert len(cells) == 6

    a0 = cells[(p0.id, a.id)]
    assert a0["price"] == 1200  # last good read, not the newer failed one
    assert a0["in_stock"] is True
    assert a0["observed_at"] is not None
    observed = datetime.fromisoformat(a0["observed_at"])
    assert timedelta(days=2) < datetime.now(UTC) - observed < timedelta(days=4)
    assert a0["srp"] is None and a0["srp_reason"] == SRP_REASON_PENDING
    # Sell out PP is distributor sell-out, never a promo tag on a shelf price.
    assert a0["promo"] is None

    b0 = cells[(p0.id, b.id)]
    assert b0["price"] == 1100
    assert b0["in_stock"] is False
    assert datetime.fromisoformat(b0["observed_at"]) == s["old"]

    a1 = cells[(p1.id, a.id)]
    assert a1["promo"] is not None
    assert a1["promo"]["promotion_type"] == "Sell-Through PP"

    b2 = cells[(p2.id, b.id)]
    assert b2["listing_id"] is not None
    assert b2["price"] is None and b2["observed_at"] is None and b2["in_stock"] is False

    missing = cells[(p2.id, a.id)]
    assert (
        missing["listing_id"] is None
        and missing["price"] is None
        and missing["observed_at"] is None
    )
