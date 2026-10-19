"""Sell-through overview (Warren 2026-10-19). One rolled-back transaction; cip_test only.

- headline units and value, VAT converted from each customer's basis, against last year;
- weekly and monthly reporters together; monthly figures spread over their days by week;
- which reports arrived, are partial, due or missing per customer;
- SKU problems: needs replenishing (per-customer weeks of cover), out of stock while selling,
  a selling streak that dropped, aged stock, and SKUs with no recent sales;
- a customer whose latest report has not arrived is judged up to its last reported day.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.sync_url import sqlalchemy_sync_engine_url
from app.models.customer_report_config import CustomerReportConfig
from app.models.dimensions import DimCustomer, DimProduct
from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.services.business_calendar import BusinessCalendar
from app.services.channel_intelligence.sell_through_overview import OverviewFilters, build_overview, filter_options

TODAY = date(2026, 10, 19)  # Monday, W43
LAST_WEEK = date(2026, 10, 12)  # the latest reported week
TENANT = "st-overview-test"


@pytest.fixture
def session():
    engine = create_engine(sqlalchemy_sync_engine_url(get_settings().database_url_sync))
    with engine.connect() as conn:
        if conn.execute(text("select current_database()")).scalar() != "cip_test":
            pytest.skip("cip_test only")
        if not conn.execute(
            text(
                "select count(*) from information_schema.columns where table_name = "
                "'customer_report_config' and column_name = 'replen_min_weeks_of_cover'"
            )
        ).scalar():
            pytest.skip("20261019_0045 is not applied")
        conn.rollback()
        outer = conn.begin()
        db = Session(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield db
        finally:
            db.close()
            outer.rollback()
    engine.dispose()


def _customer(db: Session, code: str, *, cadence: str = "weekly", replen_min: float | None = None) -> int:
    c = DimCustomer(code=code, name=f"{code} Retail", is_key_account=True)
    db.add(c)
    db.flush()
    db.add(
        CustomerReportConfig(
            customer_id=c.id,
            reports_expected=True,
            expected_cadence=cadence,
            overdue_threshold_days=10,
            replen_min_weeks_of_cover=replen_min,
        )
    )
    db.flush()
    return int(c.id)


def _product(db: Session, tag: str, **kw) -> int:
    p = DimProduct(sku=f"STO-{tag}", name=f"Overview {tag}", sales_model_name=f"Model {tag}", business_unit="NB", **kw)
    db.add(p)
    db.flush()
    return int(p.id)


_n = 0


def _row(db, cid, pid, start, units, *, grain="week", price=100.0, vat="ex_vat", soh=None):
    global _n
    _n += 1
    db.add(
        FactCustomerSellthrough(
            source_key=f"st-overview-{_n}",
            tenant_id=TENANT,
            customer_id=cid,
            product_id=pid,
            period_start_date=start,
            period_type="monthly" if grain == "month" else "weekly",
            period_grain=grain,
            units_sold=units,
            unit_sell_price=price,
            vat_basis=vat,
            reported_soh=soh,
        )
    )


def _weeks(db, cid, pid, units_by_week_ago: dict[int, float], *, soh_now=None):
    """units_by_week_ago[0] is the latest reported week (LAST_WEEK)."""
    for ago, units in units_by_week_ago.items():
        start = LAST_WEEK - timedelta(weeks=ago)
        _row(db, cid, pid, start, units, soh=soh_now if ago == 0 else None)


def test_overview(session: Session):
    db = session
    a = _customer(db, "STO-A", replen_min=3)
    b = _customer(db, "STO-B", cadence="monthly")
    c = _customer(db, "STO-C")  # expected weekly, never reported
    p1 = _product(db, "P1")  # steady seller
    p2 = _product(db, "P2")  # streak then drop
    p3 = _product(db, "P3")  # low cover
    p4 = _product(db, "P4")  # sold out
    p5 = _product(db, "P5")  # stock not moving
    p6 = _product(db, "P6")  # stopped selling, no stock figures (customer B)
    p7 = _product(db, "P7", lifecycle_status="EOL")  # ended product: not a "stopped" problem

    _weeks(db, a, p1, {i: 10 for i in range(26)}, soh_now=100)
    _weeks(db, a, p2, {i: (2 if i < 4 else 10) for i in range(26)}, soh_now=50)
    _weeks(db, a, p3, {i: 10 for i in range(26)}, soh_now=20)
    _weeks(db, a, p4, {i: 5 for i in range(26)}, soh_now=0)
    _weeks(db, a, p5, {i: (0 if i < 12 else 3) for i in range(26)}, soh_now=30)
    # Last year, same weeks: P1 sold 5 a week.
    for i in range(13):
        _row(db, a, p1, date(2025, 10, 13) - timedelta(weeks=i), 5)  # 52 weeks before

    # Customer B reports monthly, prices including VAT, no stock.
    for m in range(1, 10):
        _row(db, b, p1, date(2026, m, 1), 40, grain="month", price=115.0, vat="inc_vat")
    for m in range(1, 8):
        _row(db, b, p6, date(2026, m, 1), 8, grain="month", price=115.0, vat="inc_vat")
        _row(db, b, p7, date(2026, m, 1), 8, grain="month", price=115.0, vat="inc_vat")
    db.flush()

    f = OverviewFilters(
        date_from=LAST_WEEK - timedelta(weeks=12),
        date_to=LAST_WEEK + timedelta(days=6),
        grain="week",
        compare="prior_year",
        vat="ex_vat",
        tenant_id=TENANT,
        customer_ids=[a, b, c],
    )
    out = build_overview(db, f, BusinessCalendar(), today=TODAY, vat_rate=0.15)

    # Headline: 13 weeks of customer A plus B's months spread over the days in the window.
    a_units = 13 * (10 + 10 + 5) + (4 * 2 + 9 * 10) + 0 + 1 * 3  # P1+P3+P4, P2, P5 (week 12 ago only)
    window_days_in = {7: 31 - 20 + 1, 8: 31, 9: 30}  # 2026-07-20 .. 2026-10-18 covers part of July
    b_units = sum(40 * d / {7: 31, 8: 31, 9: 30}[m] for m, d in window_days_in.items())
    b_units += 8 * (12 / 31)  # P6 in July
    b_units += 8 * (12 / 31)  # P7 in July
    assert out["kpis"]["units"] == pytest.approx(a_units + b_units, abs=0.05)
    assert out["kpis"]["compare_units"] == pytest.approx(13 * 5, abs=0.05)
    # B's prices are incl. VAT: 115 / 1.15 = 100 excl.
    assert out["kpis"]["value"] == pytest.approx(out["kpis"]["units"] * 100, abs=1)
    assert sum(t["units"] for t in out["trend"]) == pytest.approx(out["kpis"]["units"], abs=0.05)
    assert len(out["trend"]) == 13
    assert out["trend"][-1]["compare_units"] == pytest.approx(5)
    # B reports monthly and has not sent October: the latest weeks are marked incomplete, A's are not.
    assert out["trend"][-1]["incomplete_customers"] == ["STO-B Retail"]
    assert out["trend"][0]["incomplete_customers"] == []
    assert len(out["quarters"]) == 5
    assert out["top_sellers"][0]["product_id"] == p1

    # Stock: A reports on its latest week; B never reports stock.
    assert out["kpis"]["stock_on_hand"] == pytest.approx(100 + 50 + 20 + 0 + 30)
    assert out["kpis"]["stock_customers"] == 1

    reasons = {(r["customer_id"], r["product_id"]): r for r in out["problems"]["rows"]}
    assert reasons[(a, p3)]["reason"] == "needs_replen"  # 2 weeks of cover, A replenishes below 3
    assert reasons[(a, p3)]["suggested_qty"] == 10 * 6 - 20
    assert reasons[(a, p4)]["reason"] == "out_of_stock"
    assert reasons[(a, p2)]["reason"] == "dropped"
    assert reasons[(a, p5)]["reason"] == "aged"
    assert reasons[(b, p6)]["reason"] == "stopped"
    assert (b, p7) not in reasons  # ended product
    assert (a, p1) not in reasons
    assert out["problems"]["counts"] == {"needs_replen": 1, "out_of_stock": 1, "dropped": 1, "aged": 1, "stopped": 1}

    cov = {r["customer_id"]: r for r in out["coverage"]["customers"]}
    assert cov[a]["missing"] == 0 and cov[a]["cells"][-1]["status"] == "received"
    assert cov[c]["missing"] == 11 and cov[c]["last_reported_day"] is None  # the last two weeks are still due
    # B's September month arrived; October weeks are not due for a monthly reporter yet.
    assert cov[b]["cells"][-1]["status"] == "due"
    assert "STO-C Retail" in out["coverage"]["customers_missing"]
    assert any("STO-C" in s for s in out["summary"])


def test_customer_judged_to_its_last_report(session: Session):
    """A weekly reporter whose last two weeks have not arrived is not flagged as a sales drop."""
    db = session
    a = _customer(db, "STO-L")
    p = _product(db, "PL")
    _weeks(db, a, p, {i: 10 for i in range(2, 26)}, soh_now=None)
    db.flush()
    f = OverviewFilters(date_from=date(2026, 7, 20), date_to=date(2026, 10, 18), tenant_id=TENANT, customer_ids=[a])
    out = build_overview(db, f, BusinessCalendar(), today=TODAY, vat_rate=0.15)
    assert out["problems"]["rows"] == []
    cov = out["coverage"]["customers"][0]
    # Not yet late: each week is due 10 days after it ends.
    assert [c["status"] for c in cov["cells"][-3:]] == ["received", "due", "due"]


def test_filter_options_lists_reporting_customers(session: Session):
    db = session
    a = _customer(db, "STO-F")
    p = _product(db, "PF")
    _row(db, a, p, LAST_WEEK, 3)
    db.flush()
    opts = filter_options(db, TENANT)
    row = next(c for c in opts["customers"] if c["id"] == a)
    assert row["has_data"] and row["reports_expected"]
    assert "NB" in opts["business_units"]
