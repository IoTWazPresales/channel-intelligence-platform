"""Re-upload of the same customer sell-through file: supersede its older stored rows (N-0110).

A file loaded under older keys (several sites stored as one row, a week stored under
another year) and loaded again writes rows under new keys. Without this step the old
rows stay beside the new ones and units count twice.

After a load applies, an older stored row is superseded when all of these hold:

- the load that last wrote it read only files byte-identical (sha256) to files in this
  load, so it is the same source;
- this load restates the same customer and product (a product this load could not
  resolve keeps its old rows);
- this load did not write that row's key itself.

A superseded row is moved verbatim (``row_json``) into ``fact_customer_sellthrough_superseded``
with the load that superseded it. Raw staging rows are not touched. Nothing is hard-deleted.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field

from sqlalchemy import bindparam, select, text
from sqlalchemy.orm import Session

from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.models.ingestion import RawFileMetadata
from app.storage.local import get_storage_backend

logger = logging.getLogger(__name__)

REASON_SAME_FILE = "same_file_reloaded"


@dataclass
class SupersedeSummary:
    rows: int = 0
    units: float = 0.0
    from_jobs: list[int] = field(default_factory=list)
    product_ids: set[int] = field(default_factory=set)


def _file_digests(db: Session, job_id: int) -> set[str] | None:
    """sha256 of every raw file on a job, or None when a file cannot be read."""
    storage = get_storage_backend()
    keys = db.scalars(select(RawFileMetadata.storage_key).where(RawFileMetadata.job_id == int(job_id))).all()
    if not keys:
        return None
    out: set[str] = set()
    for key in keys:
        try:
            out.add(hashlib.sha256(storage.read(key)).hexdigest())
        except Exception:  # noqa: BLE001 - a missing file means the source cannot be proven
            return None
    return out


def supersede_reloaded_rows(
    db: Session,
    *,
    job_id: int,
    tenant_id: str,
    written_keys: set[str],
    restated: dict[int, set[int]],
) -> SupersedeSummary:
    """Move older rows of the same file(s) that this load restated under other keys.

    ``restated`` maps customer id to the product ids this load wrote.
    """
    summary = SupersedeSummary()
    if not written_keys or not restated:
        return summary
    mine = _file_digests(db, job_id)
    if not mine:
        return summary

    candidates: list[tuple[int, str, int, int, int]] = []
    for customer_id, product_ids in restated.items():
        rows = db.execute(
            select(
                FactCustomerSellthrough.id,
                FactCustomerSellthrough.source_key,
                FactCustomerSellthrough.import_job_id,
                FactCustomerSellthrough.customer_id,
                FactCustomerSellthrough.product_id,
            ).where(
                FactCustomerSellthrough.tenant_id == tenant_id,
                FactCustomerSellthrough.customer_id == int(customer_id),
                FactCustomerSellthrough.product_id.in_(sorted(product_ids)),
                FactCustomerSellthrough.import_job_id.isnot(None),
                FactCustomerSellthrough.import_job_id != int(job_id),
            )
        ).all()
        candidates.extend((int(r[0]), r[1], int(r[2]), int(r[3]), int(r[4])) for r in rows if r[1] not in written_keys)
    if not candidates:
        return summary

    same_source: dict[int, bool] = {}
    for _, _, old_job, _, _ in candidates:
        if old_job not in same_source:
            theirs = _file_digests(db, old_job)
            same_source[old_job] = bool(theirs) and theirs <= mine
    fact_ids = [fid for fid, _, old_job, _, _ in candidates if same_source[old_job]]
    if not fact_ids:
        return summary

    params = {"job_id": int(job_id), "reason": REASON_SAME_FILE, "ids": fact_ids}
    moved = db.execute(
        text(
            """
            INSERT INTO fact_customer_sellthrough_superseded (
                fact_id, source_key, tenant_id, customer_id, product_id, period_start_date,
                units_sold, reported_soh, import_job_id, superseded_by_import_job_id, reason, row_json
            )
            SELECT f.id, f.source_key, f.tenant_id, f.customer_id, f.product_id, f.period_start_date,
                   f.units_sold, f.reported_soh, f.import_job_id, :job_id, :reason, to_jsonb(f.*)
            FROM fact_customer_sellthrough f
            WHERE f.id IN :ids
            RETURNING fact_id, units_sold, import_job_id, product_id
            """
        ).bindparams(bindparam("ids", expanding=True)),
        params,
    ).all()
    db.execute(
        text("DELETE FROM fact_customer_sellthrough WHERE id IN :ids").bindparams(bindparam("ids", expanding=True)),
        {"ids": [int(r[0]) for r in moved]},
    )
    summary.rows = len(moved)
    summary.units = float(sum(float(r[1] or 0) for r in moved))
    summary.from_jobs = sorted({int(r[2]) for r in moved if r[2] is not None})
    summary.product_ids = {int(r[3]) for r in moved}
    logger.info(
        "cst supersede job_id=%s rows=%s units=%s from_jobs=%s",
        job_id,
        summary.rows,
        summary.units,
        summary.from_jobs,
    )
    return summary
