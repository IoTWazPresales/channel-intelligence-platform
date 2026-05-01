"""Distributor sales & inventory import: staging, candidates, facts, double-apply guard (sync pipeline)."""

from __future__ import annotations

import pytest
from sqlalchemy import func, inspect, select

from app.db.session_sync import SessionLocal
from app.ingestion.pipeline import process_import_job_sync
from app.models.dimensions import DimChannel, DimCustomer, DimDistributor, DimProduct, DimRegion
from app.models.facts import FactInboundShipment, FactInventoryDistributor, FactSalesSellout
from app.models.import_distributor_si import (
    CustomerSourceTokenAlias,
    ImportDistributorSiStagingLine,
    ImportEntityMappingCandidate,
)
from app.models.ingestion import ImportJob, ImportRowResult, ImportTemplate, RawFileMetadata, SourceDefinition
from app.models.mapping import EntityMappingQueue
from app.services.commercial_planner.reference_bootstrap import ensure_commercial_planner_system_reference_data_sync
from app.services.seed_demo import _seed_import_core
from app.storage.local import get_storage_backend


def _dsi_source_id(db) -> int:
    sid = db.scalar(select(SourceDefinition.id).where(SourceDefinition.code == "distributor_inventory"))
    assert sid is not None
    return int(sid)


def _seed_dsi_catalog() -> int:
    """Import templates/sources + minimal dims for DSI tests. Returns distributor_inventory source_id."""
    with SessionLocal() as db:
        names = set(inspect(db.connection()).get_table_names())
        if "import_distributor_si_staging_line" not in names:
            pytest.skip(
                "Database missing DSI tables; apply Alembic revision 20260430_0024 (alembic upgrade head)."
            )
        _seed_import_core(db)
        ensure_commercial_planner_system_reference_data_sync(db.connection())

        r1 = db.scalar(select(DimRegion).where(DimRegion.code == "NA-W"))
        if not r1:
            r1 = DimRegion(code="NA-W", name="North America West")
            db.add(r1)
            db.flush()

        ch = db.scalar(select(DimChannel).where(DimChannel.code == "RET"))
        if not ch:
            ch = DimChannel(code="RET", name="Retail")
            db.add(ch)
            db.flush()

        if not db.scalar(select(DimDistributor).where(DimDistributor.code == "DIST-01")):
            db.add(DimDistributor(code="DIST-01", name="Summit Supply Co."))
        if not db.scalar(select(DimCustomer).where(DimCustomer.code == "CUST-1001")):
            db.add(
                DimCustomer(
                    code="CUST-1001",
                    name="Metro Market Group",
                    region_id=r1.id,
                    channel_id=ch.id,
                )
            )
        if not db.scalar(select(DimProduct).where(DimProduct.sku == "SKU-ALPHA-01")):
            db.add(
                DimProduct(
                    sku="SKU-ALPHA-01",
                    name="Alpha Pro 200",
                    category="Audio",
                    channel_id=ch.id,
                )
            )
        db.commit()
        return _dsi_source_id(db)


def _csv_bytes(content: str) -> bytes:
    return content.encode("utf-8")


def _run_dsi_job(source_id: int, csv_bytes: bytes, *, import_mode: str, filename: str = "dsi.csv") -> ImportJob:
    storage = get_storage_backend()
    with SessionLocal() as db:
        job = ImportJob(
            source_id=source_id,
            template_slug="distributor_inventory",
            import_mode=import_mode,
            status="pending",
            stage="uploaded",
            file_name=filename,
            content_type="text/csv",
        )
        db.add(job)
        db.flush()
        key = f"imports/test/{job.id}/{filename}"
        storage.save(key, csv_bytes, job.content_type)
        db.add(RawFileMetadata(job_id=job.id, storage_key=key, byte_size=len(csv_bytes), checksum=None))
        db.commit()
        return process_import_job_sync(db, job.id)


@pytest.fixture(scope="module")
def dsi_source_id() -> int:
    return _seed_dsi_catalog()


def test_distributor_si_template_pipeline_handler(dsi_source_id: int) -> None:
    with SessionLocal() as db:
        row = db.scalar(select(ImportTemplate).where(ImportTemplate.slug == "distributor_inventory"))
        assert row is not None
        assert row.pipeline_handler == "distributor_sales_inventory"
        assert row.display_name == "Distributor sales & inventory"


def test_distributor_si_validate_staging_candidates_no_queue_spam(dsi_source_id: int) -> None:
    csv = (
        "distributor_code,sku,date,qty,customer_name,soh\n"
        "DIST-01,SKU-ALPHA-01,2024-01-15,2,Mystery Dealer Zed,10\n"
        "DIST-01,SKU-ALPHA-01,2024-01-15,1,Mystery Dealer Zed,5\n"
    )
    job = _run_dsi_job(dsi_source_id, _csv_bytes(csv), import_mode="validate")
    job_id = job.id

    with SessionLocal() as db:
        cust_cands = db.scalars(
            select(ImportEntityMappingCandidate).where(
                ImportEntityMappingCandidate.import_job_id == job_id,
                ImportEntityMappingCandidate.entity_type == "customer_dealer_token",
            )
        ).all()
        assert len(cust_cands) == 1
        assert cust_cands[0].row_count == 2

        qn = db.scalar(select(func.count()).select_from(EntityMappingQueue).where(EntityMappingQueue.job_id == job_id))
        assert int(qn or 0) == 0

        lines = db.scalars(
            select(ImportDistributorSiStagingLine).where(ImportDistributorSiStagingLine.import_job_id == job_id)
        ).all()
        assert len(lines) == 2
        assert all(l.severity == "error" for l in lines)

        summary = db.scalars(
            select(ImportRowResult).where(
                ImportRowResult.job_id == job_id, ImportRowResult.code == "distributor_si_summary"
            )
        ).first()
        assert summary is not None
        assert "aggregated_candidates" in (summary.message or "")


def test_distributor_si_apply_sellout_and_inventory_and_double_apply(dsi_source_id: int) -> None:
    csv = (
        "distributor_code,sku,date,qty,customer_name,soh,channel,amount,revenue,currency\n"
        'DIST-01,SKU-ALPHA-01,2024-02-01,2,"",10,Open Channel retail,100,999,USD\n'
    )
    job = _run_dsi_job(dsi_source_id, _csv_bytes(csv), import_mode="apply", filename="dsi_apply.csv")
    job_id = job.id

    with SessionLocal() as db:
        fs = db.scalars(select(FactSalesSellout).where(FactSalesSellout.source_import_job_id == job_id)).all()
        assert len(fs) == 1
        assert fs[0].units == 2
        assert fs[0].unit_sellout_price_ex_tax_amount == 100
        assert fs[0].currency_code == "USD"
        assert fs[0].reported_revenue_amount == 999
        assert fs[0].computed_revenue_amount == 200

        inv = db.scalars(
            select(FactInventoryDistributor).where(FactInventoryDistributor.source_import_job_id == job_id)
        ).all()
        assert len(inv) == 1
        assert inv[0].on_hand_units == 10

        ship_n = db.scalar(select(func.count()).select_from(FactInboundShipment))
        assert int(ship_n or 0) >= 0

        j = db.get(ImportJob, job_id)
        assert j and (j.staged_metadata or {}).get("distributor_si", {}).get("applied") is True

    with SessionLocal() as db:
        process_import_job_sync(db, job_id)

    with SessionLocal() as db:
        double = db.scalars(
            select(ImportRowResult).where(
                ImportRowResult.job_id == job_id, ImportRowResult.code == "distributor_si_double_apply_blocked"
            )
        ).first()
        assert double is not None


def test_distributor_si_approved_alias_resolves_customer(dsi_source_id: int) -> None:
    with SessionLocal() as db:
        cust = db.scalars(select(DimCustomer).where(DimCustomer.code == "CUST-1001")).first()
        dist = db.scalars(select(DimDistributor).where(DimDistributor.code == "DIST-01")).first()
        assert cust and dist
        cust_id = cust.id
        db.add(
            CustomerSourceTokenAlias(
                customer_id=cust_id,
                source_definition_id=dsi_source_id,
                distributor_id=dist.id,
                raw_token="Alias Dealer Token",
                normalized_token="alias dealer token",
                status="approved",
            )
        )
        db.commit()

    csv = (
        "distributor_code,sku,date,qty,customer_name,soh\n"
        "DIST-01,SKU-ALPHA-01,2024-03-01,1,Alias Dealer Token,3\n"
    )
    job = _run_dsi_job(dsi_source_id, _csv_bytes(csv), import_mode="apply", filename="dsi_alias.csv")
    job_id = job.id

    with SessionLocal() as db:
        line = db.scalars(
            select(ImportDistributorSiStagingLine).where(ImportDistributorSiStagingLine.import_job_id == job_id)
        ).first()
        assert line is not None
        assert line.severity != "error"
        assert line.resolved_customer_id == cust_id
        fs = db.scalars(select(FactSalesSellout).where(FactSalesSellout.source_import_job_id == job_id)).all()
        assert len(fs) == 1


def test_list_distributor_si_mapping_candidates(dsi_source_id: int) -> None:
    csv = "distributor_code,sku,date,qty,customer_name,soh\nDIST-01,SKU-ALPHA-01,2024-04-01,1,Unknown X,1\n"
    job = _run_dsi_job(dsi_source_id, _csv_bytes(csv), import_mode="validate", filename="dsi_cand.csv")
    job_id = job.id

    with SessionLocal() as db:
        rows = db.scalars(
            select(ImportEntityMappingCandidate)
            .where(ImportEntityMappingCandidate.import_job_id == job_id)
            .order_by(ImportEntityMappingCandidate.entity_type)
        ).all()
        assert any(r.entity_type == "customer_dealer_token" for r in rows)
