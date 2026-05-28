"""Apply resolved customer sell-through staging lines to fact_customer_sellthrough."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.models.import_customer_sellthrough_staging import ImportCustomerSellthroughStagingLine


@dataclass
class ApplySummary:
    applied: int = 0
    skipped_unresolved: int = 0
    errors: list[str] = field(default_factory=list)


def apply_customer_sellthrough_staging(db: Session, job_id: int) -> ApplySummary:
    """Upsert fact rows for staging lines that are resolved and not yet applied."""
    from app.services.imports.customer_sell_through import customer_sellthrough_source_key

    summary = ApplySummary()
    tbl = FactCustomerSellthrough.__table__

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
    for line in lines:
        if (
            line.resolved_customer_id is None
            or line.resolved_product_id is None
            or line.period_start_date is None
            or line.units_sold is None
        ):
            summary.skipped_unresolved += 1
            continue

        try:
            cust_id = int(line.resolved_customer_id)
            prod_id = int(line.resolved_product_id)
            loc_id = int(line.resolved_location_id) if line.resolved_location_id is not None else None
            period = line.period_start_date
            sk = customer_sellthrough_source_key(
                customer_id=cust_id,
                customer_location_id=loc_id,
                product_id=prod_id,
                period_start_date=period,
            )
            stmt = (
                pg_insert(tbl)
                .values(
                    source_key=sk,
                    customer_id=cust_id,
                    customer_location_id=loc_id,
                    product_id=prod_id,
                    period_start_date=period,
                    period_type=line.period_type or "weekly",
                    units_sold=float(line.units_sold),
                    raw_mtd_units=line.raw_mtd_units,
                    is_mtd_estimate=bool(line.is_mtd_estimate),
                    unit_sell_price=line.unit_sell_price,
                    unit_cost=line.unit_cost,
                    reported_soh=line.reported_soh,
                    import_job_id=job_id,
                    raw_source_row=line.raw_row_payload,
                    updated_at=now,
                )
                .on_conflict_do_update(
                    constraint="uq_fact_customer_sellthrough_source_key",
                    set_={
                        "units_sold": text("EXCLUDED.units_sold"),
                        "unit_sell_price": text("EXCLUDED.unit_sell_price"),
                        "unit_cost": text("EXCLUDED.unit_cost"),
                        "reported_soh": text("EXCLUDED.reported_soh"),
                        "import_job_id": text("EXCLUDED.import_job_id"),
                        "raw_source_row": text("EXCLUDED.raw_source_row"),
                        "updated_at": text("EXCLUDED.updated_at"),
                    },
                )
                .returning(tbl.c.id)
            )
            fact_id = db.execute(stmt).scalar_one()
            line.apply_status = "applied"
            line.fact_sellthrough_row_id = int(fact_id)
            db.add(line)
            summary.applied += 1
        except Exception as exc:  # noqa: BLE001
            summary.errors.append(f"line {line.id}: {exc}")

    return summary
