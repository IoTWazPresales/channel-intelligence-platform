"""N-0110: re-uploading the same sell-through file does not count units twice.

One rolled-back transaction; cip_test only. Storage is an in-memory stand-in.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

import app.services.imports.customer_sell_through_supersede as supersede_mod
from app.core.config import get_settings
from app.db.sync_url import sqlalchemy_sync_engine_url
from app.models.dimensions import DimCustomer, DimProduct
from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.models.import_customer_sellthrough_staging import ImportCustomerSellthroughStagingLine
from app.models.ingestion import ImportJob, RawFileMetadata, SourceDefinition
from app.services.imports.customer_sell_through_apply import apply_customer_sellthrough_staging

TENANT = "n0110_reupload"
OLD_WEEK = date(2026, 9, 28)  # old load: week 40 stored under the wrong year, sites as one row
NEW_WEEK = date(2025, 9, 29)


class _Storage:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    def read(self, key: str) -> bytes:
        return self.files[key]


@pytest.fixture
def session(monkeypatch):
    engine = create_engine(sqlalchemy_sync_engine_url(get_settings().database_url_sync))
    with engine.connect() as conn:
        if conn.execute(text("select current_database()")).scalar() != "cip_test":
            pytest.skip("cip_test only")
        if not conn.execute(text("select to_regclass('fact_customer_sellthrough_superseded')")).scalar():
            pytest.skip("20261015_0038 is not applied")
        conn.rollback()
        outer = conn.begin()
        db = Session(bind=conn, join_transaction_mode="create_savepoint")
        storage = _Storage()
        monkeypatch.setattr(supersede_mod, "get_storage_backend", lambda: storage)
        db.info["storage"] = storage
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


def _job(db: Session, source: int, content: bytes) -> int:
    job = ImportJob(
        tenant_id=TENANT,
        source_id=source,
        template_slug="customer_sell_through",
        import_mode="apply",
        status="completed",
        stage="staged",
        file_name="Week 40.xlsx",
    )
    db.add(job)
    db.flush()
    key = f"n0110/{job.id}/Week 40.xlsx"
    db.info["storage"].files[key] = content
    db.add(RawFileMetadata(job_id=job.id, storage_key=key, byte_size=len(content)))
    db.flush()
    return int(job.id)


def _old_row(db: Session, job: int, customer: int, product: int, units: str) -> None:
    db.add(
        FactCustomerSellthrough(
            source_key=f"ct:{customer}:0:{product}:{OLD_WEEK.isoformat()}:n0110",
            tenant_id=TENANT,
            customer_id=customer,
            product_id=product,
            period_start_date=OLD_WEEK,
            period_type="weekly",
            units_sold=Decimal(units),
            reported_soh=Decimal("5"),
            import_job_id=job,
        )
    )


def _line(db: Session, job: int, n: int, customer: int, product: int, site: str, units: str) -> None:
    db.add(
        ImportCustomerSellthroughStagingLine(
            import_job_id=job,
            source_row_number=n,
            raw_row_payload={"Site": site, "Units": units},
            resolved_customer_id=customer,
            resolved_product_id=product,
            period_start_date=NEW_WEEK,
            period_type="weekly",
            period_grain="week",
            period_week=40,
            period_year=2025,
            units_sold=Decimal(units),
            reported_soh=Decimal("5"),
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


def _reupload(db: Session, source: int, content: bytes, customer: int, product: int) -> tuple[int, object]:
    job = _job(db, source, content)
    _line(db, job, 1, customer, product, "S1", "4")
    _line(db, job, 2, customer, product, "S2", "3")
    db.flush()
    return job, apply_customer_sellthrough_staging(db, job, recompute_stock_gap=False)


def test_reupload_of_same_file_supersedes_old_rows_and_is_idempotent(session: Session) -> None:
    source, customer, product, other_product = _ids(session)
    content = b"same file bytes"
    old_job = _job(session, source, content)
    _old_row(session, old_job, customer, product, "4")  # two sites stored as one row: last wins
    _old_row(session, old_job, customer, other_product, "9")  # not restated by the re-upload
    session.flush()
    assert _units(session) == Decimal("13")

    first_job, first = _reupload(session, source, content, customer, product)
    assert first.errors == []
    assert first.superseded_rows == 1 and first.superseded_units == 4.0
    # 4 + 3 per site, plus the untouched product's 9: the old row under-counted by 3.
    assert _units(session) == Decimal("16")
    moved = session.execute(
        text(
            "select source_key, units_sold, import_job_id, superseded_by_import_job_id, reason, row_json->>'units_sold' "
            "from fact_customer_sellthrough_superseded where tenant_id = :t"
        ),
        {"t": TENANT},
    ).all()
    assert len(moved) == 1
    assert moved[0][2] == old_job and moved[0][3] == first_job and moved[0][4] == "same_file_reloaded"
    assert Decimal(moved[0][1]) == Decimal("4") and Decimal(moved[0][5]) == Decimal("4")

    # Raw staging rows of every load are kept.
    assert session.scalar(
        select(func.count()).select_from(ImportCustomerSellthroughStagingLine).where(
            ImportCustomerSellthroughStagingLine.import_job_id.in_([old_job, first_job])
        )
    ) == 2

    # Loading the same file again changes nothing.
    _, second = _reupload(session, source, content, customer, product)
    assert second.superseded_rows == 0
    assert _units(session) == Decimal("16")


def test_different_file_keeps_old_rows(session: Session) -> None:
    source, customer, product, _ = _ids(session)
    old_job = _job(session, source, b"last year's week 40")
    _old_row(session, old_job, customer, product, "4")
    session.flush()

    _, summary = _reupload(session, source, b"this year's week 40", customer, product)
    assert summary.superseded_rows == 0
    assert _units(session) == Decimal("11")  # 4 kept + 4 + 3


def test_unreadable_old_file_keeps_old_rows(session: Session) -> None:
    source, customer, product, _ = _ids(session)
    content = b"same file bytes"
    old_job = _job(session, source, content)
    _old_row(session, old_job, customer, product, "4")
    session.flush()
    files = session.info["storage"].files
    for key in [k for k in files if k.startswith(f"n0110/{old_job}/")]:
        del files[key]  # the old upload is gone: same source cannot be proven

    job = _job(session, source, content)
    _line(session, job, 1, customer, product, "S1", "4")
    session.flush()
    summary = apply_customer_sellthrough_staging(session, job, recompute_stock_gap=False)
    assert summary.superseded_rows == 0
    assert _units(session) == Decimal("8")
