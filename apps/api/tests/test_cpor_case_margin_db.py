"""N-0080: CPOR case margin against a real database. One rolled-back transaction; cip_test only."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.sync_url import sqlalchemy_sync_engine_url
from app.models.commercial_planner import (
    CommercialCustomerTerm,
    CommercialDistributorTerm,
    CommercialSkuAssumption,
)
from app.models.cpor import CporCase, CporCaseLine
from app.services.cpor.case_margin import build_case_margin
from app.services.cpor.pivot import is_voided_line


@pytest.fixture
def session():
    engine = create_engine(sqlalchemy_sync_engine_url(get_settings().database_url_sync))
    with engine.connect() as conn:
        if conn.execute(text("select current_database()")).scalar() != "cip_test":
            pytest.skip("cip_test only")
        has_col = conn.execute(
            text(
                "select 1 from information_schema.columns "
                "where table_name = 'commercial_sku_assumption' and column_name = 'landed_cost_amount'"
            )
        ).scalar()
        if not has_col:
            pytest.skip("20261014_0036 is not applied")
        conn.rollback()
        outer = conn.begin()
        db = Session(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield db
        finally:
            db.close()
            outer.rollback()
    engine.dispose()


def _case_with_distributor_line(db: Session) -> tuple[CporCase, CporCaseLine]:
    for line in db.scalars(
        select(CporCaseLine)
        .where(CporCaseLine.distributor_id.is_not(None), CporCaseLine.srp > 0)
        .order_by(CporCaseLine.id)
    ):
        if not is_voided_line(line):
            return db.get(CporCase, line.case_id), line
    pytest.skip("cip_test has no case line with a distributor")


def _upsert_terms(db: Session, case: CporCase, line: CporCaseLine, *, landed: float | None) -> None:
    sku = db.scalar(select(CommercialSkuAssumption).where(CommercialSkuAssumption.product_id == line.product_id))
    if sku is None:
        sku = CommercialSkuAssumption(product_id=line.product_id, controlled_cost_amount=1.0)
        db.add(sku)
    sku.controlled_cost_amount = 100.0
    sku.controlled_cost_currency_code = "USD"
    sku.landed_cost_amount = landed
    ct = db.scalar(select(CommercialCustomerTerm).where(CommercialCustomerTerm.customer_id == case.customer_id))
    if ct is None:
        ct = CommercialCustomerTerm(customer_id=case.customer_id)
        db.add(ct)
    ct.customer_margin_pct = 0.12
    ct.customer_rebate_pct = 0.05
    dt = db.scalar(
        select(CommercialDistributorTerm).where(CommercialDistributorTerm.distributor_id == line.distributor_id)
    )
    if dt is None:
        dt = CommercialDistributorTerm(distributor_id=line.distributor_id)
        db.add(dt)
    dt.distributor_margin_pct = 0.08
    case.roe_snapshot = 18.0
    line.srp = 11500.0
    line.vat_rate = 0.15
    line.dealer_margin_pct = 0.10
    line.support_usd = 20.0
    line.result_qty = None
    line.estimate_qty = 10.0
    db.flush()


def _row(out: dict, line: CporCaseLine) -> dict:
    return next(r for r in out["lines"] if r["line_id"] == line.id)


def test_case_margin_is_dap_minus_pm_cost_minus_support(session):
    case, line = _case_with_distributor_line(session)
    _upsert_terms(session, case, line, landed=None)
    out = build_case_margin(session, case)
    row = _row(out, line)

    dap = 11500.0 / 1.15 * 0.90 * 0.95 * 0.92 / 18.0
    assert out["cost_basis"] == "pm_controlled_cost" and out["currency"] == "USD"
    assert row["dap_per_unit"] == pytest.approx(dap, abs=1e-3)
    assert row["pm_controlled_cost_per_unit"] == pytest.approx(100.0)
    assert row["support_per_unit"] == pytest.approx(20.0)
    assert row["margin_per_unit"] == pytest.approx(dap - 100.0 - 20.0, abs=1e-3)
    assert row["margin_total"] == pytest.approx((dap - 120.0) * 10, abs=1e-2)
    assert row["units_source"] == "estimate_qty"
    assert row["landed_cost_per_unit"] is None
    assert "landed_cost_not_recorded" in row["flags"]


def test_landed_cost_is_shown_and_never_changes_the_margin(session):
    case, line = _case_with_distributor_line(session)
    _upsert_terms(session, case, line, landed=None)
    before = _row(build_case_margin(session, case), line)
    _upsert_terms(session, case, line, landed=150.0)
    after = _row(build_case_margin(session, case), line)
    assert after["landed_cost_per_unit"] == pytest.approx(150.0)
    assert after["margin_per_unit"] == before["margin_per_unit"]
    assert after["margin_total"] == before["margin_total"]


def test_non_usd_cost_is_flagged_not_converted(session):
    case, line = _case_with_distributor_line(session)
    _upsert_terms(session, case, line, landed=None)
    sku = session.scalar(select(CommercialSkuAssumption).where(CommercialSkuAssumption.product_id == line.product_id))
    sku.controlled_cost_currency_code = "ZAR"
    session.flush()
    row = _row(build_case_margin(session, case), line)
    assert row["margin_per_unit"] is None
    assert "cost_currency_not_usd" in row["flags"]
    # The case line itself is never written by the margin read.
    session.refresh(line)
    assert float(line.support_usd) == pytest.approx(20.0)
