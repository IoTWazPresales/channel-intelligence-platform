"""A customer the steward ignored stays ignored when the job is revalidated (N-0111, job 1670).

Found on Pinnacle: 19 "<NAME> - STAFF" accounts were ignored, the tabs showed nothing to do, yet the
revalidation counted their 22 rows as "still need steward mapping" because the ignore lived on the
candidate only and the rebuilt rows blocked again.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import func, select

from app.db.session_sync import SessionLocal
from app.ingestion.pipeline import process_import_job_sync
from app.models.import_distributor_si import ImportDistributorSiStagingLine, ImportEntityMappingCandidate
from app.models.ingestion import ImportJob, ImportRowResult
from app.services.imports.dsi_product_running_change import (
    IGNORE_REASON_CUSTOMER_EXCLUDED,
    IGNORE_REASON_NO_CUSTOMER,
    infer_dsi_customer_ignore_reason_code,
    load_steward_ignored_customer_keys,
    parse_steward_ignored_line_reason,
)
from tests.test_distributor_sales_inventory_import import _csv_bytes, _run_dsi_job, _seed_dsi_catalog

CSV = (
    "distributor_code,sku,date,qty,customer_name\n"
    "DIST-01,SKU-ALPHA-01,2024-04-01,1,Jane Doe - STAFF\n"
    "DIST-01,SKU-ALPHA-01,2024-04-02,2,Jane Doe - STAFF\n"
    "DIST-01,SKU-ALPHA-01,2024-04-03,1,John Roe - STAFF\n"
)


@pytest.fixture(scope="module")
def dsi_source_id() -> int:
    return _seed_dsi_catalog()


def _summary(job_id: int) -> dict:
    with SessionLocal() as db:
        msgs = db.scalars(
            select(ImportRowResult.message)
            .where(ImportRowResult.job_id == job_id, ImportRowResult.code == "distributor_si_summary")
            .order_by(ImportRowResult.id.desc())
        ).all()
        return json.loads(msgs[0].split("}", 1)[0] + "}")


def _lines(job_id: int) -> list[ImportDistributorSiStagingLine]:
    with SessionLocal() as db:
        return list(
            db.scalars(
                select(ImportDistributorSiStagingLine)
                .where(ImportDistributorSiStagingLine.import_job_id == job_id)
                .order_by(ImportDistributorSiStagingLine.source_row_number)
            ).all()
        )


def test_reason_codes_for_customer_ignore() -> None:
    assert infer_dsi_customer_ignore_reason_code("__blank__") == IGNORE_REASON_NO_CUSTOMER
    assert infer_dsi_customer_ignore_reason_code("jane doe - staff") == IGNORE_REASON_CUSTOMER_EXCLUDED
    assert infer_dsi_customer_ignore_reason_code("") is None


def test_ignored_customer_stays_excluded_after_revalidate(dsi_source_id: int) -> None:
    job = _run_dsi_job(dsi_source_id, _csv_bytes(CSV), import_mode="validate", filename="dsi_staff_ignore.csv")
    job_id = job.id

    # First validation: nobody has decided yet, so the staff rows block and the candidates are open.
    assert _summary(job_id)["blocking_rows"] == 3
    assert {ln.severity for ln in _lines(job_id)} == {"error"}

    # The steward ignores Jane Doe (status only, as the bulk ignore did on job 1670: no reason code stored).
    with SessionLocal() as db:
        cands = db.scalars(
            select(ImportEntityMappingCandidate).where(
                ImportEntityMappingCandidate.import_job_id == job_id,
                ImportEntityMappingCandidate.entity_type == "customer_dealer_token",
            )
        ).all()
        by_key = {c.normalized_key: c for c in cands}
        assert "jane doe - staff" in by_key and "john roe - staff" in by_key
        by_key["jane doe - staff"].status = "ignored"
        db.commit()
        assert load_steward_ignored_customer_keys(db, job_id) == frozenset({"jane doe - staff"})

    # Revalidate: Jane Doe's two rows are excluded (not blocking); John Roe's row still needs the steward.
    with SessionLocal() as db:
        process_import_job_sync(db, job_id)
    summary = _summary(job_id)
    assert summary["blocking_rows"] == 1
    assert summary["steward_map_blocking_rows"] == 1
    assert summary["auto_excluded_rows"] == 2
    by_status = {}
    for ln in _lines(job_id):
        by_status.setdefault(ln.resolution_status, []).append(ln)
    assert len(by_status["staged_only"]) == 2
    assert len(by_status["blocked"]) == 1
    for ln in by_status["staged_only"]:
        assert ln.severity == "info"
        assert parse_steward_ignored_line_reason(ln.diagnostic_codes) == IGNORE_REASON_CUSTOMER_EXCLUDED
    assert by_status["blocked"][0].raw_customer_dealer_token == "John Roe - STAFF"

    # The candidate stays ignored and now carries the reason, so a later re-apply knows it too.
    with SessionLocal() as db:
        cand = db.scalar(
            select(ImportEntityMappingCandidate).where(
                ImportEntityMappingCandidate.import_job_id == job_id,
                ImportEntityMappingCandidate.normalized_key == "jane doe - staff",
            )
        )
        assert cand is not None and cand.status == "ignored"
        assert (cand.context or {}).get("steward_ignore_reason_code") == IGNORE_REASON_CUSTOMER_EXCLUDED

    # Revalidating again changes nothing.
    with SessionLocal() as db:
        process_import_job_sync(db, job_id)
    again = _summary(job_id)
    assert (again["blocking_rows"], again["auto_excluded_rows"]) == (1, 2)


def test_refresh_keeps_ignored_customer_excluded(dsi_source_id: int) -> None:
    from app.services.imports.distributor_sales_inventory import refresh_dsi_staging_lines_for_job

    job = _run_dsi_job(dsi_source_id, _csv_bytes(CSV), import_mode="validate", filename="dsi_staff_refresh.csv")
    job_id = job.id
    with SessionLocal() as db:
        cand = db.scalar(
            select(ImportEntityMappingCandidate).where(
                ImportEntityMappingCandidate.import_job_id == job_id,
                ImportEntityMappingCandidate.normalized_key == "john roe - staff",
            )
        )
        assert cand is not None
        cand.status = "ignored"
        db.commit()
        j = db.get(ImportJob, job_id)
        refresh_dsi_staging_lines_for_job(db, j)
        db.commit()
    statuses = {ln.raw_dealer_group_token or ln.raw_customer_dealer_token: ln.resolution_status for ln in _lines(job_id)}
    assert statuses["John Roe - STAFF"] == "staged_only"
    assert statuses["Jane Doe - STAFF"] == "blocked"


def test_refresh_loads_shipment_evidence_and_ignored_customers_once(dsi_source_id: int) -> None:
    """Apply re-checks every staged row; per-row shipment-evidence counts made a 36k-line apply run for hours."""
    from sqlalchemy import event

    from app.services.imports.distributor_sales_inventory import refresh_dsi_staging_lines_for_job

    rows = "".join(f"DIST-01,SKU-ALPHA-01,2024-05-{d:02d},1,Jane Doe - STAFF\n" for d in range(1, 21))
    csv = "distributor_code,sku,date,qty,customer_name\n" + rows
    job = _run_dsi_job(dsi_source_id, _csv_bytes(csv), import_mode="validate", filename="dsi_refresh_once.csv")
    job_id = job.id

    def snapshot() -> list[tuple[int, str, str, tuple]]:
        return [
            (ln.source_row_number, ln.severity, ln.resolution_status, tuple(ln.diagnostic_codes or []))
            for ln in _lines(job_id)
        ]

    before = snapshot()
    assert len(before) == 20

    statements: list[str] = []
    with SessionLocal() as db:
        engine = db.get_bind()

        def _capture(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
            statements.append(statement)

        event.listen(engine, "before_cursor_execute", _capture)
        try:
            j = db.get(ImportJob, job_id)
            refresh_dsi_staging_lines_for_job(db, j)
            db.commit()
        finally:
            event.remove(engine, "before_cursor_execute", _capture)

    evidence = [s for s in statements if "shipment_evidence" in s]
    ignored = [s for s in statements if "import_entity_mapping_candidate" in s and "normalized_key" in s]
    # One bulk load each, not one per staged row (20 rows here, 36,275 on the real file).
    assert len(evidence) <= 4, len(evidence)
    assert len(ignored) <= 2, len(ignored)
    assert snapshot() == before


def _refresh_statement_counts(db, job_id: int, *, with_context: bool) -> dict[str, int]:
    from sqlalchemy import event

    from app.services.imports.distributor_sales_inventory import (
        _load_product_resolution_index,
        build_refresh_context,
        refresh_dsi_staging_line_resolution,
    )

    job = db.get(ImportJob, job_id)
    lines = list(
        db.scalars(
            select(ImportDistributorSiStagingLine)
            .where(ImportDistributorSiStagingLine.import_job_id == job_id)
            .order_by(ImportDistributorSiStagingLine.source_row_number)
        ).all()
    )
    statements: list[str] = []
    engine = db.get_bind()

    def _capture(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        statements.append(statement)

    prod_idx = _load_product_resolution_index(db)
    event.listen(engine, "before_cursor_execute", _capture)
    try:
        ctx = build_refresh_context(db, job, lines) if with_context else {}
        for ln in lines:
            refresh_dsi_staging_line_resolution(db, job, ln, prod_idx, **ctx)
        db.commit()
    finally:
        event.remove(engine, "before_cursor_execute", _capture)
    return {
        "shipment_evidence": sum("shipment_evidence" in s for s in statements),
        "customer_alias": sum("customer_source_token_alias" in s for s in statements),
        "dim_distributor": sum("FROM dim_distributor" in s for s in statements),
        "dim_customer": sum("FROM dim_customer" in s for s in statements),
    }


def test_refresh_pass_gives_same_results_with_far_fewer_queries(dsi_source_id: int) -> None:
    """Shared lookups (evidence cache, distributor/product/customer memo) change cost, never results."""
    rows = "".join(
        f"DIST-01,SKU-ALPHA-01,2024-06-{d:02d},1,{'Jane Doe - STAFF' if d % 2 else 'Metro Market Group'}\n"
        for d in range(1, 25)
    )
    csv = "distributor_code,sku,date,qty,customer_name\n" + rows
    job = _run_dsi_job(dsi_source_id, _csv_bytes(csv), import_mode="validate", filename="dsi_refresh_memo.csv")
    job_id = job.id

    def snapshot():
        return [
            (
                ln.source_row_number,
                ln.severity,
                ln.resolution_status,
                ln.resolved_distributor_id,
                ln.resolved_product_id,
                ln.resolved_customer_id,
                tuple(ln.diagnostic_codes or []),
            )
            for ln in _lines(job_id)
        ]

    with SessionLocal() as db:
        per_row = _refresh_statement_counts(db, job_id, with_context=False)
    per_row_result = snapshot()
    with SessionLocal() as db:
        shared = _refresh_statement_counts(db, job_id, with_context=True)
    shared_result = snapshot()

    assert shared_result == per_row_result
    assert len(shared_result) == 24
    # Per-row path: queries grow with the row count. Shared path: bounded by distinct tokens, not rows.
    assert per_row["shipment_evidence"] >= 24
    assert shared["shipment_evidence"] <= 4
    assert shared["dim_distributor"] <= 3
    assert shared["customer_alias"] <= per_row["customer_alias"] // 4 + 2
    assert shared["dim_customer"] <= per_row["dim_customer"] // 4 + 2


def test_apply_reports_real_counts_for_refresh_and_fact_write(dsi_source_id: int) -> None:
    from app.services.imports.dsi_apply_completion import complete_dsi_import_job_to_loaded

    rows = "".join(f"DIST-01,SKU-ALPHA-01,2024-07-{d:02d},2,Metro Market Group\n" for d in range(1, 13))
    csv = "distributor_code,sku,date,qty,customer_name\n" + rows
    job = _run_dsi_job(dsi_source_id, _csv_bytes(csv), import_mode="validate", filename="dsi_apply_progress.csv")
    job_id = job.id
    calls: list[tuple[str, str, int, int]] = []
    with SessionLocal() as db:
        j = db.get(ImportJob, job_id)
        j.import_mode = "apply"
        db.commit()
        complete_dsi_import_job_to_loaded(db, job_id, on_progress=lambda *a: calls.append(a))

    phases = {c[0] for c in calls}
    assert {"refreshing_lines", "writing_facts"} <= phases
    for phase in ("refreshing_lines", "writing_facts"):
        last = [c for c in calls if c[0] == phase][-1]
        assert (last[2], last[3]) == (12, 12), last  # real counts, not 0 / 0
    from app.models.facts import FactSalesSellout

    with SessionLocal() as db:
        n = db.scalar(select(func.count()).select_from(FactSalesSellout).where(FactSalesSellout.source_import_job_id == job_id))
        assert int(n or 0) == 12



def test_refresh_resolves_aliases_stored_under_the_canonical_key(dsi_source_id: int) -> None:
    """Job 1670: validate resolved 'WOOTWARE COMPUTERS (PTY) LTD' through the alias 'wootware computers pty ltd',
    the apply's re-check did not, and 3,638 lines came back blocked. Refresh must agree with validate."""
    from app.models.dimensions import DimCustomer
    from app.models.import_distributor_si import CustomerSourceTokenAlias
    from app.services.imports.distributor_sales_inventory import refresh_dsi_staging_lines_for_job

    with SessionLocal() as db:
        cust = db.scalars(select(DimCustomer).where(DimCustomer.code == "CUST-1001")).first()
        assert cust is not None
        cust_id = cust.id
        if not db.scalar(
            select(CustomerSourceTokenAlias.id).where(CustomerSourceTokenAlias.normalized_token == "acme widgets pty ltd")
        ):
            db.add(
                CustomerSourceTokenAlias(
                    customer_id=cust_id,
                    source_definition_id=dsi_source_id,
                    distributor_id=None,
                    raw_token="ACME WIDGETS PTY LTD",
                    normalized_token="acme widgets pty ltd",
                    status="approved",
                )
            )
            db.commit()

    csv = (
        "distributor_code,sku,date,qty,customer_name\n"
        "DIST-01,SKU-ALPHA-01,2024-08-01,3,ACME WIDGETS (PTY) LTD\n"
        "DIST-01,SKU-ALPHA-01,2024-08-02,-1,ACME WIDGETS (PTY) LTD\n"
    )
    job = _run_dsi_job(dsi_source_id, _csv_bytes(csv), import_mode="validate", filename="dsi_alias_canonical.csv")
    job_id = job.id
    before = [(ln.source_row_number, ln.resolved_customer_id, ln.resolution_status, ln.severity) for ln in _lines(job_id)]
    assert [b[1] for b in before] == [cust_id, cust_id]  # validate resolves it

    with SessionLocal() as db:
        refresh_dsi_staging_lines_for_job(db, db.get(ImportJob, job_id))
        db.commit()
    after = [(ln.source_row_number, ln.resolved_customer_id, ln.resolution_status, ln.severity) for ln in _lines(job_id)]
    assert after == before  # the re-check agrees with validate


def test_refresh_agrees_with_validate_on_alias_spellings(dsi_source_id: int) -> None:
    """Spellings seen on job 1670 ('( PTY)', '(PTY)LTD', double spaces) resolve the same in validate and in the
    apply's re-check, on both the shared-cache path (whole job) and the single-line database path."""
    from app.models.dimensions import DimCustomer
    from app.models.import_distributor_si import CustomerSourceTokenAlias
    from app.services.imports.distributor_sales_inventory import (
        _load_product_resolution_index,
        refresh_dsi_staging_line_resolution,
        refresh_dsi_staging_lines_for_job,
    )

    with SessionLocal() as db:
        cust = db.scalars(select(DimCustomer).where(DimCustomer.code == "CUST-1001")).first()
        assert cust is not None
        cust_id = cust.id
        for stored in ("frontosa tech pty ltd", "novicus dist (pty) ltd"):
            if not db.scalar(select(CustomerSourceTokenAlias.id).where(CustomerSourceTokenAlias.normalized_token == stored)):
                db.add(
                    CustomerSourceTokenAlias(
                        customer_id=cust_id,
                        source_definition_id=dsi_source_id,
                        distributor_id=None,
                        raw_token=stored.upper(),
                        normalized_token=stored,
                        status="approved",
                    )
                )
        db.commit()

    csv = (
        "distributor_code,sku,date,qty,customer_name\n"
        "DIST-01,SKU-ALPHA-01,2024-09-01,1,FRONTOSA TECH ( PTY) LTD\n"
        "DIST-01,SKU-ALPHA-01,2024-09-02,1,NOVICUS  DIST (PTY)LTD\n"
        "DIST-01,SKU-ALPHA-01,2024-09-03,1,Nobody Known Ltd\n"
    )
    job = _run_dsi_job(dsi_source_id, _csv_bytes(csv), import_mode="validate", filename="dsi_alias_spellings.csv")
    job_id = job.id

    def view():
        return [(ln.source_row_number, ln.resolved_customer_id, ln.resolution_status) for ln in _lines(job_id)]

    validated = view()
    assert [v[1] for v in validated] == [cust_id, cust_id, None]  # validate resolves the two, not the third

    with SessionLocal() as db:  # whole-job pass (shared resolution cache)
        refresh_dsi_staging_lines_for_job(db, db.get(ImportJob, job_id))
        db.commit()
    assert view() == validated

    with SessionLocal() as db:  # single-line path (database lookups)
        j = db.get(ImportJob, job_id)
        prod_idx = _load_product_resolution_index(db)
        for ln in db.scalars(
            select(ImportDistributorSiStagingLine)
            .where(ImportDistributorSiStagingLine.import_job_id == job_id)
            .order_by(ImportDistributorSiStagingLine.source_row_number)
        ).all():
            refresh_dsi_staging_line_resolution(db, j, ln, prod_idx)
        db.commit()
    assert view() == validated
