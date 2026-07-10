"""Backfill resolved_* + crad_date on existing shipment evidence lines (Unit 1).

Dry-run by default; pass --confirm to write. Warren runs against cip after migration 0058.
"""
from __future__ import annotations

import argparse

from sqlalchemy import func, select, text, update

from app.db.session_sync import SessionLocal
from app.models.facts import FactInboundShipment
from app.models.ingestion import ImportJob
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.services.imports.cip_db_identity import is_cip_application_database
from app.services.imports.shipment_resolved_entities import (
    apply_resolved_entities_to_line,
    parse_crad_from_raw_row,
)


def _require_columns(db) -> None:
    cols = {
        r[0]
        for r in db.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'shipment_evidence_line' "
                "AND column_name IN ('resolved_customer_id', 'resolved_distributor_id', 'crad_date')"
            )
        )
    }
    if cols != {"resolved_customer_id", "resolved_distributor_id", "crad_date"}:
        raise SystemExit(
            "Refusing: migration 20260629_0058 not applied "
            "(missing resolved_customer_id / resolved_distributor_id / crad_date on shipment_evidence_line)"
        )


def _count_stats(db) -> dict[str, int]:
    total = int(db.scalar(select(func.count()).select_from(ShipmentEvidenceLine)) or 0)
    rcust = int(
        db.scalar(
            select(func.count()).select_from(ShipmentEvidenceLine).where(
                ShipmentEvidenceLine.resolved_customer_id.is_not(None)
            )
        )
        or 0
    )
    rdist = int(
        db.scalar(
            select(func.count()).select_from(ShipmentEvidenceLine).where(
                ShipmentEvidenceLine.resolved_distributor_id.is_not(None)
            )
        )
        or 0
    )
    crad = int(
        db.scalar(
            select(func.count()).select_from(ShipmentEvidenceLine).where(
                ShipmentEvidenceLine.crad_date.is_not(None)
            )
        )
        or 0
    )
    return {
        "total_lines": total,
        "resolved_customer_id_set": rcust,
        "resolved_customer_id_unresolved": total - rcust,
        "resolved_distributor_id_set": rdist,
        "resolved_distributor_id_unresolved": total - rdist,
        "crad_date_set": crad,
        "crad_date_unresolved": total - crad,
    }


def _sync_facts_from_evidence(db, *, chunk: int = 500) -> int:
    """Copy resolved_* + crad_date onto fact_inbound_shipment rows linked by evidence line id."""
    n = 0
    offset = 0
    while True:
        pairs = list(
            db.execute(
                select(
                    ShipmentEvidenceLine.id,
                    ShipmentEvidenceLine.resolved_customer_id,
                    ShipmentEvidenceLine.resolved_distributor_id,
                    ShipmentEvidenceLine.crad_date,
                )
                .order_by(ShipmentEvidenceLine.id)
                .offset(offset)
                .limit(chunk)
            ).all()
        )
        if not pairs:
            break
        for line_id, rc, rd, crad in pairs:
            db.execute(
                update(FactInboundShipment)
                .where(FactInboundShipment.shipment_evidence_line_id == int(line_id))
                .values(resolved_customer_id=rc, resolved_distributor_id=rd, crad_date=crad)
            )
            n += 1
        offset += chunk
    return n


def run(*, dry_run: bool, job_id: int | None) -> dict[str, int]:
    stats: dict[str, int] = {}
    with SessionLocal() as db:
        dbname = db.scalar(text("SELECT current_database()"))
        if not is_cip_application_database(str(dbname)):
            raise SystemExit(f"Refusing: current_database()={dbname!r}")
        _require_columns(db)
        before = _count_stats(db)
        stats.update({f"before_{k}": v for k, v in before.items()})

        if dry_run:
            # Estimate crad backfill from raw JSON without writing
            raw_crad = int(
                db.scalar(
                    text(
                        "SELECT count(*) FROM shipment_evidence_line "
                        "WHERE NULLIF(TRIM(raw_source_row->>'CRAD'), '') IS NOT NULL"
                    )
                )
                or 0
            )
            stats["dry_run_crad_in_raw_source_row"] = raw_crad
            return stats

        q = select(ShipmentEvidenceLine).order_by(ShipmentEvidenceLine.id)
        if job_id is not None:
            q = q.where(ShipmentEvidenceLine.import_job_id == int(job_id))
        lines = list(db.scalars(q).all())
        stats["lines_processed"] = len(lines)

        job_source: dict[int, int | None] = {}
        for line in lines:
            jid = int(line.import_job_id)
            if jid not in job_source:
                job = db.get(ImportJob, jid)
                job_source[jid] = int(job.source_id) if job and job.source_id else None
            sid = job_source[jid]
            if line.crad_date is None:
                raw = line.raw_source_row if isinstance(line.raw_source_row, dict) else {}
                line.crad_date = parse_crad_from_raw_row(raw)
            apply_resolved_entities_to_line(line, db, sid)
            db.add(line)

        db.flush()
        stats["facts_rows_synced"] = _sync_facts_from_evidence(db)
        db.commit()

        after = _count_stats(db)
        stats.update({f"after_{k}": v for k, v in after.items()})
    return stats


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--confirm", action="store_true", help="Write backfill (default dry-run)")
    p.add_argument("--job-id", type=int, default=None, help="Limit to one import job")
    args = p.parse_args()
    stats = run(dry_run=not args.confirm, job_id=args.job_id)
    mode = "CONFIRM" if args.confirm else "DRY-RUN"
    print(f"[{mode}] backfill_shipment_resolved_entities")
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
