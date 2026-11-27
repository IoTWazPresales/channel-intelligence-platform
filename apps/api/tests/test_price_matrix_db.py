"""Price matrix end to end on cip_test (step 1, N-0121).

Mock-only tests let the listed_products UnboundLocalError through (fixed in 5ef007ae), so this runs
the real SQL on a tiny sample inside the shared rollback fixture: 2 customers, 3 products, a line-up
case with MSRP lines, listings with observations, one Sell out PP case and one Sell-Through PP case.

SRP rule (Warren, 26 Nov): sell out price, else Line up price, else website off promo price.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupLine
from app.models.cpor import CporCase, CporCaseLine
from app.models.dimensions import DimCustomer, DimProduct
from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.models.listing_capture import CustomerListing, ListingObservation
from app.services.listing_capture import price_matrix as price_matrix_module
from app.services.listing_capture.price_matrix import (
    BELOW_SRP_TOLERANCE,
    SRP_REASON_NONE,
    SRP_REASON_PENDING,
    SRP_REASON_VARIES,
    SRP_SOURCE_LINEUP,
    SRP_SOURCE_ORDER,
    SRP_SOURCE_SELL_OUT,
    SRP_SOURCE_WEBSITE,
    build_price_matrix,
    is_below_srp,
    resolve_srp,
)
from sqlalchemy.orm import Session
from test_listing_coverage import db_session  # noqa: F401 - shared cip_test-only fixture


@pytest.fixture(autouse=True)
def _isolated_tenant_profiles(tmp_path, monkeypatch):
    from app.services import commercial_tenant_profile as profile

    monkeypatch.setattr(profile, "_tenant_profiles_dir", lambda: tmp_path)


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
    from app.services.commercial_tenant_profile import save_tenant_profile_overrides

    # The rows below use these names. They are this sample tenant's saved config.
    save_tenant_profile_overrides(
        tenant,
        {
            "cpor_promotion_types": ["Sell out PP", "Sell-Through PP", "Stock PP (In-Direct)"],
            "cpor_channels": ["reseller"],
        },
    )
    p0, p1, p2 = products
    # A present spec becomes a matrix column. A blank value does not.
    p0.specs_json = {"screen": "14 in", "blank": " "}
    session.flush()

    # Line-up MSRPs, including an older, higher one for A/p0: the matrix takes the customer's latest
    # live line-up (1500), never the highest MSRP ever (2500).
    older = CommercialLineupCase(
        period_label="older",
        commercial_status="accepted",
        inferred_period_start=date.today() - timedelta(days=400),
    )
    lineup = CommercialLineupCase(
        period_label="sample",
        commercial_status="accepted",
        inferred_period_start=date.today().replace(day=1),
    )
    session.add_all([older, lineup])
    session.flush()
    session.add_all(
        [
            CommercialLineupLine(
                case_id=older.id, product_id=p0.id, customer_id=cust_a.id, msrp_local=2500
            ),
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
    l_b2 = listing(cust_b, p2, "active")  # listed, no observation yet
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
            currency_code="ZAR",
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
    return {
        "tenant": tenant,
        "a": cust_a,
        "b": cust_b,
        "p": products,
        "old": old,
        "lineup": lineup,
        "listings": {"a0": l_a0, "b0": l_b0, "a1": l_a1, "b2": l_b2},
    }


def test_price_matrix_end_to_end(db_session: Session) -> None:  # noqa: F811 - fixture
    s = _sample(db_session)
    a, b = s["a"], s["b"]
    p0, p1, p2 = s["p"]

    out = build_price_matrix(db_session, tenant_id=s["tenant"], customer_ids=[a.id, b.id])

    assert [c["id"] for c in out["customers"]] == sorted([a.id, b.id])
    assert "cheapest_at" not in out["summary"]
    assert out["summary"]["product_count"] == 3
    assert out["srp_source_order"] == list(SRP_SOURCE_ORDER)
    # No sell-out rows and no site regular price here, so every SRP is the customer's line-up price.
    # A/p0 (1200 in stock, SRP 1500) and A/p1 (700 in stock, SRP 800) are below; B/p0 is out of stock.
    assert out["summary"]["below_srp_count"] == 2

    products = {p["id"]: p for p in out["products"]}
    assert products[p0.id]["sales_model_name"] == p0.sales_model_name
    assert products[p0.id]["sku"] == p0.sku
    assert products[p0.id]["name"] == p0.name
    assert products[p0.id]["specs"] == {"screen": "14 in"}
    assert products[p1.id]["specs"] == {}
    # Product-level SRP is a figure only when every customer's SRP agrees.
    assert products[p0.id]["srp"] is None and products[p0.id]["srp_reason"] == SRP_REASON_VARIES
    assert products[p1.id]["srp"] == 800 and products[p1.id]["srp_source"] == SRP_SOURCE_LINEUP
    assert products[p2.id]["srp"] is None and products[p2.id]["srp_reason"] == SRP_REASON_NONE

    cells = {(c["product_id"], c["customer_id"]): c for c in out["cells"]}
    assert len(cells) == 6

    a0 = cells[(p0.id, a.id)]
    assert a0["price"] == 1200  # last good read, not the newer failed one
    assert a0["in_stock"] is True
    assert a0["observed_at"] is not None
    observed = datetime.fromisoformat(a0["observed_at"])
    assert timedelta(days=2) < datetime.now(UTC) - observed < timedelta(days=4)
    # The customer's latest live line-up (1500), not the older and higher one (2500).
    assert a0["srp"] == 1500 and a0["srp_source"] == SRP_SOURCE_LINEUP and a0["srp_reason"] is None
    assert a0["below_srp"] is True
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
    assert b2["srp"] is None and b2["srp_source"] is None and b2["srp_reason"] == SRP_REASON_NONE

    missing = cells[(p2.id, a.id)]
    assert (
        missing["listing_id"] is None
        and missing["price"] is None
        and missing["observed_at"] is None
    )


def test_is_below_srp_rule() -> None:
    srp = 1000.0
    boundary = srp - BELOW_SRP_TOLERANCE
    assert is_below_srp(boundary - 0.01, srp, in_stock=True) is True
    assert is_below_srp(boundary, srp, in_stock=True) is False  # exactly at the boundary
    assert is_below_srp(srp, srp, in_stock=True) is False
    assert is_below_srp(boundary - 50, srp, in_stock=False) is False  # out of stock
    assert is_below_srp(500.0, None, in_stock=True) is False  # no SRP
    assert is_below_srp(None, srp, in_stock=True) is False  # no price


def _sell_out(
    session: Session,
    s: dict,
    customer: DimCustomer,
    product: DimProduct,
    *,
    key: str,
    days_ago: int,
    price: float | None,
    vat_basis: str | None,
    units: float = 5,
) -> None:
    session.add(
        FactCustomerSellthrough(
            source_key=f"{s['tenant']}-{key}",
            tenant_id=s["tenant"],
            customer_id=customer.id,
            product_id=product.id,
            period_start_date=date.today() - timedelta(days=days_ago),
            period_type="weekly",
            period_grain="week",
            units_sold=units,
            unit_sell_price=price,
            vat_basis=vat_basis,
        )
    )
    session.flush()


def _tenant_vat(monkeypatch, rate: float | None) -> None:
    monkeypatch.setattr(price_matrix_module, "configured_vat_rate_pct", lambda tenant_id="default": rate)


def _cells(out: dict) -> dict:
    return {(c["product_id"], c["customer_id"]): c for c in out["cells"]}


def test_resolve_srp_takes_first_source_with_a_value() -> None:
    assert SRP_SOURCE_ORDER == (SRP_SOURCE_SELL_OUT, SRP_SOURCE_LINEUP, SRP_SOURCE_WEBSITE)
    every = {SRP_SOURCE_SELL_OUT: 3.0, SRP_SOURCE_LINEUP: 2.0, SRP_SOURCE_WEBSITE: 1.0}
    assert resolve_srp(every) == (3.0, SRP_SOURCE_SELL_OUT)
    assert resolve_srp({**every, SRP_SOURCE_SELL_OUT: None}) == (2.0, SRP_SOURCE_LINEUP)
    assert resolve_srp({SRP_SOURCE_WEBSITE: 1.0}) == (1.0, SRP_SOURCE_WEBSITE)
    assert resolve_srp({}) == (None, None)


def test_sell_out_price_wins_and_is_the_latest_period(db_session: Session, monkeypatch) -> None:  # noqa: F811
    s = _sample(db_session)
    a, b = s["a"], s["b"]
    p0, p1, _p2 = s["p"]
    _tenant_vat(monkeypatch, 0.15)
    # A/p0 has a line-up SRP of 1500; the newer sell-out price (1450, VAT inclusive) beats it, and the
    # older, higher sell-out price (1700) is not used.
    _sell_out(db_session, s, a, p0, key="old", days_ago=60, price=1700, vat_basis="inc_vat")
    _sell_out(db_session, s, a, p0, key="new", days_ago=14, price=1450, vat_basis="inc_vat")
    # Another customer's sell-out price is not this customer's SRP.
    _sell_out(db_session, s, b, p1, key="other", days_ago=7, price=5000, vat_basis="inc_vat")

    cells = _cells(build_price_matrix(db_session, tenant_id=s["tenant"], customer_ids=[a.id, b.id]))

    a0 = cells[(p0.id, a.id)]
    assert (a0["srp"], a0["srp_source"]) == (1450, SRP_SOURCE_SELL_OUT)
    # A/p1 still falls back to its line-up price.
    a1 = cells[(p1.id, a.id)]
    assert (a1["srp"], a1["srp_source"]) == (800, SRP_SOURCE_LINEUP)


def test_sell_out_price_is_stated_incl_vat(db_session: Session, monkeypatch) -> None:  # noqa: F811
    s = _sample(db_session)
    a, b = s["a"], s["b"]
    p0, p1, _p2 = s["p"]
    _tenant_vat(monkeypatch, 0.15)
    _sell_out(db_session, s, a, p0, key="ex", days_ago=7, price=1000, vat_basis="ex_vat")
    # Unknown VAT basis: that tier is skipped, so B/p0 falls back to its line-up price.
    _sell_out(db_session, s, b, p0, key="unknown", days_ago=7, price=777, vat_basis=None)

    cells = _cells(build_price_matrix(db_session, tenant_id=s["tenant"], customer_ids=[a.id, b.id]))

    a0 = cells[(p0.id, a.id)]
    assert a0["srp_source"] == SRP_SOURCE_SELL_OUT
    assert a0["srp"] == pytest.approx(1150.0)  # 1000 ex VAT grossed up by the tenant's 15%
    b0 = cells[(p0.id, b.id)]
    assert (b0["srp"], b0["srp_source"]) == (9999, SRP_SOURCE_LINEUP)


def test_ex_vat_sell_out_is_skipped_when_tenant_has_no_vat_rate(db_session: Session, monkeypatch) -> None:  # noqa: F811
    s = _sample(db_session)
    a, b = s["a"], s["b"]
    p0, _p1, _p2 = s["p"]
    _tenant_vat(monkeypatch, None)
    _sell_out(db_session, s, a, p0, key="ex", days_ago=7, price=1000, vat_basis="ex_vat")

    cells = _cells(build_price_matrix(db_session, tenant_id=s["tenant"], customer_ids=[a.id, b.id]))

    # No rate set: never a guessed rate, the next source answers.
    assert (cells[(p0.id, a.id)]["srp"], cells[(p0.id, a.id)]["srp_source"]) == (1500, SRP_SOURCE_LINEUP)


def test_lineup_tier_skips_cancelled_superseded_and_future_cases(db_session: Session) -> None:  # noqa: F811
    s = _sample(db_session)
    a, b = s["a"], s["b"]
    p0, p1, p2 = s["p"]
    live = s["lineup"]
    cases = {
        "cancelled": CommercialLineupCase(
            period_label="c", commercial_status="cancelled",
            inferred_period_start=date.today() - timedelta(days=1),
        ),
        "superseded": CommercialLineupCase(
            period_label="s", commercial_status="accepted", superseded_by_case_id=live.id,
            inferred_period_start=date.today() - timedelta(days=1),
        ),
        "future": CommercialLineupCase(
            period_label="f", commercial_status="accepted",
            inferred_period_start=date.today() + timedelta(days=40),
        ),
        "no_period": CommercialLineupCase(
            period_label="n", commercial_status="accepted", inferred_period_start=None
        ),
    }
    db_session.add_all(cases.values())
    db_session.flush()
    for case in cases.values():
        for customer, product, msrp in ((a, p0, 4444), (b, p2, 5555)):
            db_session.add(
                CommercialLineupLine(
                    case_id=case.id, product_id=product.id, customer_id=customer.id, msrp_local=msrp
                )
            )
    db_session.flush()

    cells = _cells(build_price_matrix(db_session, tenant_id=s["tenant"], customer_ids=[a.id, b.id]))

    assert cells[(p0.id, a.id)]["srp"] == 1500  # none of the 4444 cases counts
    b2 = cells[(p2.id, b.id)]
    assert b2["srp"] is None and b2["srp_reason"] == SRP_REASON_NONE  # 5555 never shows
    assert cells[(p1.id, a.id)]["srp"] == 800


def test_website_regular_price_is_the_last_fallback(db_session: Session, monkeypatch) -> None:  # noqa: F811
    s = _sample(db_session)
    a, b = s["a"], s["b"]
    p0, p1, p2 = s["p"]
    _tenant_vat(monkeypatch, 0.15)
    now = datetime.now(UTC)
    db_session.add_all(
        [
            # B/p2 has no sell-out and no line-up: the site's regular price answers.
            ListingObservation(
                listing_id=s["listings"]["b2"].id, fetched_at=now, extracted_price=1800,
                parser_version="t", parse_status="ok",
                parse_flags={"rrp_listing_price": "2000", "vat_basis": "inc_vat"},
            ),
            # A/p1 has a line-up price (800): it wins over the site's regular price.
            ListingObservation(
                listing_id=s["listings"]["a1"].id, fetched_at=now + timedelta(seconds=1),
                extracted_price=700, parser_version="t", parse_status="ok",
                parse_flags={"rrp_listing_price": 5000, "vat_basis": "inc_vat"},
            ),
        ]
    )
    db_session.flush()

    out = build_price_matrix(db_session, tenant_id=s["tenant"], customer_ids=[a.id, b.id])
    cells = _cells(out)

    b2 = cells[(p2.id, b.id)]
    assert (b2["srp"], b2["srp_source"]) == (2000, SRP_SOURCE_WEBSITE)
    assert b2["below_srp"] is True  # in stock at 1800, under 2000 - tolerance
    a1 = cells[(p1.id, a.id)]
    assert (a1["srp"], a1["srp_source"]) == (800, SRP_SOURCE_LINEUP)
    # The shelf price itself is never the regular price: A/p0 has no flag and keeps its line-up SRP.
    assert cells[(p0.id, a.id)]["srp_source"] == SRP_SOURCE_LINEUP


def test_website_price_without_a_vat_basis_or_a_regular_price_is_skipped(db_session: Session, monkeypatch) -> None:  # noqa: F811
    s = _sample(db_session)
    a, b = s["a"], s["b"]
    _p0, _p1, p2 = s["p"]
    _tenant_vat(monkeypatch, 0.15)
    now = datetime.now(UTC)
    db_session.add(
        ListingObservation(
            listing_id=s["listings"]["b2"].id, fetched_at=now, extracted_price=1800,
            parser_version="t", parse_status="ok",
            parse_flags={"rrp_listing_price": 2000},  # no VAT basis stated
        )
    )
    db_session.flush()

    cells = _cells(build_price_matrix(db_session, tenant_id=s["tenant"], customer_ids=[a.id, b.id]))

    assert cells[(p2.id, b.id)]["srp"] is None


def test_below_srp_flag_is_in_stock_only_and_counted(db_session: Session, monkeypatch) -> None:  # noqa: F811
    s = _sample(db_session)
    a, b = s["a"], s["b"]
    p0, p1, p2 = s["p"]
    _tenant_vat(monkeypatch, 0.15)
    # A/p0 SRP 1500 (line-up): in stock at 1200 -> below. B/p0 SRP 9999: out of stock at 1100 -> not
    # flagged. A/p1 sell-out SRP 701: in stock at 700 = exactly SRP minus tolerance -> not below.
    _sell_out(db_session, s, a, p1, key="a1", days_ago=3, price=700.0 + BELOW_SRP_TOLERANCE, vat_basis="inc_vat")

    out = build_price_matrix(db_session, tenant_id=s["tenant"], customer_ids=[a.id, b.id])
    cells = _cells(out)

    assert cells[(p0.id, a.id)]["below_srp"] is True
    assert cells[(p0.id, b.id)]["in_stock"] is False
    assert cells[(p0.id, b.id)]["below_srp"] is False
    assert cells[(p1.id, a.id)]["below_srp"] is False
    assert cells[(p2.id, a.id)]["below_srp"] is False  # no listing
    assert out["summary"]["below_srp_count"] == 1


def test_pending_wording_only_when_no_cell_has_an_srp(db_session: Session) -> None:  # noqa: F811
    s = _sample(db_session)
    a, b = s["a"], s["b"]
    # Remove every source: no line-up lines, no sell-out, no site regular price.
    db_session.query(CommercialLineupLine).filter(
        CommercialLineupLine.customer_id.in_([a.id, b.id])
    ).delete(synchronize_session=False)
    db_session.flush()

    out = build_price_matrix(db_session, tenant_id=s["tenant"], customer_ids=[a.id, b.id])

    assert out["summary"]["below_srp_count"] is None  # no comparison was possible
    for row in out["products"]:
        assert row["srp"] is None and row["srp_reason"] == SRP_REASON_PENDING
    for cell in out["cells"]:
        if cell["listing_id"] is not None:
            assert cell["srp"] is None and cell["srp_reason"] == SRP_REASON_PENDING
            assert cell["below_srp"] is False


def test_lineup_tier_ignores_unaccepted_cases_but_takes_an_accepted_older_one(db_session: Session) -> None:  # noqa: F811
    """Warren (26 Nov): "ONLY ACCEPTED ONES FFS". validated / pending_review / draft never supply an SRP."""
    s = _sample(db_session)
    a, b = s["a"], s["b"]
    p0, _p1, p2 = s["p"]
    newer = date.today()
    drafts = [
        CommercialLineupCase(period_label="d", commercial_status="draft_imported", inferred_period_start=newer),
        CommercialLineupCase(period_label="v", commercial_status="validated", inferred_period_start=newer),
        CommercialLineupCase(period_label="pr", commercial_status="pending_review", inferred_period_start=newer),
        CommercialLineupCase(period_label="p", commercial_status="proposed", inferred_period_start=newer),
        CommercialLineupCase(period_label="r", commercial_status="rejected", inferred_period_start=newer),
    ]
    db_session.add_all(drafts)
    db_session.flush()
    for case in drafts:
        for customer, product, msrp in ((a, p0, 7777), (b, p2, 6666)):
            db_session.add(
                CommercialLineupLine(
                    case_id=case.id, product_id=product.id, customer_id=customer.id, msrp_local=msrp
                )
            )
    db_session.flush()

    cells = _cells(build_price_matrix(db_session, tenant_id=s["tenant"], customer_ids=[a.id, b.id]))

    # The newer draft cases (7777) never supply the SRP: the accepted case (1500) does.
    a0 = cells[(p0.id, a.id)]
    assert (a0["srp"], a0["srp_source"]) == (1500, SRP_SOURCE_LINEUP)
    # A product that only a draft prices has no SRP at all.
    b2 = cells[(p2.id, b.id)]
    assert b2["srp"] is None and b2["srp_reason"] == SRP_REASON_NONE


def test_lineup_tier_takes_accepted_and_po_pending_cases(db_session: Session) -> None:  # noqa: F811
    """ASSUMPTION: accepted = accepted or any later ladder status, so a po_pending case supplies an SRP."""
    s = _sample(db_session)
    a, b = s["a"], s["b"]
    p0, _p1, p2 = s["p"]
    newer = date.today()
    cases = {
        "accepted": CommercialLineupCase(
            period_label="acc", commercial_status="accepted", inferred_period_start=newer
        ),
        "po_pending": CommercialLineupCase(
            period_label="po", commercial_status="po_pending", inferred_period_start=newer
        ),
    }
    db_session.add_all(cases.values())
    db_session.flush()
    for case, customer, product, msrp in (
        (cases["accepted"], a, p0, 7001),
        (cases["po_pending"], b, p2, 7002),
    ):
        db_session.add(
            CommercialLineupLine(case_id=case.id, product_id=product.id, customer_id=customer.id, msrp_local=msrp)
        )
    db_session.flush()

    cells = _cells(build_price_matrix(db_session, tenant_id=s["tenant"], customer_ids=[a.id, b.id]))

    a0 = cells[(p0.id, a.id)]
    assert (a0["srp"], a0["srp_source"]) == (7001, SRP_SOURCE_LINEUP)  # newer accepted case wins
    b2 = cells[(p2.id, b.id)]
    assert (b2["srp"], b2["srp_source"]) == (7002, SRP_SOURCE_LINEUP)  # po_pending counts as accepted


def test_lineup_tier_ranks_only_lines_with_a_usable_figure(db_session: Session) -> None:  # noqa: F811
    """A newer accepted line with no usable figure (msrp 0, chain "n/a" or 0) must not hide an older usable one."""
    s = _sample(db_session)
    a, b = s["a"], s["b"]
    p0, p1, _p2 = s["p"]
    newest = CommercialLineupCase(
        period_label="unusable", commercial_status="accepted", inferred_period_start=date.today()
    )
    db_session.add(newest)
    db_session.flush()  # the id is newer than the sample case's, so it ranks first even on the 1st of a month
    db_session.add_all(
        [
            CommercialLineupLine(
                case_id=newest.id, product_id=p1.id, customer_id=a.id, msrp_local=0,
                pricing_chain_json={"inputs": {"srp_inc_vat_local": "n/a"}},
            ),
            CommercialLineupLine(
                case_id=newest.id, product_id=p0.id, customer_id=b.id, msrp_local=0,
                pricing_chain_json={"inputs": {"srp_inc_vat_local": 0}},
            ),
        ]
    )
    db_session.flush()

    cells = _cells(build_price_matrix(db_session, tenant_id=s["tenant"], customer_ids=[a.id, b.id]))

    assert (cells[(p1.id, a.id)]["srp"], cells[(p1.id, a.id)]["srp_source"]) == (800, SRP_SOURCE_LINEUP)
    assert (cells[(p0.id, b.id)]["srp"], cells[(p0.id, b.id)]["srp_source"]) == (9999, SRP_SOURCE_LINEUP)


def test_lineup_srp_reads_the_explicit_vat_inclusive_figure_first(db_session: Session) -> None:  # noqa: F811
    s = _sample(db_session)
    a, b = s["a"], s["b"]
    p0, p1, _p2 = s["p"]
    lines = {
        (ln.customer_id, ln.product_id): ln
        for ln in db_session.query(CommercialLineupLine).filter(CommercialLineupLine.case_id == s["lineup"].id)
    }
    # A/p0: the price chain states the VAT-inclusive SRP; it wins over msrp_local (1500).
    lines[(a.id, p0.id)].pricing_chain_json = {
        "inputs": {"srp_inc_vat_local": 1600},
        "outputs": {"calc_srp_ex_vat_local": 1391.3},
    }
    # B/p0: an unusable chain value falls back to msrp_local (9999).
    lines[(b.id, p0.id)].pricing_chain_json = {"inputs": {"srp_inc_vat_local": "n/a"}}
    # A/p1: a chain with no inputs falls back to msrp_local (800); the ex-VAT output is never used.
    lines[(a.id, p1.id)].pricing_chain_json = {"outputs": {"calc_srp_ex_vat_local": 695.65}}
    db_session.flush()

    cells = _cells(build_price_matrix(db_session, tenant_id=s["tenant"], customer_ids=[a.id, b.id]))

    assert cells[(p0.id, a.id)]["srp"] == 1600
    assert cells[(p0.id, b.id)]["srp"] == 9999
    assert cells[(p1.id, a.id)]["srp"] == 800


def test_srp_period_is_returned_for_sell_out_and_lineup_tiers(db_session: Session, monkeypatch) -> None:  # noqa: F811
    s = _sample(db_session)
    a, b = s["a"], s["b"]
    p0, p1, p2 = s["p"]
    _tenant_vat(monkeypatch, 0.15)
    _sell_out(db_session, s, a, p0, key="new", days_ago=14, price=1450, vat_basis="inc_vat")
    db_session.add(
        ListingObservation(
            listing_id=s["listings"]["b2"].id, fetched_at=datetime.now(UTC), extracted_price=1800,
            parser_version="t", parse_status="ok",
            parse_flags={"rrp_listing_price": "2000", "vat_basis": "inc_vat"},
        )
    )
    db_session.flush()

    cells = _cells(build_price_matrix(db_session, tenant_id=s["tenant"], customer_ids=[a.id, b.id]))

    sell_out = cells[(p0.id, a.id)]
    assert sell_out["srp_source"] == SRP_SOURCE_SELL_OUT
    assert sell_out["srp_period"] == (date.today() - timedelta(days=14)).isoformat()
    lineup_cell = cells[(p1.id, a.id)]
    assert lineup_cell["srp_source"] == SRP_SOURCE_LINEUP
    assert lineup_cell["srp_period"] == s["lineup"].inferred_period_start.isoformat()
    website = cells[(p2.id, b.id)]
    assert website["srp_source"] == SRP_SOURCE_WEBSITE and website["srp_period"] is None
    # No SRP, no period.
    assert cells[(p2.id, a.id)]["srp_period"] is None


def test_below_srp_tolerance_defaults_to_one_and_follows_the_tenant_override(
    db_session: Session, monkeypatch, tmp_path  # noqa: F811
) -> None:
    from app.services import commercial_tenant_profile as profile

    monkeypatch.setattr(profile, "_tenant_profiles_dir", lambda: tmp_path)
    s = _sample(db_session)
    a, b = s["a"], s["b"]
    _p0, p1, _p2 = s["p"]  # A/p1: in stock at 700, line-up SRP 800

    assert price_matrix_module.below_srp_tolerance(s["tenant"]) == BELOW_SRP_TOLERANCE == 1.0
    default = _cells(build_price_matrix(db_session, tenant_id=s["tenant"], customer_ids=[a.id, b.id]))
    assert default[(p1.id, a.id)]["below_srp"] is True

    # 100 under SRP is exactly the tolerance: not below. 99 is: below.
    profile.save_tenant_profile_overrides(s["tenant"], {"below_srp_tolerance": "100"})
    wide = _cells(build_price_matrix(db_session, tenant_id=s["tenant"], customer_ids=[a.id, b.id]))
    assert wide[(p1.id, a.id)]["below_srp"] is False
    profile.save_tenant_profile_overrides(s["tenant"], {"below_srp_tolerance": "99"})
    narrow = _cells(build_price_matrix(db_session, tenant_id=s["tenant"], customer_ids=[a.id, b.id]))
    assert narrow[(p1.id, a.id)]["below_srp"] is True
