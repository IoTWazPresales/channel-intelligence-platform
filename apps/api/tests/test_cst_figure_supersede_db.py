"""N-0111: a newer sell-through load replaces only the figures it carries (Warren 2026-10-16).

Units sold, on-hand, in-transit and on-order are superseded independently: a stock-only load
never wipes sales and a sales-only load never wipes stock. Superseded figures are kept with the
superseding load; nothing is hard-deleted. A load whose week numbers have no confirmed year
applies nothing.

One rolled-back transaction; cip_test only.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.sync_url import sqlalchemy_sync_engine_url
from app.models.dimensions import DimCustomer, DimProduct
from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.models.import_customer_sellthrough_staging import ImportCustomerSellthroughStagingLine
from app.models.ingestion import ImportJob, SourceDefinition
from app.services.imports.customer_sell_through_apply import apply_customer_sellthrough_staging

TENANT = "n0111_figures"
WEEK = date(2025, 3, 10)
T0 = datetime(2026, 8, 1, tzinfo=timezone.utc)


@pytest.fixture
def session():
    engine = create_engine(sqlalchemy_sync_engine_url(get_settings().database_url_sync))
    with engine.connect() as conn:
        if conn.execute(text("select current_database()")).scalar() != "cip_test":
            pytest.skip("cip_test only")
        has_col = conn.execute(
            text(
                "select count(*) from information_schema.columns "
                "where table_name = 'fact_customer_sellthrough' and column_name = 'figure_import_jobs'"
            )
        ).scalar()
        if not has_col:
            pytest.skip("20261016_0041 is not applied")
        conn.rollback()
        outer = conn.begin()
        db = Session(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield db
        finally:
            db.close()
            outer.rollback()
    engine.dispose()


def _ids(db: Session) -> tuple[int, int, int]:
    source = db.scalar(select(SourceDefinition.id).order_by(SourceDefinition.id).limit(1))
    customer = db.scalar(select(DimCustomer.id).order_by(DimCustomer.id).limit(1))
    product = db.scalar(select(DimProduct.id).order_by(DimProduct.id).limit(1))
    if source is None or customer is None or product is None:
        pytest.skip("cip_test needs a source, a customer and a product")
    return int(source), int(customer), int(product)


def _job(db: Session, source: int, created: datetime, meta: dict | None = None) -> int:
    job = ImportJob(
        tenant_id=TENANT,
        source_id=source,
        template_slug="customer_sell_through",
        import_mode="apply",
        status="completed",
        stage="staged",
        file_name="history.xlsx",
        created_at=created,
        staged_metadata=meta or {},
    )
    db.add(job)
    db.flush()
    return int(job.id)


def _load(db: Session, source: int, customer: int, product: int, created: datetime, *, units: str | None,
          soh: str | None, site: str = "S1", start: date = WEEK, meta: dict | None = None, n: int = 1):
    job = _job(db, source, created, meta)
    db.add(
        ImportCustomerSellthroughStagingLine(
            import_job_id=job,
            source_row_number=n,
            raw_row_payload={"Site": site, "Units": units, "SOH": soh},
            resolved_customer_id=customer,
            resolved_product_id=product,
            period_start_date=start,
            period_type="weekly",
            period_grain="week",
            units_sold=Decimal(units) if units is not None else None,
            reported_soh=Decimal(soh) if soh is not None else None,
            site_label=site,
            resolution_status="resolved",
        )
    )
    db.flush()
    return job, apply_customer_sellthrough_staging(db, job, recompute_stock_gap=False)


def _totals(db: Session) -> tuple[Decimal, Decimal]:
    units, soh = db.execute(
        select(
            func.coalesce(func.sum(FactCustomerSellthrough.units_sold), 0),
            func.coalesce(func.sum(FactCustomerSellthrough.reported_soh), 0),
        ).where(FactCustomerSellthrough.tenant_id == TENANT)
    ).one()
    return Decimal(units), Decimal(soh)


def _kept(db: Session) -> list[tuple]:
    return db.execute(
        text(
            "select superseded_by_import_job_id, reason, figures, row_json->>'units_sold', row_json->>'reported_soh' "
            "from fact_customer_sellthrough_superseded where tenant_id = :t order by id"
        ),
        {"t": TENANT},
    ).all()


def test_stock_only_never_wipes_sales_and_sales_only_never_wipes_stock(session: Session) -> None:
    source, customer, product = _ids(session)
    _, first = _load(session, source, customer, product, T0, units="12", soh="40")
    assert first.errors == []
    assert _totals(session) == (Decimal("12"), Decimal("40"))

    stock_job, stock = _load(session, source, customer, product, T0 + timedelta(days=1), units=None, soh="35")
    assert stock.errors == [] and stock.applied == 1
    assert _totals(session) == (Decimal("12"), Decimal("35"))  # sales unchanged, on-hand replaced
    kept = _kept(session)
    assert len(kept) == 1
    assert kept[0][0] == stock_job and kept[0][1] == "figure_replaced_same_key" and kept[0][2] == ["reported_soh"]
    assert Decimal(kept[0][4]) == Decimal("40")

    sales_job, sales = _load(session, source, customer, product, T0 + timedelta(days=2), units="15", soh=None)
    assert sales.errors == []
    assert _totals(session) == (Decimal("15"), Decimal("35"))  # stock unchanged, units replaced
    kept = _kept(session)
    assert kept[-1][0] == sales_job and kept[-1][2] == ["units_sold"] and Decimal(kept[-1][3]) == Decimal("12")

    row = session.scalar(select(FactCustomerSellthrough).where(FactCustomerSellthrough.tenant_id == TENANT))
    assert row.figure_import_jobs == {"units_sold": sales_job, "reported_soh": stock_job}


def test_stock_only_first_then_sales_for_the_same_week(session: Session) -> None:
    source, customer, product = _ids(session)
    _, stock = _load(session, source, customer, product, T0, units=None, soh="20")
    assert stock.errors == []
    assert _totals(session) == (Decimal("0"), Decimal("20"))
    _, sales = _load(session, source, customer, product, T0 + timedelta(days=1), units="6", soh=None)
    assert sales.errors == []
    assert _totals(session) == (Decimal("6"), Decimal("20"))
    assert _kept(session) == []  # units were never reported before: nothing was replaced


def test_cross_key_supersedes_only_the_carried_figure(session: Session) -> None:
    """An older chain-level row keeps its units when a newer per-site load carries only stock."""
    source, customer, product = _ids(session)
    _load(session, source, customer, product, T0, units="9", soh="30", site="0")
    newer_job, newer = _load(session, source, customer, product, T0 + timedelta(days=1), units=None, soh="25", site="S1")
    assert newer.errors == []
    assert newer.superseded_rows == 0 and newer.superseded_partial_rows == 1
    assert newer.superseded_figures == {"reported_soh": 1}
    assert _totals(session) == (Decimal("9"), Decimal("25"))
    kept = _kept(session)
    assert kept[-1][0] == newer_job and kept[-1][1] == "figures_restated_by_newer_load"
    assert kept[-1][2] == ["reported_soh"] and Decimal(kept[-1][4]) == Decimal("30")


def test_whole_row_supersede_names_every_figure_it_gave_up(session: Session) -> None:
    source, customer, product = _ids(session)
    _load(session, source, customer, product, T0, units="9", soh="30", site="0")
    newer_job, newer = _load(session, source, customer, product, T0 + timedelta(days=1), units="7", soh="25", site="S1")
    assert newer.superseded_rows == 1 and newer.superseded_partial_rows == 0
    assert _totals(session) == (Decimal("7"), Decimal("25"))
    kept = _kept(session)
    assert kept[-1][0] == newer_job and kept[-1][1] == "restated_by_newer_load"
    assert kept[-1][2] == ["units_sold", "reported_soh"]


def test_rerun_and_identical_reupload_change_nothing(session: Session) -> None:
    source, customer, product = _ids(session)
    _load(session, source, customer, product, T0, units="5", soh="10")
    before = _totals(session)
    _, again = _load(session, source, customer, product, T0 + timedelta(days=1), units="5", soh="10")
    assert again.errors == [] and again.superseded_figures == {} and again.superseded_rows == 0
    assert _totals(session) == before
    assert _kept(session) == []


def test_week_numbers_without_a_confirmed_year_apply_nothing(session: Session) -> None:
    source, customer, product = _ids(session)
    pending = {"cst_year_required": [{"filename": "W12.xlsx", "suggested_year": None}]}
    job, summary = _load(session, source, customer, product, T0, units="5", soh="10", meta=pending)
    assert summary.applied == 0 and any("Confirm the year" in e for e in summary.errors)
    assert _totals(session) == (Decimal("0"), Decimal("0"))

    confirmed = dict(pending, cst_confirmed_year=2025)
    _, ok = _load(session, source, customer, product, T0 + timedelta(days=1), units="5", soh="10", meta=confirmed, n=2)
    assert ok.errors == [] and ok.applied == 1
