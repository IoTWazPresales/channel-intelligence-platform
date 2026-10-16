"""N-0111 repair (D-0110, Warren 2026-10-16): distributor reloads of the same invoice line.

A line with a new invoice number is a new transaction and is added. Reloading the same invoice
line keeps the replaced figures in ``fact_distributor_line_superseded`` instead of overwriting them
silently; re-applying a load changes nothing. Lines of one load that repeat a key replace each
other in file order and the earlier figures are kept the same way.

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
from app.services.imports.dsi_line_supersede import replaced_within_load

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


def test_a_repeated_line_in_one_load_is_kept_and_named(session: Session) -> None:
    db = session
    ids = _ids(db)
    job = _load(db, ids, [{"invoice_no": "N111-INV-R", "quantity_sold": 1},
                          {"invoice_no": "N111-INV-R", "quantity_sold": 4}])
    assert _sellout(db, ids, "N111-INV-R") == 4
    kept = _kept(db, ids)
    assert [(k[0], k[3], k[4]) for k in kept] == [("fact_sales_sellout", job.id, job.id)]
    first_line = db.scalar(select(ImportDistributorSiStagingLine.id).where(
        ImportDistributorSiStagingLine.import_job_id == job.id, ImportDistributorSiStagingLine.source_row_number == 1))
    assert replaced_within_load(db, job.id) == {int(first_line): "fact_sales_sellout"}
    _apply(db, job)
    assert _sellout(db, ids, "N111-INV-R") == 4
    assert len(_kept(db, ids)) == 1


def test_a_return_reload_keeps_the_replaced_quantity(session: Session) -> None:
    db = session
    ids = _ids(db)
    first = _load(db, ids, [{"invoice_no": "N111-CR-1", "quantity_sold": -2, "unit_sellout_price_ex_tax_amount": 10}])
    again = _load(db, ids, [{"invoice_no": "N111-CR-1", "quantity_sold": -3, "unit_sellout_price_ex_tax_amount": 10}])
    kept = _kept(db, ids)
    assert [(k[0], k[3], k[4]) for k in kept] == [("fact_returns", first.id, again.id)]
    assert kept[0][2]["return_quantity"] == {"old": 2.0, "new": 3.0}
