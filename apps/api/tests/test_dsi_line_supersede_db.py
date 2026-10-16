"""N-0111 repair (D-0110, Warren 2026-10-16): distributor reloads of the same invoice line.

A line with a new invoice number is a new transaction and is added. Reloading the same invoice
line keeps the replaced figures in ``fact_distributor_line_superseded`` instead of overwriting them
silently; re-applying a load changes nothing. Lines of one load that repeat a key follow D-0091:
lines that differ are summed, lines identical in every source column count once and are flagged.

One rolled-back transaction; cip_test only.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.sync_url import sqlalchemy_sync_engine_url
from app.models.dimensions import DimCustomer, DimDistributor, DimProduct
from app.models.import_distributor_si import ImportDistributorSiStagingLine
from app.models.ingestion import ImportJob, SourceDefinition
from app.services.imports.distributor_sales_inventory import upsert_dsi_facts_for_staging_job

TENANT = "default"
DAY = date(2024, 6, 3)


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
    out = {
        "source": db.scalar(select(SourceDefinition.id).order_by(SourceDefinition.id).limit(1)),
        "distributor": db.scalar(select(DimDistributor.id).order_by(DimDistributor.id).limit(1)),
        "customer": db.scalar(select(DimCustomer.id).order_by(DimCustomer.id).limit(1)),
        "product": db.scalar(select(DimProduct.id).order_by(DimProduct.id.desc()).limit(1)),
    }
    if any(v is None for v in out.values()):
        pytest.skip("cip_test needs a source, a distributor, a customer and a product")
    return {k: int(v) for k, v in out.items()}


def _load(db: Session, ids: dict[str, int], lines: list[dict]) -> ImportJob:
    job = ImportJob(tenant_id=TENANT, source_id=ids["source"], template_slug="distributor_inventory",
                    import_mode="apply", status="pending", stage="validated", file_name="pinnacle.xlsx",
                    staged_metadata={})
    db.add(job)
    db.flush()
    for i, ln in enumerate(lines, 1):
        db.add(ImportDistributorSiStagingLine(
            import_job_id=job.id, source_row_number=i, resolved_distributor_id=ids["distributor"],
            resolved_customer_id=ids["customer"], resolved_product_id=ids["product"], resolution_status="resolved",
            transaction_date=DAY, **ln))
    db.flush()
    _apply(db, job)
    return job


def _apply(db: Session, job: ImportJob) -> None:
    sell, _inv, ret, errors = upsert_dsi_facts_for_staging_job(db, job)
    assert not errors, errors
    db.flush()


def _sellout(db: Session, ids: dict[str, int], invoice: str) -> float | None:
    v = db.scalar(text("select units from fact_sales_sellout where distributor_id = :d and customer_id = :c "
                       "and product_id = :p and transaction_date = :t and invoice_no = :i"),
                  {"d": ids["distributor"], "c": ids["customer"], "p": ids["product"], "t": DAY, "i": invoice})
    return float(v) if v is not None else None


def _kept(db: Session, ids: dict[str, int]) -> list[tuple]:
    return [tuple(r) for r in db.execute(text(
        "select fact_table, invoice_no, figures, previous_import_job_id, superseded_by_import_job_id "
        "from fact_distributor_line_superseded where product_id = :p and transaction_date = :t order by id"),
        {"p": ids["product"], "t": DAY}).all()]


def test_reload_of_the_same_invoice_keeps_the_replaced_figures(session: Session) -> None:
    db = session
    ids = _ids(db)
    first = _load(db, ids, [{"invoice_no": "N111-INV-1", "quantity_sold": 5, "reported_revenue_amount": 50}])
    assert _sellout(db, ids, "N111-INV-1") == 5
    assert _kept(db, ids) == []

    reload = _load(db, ids, [{"invoice_no": "N111-INV-1", "quantity_sold": 7, "reported_revenue_amount": 70}])
    assert _sellout(db, ids, "N111-INV-1") == 7
    kept = _kept(db, ids)
    assert len(kept) == 1
    table, invoice, figures, prev_job, by_job = kept[0]
    assert (table, invoice, prev_job, by_job) == ("fact_sales_sellout", "N111-INV-1", first.id, reload.id)
    assert figures["units"] == {"old": 5.0, "new": 7.0}
    assert figures["reported_revenue_amount"] == {"old": 50.0, "new": 70.0}
    assert (reload.staged_metadata or {})["distributor_si"]["superseded_lines"] == 1

    # Re-applying the same load changes nothing and keeps no second record.
    _apply(db, reload)
    assert _sellout(db, ids, "N111-INV-1") == 7
    assert len(_kept(db, ids)) == 1

    # A reload with the same figures replaces nothing.
    _load(db, ids, [{"invoice_no": "N111-INV-1", "quantity_sold": 7, "reported_revenue_amount": 70}])
    assert len(_kept(db, ids)) == 1


def test_a_new_invoice_number_is_added_unchanged(session: Session) -> None:
    db = session
    ids = _ids(db)
    _load(db, ids, [{"invoice_no": "N111-INV-A", "quantity_sold": 3}])
    _load(db, ids, [{"invoice_no": "N111-INV-B", "quantity_sold": 2}])
    assert (_sellout(db, ids, "N111-INV-A"), _sellout(db, ids, "N111-INV-B")) == (3, 2)
    assert _kept(db, ids) == []


def _statuses(db: Session, job: ImportJob) -> list[str]:
    return list(db.scalars(select(ImportDistributorSiStagingLine.apply_status).where(
        ImportDistributorSiStagingLine.import_job_id == job.id).order_by(
        ImportDistributorSiStagingLine.source_row_number)).all())


def test_repeated_lines_that_differ_in_one_load_are_summed(session: Session) -> None:
    """D-0091 for Pinnacle (Warren 2026-10-16): lines of one load with the same key that differ are summed."""
    db = session
    ids = _ids(db)
    job = _load(db, ids, [
        {"invoice_no": "N111-INV-R", "quantity_sold": 1, "reported_revenue_amount": 10, "raw_row_payload": {"Qty": 1}},
        {"invoice_no": "N111-INV-R", "quantity_sold": 4, "reported_revenue_amount": 40, "raw_row_payload": {"Qty": 4}},
    ])
    assert _sellout(db, ids, "N111-INV-R") == 5
    revenue = db.scalar(text("select reported_revenue_amount from fact_sales_sellout where product_id = :p "
                             "and invoice_no = 'N111-INV-R' and transaction_date = :t"), {"p": ids["product"], "t": DAY})
    assert float(revenue) == 50.0
    assert _kept(db, ids) == []  # nothing was replaced: both lines count
    assert _statuses(db, job) == ["sellout", "sellout"]
    assert job.staged_metadata["distributor_si"]["summed_lines"] == 1
    assert job.staged_metadata["distributor_si"]["duplicate_lines"] == 0
    fact_ids = set(db.scalars(select(ImportDistributorSiStagingLine.fact_sellout_row_id).where(
        ImportDistributorSiStagingLine.import_job_id == job.id)).all())
    assert len(fact_ids) == 1 and None not in fact_ids  # both lines point at the one stored row
    # Re-applying the load changes nothing and keeps nothing.
    _apply(db, job)
    assert _sellout(db, ids, "N111-INV-R") == 5
    assert _kept(db, ids) == []


def test_repeated_lines_identical_in_every_source_column_count_once_and_are_flagged(session: Session) -> None:
    db = session
    ids = _ids(db)
    same = {"invoice_no": "N111-INV-D", "quantity_sold": 3, "raw_row_payload": {"Qty": 3, "Ref": "A"}}
    job = _load(db, ids, [same, dict(same), {**same, "raw_row_payload": {"Qty": 3, "Ref": "B"}}])
    # Lines 1 and 2 are identical (counted once); line 3 differs in a source column (summed): 3 + 3.
    assert _sellout(db, ids, "N111-INV-D") == 6
    assert _statuses(db, job) == ["sellout", "duplicate", "sellout"]
    assert job.staged_metadata["distributor_si"]["duplicate_lines"] == 1
    assert job.staged_metadata["distributor_si"]["summed_lines"] == 1
    _apply(db, job)
    assert _sellout(db, ids, "N111-INV-D") == 6
    assert _statuses(db, job) == ["sellout", "duplicate", "sellout"]
    assert _kept(db, ids) == []


def test_a_reload_of_a_summed_invoice_line_keeps_the_replaced_total(session: Session) -> None:
    db = session
    ids = _ids(db)
    first = _load(db, ids, [{"invoice_no": "N111-INV-S", "quantity_sold": 2, "raw_row_payload": {"Q": 2}},
                            {"invoice_no": "N111-INV-S", "quantity_sold": 3, "raw_row_payload": {"Q": 3}}])
    assert _sellout(db, ids, "N111-INV-S") == 5
    again = _load(db, ids, [{"invoice_no": "N111-INV-S", "quantity_sold": 9, "raw_row_payload": {"Q": 9}}])
    assert _sellout(db, ids, "N111-INV-S") == 9
    kept = _kept(db, ids)
    assert [(k[0], k[3], k[4]) for k in kept] == [("fact_sales_sellout", first.id, again.id)]
    assert kept[0][2]["units"] == {"old": 5.0, "new": 9.0}


def test_repeated_return_lines_that_differ_are_summed(session: Session) -> None:
    db = session
    ids = _ids(db)
    _load(db, ids, [
        {"invoice_no": "N111-CR-R", "quantity_sold": -2, "unit_sellout_price_ex_tax_amount": 10, "raw_row_payload": {"Q": -2}},
        {"invoice_no": "N111-CR-R", "quantity_sold": -3, "unit_sellout_price_ex_tax_amount": 10, "raw_row_payload": {"Q": -3}},
    ])
    qty = db.scalar(text("select return_quantity from fact_returns where product_id = :p and invoice_no = 'N111-CR-R' "
                         "and transaction_date = :t"), {"p": ids["product"], "t": DAY})
    assert float(qty) == 5.0
    assert _kept(db, ids) == []


def test_a_return_reload_keeps_the_replaced_quantity(session: Session) -> None:
    db = session
    ids = _ids(db)
    first = _load(db, ids, [{"invoice_no": "N111-CR-1", "quantity_sold": -2, "unit_sellout_price_ex_tax_amount": 10}])
    again = _load(db, ids, [{"invoice_no": "N111-CR-1", "quantity_sold": -3, "unit_sellout_price_ex_tax_amount": 10}])
    kept = _kept(db, ids)
    assert [(k[0], k[3], k[4]) for k in kept] == [("fact_returns", first.id, again.id)]
    assert kept[0][2]["return_quantity"] == {"old": 2.0, "new": 3.0}
