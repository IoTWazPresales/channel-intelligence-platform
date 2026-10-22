"""N-0113 (Warren 2026-10-22): rows dated after the upload day are not loaded.

A sell-through row whose period starts, or a distributor row whose sale or stock date falls, after
the day its file was uploaded stays staged and shows in the job's load report as "Dated after the
upload date (check the year)". Day, week and month grains and the confirmed-year path all apply.

One rolled-back transaction; cip_test only.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.sync_url import sqlalchemy_sync_engine_url
from app.models.dimensions import DimCustomer, DimDistributor, DimProduct
from app.models.import_customer_sellthrough_staging import ImportCustomerSellthroughStagingLine
from app.models.import_distributor_si import ImportDistributorSiStagingLine
from app.models.ingestion import ImportJob, SourceDefinition
from app.services.imports.customer_sell_through_apply import apply_customer_sellthrough_staging
from app.services.imports.distributor_sales_inventory import upsert_dsi_facts_for_staging_job
from app.services.imports.import_load_report import load_report_sync
from app.services.imports.upload_date_rule import DATED_AFTER_UPLOAD, dated_after, upload_day

# Uploaded 2026-10-22 at 08:00 in Johannesburg.
UPLOADED = datetime(2026, 10, 22, 6, 0, tzinfo=timezone.utc)
UPLOAD_DAY = date(2026, 10, 22)
LABEL = "Dated after the upload date (check the year)"


def test_upload_day_is_the_reporting_timezone_date() -> None:
    class Job:
        created_at = datetime(2026, 10, 21, 22, 30, tzinfo=timezone.utc)  # 00:30 on the 22nd in Johannesburg

    assert upload_day(Job()) == UPLOAD_DAY
    assert dated_after(date(2026, 10, 23), UPLOAD_DAY)
    assert not dated_after(UPLOAD_DAY, UPLOAD_DAY)
    assert not dated_after(None, UPLOAD_DAY)


@pytest.fixture
def session():
    engine = create_engine(sqlalchemy_sync_engine_url(get_settings().database_url_sync))
    with engine.connect() as conn:
        if conn.execute(text("select current_database()")).scalar() != "cip_test":
            pytest.skip("cip_test only")
        conn.rollback()
        outer = conn.begin()
        db = Session(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield db
        finally:
            db.close()
            outer.rollback()
    engine.dispose()


def _ids(db: Session) -> dict[str, int]:
    out = {
        "source": db.scalar(select(SourceDefinition.id).order_by(SourceDefinition.id).limit(1)),
        "distributor": db.scalar(select(DimDistributor.id).order_by(DimDistributor.id).limit(1)),
        "customer": db.scalar(select(DimCustomer.id).order_by(DimCustomer.id).limit(1)),
        "product": db.scalar(select(DimProduct.id).order_by(DimProduct.id.desc()).limit(1)),
    }
    if any(v is None for v in out.values()):
        pytest.skip("cip_test needs a source, a distributor, a customer and a product")
    return {k: int(v) for k, v in out.items()}


def _job(db: Session, ids: dict[str, int], slug: str, meta: dict | None = None) -> ImportJob:
    job = ImportJob(tenant_id="default", source_id=ids["source"], template_slug=slug, import_mode="apply",
                    status="completed", stage="validated", file_name="dated.xlsx", staged_metadata=meta or {},
                    created_at=UPLOADED)
    db.add(job)
    db.flush()
    return job


def _reasons(db: Session, job: ImportJob) -> dict[str, tuple[int, str]]:
    report = load_report_sync(db, job)
    return {i["reason"]: (i["rows"], i["label"]) for i in report["not_loaded"]}


def _cst_lines(db: Session, ids: dict[str, int], job: ImportJob, rows: list[tuple[date, str, str]]) -> None:
    for i, (start, grain, token) in enumerate(rows, 1):
        db.add(ImportCustomerSellthroughStagingLine(
            import_job_id=job.id, source_row_number=i, resolved_customer_id=ids["customer"],
            resolved_product_id=ids["product"], resolution_status="resolved", raw_product_token=token,
            units_sold=3, period_start_date=start, period_type=grain, raw_row_payload={"SKU": token}))
    db.flush()


def _cst_loaded(db: Session, job: ImportJob) -> list[date]:
    return sorted(db.scalars(text(
        "select period_start_date from fact_customer_sellthrough where import_job_id = :j"), {"j": job.id}).all())


def test_sell_through_rows_dated_after_the_upload_day_are_not_loaded(session: Session) -> None:
    db = session
    ids = _ids(db)
    job = _job(db, ids, "customer_sell_through")
    _cst_lines(db, ids, job, [
        (UPLOAD_DAY, "daily", "on-the-day"),             # day grain, the upload day itself: loaded
        (date(2026, 10, 19), "weekly", "this-week"),     # week starting before the upload day: loaded
        (date(2026, 10, 23), "daily", "next-day"),       # day grain, the day after: not loaded
        (date(2026, 10, 26), "weekly", "next-week"),     # week starting after: not loaded
        (date(2026, 11, 1), "monthly", "next-month"),    # month starting after: not loaded
        (date(2027, 10, 18), "weekly", "wrong-year"),    # a week number read into next year: not loaded
    ])

    summary = apply_customer_sellthrough_staging(db, job.id, recompute_stock_gap=False)
    db.flush()

    assert not summary.errors
    assert summary.skipped_dated_after_upload == 4
    assert _cst_loaded(db, job) == [date(2026, 10, 19), UPLOAD_DAY]
    assert _reasons(db, job) == {DATED_AFTER_UPLOAD: (4, LABEL)}
    left = db.scalars(text(
        "select apply_status from import_customer_sellthrough_staging_line where import_job_id = :j "
        "and period_start_date > :d"), {"j": job.id, "d": UPLOAD_DAY}).all()
    assert left == [None] * 4  # still staged, never applied


def test_sell_through_confirmed_year_path_keeps_out_weeks_after_the_upload_day(session: Session) -> None:
    db = session
    ids = _ids(db)
    # Week numbers without a year, year confirmed as 2027 by mistake: the weeks land after the upload day.
    meta = {"cst_year_required": [{"filename": "dated.xlsx"}], "cst_confirmed_year": 2027}
    job = _job(db, ids, "customer_sell_through", meta)
    _cst_lines(db, ids, job, [(date(2027, 1, 4), "weekly", "wk1"), (date(2027, 1, 11), "weekly", "wk2")])

    summary = apply_customer_sellthrough_staging(db, job.id, recompute_stock_gap=False)
    db.flush()

    assert not summary.errors  # the year is confirmed, so the apply runs
    assert summary.skipped_dated_after_upload == 2
    assert _cst_loaded(db, job) == []
    assert _reasons(db, job) == {DATED_AFTER_UPLOAD: (2, LABEL)}


def test_distributor_lines_dated_after_the_upload_day_are_not_loaded(session: Session) -> None:
    db = session
    ids = _ids(db)
    job = _job(db, ids, "distributor_inventory")
    full = {"resolved_distributor_id": ids["distributor"], "resolved_customer_id": ids["customer"],
            "resolved_product_id": ids["product"], "resolution_status": "resolved"}
    lines = [
        {**full, "transaction_date": UPLOAD_DAY, "invoice_no": "UD-1", "quantity_sold": 2},          # loaded
        {**full, "transaction_date": date(2026, 10, 23), "invoice_no": "UD-2", "quantity_sold": 1},  # sale after
        {**full, "transaction_date": date(2027, 10, 20), "invoice_no": "UD-3", "quantity_sold": 4},  # wrong year
        {**full, "resolved_customer_id": None, "snapshot_date": date(2026, 10, 30), "stock_on_hand": 7},  # stock after
        # sale on time, its stock snapshot after: the whole line stays out
        {**full, "transaction_date": UPLOAD_DAY, "invoice_no": "UD-4", "quantity_sold": 1,
         "snapshot_date": date(2026, 11, 2), "stock_on_hand": 5},
    ]
    for i, ln in enumerate(lines, 1):
        db.add(ImportDistributorSiStagingLine(import_job_id=job.id, source_row_number=i, **ln))
    db.flush()

    sell, inv, _ret, errors = upsert_dsi_facts_for_staging_job(db, job)
    db.flush()

    assert not errors, errors
    assert (sell, inv) == (1, 0)
    invoices = db.scalars(text(
        "select invoice_no from fact_sales_sellout where source_import_job_id = :j"), {"j": job.id}).all()
    assert invoices == ["UD-1"]
    assert db.scalar(text(
        "select count(*) from fact_inventory_distributor where source_import_job_id = :j"), {"j": job.id}) == 0
    report = load_report_sync(db, job)
    assert (report["rows_read"], report["rows_loaded"], report["rows_not_loaded"]) == (5, 1, 4)
    assert _reasons(db, job) == {DATED_AFTER_UPLOAD: (4, LABEL)}
