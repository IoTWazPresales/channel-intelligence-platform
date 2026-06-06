"""DSI validate bulk staging + cache-backed AI candidates (BACKLOG-030)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text

from app.db.session_sync import SessionLocal
from app.models.dimensions import DimCustomer, DimDistributor
from app.models.import_distributor_si import ImportDistributorSiStagingLine
from app.models.ingestion import ImportJob, ImportTemplate, RawFileMetadata, SourceDefinition
from app.services.imports.ai_resolver_wiring import (
    customer_candidates,
    customer_candidates_from_cache,
    distributor_candidates_from_cache,
)
from app.services.imports.distributor_sales_inventory import (
    DSIResolutionCache,
    _DSI_STAGING_INSERT_CHUNK,
    _DSI_VALIDATE_COMMIT_INTERVAL,
    _build_resolution_cache,
    _flush_dsi_staging_batch,
    _persist_dsi_validate_checkpoint,
    _staging_line_row_dict,
)
from app.services.seed_demo import _seed_import_core
from app.storage.local import get_storage_backend
from app.ingestion.pipeline import process_import_job_sync


def _ensure_dsi_tables(db) -> None:
    from sqlalchemy import inspect

    names = set(inspect(db.connection()).get_table_names())
    if "import_distributor_si_staging_line" not in names:
        pytest.skip("DSI tables missing — apply Alembic head.")


def test_dsi_validate_commit_interval_larger_than_insert_chunk() -> None:
    assert _DSI_VALIDATE_COMMIT_INTERVAL >= _DSI_STAGING_INSERT_CHUNK


def test_staging_line_row_dict_shape() -> None:
    row = _staging_line_row_dict(
        job_id=1,
        source_row_number=42,
        raw_payload={"a": 1},
        mapped={"distributor_token": "D1"},
        dist_raw="D1",
        cust_raw=None,
        dg_raw=None,
        prod_raw="SKU",
        rdistributor_id=10,
        rcustomer_id=None,
        rpid=20,
        tx_date=date(2024, 1, 1),
        invoice_no_val=None,
        snap_date=date(2024, 1, 1),
        qty_sold=Decimal("1"),
        soh=Decimal("5"),
        unit_price=Decimal("9.99"),
        reported_rev=None,
        computed_rev=Decimal("9.99"),
        cur="USD",
        res_status="ready_both",
        diag=["ok"],
        sev="info",
    )
    assert row["import_job_id"] == 1
    assert row["source_row_number"] == 42
    assert row["apply_status"] == "pending"
    assert row["quantity_sold"] == 1.0


def test_flush_dsi_staging_batch_real_db() -> None:
    with SessionLocal() as db:
        _ensure_dsi_tables(db)
        _seed_import_core(db)
        tpl = db.scalar(select(ImportTemplate).where(ImportTemplate.slug == "distributor_inventory"))
        assert tpl is not None
        src = db.scalar(select(SourceDefinition).where(SourceDefinition.import_template_id == tpl.id))
        assert src is not None
        job = ImportJob(
            source_id=src.id,
            template_slug="distributor_inventory",
            file_name="bulk_staging_test.csv",
            import_mode="validate",
            status="running",
            stage="mapped",
        )
        db.add(job)
        db.flush()
        jid = int(job.id)
        rows = [
            _staging_line_row_dict(
                job_id=jid,
                source_row_number=i,
                raw_payload={"row": i},
                mapped={},
                dist_raw="DIST",
                cust_raw=None,
                dg_raw=None,
                prod_raw="SKU",
                rdistributor_id=None,
                rcustomer_id=None,
                rpid=None,
                tx_date=None,
                invoice_no_val=None,
                snap_date=None,
                qty_sold=None,
                soh=Decimal("1"),
                unit_price=None,
                reported_rev=None,
                computed_rev=None,
                cur=None,
                res_status="staged_only",
                diag=[],
                sev="info",
            )
            for i in range(1, 4)
        ]
        _flush_dsi_staging_batch(db, rows)
        db.commit()
        count = db.scalar(
            select(func.count())
            .select_from(ImportDistributorSiStagingLine)
            .where(ImportDistributorSiStagingLine.import_job_id == jid)
        )
        assert count == 3
        db.execute(
            text("DELETE FROM import_distributor_si_staging_line WHERE import_job_id = :jid"),
            {"jid": jid},
        )
        db.execute(text("DELETE FROM import_job WHERE id = :jid"), {"jid": jid})
        db.commit()


def test_persist_dsi_validate_checkpoint_real_db() -> None:
    with SessionLocal() as db:
        _ensure_dsi_tables(db)
        _seed_import_core(db)
        tpl = db.scalar(select(ImportTemplate).where(ImportTemplate.slug == "distributor_inventory"))
        src = db.scalar(select(SourceDefinition).where(SourceDefinition.import_template_id == tpl.id))
        job = ImportJob(
            source_id=src.id,
            template_slug="distributor_inventory",
            file_name="checkpoint_test.csv",
            import_mode="validate",
            status="running",
            stage="mapped",
            staged_metadata={"dsi_validate_total_rows": 5000},
        )
        db.add(job)
        db.flush()
        jid = int(job.id)
        _persist_dsi_validate_checkpoint(db, job, rows_committed=1000, phase="processing_rows")
        db.refresh(job)
        meta = job.staged_metadata or {}
        assert meta.get("dsi_validate_rows_committed") == 1000
        assert meta.get("dsi_validate_phase") == "processing_rows"
        assert meta.get("dsi_validate_checkpoint_at")
        db.execute(text("DELETE FROM import_job WHERE id = :jid"), {"jid": jid})
        db.commit()


def test_customer_candidates_from_cache_matches_db_filtering() -> None:
    with SessionLocal() as db:
        _ensure_dsi_tables(db)
        res_cache = _build_resolution_cache(db, None)
        token = "metro"
        from_db = customer_candidates(db, token, limit=20)
        from_cache = customer_candidates_from_cache(res_cache, token, limit=20)
        assert {c["id"] for c in from_cache} == {c["id"] for c in from_db}


def test_distributor_candidates_from_cache_no_db_query(monkeypatch) -> None:
    cache = DSIResolutionCache(
        all_distributors=[
            type("D", (), {"id": 1, "code": "DIST-01", "name": "Summit Supply"})(),
        ],
        dist_aliases=[],
        all_customers=[],
        customer_code_to_id={},
        customer_name_to_ids={},
        cust_aliases=[],
        open_channel_cid=None,
    )

    def _fail_query(*_a, **_k):
        raise AssertionError("distributor_candidates_from_cache must not query DB")

    monkeypatch.setattr(
        "app.services.imports.ai_resolver_wiring.select",
        _fail_query,
    )
    out = distributor_candidates_from_cache(cache, "summit", limit=5)
    assert len(out) == 1
    assert out[0]["id"] == 1


def test_dsi_validate_bulk_staging_checkpoint_on_process(dsi_source_id: int) -> None:
    """Multi-row validate persists checkpoint metadata and uses chunked staging."""
    row_count = _DSI_STAGING_INSERT_CHUNK + 50
    header = "distributor_code,sku,date,qty,customer_name,soh\n"
    body = "".join(
        f"DIST-01,SKU-ALPHA-01,2024-07-{1 + (i % 28):02d},1,CUST-1001,{i % 10}\n"
        for i in range(row_count)
    )
    csv_bytes = (header + body).encode("utf-8")
    storage = get_storage_backend()
    with SessionLocal() as db:
        from app.services.commercial_planner.reference_bootstrap import (
            ensure_commercial_planner_system_reference_data_sync,
        )
        from sqlalchemy import inspect

        _ensure_dsi_tables(db)
        ensure_commercial_planner_system_reference_data_sync(db.connection())
        if not db.scalar(select(DimDistributor).where(DimDistributor.code == "DIST-01")):
            db.add(DimDistributor(code="DIST-01", name="Summit Supply Co."))
        if not db.scalar(select(DimCustomer).where(DimCustomer.code == "CUST-1001")):
            from app.models.dimensions import DimChannel, DimRegion

            r1 = db.scalar(select(DimRegion).where(DimRegion.code == "NA-W")) or DimRegion(
                code="NA-W", name="West"
            )
            if r1.id is None:
                db.add(r1)
                db.flush()
            ch = db.scalar(select(DimChannel).where(DimChannel.code == "RET")) or DimChannel(
                code="RET", name="Retail"
            )
            if ch.id is None:
                db.add(ch)
                db.flush()
            db.add(
                DimCustomer(
                    code="CUST-1001",
                    name="Metro Market Group",
                    region_id=r1.id,
                    channel_id=ch.id,
                )
            )
        from app.models.dimensions import DimProduct

        if not db.scalar(select(DimProduct).where(DimProduct.sku == "SKU-ALPHA-01")):
            ch = db.scalar(select(DimChannel).where(DimChannel.code == "RET"))
            db.add(
                DimProduct(
                    sku="SKU-ALPHA-01",
                    name="Alpha Pro 200",
                    category="Audio",
                    channel_id=ch.id if ch else None,
                )
            )
        db.commit()

        job = ImportJob(
            source_id=dsi_source_id,
            template_slug="distributor_inventory",
            file_name="bulk_checkpoint.csv",
            import_mode="validate",
            status="queued",
            stage="raw_stored",
            field_mapping={
                "distributor_code": "distributor_token",
                "sku": "product_identifier",
                "date": "transaction_date",
                "qty": "quantity_sold",
                "customer_name": "customer_dealer_token",
                "soh": "stock_on_hand",
            },
            staged_metadata={"dsi_workflow_mode_explicit": "historical"},
        )
        db.add(job)
        db.flush()
        jid = int(job.id)
        key = storage.save(f"imports/test/{jid}/bulk_checkpoint.csv", csv_bytes)
        db.add(RawFileMetadata(job_id=jid, storage_key=key, byte_size=len(csv_bytes)))
        db.commit()

    with SessionLocal() as db:
        job = process_import_job_sync(db, jid)
    assert job.stage == "validated"
    with SessionLocal() as db:
        staging_count = db.scalar(
            select(func.count())
            .select_from(ImportDistributorSiStagingLine)
            .where(ImportDistributorSiStagingLine.import_job_id == jid)
        )
        assert staging_count == row_count
        j = db.get(ImportJob, jid)
        meta = j.staged_metadata or {}
        assert meta.get("dsi_validate_rows_committed") == row_count
        db.execute(text("DELETE FROM import_entity_mapping_candidate WHERE import_job_id = :jid"), {"jid": jid})
        db.execute(text("DELETE FROM import_distributor_si_staging_line WHERE import_job_id = :jid"), {"jid": jid})
        db.execute(text("DELETE FROM import_row_result WHERE job_id = :jid"), {"jid": jid})
        db.execute(text("DELETE FROM raw_file_metadata WHERE job_id = :jid"), {"jid": jid})
        db.execute(text("DELETE FROM import_job WHERE id = :jid"), {"jid": jid})
        db.commit()


@pytest.fixture(scope="module")
def dsi_source_id() -> int:
    with SessionLocal() as db:
        _ensure_dsi_tables(db)
        _seed_import_core(db)
        sid = db.scalar(
            select(SourceDefinition.id).where(SourceDefinition.code == "distributor_inventory")
        )
        assert sid is not None
        return int(sid)
