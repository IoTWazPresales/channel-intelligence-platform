"""N-0112 (Warren 2026-10-22): deleting an import job removes the data it loaded and restores what it
replaced. Loads go through the real apply paths; one rolled-back transaction per test; cip_test only.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.sync_url import sqlalchemy_sync_engine_url
from app.models.dimensions import DimCustomer, DimDistributor, DimProduct
from app.models.import_customer_sellthrough_staging import ImportCustomerSellthroughStagingLine
from app.models.import_distributor_si import CustomerSourceTokenAlias, ImportDistributorSiStagingLine
from app.models.ingestion import ImportJob, SourceDefinition
from app.services.imports.customer_sell_through_apply import apply_customer_sellthrough_staging
from app.services.imports.distributor_sales_inventory import upsert_dsi_facts_for_staging_job
from app.services.imports.import_job_bulk_delete import bulk_delete_import_jobs, preview_import_job_bulk_delete

TENANT = "n0112_delete"
WEEK = date(2025, 3, 10)
DAY = date(2024, 6, 3)
T0 = datetime(2026, 8, 1, tzinfo=timezone.utc)


@pytest.fixture
def session():
    engine = create_engine(sqlalchemy_sync_engine_url(get_settings().database_url_sync))
    with engine.connect() as conn:
        if conn.execute(text("select current_database()")).scalar() != "cip_test":
            pytest.skip("cip_test only")
        has_policy = conn.execute(
            text(
                "select count(*) from pg_policies where policyname = 'cip_pl_delete' "
                "and tablename in ('fact_customer_sellthrough_superseded', 'fact_distributor_line_superseded')"
            )
        ).scalar()
        if has_policy != 2:
            pytest.skip("20261022_0047 is not applied")
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


def _delete(db: Session, *jobs: int, aliases: bool = False) -> dict:
    out = bulk_delete_import_jobs(db, list(jobs), delete_semantic_artifacts=aliases)
    db.flush()
    db.expire_all()
    return out


# ---------------------------------------------------------------------------------- sell-through
def _st_load(db: Session, ids: dict[str, int], day: int, *, units: str | None, soh: str | None, site: str = "S1") -> int:
    job = ImportJob(
        tenant_id=TENANT, source_id=ids["source"], template_slug="customer_sell_through", import_mode="apply",
        status="completed", stage="staged", file_name=f"n0112-{day}.xlsx", created_at=T0 + timedelta(days=day),
        staged_metadata={},
    )
    db.add(job)
    db.flush()
    db.add(ImportCustomerSellthroughStagingLine(
        import_job_id=job.id, source_row_number=1, raw_row_payload={"Site": site, "Units": units, "SOH": soh},
        resolved_customer_id=ids["customer"], resolved_product_id=ids["product"], period_start_date=WEEK,
        period_type="weekly", period_grain="week", units_sold=Decimal(units) if units is not None else None,
        reported_soh=Decimal(soh) if soh is not None else None, site_label=site, resolution_status="resolved",
    ))
    db.flush()
    summary = apply_customer_sellthrough_staging(db, int(job.id), recompute_stock_gap=False)
    assert summary.errors == [], summary.errors
    return int(job.id)


def _st_rows(db: Session) -> list[tuple]:
    return [tuple(r) for r in db.execute(text(
        "select site_label, units_sold::float, reported_soh::float, figure_import_jobs from fact_customer_sellthrough "
        "where tenant_id = :t order by site_label"), {"t": TENANT}).all()]


def _st_records(db: Session) -> list[tuple]:
    return [tuple(r) for r in db.execute(text(
        "select superseded_by_import_job_id, (row_json->>'units_sold')::float, figures "
        "from fact_customer_sellthrough_superseded where tenant_id = :t order by id"), {"t": TENANT}).all()]


def test_deleting_a_reload_brings_back_the_figures_it_replaced(session: Session) -> None:
    ids = _ids(session)
    real = _st_load(session, ids, 0, units="12", soh="40")
    test = _st_load(session, ids, 1, units="15", soh="35")
    assert _st_rows(session) == [("S1", 15.0, 35.0, {"units_sold": test, "reported_soh": test})]
    out = _delete(session, test)
    assert _st_rows(session) == [("S1", 12.0, 40.0, {"units_sold": real, "reported_soh": real})]
    assert _st_records(session) == []
    assert out["data"]["per_job"][test]["sellthrough_figures_restored"] == 2
    assert out["deleted"]["import_jobs_deleted"] == 1


def test_deleting_an_identical_reload_hands_the_figures_back_to_the_earlier_load(session: Session) -> None:
    ids = _ids(session)
    real = _st_load(session, ids, 0, units="12", soh="40")
    test = _st_load(session, ids, 1, units="12", soh="40")
    assert _st_records(session) == []  # identical: nothing was recorded
    _delete(session, test)
    assert _st_rows(session) == [("S1", 12.0, 40.0, {"units_sold": real, "reported_soh": real})]


def test_a_row_moved_aside_whole_comes_back_and_the_deleted_rows_go(session: Session) -> None:
    ids = _ids(session)
    real = _st_load(session, ids, 0, units="9", soh="30", site="0")
    test = _st_load(session, ids, 1, units="7", soh="25", site="S1")
    assert _st_rows(session) == [("S1", 7.0, 25.0, {"units_sold": test, "reported_soh": test})]
    out = _delete(session, test)
    assert _st_rows(session) == [("0", 9.0, 30.0, {"units_sold": real, "reported_soh": real})]
    assert out["data"]["per_job"][test]["sellthrough_rows_removed"] == 1
    assert _st_records(session) == []


def test_a_figure_cleared_by_a_stock_only_load_comes_back(session: Session) -> None:
    ids = _ids(session)
    real = _st_load(session, ids, 0, units="9", soh="30", site="0")
    test = _st_load(session, ids, 1, units=None, soh="25", site="S1")
    assert sorted(r[:3] for r in _st_rows(session)) == [("0", 9.0, None), ("S1", 0.0, 25.0)]
    _delete(session, test)
    assert _st_rows(session) == [("0", 9.0, 30.0, {"units_sold": real, "reported_soh": real})]


def test_a_later_load_keeps_its_figures_and_its_record_points_past_the_deleted_load(session: Session) -> None:
    ids = _ids(session)
    real = _st_load(session, ids, 0, units="12", soh="40")
    test = _st_load(session, ids, 1, units="15", soh="35")
    later = _st_load(session, ids, 2, units="20", soh="50")
    preview = preview_import_job_bulk_delete(session, [test])
    assert preview["jobs"][0]["counts"]["sellthrough_figures_kept_later"] == 2
    assert _st_rows(session)[0][:3] == ("S1", 20.0, 50.0)  # the preview rolled back: nothing changed
    _delete(session, test)
    assert _st_rows(session) == [("S1", 20.0, 50.0, {"units_sold": later, "reported_soh": later})]
    assert _st_records(session) == [(later, 12.0, ["units_sold", "reported_soh"])]
    _delete(session, later)
    assert _st_rows(session) == [("S1", 12.0, 40.0, {"units_sold": real, "reported_soh": real})]


def test_a_row_only_the_deleted_load_wrote_is_removed(session: Session) -> None:
    ids = _ids(session)
    test = _st_load(session, ids, 0, units="4", soh="8")
    _delete(session, test)
    assert _st_rows(session) == []


def test_deleting_two_loads_in_a_chain_goes_back_past_both(session: Session) -> None:
    ids = _ids(session)
    real = _st_load(session, ids, 0, units="5", soh="10")
    first = _st_load(session, ids, 1, units="7", soh="10")
    second = _st_load(session, ids, 2, units="7", soh="10")
    _delete(session, first, second)
    assert _st_rows(session) == [("S1", 5.0, 10.0, {"units_sold": real, "reported_soh": real})]


# ---------------------------------------------------------------------------------- distributor lines
def _dsi_load(db: Session, ids: dict[str, int], lines: list[dict], day: int = 0) -> int:
    job = ImportJob(tenant_id="default", source_id=ids["source"], template_slug="distributor_inventory",
                    import_mode="apply", status="pending", stage="validated", file_name=f"n0112-dsi-{day}.xlsx",
                    created_at=T0 + timedelta(days=day), staged_metadata={})
    db.add(job)
    db.flush()
    for i, ln in enumerate(lines, 1):
        db.add(ImportDistributorSiStagingLine(
            import_job_id=job.id, source_row_number=i, resolved_distributor_id=ids["distributor"],
            resolved_customer_id=ids["customer"], resolved_product_id=ids["product"], resolution_status="resolved",
            transaction_date=DAY, **ln))
    db.flush()
    _s, _i, _r, errors = upsert_dsi_facts_for_staging_job(db, job)
    assert not errors, errors
    db.flush()
    return int(job.id)


def _line(db: Session, ids: dict[str, int], table: str, qty_col: str, job_col: str, invoice: str) -> tuple | None:
    r = db.execute(text(f"select {qty_col}::float, {job_col} from {table} where product_id = :p and customer_id = :c "
                        f"and transaction_date = :t and invoice_no = :i"),
                   {"p": ids["product"], "c": ids["customer"], "t": DAY, "i": invoice}).first()
    return tuple(r) if r else None


def _sellout(db, ids, invoice):
    return _line(db, ids, "fact_sales_sellout", "units", "source_import_job_id", invoice)


def _dsi_records(db: Session, ids: dict[str, int]) -> list[tuple]:
    return [tuple(r) for r in db.execute(text(
        "select fact_table, previous_import_job_id, superseded_by_import_job_id, (figures->'units'->>'old')::float "
        "from fact_distributor_line_superseded where product_id = :p and transaction_date = :t order by id"),
        {"p": ids["product"], "t": DAY}).all()]


def test_deleting_a_distributor_reload_brings_back_the_line_it_replaced(session: Session) -> None:
    ids = _ids(session)
    real = _dsi_load(session, ids, [{"invoice_no": "N112-1", "quantity_sold": 5, "reported_revenue_amount": 50}])
    test = _dsi_load(session, ids, [{"invoice_no": "N112-1", "quantity_sold": 7, "reported_revenue_amount": 70}], 1)
    assert _sellout(session, ids, "N112-1") == (7.0, test)
    _delete(session, test)
    assert _sellout(session, ids, "N112-1") == (5.0, real)
    assert _dsi_records(session, ids) == []
    line = session.scalar(text("select staging_line_id from fact_sales_sellout where invoice_no = 'N112-1' "
                               "and product_id = :p"), {"p": ids["product"]})
    owner = session.scalar(select(ImportDistributorSiStagingLine.import_job_id).where(ImportDistributorSiStagingLine.id == line))
    assert owner == real


def test_deleting_an_identical_distributor_reload_hands_the_line_back(session: Session) -> None:
    ids = _ids(session)
    real = _dsi_load(session, ids, [{"invoice_no": "N112-2", "quantity_sold": 5}])
    test = _dsi_load(session, ids, [{"invoice_no": "N112-2", "quantity_sold": 5}], 1)
    _delete(session, test)
    assert _sellout(session, ids, "N112-2") == (5.0, real)


def test_returns_and_sell_out_a_job_alone_loaded_are_removed(session: Session) -> None:
    """Job 1679 on cip left 3 returns rows behind with their job link cleared."""
    ids = _ids(session)
    test = _dsi_load(session, ids, [
        {"invoice_no": "N112-3", "quantity_sold": 4},
        {"invoice_no": "N112-CR3", "quantity_sold": -2, "unit_sellout_price_ex_tax_amount": 10},
    ])
    assert _line(session, ids, "fact_returns", "return_quantity", "import_job_id", "N112-CR3") == (2.0, test)
    out = _delete(session, test)
    assert _sellout(session, ids, "N112-3") is None
    assert _line(session, ids, "fact_returns", "return_quantity", "import_job_id", "N112-CR3") is None
    assert out["data"]["per_job"][test]["fact_returns_rows_removed"] == 1
    assert out["data"]["per_job"][test]["fact_sales_sellout_rows_removed"] == 1


def test_a_later_distributor_load_keeps_its_line_and_its_record_points_past_the_deleted_load(session: Session) -> None:
    ids = _ids(session)
    real = _dsi_load(session, ids, [{"invoice_no": "N112-4", "quantity_sold": 5}])
    test = _dsi_load(session, ids, [{"invoice_no": "N112-4", "quantity_sold": 7}], 1)
    later = _dsi_load(session, ids, [{"invoice_no": "N112-4", "quantity_sold": 9}], 2)
    out = _delete(session, test)
    assert out["data"]["per_job"][test]["fact_sales_sellout_kept_later"] == 1
    assert _sellout(session, ids, "N112-4") == (9.0, later)
    assert _dsi_records(session, ids) == [("fact_sales_sellout", real, later, 5.0)]
    _delete(session, later)
    assert _sellout(session, ids, "N112-4") == (5.0, real)


def test_a_return_reload_deleted_brings_back_the_earlier_quantity(session: Session) -> None:
    ids = _ids(session)
    real = _dsi_load(session, ids, [{"invoice_no": "N112-CR5", "quantity_sold": -2, "unit_sellout_price_ex_tax_amount": 10}])
    test = _dsi_load(session, ids, [{"invoice_no": "N112-CR5", "quantity_sold": -3, "unit_sellout_price_ex_tax_amount": 10}], 1)
    _delete(session, test)
    assert _line(session, ids, "fact_returns", "return_quantity", "import_job_id", "N112-CR5") == (2.0, real)


def test_distributor_stock_comes_back_from_the_earlier_load(session: Session) -> None:
    ids = _ids(session)
    snap = {"snapshot_date": DAY, "invoice_no": None}
    real = _dsi_load(session, ids, [{**snap, "stock_on_hand": 10}])
    test = _dsi_load(session, ids, [{**snap, "stock_on_hand": 4}], 1)

    def soh():
        r = session.execute(text("select on_hand_units::float, source_import_job_id from fact_inventory_distributor "
                                 "where distributor_id = :d and product_id = :p and as_of_date = :t"),
                            {"d": ids["distributor"], "p": ids["product"], "t": DAY}).first()
        return tuple(r) if r else None

    assert soh() == (4.0, test)
    _delete(session, test)
    assert soh() == (10.0, real)
    _delete(session, real)
    assert soh() is None


# ---------------------------------------------------------------------------------- the delete itself
def test_aliases_are_kept_by_default_and_the_delete_is_audited(session: Session) -> None:
    ids = _ids(session)
    test = _dsi_load(session, ids, [{"invoice_no": "N112-6", "quantity_sold": 1}])
    alias = CustomerSourceTokenAlias(customer_id=ids["customer"], raw_token=f"n0112-{test}",
                                     normalized_token=f"n0112-{test}", created_from_import_job_id=test)
    session.add(alias)
    session.flush()
    out = _delete(session, test)
    assert out["deleted"]["customer_source_token_aliases_kept"] == 1
    kept = session.get(CustomerSourceTokenAlias, alias.id)
    assert kept is not None and kept.created_from_import_job_id is None
    event = session.execute(text(
        "select action, detail_json from platform_audit_event where target_type = 'import_job' and target_id = :t "
        "order by id desc limit 1"), {"t": str(test)}).first()
    assert event is not None and event[0] == "import_jobs_delete"
    assert event[1]["counts"]["fact_sales_sellout_rows_removed"] == 1
    assert session.get(ImportJob, test) is None


def _last_audit(db: Session, job: int) -> dict:
    return db.scalar(text(
        "select detail_json from platform_audit_event where action = 'import_jobs_delete' and target_id = :t "
        "order by id desc limit 1"), {"t": str(job)})


def test_the_audit_event_keeps_every_removed_superseded_record_in_full(session: Session) -> None:
    ids = _ids(session)
    real = _st_load(session, ids, 0, units="12", soh="40")
    test = _st_load(session, ids, 1, units="15", soh="35")
    kept = session.execute(text(
        "select id, fact_id, source_key, import_job_id, superseded_by_import_job_id, figures, row_json "
        "from fact_customer_sellthrough_superseded where superseded_by_import_job_id = :j"), {"j": test}).mappings().one()
    _delete(session, test)
    (rec,) = _last_audit(session, test)["superseded_records_removed"]
    assert rec["table"] == "fact_customer_sellthrough_superseded"
    assert rec["id"] == kept["id"] and rec["fact_id"] == kept["fact_id"] and rec["source_key"] == kept["source_key"]
    assert (rec["import_job_id"], rec["superseded_by_import_job_id"]) == (real, test)
    assert rec["figures"] == ["units_sold", "reported_soh"]
    assert float(rec["row_json"]["units_sold"]) == 12.0 and float(rec["row_json"]["reported_soh"]) == 40.0

    dsi_real = _dsi_load(session, ids, [{"invoice_no": "N112-7", "quantity_sold": 5, "reported_revenue_amount": 50}])
    dsi_test = _dsi_load(session, ids, [{"invoice_no": "N112-7", "quantity_sold": 8, "reported_revenue_amount": 80}], 1)
    _delete(session, dsi_test)
    (rec,) = _last_audit(session, dsi_test)["superseded_records_removed"]
    assert rec["table"] == "fact_distributor_line_superseded" and rec["fact_table"] == "fact_sales_sellout"
    assert (rec["previous_import_job_id"], rec["superseded_by_import_job_id"]) == (dsi_real, dsi_test)
    assert rec["figures"]["units"] == {"old": 5.0, "new": 8.0}
    assert rec["invoice_no"] == "N112-7" and float(rec["row_json"]["units"]) == 5.0


def test_the_preview_shows_what_the_delete_does_and_changes_nothing(session: Session) -> None:
    ids = _ids(session)
    real = _st_load(session, ids, 0, units="12", soh="40")
    test = _st_load(session, ids, 1, units="15", soh="35")
    preview = preview_import_job_bulk_delete(session, [test, 999_999_999])
    assert preview["missing_job_ids"] == [999_999_999]
    (job,) = preview["jobs"]
    assert job["id"] == test and job["counts"]["sellthrough_figures_restored"] == 2
    assert job["counts"]["cst_staging_rows"] == 1
    assert session.get(ImportJob, test) is not None
    assert _st_rows(session)[0][:3] == ("S1", 15.0, 35.0)
    out = _delete(session, test)
    assert out["data"]["per_job"][test]["sellthrough_figures_restored"] == 2
    assert _st_rows(session)[0][3] == {"units_sold": real, "reported_soh": real}
