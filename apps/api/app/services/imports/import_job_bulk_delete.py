"""Domain-specific import job bulk delete: preview counts and transactional cleanup."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.commercial_lineup import CommercialLineupCase
from app.models.facts import FactCompetitorPrice, FactInventoryDistributor, FactSalesSellout
from app.models.historical_lineup import HistoricalLineupImportHeader, HistoricalLineupImportLine
from app.models.import_distributor_si import (
    CustomerSourceTokenAlias,
    DistributorSourceTokenAlias,
    ImportDistributorSiStagingLine,
    ImportEntityMappingCandidate,
)
from app.models.ingestion import ImportJob, ImportRowResult, RawFileMetadata
from app.models.mapping import EntityMappingQueue
from app.models.product_catalog import CatalogProduct


def normalize_job_ids(job_ids: list[int], *, max_jobs: int = 200) -> list[int]:
    out: list[int] = []
    seen: set[int] = set()
    for j in job_ids:
        if not isinstance(j, int) or j < 1:
            continue
        if j in seen:
            continue
        seen.add(j)
        out.append(j)
        if len(out) >= max_jobs:
            break
    return out


def preview_import_job_bulk_delete(db: Session, job_ids: list[int]) -> dict[str, Any]:
    ids = normalize_job_ids(job_ids)
    if not ids:
        return {"error": "no_valid_job_ids", "job_ids": [], "counts": {}, "risky": {}}

    id_tuple = tuple(ids)
    existing = set(db.scalars(select(ImportJob.id).where(ImportJob.id.in_(id_tuple))).all())
    missing = [i for i in ids if i not in existing]

    raw_rows = list(db.scalars(select(RawFileMetadata).where(RawFileMetadata.job_id.in_(id_tuple))).all())
    storage_keys = [r.storage_key for r in raw_rows]

    header_ids = list(
        db.scalars(select(HistoricalLineupImportHeader.id).where(HistoricalLineupImportHeader.import_job_id.in_(id_tuple))).all()
    )
    line_count = 0
    if header_ids:
        line_count = int(
            db.scalar(
                select(func.count())
                .select_from(HistoricalLineupImportLine)
                .where(HistoricalLineupImportLine.header_id.in_(header_ids))
            )
            or 0
        )

    counts = {
        "import_jobs": len(existing),
        "import_jobs_requested": len(ids),
        "import_jobs_missing": len(missing),
        "raw_file_metadata_rows": len(raw_rows),
        "import_row_result_rows": int(
            db.scalar(select(func.count()).select_from(ImportRowResult).where(ImportRowResult.job_id.in_(id_tuple))) or 0
        ),
        "dsi_staging_rows": int(
            db.scalar(
                select(func.count())
                .select_from(ImportDistributorSiStagingLine)
                .where(ImportDistributorSiStagingLine.import_job_id.in_(id_tuple))
            )
            or 0
        ),
        "dsi_mapping_candidate_rows": int(
            db.scalar(
                select(func.count())
                .select_from(ImportEntityMappingCandidate)
                .where(ImportEntityMappingCandidate.import_job_id.in_(id_tuple))
            )
            or 0
        ),
        "entity_mapping_queue_rows": int(
            db.scalar(
                select(func.count()).select_from(EntityMappingQueue).where(EntityMappingQueue.job_id.in_(id_tuple))
            )
            or 0
        ),
        "historical_lineup_header_rows": len(header_ids),
        "historical_lineup_line_rows": line_count,
        "commercial_lineup_case_rows": int(
            db.scalar(
                select(func.count())
                .select_from(CommercialLineupCase)
                .where(CommercialLineupCase.import_job_id.in_(id_tuple))
            )
            or 0
        ),
        "fact_sales_sellout_rows": int(
            db.scalar(
                select(func.count())
                .select_from(FactSalesSellout)
                .where(FactSalesSellout.source_import_job_id.in_(id_tuple))
            )
            or 0
        ),
        "fact_inventory_distributor_rows": int(
            db.scalar(
                select(func.count())
                .select_from(FactInventoryDistributor)
                .where(FactInventoryDistributor.source_import_job_id.in_(id_tuple))
            )
            or 0
        ),
        "catalog_products_pointing_at_jobs": int(
            db.scalar(
                select(func.count())
                .select_from(CatalogProduct)
                .where(CatalogProduct.last_import_job_id.in_(id_tuple))
            )
            or 0
        ),
        "fact_competitor_price_rows": int(
            db.scalar(
                select(func.count())
                .select_from(FactCompetitorPrice)
                .where(FactCompetitorPrice.source_job_id.in_(id_tuple))
            )
            or 0
        ),
    }

    risky = {
        "customer_source_token_aliases": int(
            db.scalar(
                select(func.count())
                .select_from(CustomerSourceTokenAlias)
                .where(CustomerSourceTokenAlias.created_from_import_job_id.in_(id_tuple))
            )
            or 0
        ),
        "distributor_source_token_aliases": int(
            db.scalar(
                select(func.count())
                .select_from(DistributorSourceTokenAlias)
                .where(DistributorSourceTokenAlias.created_from_import_job_id.in_(id_tuple))
            )
            or 0
        ),
    }

    return {
        "job_ids": list(ids),
        "missing_job_ids": missing,
        "counts": counts,
        "risky": risky,
        "storage_keys_sample": storage_keys[:20],
        "storage_keys_total": len(storage_keys),
    }


def _unlink_local_storage_key(key: str) -> None:
    settings = get_settings()
    root = Path(settings.local_storage_path)
    safe = key.replace("..", "").lstrip("/\\")
    path = root / safe
    if path.is_file():
        path.unlink()


def bulk_delete_import_jobs(
    db: Session, job_ids: list[int], *, delete_semantic_artifacts: bool
) -> dict[str, Any]:
    """Delete import jobs and directly linked artifacts in one transaction.

    Does **not** delete steward aliases unless ``delete_semantic_artifacts`` is true.
    """
    ids = normalize_job_ids(job_ids)
    if not ids:
        raise ValueError("no_valid_job_ids")

    id_tuple = tuple(ids)
    existing = set(db.scalars(select(ImportJob.id).where(ImportJob.id.in_(id_tuple))).all())
    if existing != set(ids):
        raise ValueError("not_all_jobs_found")

    cust_alias_n = int(
        db.scalar(
            select(func.count())
            .select_from(CustomerSourceTokenAlias)
            .where(CustomerSourceTokenAlias.created_from_import_job_id.in_(id_tuple))
        )
        or 0
    )
    dist_alias_n = int(
        db.scalar(
            select(func.count())
            .select_from(DistributorSourceTokenAlias)
            .where(DistributorSourceTokenAlias.created_from_import_job_id.in_(id_tuple))
        )
        or 0
    )
    if not delete_semantic_artifacts and (cust_alias_n > 0 or dist_alias_n > 0):
        raise ValueError("semantic_artifacts_present")

    deleted: dict[str, int] = {}

    # Facts first (reference import_job)
    r = db.execute(delete(FactSalesSellout).where(FactSalesSellout.source_import_job_id.in_(id_tuple)))
    deleted["fact_sales_sellout_rows"] = int(r.rowcount or 0)
    r = db.execute(delete(FactInventoryDistributor).where(FactInventoryDistributor.source_import_job_id.in_(id_tuple)))
    deleted["fact_inventory_distributor_rows"] = int(r.rowcount or 0)
    r = db.execute(delete(FactCompetitorPrice).where(FactCompetitorPrice.source_job_id.in_(id_tuple)))
    deleted["fact_competitor_price_rows"] = int(r.rowcount or 0)

    r = db.execute(delete(EntityMappingQueue).where(EntityMappingQueue.job_id.in_(id_tuple)))
    deleted["entity_mapping_queue_rows"] = int(r.rowcount or 0)

    r = db.execute(delete(ImportDistributorSiStagingLine).where(ImportDistributorSiStagingLine.import_job_id.in_(id_tuple)))
    deleted["dsi_staging_rows"] = int(r.rowcount or 0)

    if delete_semantic_artifacts:
        r = db.execute(
            delete(CustomerSourceTokenAlias).where(CustomerSourceTokenAlias.created_from_import_job_id.in_(id_tuple))
        )
        deleted["customer_source_token_aliases_deleted"] = int(r.rowcount or 0)
        r = db.execute(
            delete(DistributorSourceTokenAlias).where(DistributorSourceTokenAlias.created_from_import_job_id.in_(id_tuple))
        )
        deleted["distributor_source_token_aliases_deleted"] = int(r.rowcount or 0)
    else:
        deleted["customer_source_token_aliases_deleted"] = 0
        deleted["distributor_source_token_aliases_deleted"] = 0

    r = db.execute(delete(ImportEntityMappingCandidate).where(ImportEntityMappingCandidate.import_job_id.in_(id_tuple)))
    deleted["dsi_mapping_candidate_rows"] = int(r.rowcount or 0)

    r = db.execute(delete(ImportRowResult).where(ImportRowResult.job_id.in_(id_tuple)))
    deleted["import_row_result_rows"] = int(r.rowcount or 0)

    raw_rows = list(db.scalars(select(RawFileMetadata).where(RawFileMetadata.job_id.in_(id_tuple))).all())
    for meta in raw_rows:
        try:
            _unlink_local_storage_key(meta.storage_key)
        except OSError:
            pass
    r = db.execute(delete(RawFileMetadata).where(RawFileMetadata.job_id.in_(id_tuple)))
    deleted["raw_file_metadata_rows"] = int(r.rowcount or 0)

    header_ids = list(
        db.scalars(select(HistoricalLineupImportHeader.id).where(HistoricalLineupImportHeader.import_job_id.in_(id_tuple))).all()
    )
    if header_ids:
        r = db.execute(delete(HistoricalLineupImportLine).where(HistoricalLineupImportLine.header_id.in_(header_ids)))
        deleted["historical_lineup_line_rows"] = int(r.rowcount or 0)
        r = db.execute(delete(HistoricalLineupImportHeader).where(HistoricalLineupImportHeader.id.in_(header_ids)))
        deleted["historical_lineup_header_rows"] = int(r.rowcount or 0)
    else:
        deleted["historical_lineup_line_rows"] = 0
        deleted["historical_lineup_header_rows"] = 0

    r = db.execute(
        update(CommercialLineupCase)
        .where(CommercialLineupCase.import_job_id.in_(id_tuple))
        .values(import_job_id=None)
    )
    deleted["commercial_lineup_cases_cleared"] = int(r.rowcount or 0)

    r = db.execute(
        update(CatalogProduct)
        .where(CatalogProduct.last_import_job_id.in_(id_tuple))
        .values(last_import_job_id=None)
    )
    deleted["catalog_products_cleared"] = int(r.rowcount or 0)

    r = db.execute(delete(ImportJob).where(ImportJob.id.in_(id_tuple)))
    deleted["import_jobs_deleted"] = int(r.rowcount or 0)

    return {"deleted": deleted, "job_ids": list(ids)}
