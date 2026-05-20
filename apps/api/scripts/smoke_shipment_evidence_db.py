"""One-off local smoke: verify DB objects + optional import runs (invoke manually)."""

from __future__ import annotations

import pathlib
import sys

from sqlalchemy import create_engine, func, select, text

from app.core.config import get_settings
from app.db.sync_url import sqlalchemy_sync_engine_url
from app.db.session_sync import SessionLocal
from app.ingestion.pipeline import process_import_job_sync
from app.models.ingestion import ImportJob, ImportTemplate, RawFileMetadata, SourceDefinition
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.storage.local import get_storage_backend


def main() -> int:
    settings = get_settings()
    u = sqlalchemy_sync_engine_url(settings.database_url_sync)
    e = create_engine(u)
    with e.connect() as c:
        dbn = c.execute(text("SELECT current_database()")).scalar()
        print("current_database():", dbn)
        reg = c.execute(text("SELECT to_regclass('public.shipment_evidence_line')")).scalar()
        print("shipment_evidence_line to_regclass:", reg)
        h = c.execute(text("SELECT pipeline_handler FROM import_template WHERE slug = 'inbound_shipments'")).scalar()
        print("inbound_shipments pipeline_handler:", h)

    if len(sys.argv) < 2:
        print("(No file args: skip import smoke. Pass one or two CSV paths to run imports.)")
        return 0

    paths = [pathlib.Path(p) for p in sys.argv[1:] if p.strip()]
    storage = get_storage_backend()
    with SessionLocal() as db:
        src_id = db.scalar(
            select(SourceDefinition.id)
            .join(ImportTemplate, ImportTemplate.id == SourceDefinition.import_template_id)
            .where(ImportTemplate.slug == "inbound_shipments", SourceDefinition.is_active.is_(True))
            .limit(1)
        )
        if not src_id:
            print("ERROR: no active SourceDefinition for inbound_shipments")
            return 1
        print("Using source_definition.id:", int(src_id))

        for p in paths:
            if not p.is_file():
                print("SKIP missing file:", p)
                continue
            raw = p.read_bytes()
            job = ImportJob(
                source_id=int(src_id),
                template_slug="inbound_shipments",
                import_mode="apply",
                status="pending",
                stage="uploaded",
                file_name=p.name,
                content_type="text/csv" if p.suffix.lower() == ".csv" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            db.add(job)
            db.flush()
            key = f"imports/smoke/{job.id}/{p.name}"
            storage.save(key, raw, job.content_type)
            db.add(RawFileMetadata(job_id=job.id, storage_key=key, byte_size=len(raw), checksum=None))
            db.commit()
            print("Running import job", job.id, p.name, "bytes", len(raw))
            out = process_import_job_sync(db, job.id)
            print("  job status:", out.status, "stage:", out.stage, "error_summary:", out.error_summary)
            n = db.scalar(select(func.count()).select_from(ShipmentEvidenceLine).where(ShipmentEvidenceLine.import_job_id == job.id))
            print("  shipment_evidence_line rows for job:", int(n or 0))
            if n:
                st = db.execute(
                    select(ShipmentEvidenceLine.product_resolution_status, func.count())
                    .where(ShipmentEvidenceLine.import_job_id == job.id)
                    .group_by(ShipmentEvidenceLine.product_resolution_status)
                ).all()
                print("  product_resolution_status counts:", dict(st))
                dt = db.execute(
                    select(ShipmentEvidenceLine.distributor_resolution_status, func.count())
                    .where(ShipmentEvidenceLine.import_job_id == job.id)
                    .group_by(ShipmentEvidenceLine.distributor_resolution_status)
                ).all()
                print("  distributor_resolution_status counts:", dict(dt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
