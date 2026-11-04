"""Distributor-sales validate must keep the tenant id while indexing customers.

``_build_resolution_cache`` loads every customer for the job tenant, then queries
approved customer source-token aliases with that same tenant id. A customer id
must not be passed into ``effective_tenant_id`` (which calls ``str.strip``).
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import delete, select, text

from app.db.session_sync import SessionLocal
from app.ingestion.pipeline import process_import_job_sync
from app.models.dimensions import DimCustomer, DimDistributor, DimProduct
from app.models.iam import Tenant
from app.models.import_distributor_si import (
    CustomerSourceTokenAlias,
    ImportDistributorSiStagingLine,
    ImportEntityMappingCandidate,
)
from app.models.ingestion import ImportJob, ImportRowResult, ImportTemplate, RawFileMetadata, SourceDefinition
from app.models.mapping import EntityMappingQueue
from app.services.seed_demo import _seed_import_core
from app.storage.local import LocalStorageBackend, get_storage_backend


def _require_cip_test(db) -> None:
    name = db.scalar(text("select current_database()"))
    print("current_database()", name)
    assert name == "cip_test"


def _cleanup(created: dict) -> None:
    tenant = created.get("tenant")
    with SessionLocal() as db:
        _require_cip_test(db)
        job_id = created.get("job_id")
        if job_id is not None:
            db.execute(delete(CustomerSourceTokenAlias).where(CustomerSourceTokenAlias.tenant_id == tenant))
            db.execute(delete(EntityMappingQueue).where(EntityMappingQueue.job_id == job_id))
            db.execute(
                delete(ImportDistributorSiStagingLine).where(ImportDistributorSiStagingLine.import_job_id == job_id)
            )
            db.execute(
                delete(ImportEntityMappingCandidate).where(ImportEntityMappingCandidate.import_job_id == job_id)
            )
            db.execute(delete(ImportRowResult).where(ImportRowResult.job_id == job_id))
            db.execute(delete(RawFileMetadata).where(RawFileMetadata.job_id == job_id))
            db.execute(delete(ImportJob).where(ImportJob.id == job_id))
        if created.get("alias_id") is not None and job_id is None:
            db.execute(delete(CustomerSourceTokenAlias).where(CustomerSourceTokenAlias.id == created["alias_id"]))
        if created.get("customer_id") is not None:
            db.execute(
                delete(DimCustomer).where(DimCustomer.id == created["customer_id"], DimCustomer.tenant_id == tenant)
            )
        if created.get("distributor_id") is not None:
            db.execute(
                delete(DimDistributor).where(
                    DimDistributor.id == created["distributor_id"], DimDistributor.tenant_id == tenant
                )
            )
        if created.get("product_id") is not None:
            db.execute(
                delete(DimProduct).where(DimProduct.id == created["product_id"], DimProduct.tenant_id == tenant)
            )
        if created.get("source_id") is not None and created.get("own_source"):
            db.execute(delete(SourceDefinition).where(SourceDefinition.id == created["source_id"]))
        if created.get("own_tenant"):
            db.execute(delete(Tenant).where(Tenant.id == tenant))
        db.commit()
    key = created.get("storage_key")
    if key:
        path = LocalStorageBackend()._root / key
        if path.is_file():
            path.unlink()


def test_dsi_validate_writes_summary_when_tenant_has_customer_source_token() -> None:
    """Validate completes and writes distributor_si_summary for a tenant that has a customer alias."""
    suffix = uuid4().hex[:10]
    tenant = f"tidfix-{suffix}"
    dist_code = f"D{suffix}"
    sku = f"SKU-TID-{suffix}"
    raw_token = f"Tid Fix Dealer {suffix}"
    created: dict = {"tenant": tenant, "own_source": False, "own_tenant": False}
    try:
        with SessionLocal() as db:
            _require_cip_test(db)
            db.add(Tenant(id=tenant, name=f"DSI tid regression {suffix}"))
            db.commit()
            created["own_tenant"] = True
            if db.scalar(select(ImportTemplate.id).where(ImportTemplate.slug == "distributor_inventory")) is None:
                _seed_import_core(db)
                db.commit()
            source = db.scalar(select(SourceDefinition).where(SourceDefinition.code == "distributor_inventory"))
            if source is None:
                template_id = db.scalar(
                    select(ImportTemplate.id).where(ImportTemplate.slug == "distributor_inventory")
                )
                assert template_id is not None
                source = SourceDefinition(
                    tenant_id=tenant,
                    import_template_id=int(template_id),
                    code=f"dsi-tid-{suffix}",
                    name="DSI tenant id regression",
                    source_kind="distributor_reports",
                    is_active=True,
                )
                db.add(source)
                db.flush()
                created["own_source"] = True
            distributor = DimDistributor(tenant_id=tenant, code=dist_code, name=f"Tid Fix Dist {suffix}")
            customer = DimCustomer(tenant_id=tenant, code=f"C-TID-{suffix}", name=raw_token)
            product = DimProduct(tenant_id=tenant, sku=sku, name=f"Tid Fix Sku {suffix}")
            db.add(distributor)
            db.add(customer)
            db.add(product)
            db.flush()
            alias = CustomerSourceTokenAlias(
                tenant_id=tenant,
                customer_id=int(customer.id),
                source_definition_id=int(source.id),
                distributor_id=int(distributor.id),
                raw_token=raw_token,
                normalized_token=raw_token.lower(),
                status="approved",
            )
            db.add(alias)
            db.commit()
            created.update(
                source_id=int(source.id),
                distributor_id=int(distributor.id),
                customer_id=int(customer.id),
                product_id=int(product.id),
                alias_id=int(alias.id),
            )

        csv = (
            "distributor_code,sku,date,qty,customer_name\n"
            f"{dist_code},{sku},2026-11-01,1,{raw_token}\n"
        ).encode()
        filename = f"dsi-tid-{suffix}.csv"
        storage = get_storage_backend()
        with SessionLocal() as db:
            _require_cip_test(db)
            job = ImportJob(
                tenant_id=tenant,
                source_id=created["source_id"],
                template_slug="distributor_inventory",
                import_mode="validate",
                status="pending",
                stage="uploaded",
                file_name=filename,
                content_type="text/csv",
            )
            db.add(job)
            db.flush()
            key = f"imports/test/{job.id}/{filename}"
            storage.save(key, csv, job.content_type)
            db.add(RawFileMetadata(job_id=job.id, storage_key=key, byte_size=len(csv), checksum=None))
            db.commit()
            created["job_id"] = int(job.id)
            created["storage_key"] = key
            job = process_import_job_sync(db, job.id)
            job_id = int(job.id)

        with SessionLocal() as db:
            _require_cip_test(db)
            finished = db.get(ImportJob, job_id)
            assert finished is not None
            assert finished.status in {"completed", "completed_with_errors"}, finished.error_summary
            summary = db.scalar(
                select(ImportRowResult).where(
                    ImportRowResult.job_id == job_id,
                    ImportRowResult.code == "distributor_si_summary",
                )
            )
            assert summary is not None
    finally:
        _cleanup(created)
