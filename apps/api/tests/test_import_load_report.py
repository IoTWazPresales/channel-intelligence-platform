"""N-0111 repair (D-0108, Warren 2026-10-16): a load that drops rows says so.

Every sell-through and distributor load reports rows read, loaded and not loaded with the reason
per category. A job with any row not loaded reads "Completed with rows not loaded (N)", never a
plain "Completed".
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.sync_url import sqlalchemy_sync_engine_url
from app.services.imports.import_load_report import build_report, display_status, load_report_sync


def test_rows_not_loaded_never_read_as_plain_completed() -> None:
    report = build_report("customer_sell_through", {"loaded": 10, "no_period": 3})
    assert (report["rows_read"], report["rows_loaded"], report["rows_not_loaded"]) == (13, 10, 3)
    assert display_status("completed", report) == "Completed with rows not loaded (3)"
    assert display_status("completed_with_errors", report) == "Completed with rows not loaded (3)"
    assert report["not_loaded"] == [
        {"reason": "no_period", "label": "No sale date or period", "rows": 3, "partly_loaded": False}
    ]


def test_everything_loaded_reads_completed() -> None:
    report = build_report("customer_sell_through", {"loaded": 4, "duplicate": 1})
    assert (report["rows_read"], report["rows_loaded"], report["rows_not_loaded"]) == (5, 5, 0)
    assert report["identical_copies_counted_once"] == 1
    assert display_status("completed", report) == "Completed"
    assert display_status("running", report) == "Running"
    assert display_status("completed", None) == "Completed"


def test_parser_drops_and_refused_files_are_counted() -> None:
    parse = {
        "rows_not_staged": {"missing_product_or_units": 2},
        "file_rows_refused": {"year_required": 5},
        "files_not_read": [{"filename": "bad.xlsx", "reason": "parse_error"}],
        "files_excluded": 1,
    }
    report = build_report("customer_sell_through", {"loaded": 7}, parse)
    assert (report["rows_read"], report["rows_loaded"], report["rows_not_loaded"]) == (14, 7, 7)
    assert [(i["reason"], i["rows"]) for i in report["not_loaded"]] == [
        ("year_required", 5),
        ("missing_product_or_units", 2),
    ]
    assert report["files_not_read"] == parse["files_not_read"] and report["files_excluded"] == 1
    only_files = build_report("customer_sell_through", {"loaded": 7}, {"files_not_read": parse["files_not_read"]})
    assert display_status("completed", only_files) == "Completed with files not read (1)"


def test_partly_loaded_distributor_rows_count_as_not_loaded() -> None:
    report = build_report("distributor_inventory", {"loaded": 3, "partly_customer_not_matched": 2})
    assert (report["rows_loaded"], report["rows_partly_loaded"], report["rows_not_loaded"]) == (3, 2, 0)
    assert display_status("completed", report) == "Completed with rows not loaded (2)"
    assert report["not_loaded"][0]["partly_loaded"] is True


# ---------------------------------------------------------------- database (cip_test)


@pytest.fixture
def session():
    engine = create_engine(sqlalchemy_sync_engine_url(get_settings().database_url_sync))
    with engine.connect() as conn:
        if conn.execute(text("select current_database()")).scalar() != "cip_test":
            pytest.skip("cip_test only")
        if not conn.execute(text("select to_regclass('fact_distributor_line_superseded')")).scalar():
            pytest.skip("20261016_0042 is not applied")
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
    from app.models.dimensions import DimCustomer, DimDistributor, DimProduct
    from app.models.ingestion import SourceDefinition

    out = {
        "source": db.scalar(select(SourceDefinition.id).order_by(SourceDefinition.id).limit(1)),
        "distributor": db.scalar(select(DimDistributor.id).order_by(DimDistributor.id).limit(1)),
        "customer": db.scalar(select(DimCustomer.id).order_by(DimCustomer.id).limit(1)),
        "product": db.scalar(select(DimProduct.id).order_by(DimProduct.id.desc()).limit(1)),
    }
    if any(v is None for v in out.values()):
        pytest.skip("cip_test needs a source, a distributor, a customer and a product")
    return {k: int(v) for k, v in out.items()}


def test_distributor_load_report_names_each_reason(session: Session) -> None:
    from app.models.import_distributor_si import ImportDistributorSiStagingLine
    from app.models.ingestion import ImportJob
    from app.services.imports.distributor_sales_inventory import upsert_dsi_facts_for_staging_job

    db = session
    ids = _ids(db)
    day = date(2024, 7, 1)
    job = ImportJob(tenant_id="default", source_id=ids["source"], template_slug="distributor_inventory",
                    import_mode="apply", status="completed", stage="validated", file_name="p.xlsx", staged_metadata={})
    db.add(job)
    db.flush()
    full = {"resolved_distributor_id": ids["distributor"], "resolved_customer_id": ids["customer"],
            "resolved_product_id": ids["product"], "resolution_status": "resolved"}
    lines = [
        {**full, "transaction_date": day, "invoice_no": "LR-1", "quantity_sold": 2},
        {**full, "transaction_date": day, "invoice_no": "LR-2", "quantity_sold": 1, "raw_row_payload": {"Qty": 1}},
        # D-0091: differs from the line above, so it is summed into the same invoice line (loaded)
        {**full, "transaction_date": day, "invoice_no": "LR-2", "quantity_sold": 5, "raw_row_payload": {"Qty": 5}},
        {**full, "transaction_date": day, "invoice_no": "LR-6", "quantity_sold": 2, "raw_row_payload": {"Qty": 2}},
        # identical to the line above in every source column: counted once, flagged duplicate
        {**full, "transaction_date": day, "invoice_no": "LR-6", "quantity_sold": 2, "raw_row_payload": {"Qty": 2}},
        {**full, "resolved_product_id": None, "transaction_date": day, "invoice_no": "LR-3", "quantity_sold": 1},
        {**full, "transaction_date": None, "invoice_no": "LR-4", "quantity_sold": 1},
        {**full, "resolved_customer_id": None, "transaction_date": day, "invoice_no": "LR-5", "quantity_sold": 1,
         "snapshot_date": day, "stock_on_hand": 9},
    ]
    for i, ln in enumerate(lines, 1):
        db.add(ImportDistributorSiStagingLine(import_job_id=job.id, source_row_number=i, **ln))
    db.flush()
    upsert_dsi_facts_for_staging_job(db, job)
    db.flush()

    report = load_report_sync(db, job)
    reasons = {i["reason"]: i["rows"] for i in report["not_loaded"]}
    assert report["rows_read"] == 8
    assert report["rows_loaded"] == 5  # LR-1, both LR-2 lines, LR-6 and its identical copy
    assert report["identical_copies_counted_once"] == 1
    assert reasons == {"product_not_matched": 1, "no_date": 1, "partly_customer_not_matched": 1}
    assert display_status(job.status, report) == "Completed with rows not loaded (3)"


def test_sell_through_load_report_names_each_reason(session: Session) -> None:
    from app.models.import_customer_sellthrough_staging import ImportCustomerSellthroughStagingLine
    from app.models.ingestion import ImportJob

    db = session
    ids = _ids(db)
    job = ImportJob(tenant_id="default", source_id=ids["source"], template_slug="customer_sell_through",
                    import_mode="apply", status="completed", stage="loaded", file_name="h.xlsx",
                    staged_metadata={"cst_load_parse": {"rows_not_staged": {"missing_product_or_units": 2}}})
    db.add(job)
    db.flush()
    base = {"resolved_customer_id": ids["customer"], "resolved_product_id": ids["product"],
            "raw_product_token": "X", "units_sold": 1, "period_start_date": date(2024, 7, 1),
            "raw_row_payload": {"SKU": "X"}}
    rows = [
        {**base, "resolution_status": "resolved", "apply_status": "applied"},
        {**base, "resolution_status": "resolved", "apply_status": "duplicate"},
        {**base, "resolution_status": "unresolved", "resolved_product_id": None},
        {**base, "resolution_status": "resolved", "period_start_date": None},
    ]
    for i, r in enumerate(rows, 1):
        db.add(ImportCustomerSellthroughStagingLine(import_job_id=job.id, source_row_number=i, **r))
    db.flush()

    report = load_report_sync(db, job)
    assert (report["rows_read"], report["rows_loaded"], report["rows_not_loaded"]) == (6, 2, 4)
    assert {i["reason"]: i["rows"] for i in report["not_loaded"]} == {
        "missing_product_or_units": 2, "product_not_matched": 1, "no_period": 1,
    }
    assert display_status(job.status, report) == "Completed with rows not loaded (4)"
