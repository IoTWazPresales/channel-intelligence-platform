"""Domain-specific import job bulk delete: preview counts and transactional cleanup.

N-0112 (Warren 2026-10-22): deleting a job removes the data it loaded in every fact table and brings
back the figures it replaced (``import_job_delete_figures``). The preview runs the same delete and
rolls it back, so what it shows per job is what the delete does. Learned aliases are kept unless the
caller asks for them to go too.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.commercial_lineup import CommercialLineupCase
from app.models.facts import FactCompetitorPrice, FactInventoryDistributor, FactSalesSellout
from app.models.historical_lineup import HistoricalLineupImportHeader, HistoricalLineupImportLine
from app.models.import_distributor_si import (
    ChannelSourceTokenAlias,
    CustomerSourceTokenAlias,
    DistributorSourceTokenAlias,
    ImportDistributorSiStagingLine,
    ImportEntityMappingCandidate,
    RegionSourceTokenAlias,
)
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.models.ingestion import ImportJob, ImportRowResult, RawFileMetadata
from app.models.mapping import EntityMappingQueue
from app.models.product_catalog import CatalogProduct
from app.services.imports.import_job_delete_figures import remove_job_data

MAX_JOBS = 200

_ALIASES = (
    ("customer_source_token_aliases", CustomerSourceTokenAlias),
    ("channel_source_token_aliases", ChannelSourceTokenAlias),
    ("region_source_token_aliases", RegionSourceTokenAlias),
    ("distributor_source_token_aliases", DistributorSourceTokenAlias),
)

# Rows each job owns outright, counted per job for the preview: (count key, table, job column).
_OWNED = (
    ("raw_file_metadata_rows", "raw_file_metadata", "job_id"),
    ("import_row_result_rows", "import_row_result", "job_id"),
    ("dsi_staging_rows", "import_distributor_si_staging_line", "import_job_id"),
    ("cst_staging_rows", "import_customer_sellthrough_staging_line", "import_job_id"),
    ("dsi_mapping_candidate_rows", "import_entity_mapping_candidate", "import_job_id"),
    ("shipment_evidence_line_rows", "shipment_evidence_line", "import_job_id"),
    ("entity_mapping_queue_rows", "entity_mapping_queue", "job_id"),
    ("historical_lineup_header_rows", "historical_lineup_import_header", "import_job_id"),
    ("commercial_lineup_case_rows", "commercial_lineup_case", "import_job_id"),
    ("catalog_products_pointing_at_jobs", "catalog_product", "last_import_job_id"),
    ("fact_competitor_price_rows", "fact_competitor_price", "source_job_id"),
)


def normalize_job_ids(job_ids: list[int], *, max_jobs: int = MAX_JOBS) -> list[int]:
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


def _table_exists(db: Session, name: str) -> bool:
    return bool(db.scalar(text("SELECT to_regclass(:t) IS NOT NULL"), {"t": f"public.{name}"}))


def _per_job_counts(db: Session, ids: list[int]) -> dict[int, Counter]:
    out: dict[int, Counter] = {j: Counter() for j in ids}
    for key, table, col in _OWNED:
        if not _table_exists(db, table):
            continue
        for jid, n in db.execute(
            text(f"SELECT {col}, count(*) FROM {table} WHERE {col} = ANY(:ids) GROUP BY 1"), {"ids": ids}
        ).all():
            out[int(jid)][key] += int(n)
    if _table_exists(db, "historical_lineup_import_line"):
        for jid, n in db.execute(
            text(
                """
                SELECT h.import_job_id, count(*) FROM historical_lineup_import_line l
                JOIN historical_lineup_import_header h ON h.id = l.header_id
                WHERE h.import_job_id = ANY(:ids) GROUP BY 1
                """
            ),
            {"ids": ids},
        ).all():
            out[int(jid)]["historical_lineup_line_rows"] += int(n)
    for key, model in _ALIASES:
        for jid, n in db.execute(
            select(model.created_from_import_job_id, func.count())
            .where(model.created_from_import_job_id.in_(ids))
            .group_by(model.created_from_import_job_id)
        ).all():
            out[int(jid)][key] += int(n)
    return out


def preview_import_job_bulk_delete(db: Session, job_ids: list[int]) -> dict[str, Any]:
    """What deleting these jobs removes, restores and recomputes, per job. Writes nothing.

    Runs the delete itself inside a savepoint and rolls the savepoint back.
    """
    ids = normalize_job_ids(job_ids)
    if not ids:
        return {"error": "no_valid_job_ids", "job_ids": [], "counts": {}, "risky": {}, "jobs": []}

    jobs = {
        int(j.id): j
        for j in db.scalars(select(ImportJob).where(ImportJob.id.in_(ids))).all()
    }
    missing = [i for i in ids if i not in jobs]
    present = [i for i in ids if i in jobs]
    storage_keys = list(db.scalars(select(RawFileMetadata.storage_key).where(RawFileMetadata.job_id.in_(ids))).all())
    owned = _per_job_counts(db, present) if present else {}

    removal: dict[str, Any] = {"per_job": {}, "totals": {}}
    if present:
        rehearsal = db.begin_nested()
        try:
            out = bulk_delete_import_jobs(db, present, delete_semantic_artifacts=False, dry_run=True)
            removal = out["data"]
        finally:
            rehearsal.rollback()
            db.expire_all()

    per_job = []
    totals: Counter = Counter()
    for jid in present:
        counts = Counter(owned.get(jid, {}))
        counts.update(removal["per_job"].get(jid, {}))
        totals.update(counts)
        job = jobs[jid]
        per_job.append(
            {
                "id": jid,
                "file_name": job.file_name,
                "template_slug": job.template_slug,
                "status": job.status,
                "stage": job.stage,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "counts": dict(counts),
            }
        )

    counts = {
        "import_jobs": len(present),
        "import_jobs_requested": len(ids),
        "import_jobs_missing": len(missing),
        **{k: int(totals.get(k, 0)) for k, _t, _c in _OWNED},
        "historical_lineup_line_rows": int(totals.get("historical_lineup_line_rows", 0)),
        # Kept for older clients: rows these jobs hold now, before anything is restored.
        "fact_sales_sellout_rows": int(
            db.scalar(select(func.count()).select_from(FactSalesSellout).where(FactSalesSellout.source_import_job_id.in_(ids)))
            or 0
        ),
        "fact_inventory_distributor_rows": int(
            db.scalar(
                select(func.count())
                .select_from(FactInventoryDistributor)
                .where(FactInventoryDistributor.source_import_job_id.in_(ids))
            )
            or 0
        ),
    }
    for k, v in removal["totals"].items():
        if k not in ("customers_recomputed", "distributors_recomputed", "superseded_records_relinked"):
            counts[k] = int(v)
    risky = {k: int(totals.get(k, 0)) for k, _m in _ALIASES}
    return {
        "job_ids": list(ids),
        "missing_job_ids": missing,
        "jobs": per_job,
        "counts": counts,
        "risky": risky,
        "recomputed": {
            "customers": int(removal["totals"].get("customers_recomputed", 0)),
            "distributors": int(removal["totals"].get("distributors_recomputed", 0)),
            "superseded_records_relinked": int(removal["totals"].get("superseded_records_relinked", 0)),
        },
        "storage_keys_sample": storage_keys[:20],
        "storage_keys_total": len(storage_keys),
        "max_jobs": MAX_JOBS,
    }


def _unlink_local_storage_key(key: str) -> None:
    settings = get_settings()
    root = Path(settings.local_storage_path)
    safe = key.replace("..", "").lstrip("/\\")
    path = root / safe
    if path.is_file():
        path.unlink()


def bulk_delete_import_jobs(
    db: Session,
    job_ids: list[int],
    *,
    delete_semantic_artifacts: bool,
    user: dict | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Delete import jobs, the data they loaded and their linked artifacts, in one transaction.

    The caller commits or rolls back. Steward aliases learned from the jobs are kept (their job link
    is cleared) unless ``delete_semantic_artifacts`` is true. ``dry_run`` leaves stored files and
    the audit trail alone, for the preview, which rolls back.
    """
    ids = normalize_job_ids(job_ids)
    if not ids:
        raise ValueError("no_valid_job_ids")

    id_tuple = tuple(ids)
    existing = set(db.scalars(select(ImportJob.id).where(ImportJob.id.in_(id_tuple))).all())
    if existing != set(ids):
        raise ValueError("not_all_jobs_found")

    deleted: dict[str, int] = {}

    # N-0112: remove what the jobs loaded and bring back what they replaced, before the jobs go.
    data = remove_job_data(db, ids)

    # Whatever the restore left behind (none expected) goes as before.
    r = db.execute(delete(FactSalesSellout).where(FactSalesSellout.source_import_job_id.in_(id_tuple)))
    deleted["fact_sales_sellout_rows"] = int(r.rowcount or 0)
    r = db.execute(delete(FactInventoryDistributor).where(FactInventoryDistributor.source_import_job_id.in_(id_tuple)))
    deleted["fact_inventory_distributor_rows"] = int(r.rowcount or 0)
    r = db.execute(delete(FactCompetitorPrice).where(FactCompetitorPrice.source_job_id.in_(id_tuple)))
    deleted["fact_competitor_price_rows"] = int(r.rowcount or 0)

    r = db.execute(delete(EntityMappingQueue).where(EntityMappingQueue.job_id.in_(id_tuple)))
    deleted["entity_mapping_queue_rows"] = int(r.rowcount or 0)

    r = db.execute(delete(ShipmentEvidenceLine).where(ShipmentEvidenceLine.import_job_id.in_(id_tuple)))
    deleted["shipment_evidence_line_rows"] = int(r.rowcount or 0)

    r = db.execute(delete(ImportDistributorSiStagingLine).where(ImportDistributorSiStagingLine.import_job_id.in_(id_tuple)))
    deleted["dsi_staging_rows"] = int(r.rowcount or 0)

    for key, model in _ALIASES:
        if delete_semantic_artifacts:
            r = db.execute(delete(model).where(model.created_from_import_job_id.in_(id_tuple)))
            deleted[f"{key}_deleted"] = int(r.rowcount or 0)
        else:
            # Kept by default (Warren 2026-10-22); the database clears the job link with the job.
            deleted[f"{key}_deleted"] = 0
            deleted[f"{key}_kept"] = int(
                db.scalar(select(func.count()).select_from(model).where(model.created_from_import_job_id.in_(id_tuple)))
                or 0
            )

    r = db.execute(delete(ImportEntityMappingCandidate).where(ImportEntityMappingCandidate.import_job_id.in_(id_tuple)))
    deleted["dsi_mapping_candidate_rows"] = int(r.rowcount or 0)

    r = db.execute(delete(ImportRowResult).where(ImportRowResult.job_id.in_(id_tuple)))
    deleted["import_row_result_rows"] = int(r.rowcount or 0)

    raw_rows = list(db.scalars(select(RawFileMetadata).where(RawFileMetadata.job_id.in_(id_tuple))).all())
    if not dry_run:
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

    data_out = {
        "per_job": {int(j): dict(c) for j, c in data.per_job.items()},
        "totals": dict(data.totals),
    }
    deleted.update({k: int(v) for k, v in data.totals.items()})
    if not dry_run:
        from app.services.platform_audit import record_platform_audit_sync

        record_platform_audit_sync(
            db,
            user,
            area="admin",
            action="import_jobs_delete",
            target_type="import_job",
            target_id=",".join(map(str, ids))[:128],
            detail={
                "job_ids": list(ids),
                "aliases_deleted": bool(delete_semantic_artifacts),
                "counts": deleted,
                "per_job": {str(j): c for j, c in data_out["per_job"].items()},
                # Every superseded record removed, in full: figures, keys and job ids (Warren 2026-10-22).
                "superseded_records_removed": data.removed_records,
            },
        )
    return {"deleted": deleted, "job_ids": list(ids), "data": data_out}
