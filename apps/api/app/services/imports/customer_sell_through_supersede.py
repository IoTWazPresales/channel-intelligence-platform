"""A newer customer sell-through load supersedes older rows for the same customer, product and period (N-0110, D-0090).

An older load can have stored the same sales under other keys: several sites as one chain-level
row (``loc=0``), a week where the newer load has sale days, or another file entirely. Without
this step the old rows stay beside the new ones and units count twice.

After a load applies, an older stored row is superseded when all of these hold:

- its load is older than this load and is not this load;
- this load wrote the same customer and product for a period that overlaps the row's period
  (a product this load could not resolve keeps its old rows);
- the row's period lies inside the span this load reports for that customer (a month row is
  not superseded by one week of it);
- this load did not write that row's key itself (same-key restatement is the source_key upsert).

Site, day grain and file bytes do not matter. A superseded row is moved verbatim (``row_json``)
into ``fact_customer_sellthrough_superseded`` with the load that superseded it. Raw staging rows
are not touched. Nothing is hard-deleted.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable

from sqlalchemy import bindparam, select, text
from sqlalchemy.orm import Session

from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.models.ingestion import ImportJob
from app.services.imports.parsers.customer_sell_through_grain import period_end

logger = logging.getLogger(__name__)

REASON_RESTATED = "restated_by_newer_load"
# A week stored under a year that had not happened when its file was received (N-0110 repair).
REASON_FUTURE_WEEK = "week_not_yet_happened"


@dataclass
class SupersedeSummary:
    rows: int = 0
    units: float = 0.0
    from_jobs: list[int] = field(default_factory=list)
    product_ids: set[int] = field(default_factory=set)


def _grain(period_grain: str | None, period_type: str | None) -> str:
    from app.services.channel_intelligence.customer_stock_gap import grain_of

    return grain_of(period_grain, period_type)


def _range(values: Any) -> tuple[date, date]:
    get = values.get if isinstance(values, dict) else lambda k: getattr(values, k)
    start = get("period_start_date")
    return start, period_end(start, _grain(get("period_grain"), get("period_type")))


def move_to_superseded(db: Session, fact_ids: Iterable[int], *, by_job_id: int, reason: str) -> SupersedeSummary:
    """Move stored rows verbatim into ``fact_customer_sellthrough_superseded``."""
    summary = SupersedeSummary()
    ids = sorted({int(i) for i in fact_ids})
    if not ids:
        return summary
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
        {"job_id": int(by_job_id), "reason": reason, "ids": ids},
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
        "cst supersede job_id=%s reason=%s rows=%s units=%s from_jobs=%s",
        by_job_id,
        reason,
        summary.rows,
        summary.units,
        summary.from_jobs,
    )
    return summary


def supersede_restated_rows(
    db: Session,
    *,
    job_id: int,
    tenant_id: str,
    written_keys: set[str],
    restated: list[dict[str, Any]],
) -> SupersedeSummary:
    """Move older rows for the customers, products and periods this load restated under other keys.

    ``restated`` are the fact values this load wrote (customer_id, product_id, period fields).
    """
    if not written_keys or not restated:
        return SupersedeSummary()
    this_job = db.get(ImportJob, int(job_id))
    this_created = getattr(this_job, "created_at", None)

    ranges: dict[tuple[int, int], list[tuple[date, date]]] = defaultdict(list)
    span: dict[int, tuple[date, date]] = {}
    for v in restated:
        start, end = _range(v)
        cust, prod = int(v["customer_id"]), int(v["product_id"])
        ranges[(cust, prod)].append((start, end))
        lo, hi = span.get(cust, (start, end))
        span[cust] = (min(lo, start), max(hi, end))

    f = FactCustomerSellthrough
    fact_ids: list[int] = []
    for cust, (lo, hi) in span.items():
        products = sorted({p for (c, p) in ranges if c == cust})
        rows = db.execute(
            select(
                f.id, f.source_key, f.product_id, f.period_start_date, f.period_grain, f.period_type, ImportJob.created_at
            )
            .join(ImportJob, ImportJob.id == f.import_job_id)
            .where(
                f.tenant_id == tenant_id,
                f.customer_id == cust,
                f.product_id.in_(products),
                f.import_job_id != int(job_id),
                f.period_start_date >= lo,
                f.period_start_date <= hi,
            )
        ).all()
        for fid, sk, prod, start, pg, pt, created in rows:
            if sk in written_keys:
                continue
            if this_created is not None and created is not None and created > this_created:
                continue  # a newer load's row is never superseded by an older one
            end = period_end(start, _grain(pg, pt))
            if end > hi:
                continue
            if any(start <= r_end and r_start <= end for r_start, r_end in ranges[(cust, int(prod))]):
                fact_ids.append(int(fid))
    return move_to_superseded(db, fact_ids, by_job_id=int(job_id), reason=REASON_RESTATED)
