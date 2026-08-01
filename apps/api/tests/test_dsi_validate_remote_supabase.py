"""Opt-in Supabase E2E for DSI validate bulk staging (BACKLOG-030 Phase 1).

Set ``CIP_DSI_SUPABASE_E2E=1`` to run against ``DATABASE_URL_SYNC`` (remote pooler).
Verifies ``SELECT current_database()`` and records wall time for chunked validate.
"""

from __future__ import annotations

import os
import time

import pytest
from sqlalchemy import func, select, text

from app.core.config import get_settings
from app.db.session_sync import SessionLocal
from app.ingestion.pipeline import process_import_job_sync
from app.models.dimensions import DimCustomer, DimDistributor, DimProduct
from app.models.import_distributor_si import ImportDistributorSiStagingLine
from app.models.ingestion import ImportJob, RawFileMetadata, SourceDefinition
from app.services.commercial_planner.reference_bootstrap import (
    ensure_commercial_planner_system_reference_data_sync,
)
from app.services.imports.distributor_sales_inventory import _DSI_STAGING_INSERT_CHUNK
from app.services.seed_demo import _seed_import_core
from app.storage.local import get_storage_backend

pytestmark = pytest.mark.skipif(
    os.environ.get("CIP_DSI_SUPABASE_E2E", "").strip() != "1",
    reason="Set CIP_DSI_SUPABASE_E2E=1 to run remote Supabase DSI validate E2E",
)


def _sqlalchemy_db_name(url: str) -> str:
    if not url or "://" not in url:
        return ""
    rest = url.split("://", 1)[1]
    if "/" not in rest:
        return ""
    return rest.rsplit("/", 1)[-1].split("?", 1)[0].strip()


@pytest.fixture(scope="module")
def supabase_db_name() -> str:
    settings = get_settings()
    name = _sqlalchemy_db_name(settings.database_url_sync)
    if not name:
        pytest.skip("DATABASE_URL_SYNC has no database name")
    return name


def test_supabase_dsi_validate_bulk_staging_e2e(supabase_db_name: str) -> None:
    """≥2 staging chunks against remote Supabase; checkpoint metadata + row counts."""
    row_count = _DSI_STAGING_INSERT_CHUNK + 100
    with SessionLocal() as db:
        db_name = db.scalar(text("SELECT current_database()"))
        assert db_name == supabase_db_name, f"Expected {supabase_db_name!r}, got {db_name!r}"
        print(f"E2E target database: {db_name}")

        from sqlalchemy import inspect

        if "import_distributor_si_staging_line" not in set(inspect(db.connection()).get_table_names()):
            pytest.skip("DSI staging table missing on target database")

        _seed_import_core(db)
        ensure_commercial_planner_system_reference_data_sync(db.connection())

        if not db.scalar(select(DimDistributor).where(DimDistributor.code == "DIST-01")):
            db.add(DimDistributor(code="DIST-01", name="Summit Supply Co."))
        if not db.scalar(select(DimCustomer).where(DimCustomer.code == "CUST-1001")):
            from app.models.dimensions import DimChannel, DimRegion

            r1 = db.scalar(select(DimRegion).limit(1))
            ch = db.scalar(select(DimChannel).limit(1))
            db.add(
                DimCustomer(
                    code="CUST-1001",
                    name="Metro Market E2E",
                    region_id=r1.id if r1 else None,
                    channel_id=ch.id if ch else None,
                )
            )
        if not db.scalar(select(DimProduct).where(DimProduct.sku == "SKU-ALPHA-01")):
            ch = db.scalar(select(DimChannel).limit(1))
            db.add(
                DimProduct(
                    sku="SKU-ALPHA-01",
                    name="Alpha Pro E2E",
                    category="Audio",
                )
            )
        db.commit()

        sid = db.scalar(
            select(SourceDefinition.id).where(SourceDefinition.code == "distributor_inventory")
        )
        assert sid is not None

        header = "distributor_code,sku,date,qty,customer_name,soh\n"
        body = "".join(
            f"DIST-01,SKU-ALPHA-01,2024-06-{1 + (i % 28):02d},1,CUST-1001,{i % 10}\n"
            for i in range(row_count)
        )
        csv_bytes = (header + body).encode("utf-8")

        job = ImportJob(
            source_id=int(sid),
            template_slug="distributor_inventory",
            file_name="supabase_e2e_bulk.csv",
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
        storage = get_storage_backend()
        key = storage.save(f"imports/test/{jid}/supabase_e2e_bulk.csv", csv_bytes)
        db.add(RawFileMetadata(job_id=jid, storage_key=key, byte_size=len(csv_bytes)))
        db.commit()

    t0 = time.monotonic()
    with SessionLocal() as db:
        result = process_import_job_sync(db, jid)
    elapsed_s = time.monotonic() - t0
    print(f"Supabase E2E validate: {row_count} rows in {elapsed_s:.1f}s ({row_count / elapsed_s:.1f} rows/s)")

    assert result.stage == "validated", f"job failed: {result.error_summary}"
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
        assert meta.get("dsi_validate_phase") in ("building_candidates", "processing_rows")

        db.execute(text("DELETE FROM import_entity_mapping_candidate WHERE import_job_id = :jid"), {"jid": jid})
        db.execute(text("DELETE FROM import_distributor_si_staging_line WHERE import_job_id = :jid"), {"jid": jid})
        db.execute(text("DELETE FROM import_row_result WHERE job_id = :jid"), {"jid": jid})
        db.execute(text("DELETE FROM raw_file_metadata WHERE job_id = :jid"), {"jid": jid})
        db.execute(text("DELETE FROM import_job WHERE id = :jid"), {"jid": jid})
        db.commit()
