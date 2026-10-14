"""N-0110: a newer sell-through load supersedes older rows for the same customer, product and
period (D-0090), and repeated source rows of one key are summed or flagged (D-0091).

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

TENANT = "n0110_reupload"
WEEK = date(2025, 9, 29)
T0 = datetime(2026, 8, 1, tzinfo=timezone.utc)


@pytest.fixture
def session():
    engine = create_engine(sqlalchemy_sync_engine_url(get_settings().database_url_sync))
    with engine.connect() as conn:
        if conn.execute(text("select current_database()")).scalar() != "cip_test":
            pytest.skip("cip_test only")
        if not conn.execute(text("select to_regclass('fact_customer_sellthrough_superseded')")).scalar():
            pytest.skip("20261015_0038 is not applied")
        conn.rollback()
        outer = conn.begin()
        db = Session(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield db
        finally:
            db.close()
            outer.rollback()
    engine.dispose()


def _ids(db: Session) -> tuple[int, int, int, int]:
    source = db.scalar(select(SourceDefinition.id).order_by(SourceDefinition.id).limit(1))
    customer = db.scalar(select(DimCustomer.id).order_by(DimCustomer.id).limit(1))
    products = db.scalars(select(DimProduct.id).order_by(DimProduct.id).limit(2)).all()
    if source is None or customer is None or len(products) < 2:
        pytest.skip("cip_test needs a source, a customer and two products")
    return int(source), int(customer), int(products[0]), int(products[1])


def _job(db: Session, source: int, created: datetime) -> int:
    job = ImportJob(
        tenant_id=TENANT,
        source_id=source,
        template_slug="customer_sell_through",
        import_mode="apply",
        status="completed",
        stage="staged",
        file_name="Week 40.xlsx",
        created_at=created,
    )
    db.add(job)
    db.flush()
    return int(job.id)


def _old_row(db: Session, job: int, customer: int, product: int, units: str, *, start: date = WEEK,
             grain: str = "week", site: str = "0") -> None:
    db.add(
        FactCustomerSellthrough(
            source_key=f"ct:{customer}:{site}:{product}:{start.isoformat()}",
            tenant_id=TENANT,
            customer_id=customer,
            product_id=product,
            period_start_date=start,
            period_type="monthly" if grain == "month" else "weekly",
            period_grain=grain,
            units_sold=Decimal(units),
            reported_soh=Decimal("5"),
            import_job_id=job,
        )
    )


def _line(db: Session, job: int, n: int, customer: int, product: int, site: str, units: str, *,
          soh: str = "5", day: date | None = None, payload: dict | None = None) -> None:
    db.add(
        ImportCustomerSellthroughStagingLine(
            import_job_id=job,
            source_row_number=n,
            raw_row_payload=payload if payload is not None else {"Site": site, "Units": units, "n": n},
            resolved_customer_id=customer,
            resolved_product_id=product,
            period_start_date=day or WEEK,
            period_type="daily" if day else "weekly",
            period_grain="day" if day else "week",
            units_sold=Decimal(units),
            reported_soh=Decimal(soh),
            site_label=site,
            resolution_status="resolved",
        )
    )


def _units(db: Session) -> Decimal:
    return Decimal(
        db.scalar(select(func.coalesce(func.sum(FactCustomerSellthrough.units_sold), 0)).where(
            FactCustomerSellthrough.tenant_id == TENANT
        ))
    )


def _per_site_load(db: Session, source: int, customer: int, product: int, created: datetime):
    job = _job(db, source, created)
    _line(db, job, 1, customer, product, "S1", "4")
    _line(db, job, 2, customer, product, "S2", "3")
    db.flush()
    return job, apply_customer_sellthrough_staging(db, job, recompute_stock_gap=False)


def test_newer_per_site_load_supersedes_chain_level_row_and_is_idempotent(session: Session) -> None:
    source, customer, product, other_product = _ids(session)
    old_job = _job(session, source, T0)
    _old_row(session, old_job, customer, product, "4")  # two sites stored as one chain-level row
    _old_row(session, old_job, customer, other_product, "9")  # not restated by the newer load
    session.flush()
    assert _units(session) == Decimal("13")

    first_job, first = _per_site_load(session, source, customer, product, T0 + timedelta(days=1))
    assert first.errors == []
    assert first.superseded_rows == 1 and first.superseded_units == 4.0
    assert _units(session) == Decimal("16")  # 4 + 3 per site, plus the untouched product's 9
    moved = session.execute(
        text(
            "select import_job_id, superseded_by_import_job_id, reason, row_json->>'units_sold' "
            "from fact_customer_sellthrough_superseded where tenant_id = :t"
        ),
        {"t": TENANT},
    ).all()
    assert len(moved) == 1
    assert moved[0][0] == old_job and moved[0][1] == first_job and moved[0][2] == "restated_by_newer_load"
    assert Decimal(moved[0][3]) == Decimal("4")
    assert session.scalar(
        select(func.count()).select_from(ImportCustomerSellthroughStagingLine).where(
            ImportCustomerSellthroughStagingLine.import_job_id == first_job
        )
    ) == 2  # raw staging kept

    _, second = _per_site_load(session, source, customer, product, T0 + timedelta(days=2))
    assert second.superseded_rows == 0
    assert _units(session) == Decimal("16")


def test_day_rows_supersede_the_week_but_not_the_month(session: Session) -> None:
    source, customer, product, _ = _ids(session)
    old_job = _job(session, source, T0)
    _old_row(session, old_job, customer, product, "5")  # the week
    _old_row(session, old_job, customer, product, "20", start=date(2025, 9, 1), grain="month")
    session.flush()

    job = _job(session, source, T0 + timedelta(days=1))
    for i in range(7):
        _line(session, job, i + 1, customer, product, "S1", "1" if i in (1, 3) else "0", day=WEEK + timedelta(days=i))
    session.flush()
    summary = apply_customer_sellthrough_staging(session, job, recompute_stock_gap=False)
    assert summary.superseded_rows == 1 and summary.superseded_units == 5.0
    assert _units(session) == Decimal("22")  # month 20 kept, week 5 replaced by 2 sale days


def test_older_load_never_supersedes_a_newer_row(session: Session) -> None:
    source, customer, product, _ = _ids(session)
    newer_job = _job(session, source, T0 + timedelta(days=5))
    _old_row(session, newer_job, customer, product, "4")
    session.flush()

    _, summary = _per_site_load(session, source, customer, product, T0)
    assert summary.superseded_rows == 0
    assert _units(session) == Decimal("11")


def test_repeated_rows_differing_are_summed_identical_are_flagged(session: Session) -> None:
    source, customer, product, other_product = _ids(session)
    job = _job(session, source, T0)
    same = {"Article": "A1", "Month": "2025-09", "Units": 4}
    _line(session, job, 1, customer, product, "S1", "4", payload=same)
    _line(session, job, 2, customer, product, "S1", "3", payload={"Article": "A1", "Month": "2025-10", "Units": 3})
    _line(session, job, 3, customer, product, "S1", "4", payload=dict(same))  # identical copy
    _line(session, job, 4, customer, other_product, "S1", "2", soh="5", payload={"Article": "B1", "Units": 2})
    _line(session, job, 5, customer, other_product, "S1", "1", soh="2", payload={"Article": "B2", "Units": 1})
    session.flush()
    summary = apply_customer_sellthrough_staging(session, job, recompute_stock_gap=False)
    assert summary.errors == []
    assert summary.applied == 4 and summary.duplicate_lines == 1

    rows = dict(
        session.execute(
            select(FactCustomerSellthrough.product_id, FactCustomerSellthrough.units_sold).where(
                FactCustomerSellthrough.tenant_id == TENANT
            )
        ).all()
    )
    soh = dict(
        session.execute(
            select(FactCustomerSellthrough.product_id, FactCustomerSellthrough.reported_soh).where(
                FactCustomerSellthrough.tenant_id == TENANT
            )
        ).all()
    )
    assert Decimal(rows[product]) == Decimal("7") and Decimal(soh[product]) == Decimal("5")  # one snapshot
    assert Decimal(rows[other_product]) == Decimal("3") and Decimal(soh[other_product]) == Decimal("7")
    flags = dict(
        session.execute(
            select(ImportCustomerSellthroughStagingLine.source_row_number, ImportCustomerSellthroughStagingLine.apply_status)
            .where(ImportCustomerSellthroughStagingLine.import_job_id == job)
        ).all()
    )
    assert flags == {1: "applied", 2: "applied", 3: "duplicate", 4: "applied", 5: "applied"}
