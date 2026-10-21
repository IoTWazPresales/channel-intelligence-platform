"""N-0110 repair: re-upload an existing CST job's stored file as a new job (clone databases only).

Runs inside dbrun.py (DATABASE_URL* point at one database). Refuses to run on cip or cip_test.

usage (via dbrun):  python reupload.py keys  <job_id> [<job_id> ...]   validate only; compare keys
                    python reupload.py apply <job_id>                  process + apply; print new job id
                    python reupload.py totals                          per-customer unit totals (JSON)
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

API = Path(__file__).resolve().parents[4] / "apps" / "api"
sys.path.insert(0, str(API))

from sqlalchemy import func, select, text  # noqa: E402

from app.db.session_sync import SessionLocal  # noqa: E402
from app.ingestion.pipeline import process_import_job_sync  # noqa: E402
from app.models.fact_customer_sellthrough import FactCustomerSellthrough  # noqa: E402
from app.models.import_customer_sellthrough_staging import ImportCustomerSellthroughStagingLine  # noqa: E402
from app.models.ingestion import ImportJob, RawFileMetadata  # noqa: E402
from app.services.imports.customer_sell_through import customer_sellthrough_source_key  # noqa: E402

PROTECTED = {"cip", "cip_test"}


def guard(s) -> str:
    db = s.execute(text("select current_database()")).scalar()
    print(f"current_database()={db}", flush=True)
    if db in PROTECTED:
        raise SystemExit(f"refusing to write on {db}")
    return db


def clone_job(s, old_id: int, mode: str) -> int:
    old = s.get(ImportJob, int(old_id))
    raws = list(s.scalars(select(RawFileMetadata).where(RawFileMetadata.job_id == old.id).order_by(RawFileMetadata.id)))
    job = ImportJob(
        tenant_id=old.tenant_id,
        source_id=old.source_id,
        template_slug=old.template_slug,
        import_mode=mode,
        status="pending",
        stage="uploaded",
        file_name=old.file_name,
        content_type=old.content_type,
        inferred_schema=copy.deepcopy(old.inferred_schema),
        field_mapping=copy.deepcopy(old.field_mapping),
        file_headers=copy.deepcopy(old.file_headers),
        mapping_decisions=copy.deepcopy(old.mapping_decisions),
        staged_metadata=copy.deepcopy(old.staged_metadata),
    )
    s.add(job)
    s.flush()
    for r in raws:
        s.add(RawFileMetadata(job_id=job.id, storage_key=r.storage_key, byte_size=r.byte_size, checksum=r.checksum))
    s.commit()
    process_import_job_sync(s, job.id)
    s.commit()
    return int(job.id)


def staged_keys(s, job_id: int) -> set[str]:
    keys = set()
    for line in s.scalars(
        select(ImportCustomerSellthroughStagingLine).where(
            ImportCustomerSellthroughStagingLine.import_job_id == job_id,
            ImportCustomerSellthroughStagingLine.resolution_status == "resolved",
        )
    ):
        if None in (line.resolved_customer_id, line.resolved_product_id, line.period_start_date, line.units_sold):
            continue
        site = line.site_label
        if site is None and line.raw_location_token:
            site = str(line.raw_location_token).strip() or None
        keys.add(
            customer_sellthrough_source_key(
                customer_id=int(line.resolved_customer_id),
                customer_location_id=int(line.resolved_location_id) if line.resolved_location_id is not None else None,
                product_id=int(line.resolved_product_id),
                period_start_date=line.period_start_date,
                site_label=site,
            )
        )
    return keys


def cmd_keys(job_ids: list[int]) -> None:
    with SessionLocal() as s:
        guard(s)
        for old_id in job_ids:
            new_id = clone_job(s, old_id, "validate")
            new = s.get(ImportJob, new_id)
            mine = set(s.scalars(select(FactCustomerSellthrough.source_key).where(FactCustomerSellthrough.import_job_id == old_id)))
            keys = staged_keys(s, new_id)
            existing = set(s.scalars(select(FactCustomerSellthrough.source_key).where(FactCustomerSellthrough.source_key.in_(keys)))) if keys else set()
            grains = dict(
                s.execute(
                    select(ImportCustomerSellthroughStagingLine.period_grain, func.count())
                    .where(ImportCustomerSellthroughStagingLine.import_job_id == new_id)
                    .group_by(ImportCustomerSellthroughStagingLine.period_grain)
                ).all()
            )
            print(
                json.dumps(
                    {
                        "old_job": old_id,
                        "file": new.file_name,
                        "new_status": new.status,
                        "error": (new.error_summary or "")[:160] or None,
                        "grain": {str(k): v for k, v in grains.items()},
                        "old_job_fact_rows": len(mine),
                        "reupload_keys": len(keys),
                        "keys_already_stored": len(existing),
                        "new_keys_beside_old": len(keys - existing),
                        "old_rows_not_restated": len(mine - keys),
                    }
                ),
                flush=True,
            )


def cmd_apply(old_id: int) -> None:
    with SessionLocal() as s:
        guard(s)
        new_id = clone_job(s, old_id, "apply")
        new = s.get(ImportJob, new_id)
        print(json.dumps({"old_job": old_id, "new_job": new_id, "status": new.status, "error": new.error_summary}), flush=True)


def cmd_totals() -> None:
    with SessionLocal() as s:
        print(f"current_database()={s.execute(text('select current_database()')).scalar()}", file=sys.stderr)
        rows = s.execute(
            select(FactCustomerSellthrough.customer_id, func.count(), func.sum(FactCustomerSellthrough.units_sold))
            .group_by(FactCustomerSellthrough.customer_id)
            .order_by(FactCustomerSellthrough.customer_id)
        ).all()
        print(json.dumps({str(c): [int(n), float(u or 0)] for c, n, u in rows}))


if __name__ == "__main__":
    action = sys.argv[1]
    if action == "keys":
        cmd_keys([int(a) for a in sys.argv[2:]])
    elif action == "apply":
        cmd_apply(int(sys.argv[2]))
    elif action == "totals":
        cmd_totals()
    elif action == "diff":
        pass
    else:
        raise SystemExit(f"unknown action {action}")


def cmd_diff(old_id: int, new_id: int) -> None:
    """Sample old vs re-upload keys for one product (read-only)."""
    with SessionLocal() as s:
        print(f"current_database()={s.execute(text('select current_database()')).scalar()}")
        old = sorted(s.scalars(select(FactCustomerSellthrough.source_key).where(FactCustomerSellthrough.import_job_id == old_id)))
        new = sorted(staged_keys(s, new_id))
        print("old", len(old), old[:6])
        print("new", len(new), new[:6])
        def parts(keys):
            out = {}
            for k in keys:
                _, c, site, p, d = k.split(":", 4) if k.count(":") == 4 else (k.split(":") + [""] * 5)[:5]
                out.setdefault("periods", set()).add(d)
                out.setdefault("sites", set()).add(site)
                out.setdefault("products", set()).add(p)
                out.setdefault("customers", set()).add(c)
            return {k: (len(v), sorted(v)[:8]) for k, v in out.items()}
        print("old parts", parts(old))
        print("new parts", parts(new))


if __name__ == "__main__" and sys.argv[1] == "diff":
    cmd_diff(int(sys.argv[2]), int(sys.argv[3]))
