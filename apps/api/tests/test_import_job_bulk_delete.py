"""Admin import job bulk delete preview + confirm (mutates DB — same cip guard as import pipeline tests)."""

from __future__ import annotations

import os
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.session_sync import SessionLocal
from app.main import app
from app.models.dimensions import DimCustomer, DimDistributor, DimProduct
from app.models.facts import FactInventoryDistributor, FactSalesSellout
from app.models.dimensions import DimChannel
from app.models.import_distributor_si import (
    ChannelSourceTokenAlias,
    CustomerSourceTokenAlias,
    DistributorSourceTokenAlias,
    ImportDistributorSiStagingLine,
    ImportEntityMappingCandidate,
)
from app.models.ingestion import ImportJob, ImportRowResult, RawFileMetadata, SourceDefinition
from app.models.mapping import EntityMappingQueue
from app.services.seed_demo import _seed_import_core


def _sqlalchemy_db_name(url: str) -> str:
    if not url or "://" not in url:
        return ""
    rest = url.split("://", 1)[1]
    if "/" not in rest:
        return ""
    db = rest.rsplit("/", 1)[-1]
    return db.split("?", 1)[0].strip()


def _skip_mutations_on_shared_cip() -> None:
    """Same safety policy as conftest import-pipeline guard: no accidental writes to shared cip."""
    if os.environ.get("ALLOW_TESTS_ON_DEV_DB", "").strip() == "1":
        return
    from app.core.config import get_settings

    settings = get_settings()
    async_name = _sqlalchemy_db_name(settings.database_url)
    sync_name = _sqlalchemy_db_name(settings.database_url_sync)
    if async_name == "cip" or sync_name == "cip":
        pytest.skip(
            "Skipping DB-mutating bulk-delete tests: database name is 'cip'. "
            "Use DATABASE_URL / DATABASE_URL_SYNC pointing at a disposable DB (e.g. cip_test), "
            "or set ALLOW_TESTS_ON_DEV_DB=1 to acknowledge writes to the current database."
        )


def _first_dims(session):
    c = session.scalar(select(DimCustomer).limit(1))
    p = session.scalar(select(DimProduct).limit(1))
    d = session.scalar(select(DimDistributor).limit(1))
    return c, p, d


def _seed_job_with_artifacts(session) -> int:
    _seed_import_core(session)
    src = session.scalar(select(SourceDefinition).limit(1))
    assert src is not None
    c, p, d = _first_dims(session)
    if not (c and p and d):
        import pytest

        pytest.skip("Database needs at least one dim_customer, dim_product, and dim_distributor row.")

    job = ImportJob(
        source_id=src.id,
        template_slug="distributor_inventory",
        import_mode="validate",
        status="completed",
        stage="test_cleanup_fixture",
        file_name="bulk-delete-test.csv",
    )
    session.add(job)
    session.flush()

    session.add(
        RawFileMetadata(
            job_id=job.id,
            storage_key=f"imports/test/bulk-delete-{job.id}.csv",
            byte_size=3,
        )
    )
    session.add(
        ImportRowResult(
            job_id=job.id,
            row_number=1,
            severity="info",
            code="test",
            message="fixture",
        )
    )
    session.add(
        ImportDistributorSiStagingLine(
            import_job_id=job.id,
            source_row_number=1,
            resolution_status="pending",
            severity="info",
            apply_status="pending",
        )
    )
    session.add(
        ImportEntityMappingCandidate(
            import_job_id=job.id,
            entity_type="customer",
            normalized_key=f"test-key-{job.id}",
            row_count=1,
        )
    )
    session.add(
        EntityMappingQueue(
            entity_type="customer",
            raw_value="fixture",
            status="review_required",
            job_id=job.id,
        )
    )
    session.add(
        FactSalesSellout(
            source_key=f"bulk-delete-test-sellout-{p.id}-{c.id}-2024-01-01",
            staging_line_id=None,
            product_id=p.id,
            customer_id=c.id,
            channel_id=None,
            distributor_id=d.id,
            period_start=date(2024, 1, 1),
            units=1,
            revenue=1,
            source_import_job_id=job.id,
        )
    )
    session.add(
        FactInventoryDistributor(
            product_id=p.id,
            distributor_id=d.id,
            as_of_date=date(2024, 1, 1),
            on_hand_units=1,
            source_import_job_id=job.id,
        )
    )
    session.commit()
    return job.id


def test_bulk_delete_preview_requires_admin() -> None:
    with TestClient(app) as client:
        r = client.post("/api/v1/imports/jobs/bulk-delete-preview", json={"job_ids": [1]})
        assert r.status_code == 403


def test_bulk_delete_preview_and_confirm_round_trip() -> None:
    _skip_mutations_on_shared_cip()
    with SessionLocal() as session:
        job_id = _seed_job_with_artifacts(session)

    admin = {"X-User-Role": "admin", "X-User-Id": "test"}
    with TestClient(app) as client:
        pr = client.post("/api/v1/imports/jobs/bulk-delete-preview", json={"job_ids": [job_id]}, headers=admin)
        assert pr.status_code == 200
        body = pr.json()
        assert body["counts"]["import_row_result_rows"] >= 1
        assert body["counts"]["dsi_staging_rows"] >= 1
        assert body["counts"]["fact_sales_sellout_rows"] >= 1
        assert body["counts"]["fact_inventory_distributor_rows"] >= 1
        assert body["risky"]["customer_source_token_aliases"] == 0
        assert body["risky"]["channel_source_token_aliases"] == 0
        assert body["risky"]["region_source_token_aliases"] == 0

        cr = client.post(
            "/api/v1/imports/jobs/bulk-delete-confirm",
            json={"job_ids": [job_id], "delete_semantic_artifacts": False},
            headers=admin,
        )
        assert cr.status_code == 200
        assert cr.json()["deleted"]["import_jobs_deleted"] == 1

        gone = client.post("/api/v1/imports/jobs/bulk-delete-preview", json={"job_ids": [job_id]}, headers=admin)
        assert gone.status_code == 200
        assert gone.json()["counts"]["import_jobs"] == 0
        assert gone.json()["counts"]["import_jobs_missing"] == 1


def test_bulk_delete_confirm_blocked_by_customer_aliases() -> None:
    _skip_mutations_on_shared_cip()
    with SessionLocal() as session:
        _seed_import_core(session)
        src = session.scalar(select(SourceDefinition).limit(1))
        assert src is not None
        c, p, d = _first_dims(session)
        if not (c and p and d):
            import pytest

            pytest.skip("Database needs at least one dim_customer, dim_product, and dim_distributor row.")

        job = ImportJob(
            source_id=src.id,
            template_slug="distributor_inventory",
            import_mode="validate",
            status="completed",
            stage="alias_block_fixture",
            file_name="alias-block.csv",
        )
        session.add(job)
        session.flush()
        session.add(
            CustomerSourceTokenAlias(
                customer_id=c.id,
                raw_token=f"raw-{job.id}",
                normalized_token=f"norm-{job.id}",
                created_from_import_job_id=job.id,
            )
        )
        session.commit()
        job_id = job.id

    admin = {"X-User-Role": "admin", "X-User-Id": "test"}
    with TestClient(app) as client:
        br = client.post(
            "/api/v1/imports/jobs/bulk-delete-confirm",
            json={"job_ids": [job_id], "delete_semantic_artifacts": False},
            headers=admin,
        )
        assert br.status_code == 422

        ok = client.post(
            "/api/v1/imports/jobs/bulk-delete-confirm",
            json={"job_ids": [job_id], "delete_semantic_artifacts": True},
            headers=admin,
        )
        assert ok.status_code == 200
        assert ok.json()["deleted"].get("customer_source_token_aliases_deleted", 0) >= 1


def test_bulk_delete_confirm_blocked_by_distributor_aliases() -> None:
    _skip_mutations_on_shared_cip()
    with SessionLocal() as session:
        _seed_import_core(session)
        src = session.scalar(select(SourceDefinition).limit(1))
        assert src is not None
        c, p, d = _first_dims(session)
        if not (c and p and d):
            import pytest

            pytest.skip("Database needs at least one dim_customer, dim_product, and dim_distributor row.")

        job = ImportJob(
            source_id=src.id,
            template_slug="distributor_inventory",
            import_mode="validate",
            status="completed",
            stage="dist-alias-fixture",
            file_name="dist-alias.csv",
        )
        session.add(job)
        session.flush()
        session.add(
            DistributorSourceTokenAlias(
                distributor_id=d.id,
                raw_token=f"draw-{job.id}",
                normalized_token=f"dnorm-{job.id}",
                created_from_import_job_id=job.id,
            )
        )
        session.commit()
        job_id = job.id

    admin = {"X-User-Role": "admin", "X-User-Id": "test"}
    with TestClient(app) as client:
        br = client.post(
            "/api/v1/imports/jobs/bulk-delete-confirm",
            json={"job_ids": [job_id], "delete_semantic_artifacts": False},
            headers=admin,
        )
        assert br.status_code == 422

        ok = client.post(
            "/api/v1/imports/jobs/bulk-delete-confirm",
            json={"job_ids": [job_id], "delete_semantic_artifacts": True},
            headers=admin,
        )
        assert ok.status_code == 200
        assert ok.json()["deleted"].get("distributor_source_token_aliases_deleted", 0) >= 1


def test_bulk_delete_confirm_blocked_by_channel_aliases() -> None:
    _skip_mutations_on_shared_cip()
    with SessionLocal() as session:
        _seed_import_core(session)
        src = session.scalar(select(SourceDefinition).limit(1))
        assert src is not None
        ch = session.scalar(select(DimChannel).limit(1))
        c, p, d = _first_dims(session)
        if not (ch and c and p and d):
            pytest.skip("Database needs dim_channel, dim_customer, dim_product, and dim_distributor rows.")

        job = ImportJob(
            source_id=src.id,
            template_slug="distributor_inventory",
            import_mode="validate",
            status="completed",
            stage="ch-alias-fixture",
            file_name="ch-alias.csv",
        )
        session.add(job)
        session.flush()
        session.add(
            ChannelSourceTokenAlias(
                channel_id=ch.id,
                raw_token=f"raw-ch-{job.id}",
                normalized_token=f"norm-ch-{job.id}",
                created_from_import_job_id=job.id,
            )
        )
        session.commit()
        job_id = job.id

    admin = {"X-User-Role": "admin", "X-User-Id": "test"}
    with TestClient(app) as client:
        pr = client.post("/api/v1/imports/jobs/bulk-delete-preview", json={"job_ids": [job_id]}, headers=admin)
        assert pr.status_code == 200
        assert pr.json()["risky"]["channel_source_token_aliases"] >= 1

        br = client.post(
            "/api/v1/imports/jobs/bulk-delete-confirm",
            json={"job_ids": [job_id], "delete_semantic_artifacts": False},
            headers=admin,
        )
        assert br.status_code == 422

        ok = client.post(
            "/api/v1/imports/jobs/bulk-delete-confirm",
            json={"job_ids": [job_id], "delete_semantic_artifacts": True},
            headers=admin,
        )
        assert ok.status_code == 200
        assert ok.json()["deleted"].get("channel_source_token_aliases_deleted", 0) >= 1
