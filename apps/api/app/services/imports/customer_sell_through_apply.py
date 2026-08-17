"""Apply resolved customer sell-through staging lines to fact_customer_sellthrough."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.models.import_customer_sellthrough_staging import ImportCustomerSellthroughStagingLine

# Conflict-update column set — kept identical to the prior per-row upsert so the
# transaction-immutable sell-out write semantics are unchanged; only the *mechanism*
# (one statement per chunk instead of one per row) is batched.
_CONFLICT_SET = {
    "units_sold": text("EXCLUDED.units_sold"),
    "unit_sell_price": text("EXCLUDED.unit_sell_price"),
    "unit_cost": text("EXCLUDED.unit_cost"),
    "unit_mac": text("EXCLUDED.unit_mac"),
    "reported_soh": text("EXCLUDED.reported_soh"),
    "site_label": text("EXCLUDED.site_label"),
    "vat_basis": text("EXCLUDED.vat_basis"),
    "import_job_id": text("EXCLUDED.import_job_id"),
    "raw_source_row": text("EXCLUDED.raw_source_row"),
    "tenant_id": text("EXCLUDED.tenant_id"),
    "updated_at": text("EXCLUDED.updated_at"),
}

_APPLY_CHUNK_SIZE = 500


@dataclass
class ApplySummary:
    applied: int = 0
    skipped_unresolved: int = 0
    errors: list[str] = field(default_factory=list)


def apply_customer_sellthrough_staging(
    db: Session,
    job_id: int,
    *,
    on_progress: Callable[[int, int], None] | None = None,
    chunk_size: int = _APPLY_CHUNK_SIZE,
) -> ApplySummary:
    """Upsert fact rows for staging lines that are resolved and not yet applied.

    Batched: lines are grouped by ``source_key`` (last value wins — matching the prior sequential
    last-write-wins) and upserted in chunked multi-row ``INSERT … ON CONFLICT DO UPDATE`` statements
    rather than one round-trip per row. The conflict target/columns are unchanged. Dedup-by-source_key
    within a chunk is required: Postgres rejects an ``ON CONFLICT DO UPDATE`` that touches the same
    key twice in one statement. ``on_progress(current, total)`` reports per chunk (optional).
    """
    from app.models.ingestion import ImportJob
    from app.services.imports.customer_sell_through import customer_sellthrough_source_key

    summary = ApplySummary()
    tbl = FactCustomerSellthrough.__table__
    job = db.get(ImportJob, int(job_id))
    tid = (getattr(job, "tenant_id", None) or "default").strip() or "default" if job else "default"

    lines = list(
        db.scalars(
            select(ImportCustomerSellthroughStagingLine)
            .where(ImportCustomerSellthroughStagingLine.import_job_id == job_id)
            .where(ImportCustomerSellthroughStagingLine.resolution_status == "resolved")
            .where(ImportCustomerSellthroughStagingLine.apply_status.is_(None))
        ).all()
    )

    summary.skipped_unresolved = int(
        db.scalar(
            select(func.count())
            .select_from(ImportCustomerSellthroughStagingLine)
            .where(ImportCustomerSellthroughStagingLine.import_job_id == job_id)
            .where(ImportCustomerSellthroughStagingLine.resolution_status != "resolved")
        )
        or 0
    )

    now = datetime.now(timezone.utc)

    # Group by source_key: keep the last line's values (sequential last-wins), but remember every
    # line in the group so they all get marked applied + pointed at the resulting fact id.
    grouped: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for line in lines:
        if (
            line.resolved_customer_id is None
            or line.resolved_product_id is None
            or line.period_start_date is None
            or line.units_sold is None
        ):
            summary.skipped_unresolved += 1
            continue
        cust_id = int(line.resolved_customer_id)
        prod_id = int(line.resolved_product_id)
        loc_id = int(line.resolved_location_id) if line.resolved_location_id is not None else None
        period = line.period_start_date
        # site_label: prefer explicit staging column; fall back to raw location token (verbatim).
        site_label = getattr(line, "site_label", None)
        if site_label is None and line.raw_location_token:
            site_label = str(line.raw_location_token).strip() or None
        sk = customer_sellthrough_source_key(
            customer_id=cust_id,
            customer_location_id=loc_id,
            product_id=prod_id,
            period_start_date=period,
            site_label=site_label,
        )
        values = {
            "source_key": sk,
            "customer_id": cust_id,
            "customer_location_id": loc_id,
            "product_id": prod_id,
            "period_start_date": period,
            "period_type": line.period_type or "weekly",
            "units_sold": float(line.units_sold),
            "raw_mtd_units": line.raw_mtd_units,
            "is_mtd_estimate": bool(line.is_mtd_estimate),
            "unit_sell_price": line.unit_sell_price,
            "unit_cost": line.unit_cost,
            "unit_mac": getattr(line, "unit_mac", None),
            "reported_soh": line.reported_soh,
            "site_label": site_label,
            "vat_basis": getattr(line, "vat_basis", None) or "ex_vat",
            "import_job_id": job_id,
            "raw_source_row": line.raw_row_payload,
            "tenant_id": tid,
            "updated_at": now,
        }
        if sk in grouped:
            grouped[sk]["values"] = values  # last wins (matches sequential upsert)
            grouped[sk]["lines"].append(line)
        else:
            grouped[sk] = {"values": values, "lines": [line]}
            order.append(sk)

    total = len(order)
    for start in range(0, total, chunk_size):
        chunk_sks = order[start : start + chunk_size]
        rows = [grouped[sk]["values"] for sk in chunk_sks]
        try:
            stmt = (
                pg_insert(tbl)
                .values(rows)
                .on_conflict_do_update(
                    constraint="uq_fact_customer_sellthrough_source_key",
                    set_=_CONFLICT_SET,
                )
                .returning(tbl.c.id, tbl.c.source_key)
            )
            returned = db.execute(stmt).all()
            id_by_sk = {r.source_key: int(r.id) for r in returned}
            for sk in chunk_sks:
                fid = id_by_sk.get(sk)
                for line in grouped[sk]["lines"]:
                    line.apply_status = "applied"
                    if fid is not None:
                        line.fact_sellthrough_row_id = fid
                    db.add(line)
                    summary.applied += 1
        except Exception as exc:  # noqa: BLE001
            for sk in chunk_sks:
                for line in grouped[sk]["lines"]:
                    summary.errors.append(f"line {line.id}: {exc}")
        if on_progress is not None:
            on_progress(min(start + chunk_size, total), total)

    return summary
