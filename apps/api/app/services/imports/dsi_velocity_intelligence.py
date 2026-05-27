"""DSI sell-out velocity computation from ``fact_sales_sellout``."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from statistics import mean

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.fact_customer_velocity import FactCustomerVelocity
from app.models.facts import FactSalesSellout

logger = logging.getLogger(__name__)


def dsi_velocity_source_key(*, distributor_id: int, product_id: int, customer_id: int) -> str:
    return f"dsi-velocity:{int(distributor_id)}:{int(product_id)}:{int(customer_id)}"


def _table_exists(session: Session, table_name: str) -> bool:
    from sqlalchemy import inspect as sa_inspect

    try:
        return bool(sa_inspect(session.get_bind()).has_table(table_name))
    except Exception:
        return False


def _sum_units_in_window(
    rows: list[tuple[date, Decimal]],
    *,
    anchor: date,
    window_days: int,
) -> Decimal:
    # Inclusive calendar window: anchor and the prior (window_days - 1) days.
    cutoff = anchor - timedelta(days=window_days - 1)
    total = Decimal("0")
    for txn_date, units in rows:
        if cutoff <= txn_date <= anchor:
            total += units
    return total


def _distinct_iso_weeks(rows: list[tuple[date, Decimal]]) -> int:
    weeks: set[tuple[int, int]] = set()
    for txn_date, _units in rows:
        iso = txn_date.isocalendar()
        weeks.add((iso.year, iso.week))
    return len(weeks)


def _model_confidence(distinct_weeks: int) -> str:
    if distinct_weeks >= 52:
        return "high"
    if distinct_weeks >= 26:
        return "medium"
    return "low"


def _weekly_totals(rows: list[tuple[date, Decimal]]) -> dict[tuple[int, int], Decimal]:
    by_week: dict[tuple[int, int], Decimal] = defaultdict(lambda: Decimal("0"))
    for txn_date, units in rows:
        iso = txn_date.isocalendar()
        by_week[(iso.year, iso.week)] += units
    return by_week


def _seasonal_index(rows: list[tuple[date, Decimal]]) -> Decimal:
    by_week = _weekly_totals(rows)
    if not by_week:
        return Decimal("1.0")
    years = {y for y, _w in by_week}
    if len(years) < 2:
        return Decimal("1.0")
    all_weekly = [float(v) for v in by_week.values()]
    mean_all = mean(all_weekly)
    if mean_all <= 0:
        return Decimal("1.0")
    by_iso_week_num: dict[int, list[float]] = defaultdict(list)
    for (_year, week_num), units in by_week.items():
        by_iso_week_num[int(week_num)].append(float(units))
    week_means = [mean(vals) for vals in by_iso_week_num.values() if vals]
    if not week_means:
        return Decimal("1.0")
    return Decimal(str(mean(week_means) / mean_all))


def _upsert_velocity_row(
    session: Session,
    *,
    distributor_id: int,
    product_id: int,
    customer_id: int,
    computed_through_date: date,
    velocity_4wk: Decimal | None,
    velocity_13wk: Decimal | None,
    velocity_52wk: Decimal | None,
    seasonal_index: Decimal,
    model_confidence: str,
    import_job_id: int,
) -> None:
    source_key = dsi_velocity_source_key(
        distributor_id=distributor_id,
        product_id=product_id,
        customer_id=customer_id,
    )
    values = {
        "source_key": source_key,
        "distributor_id": int(distributor_id),
        "product_id": int(product_id),
        "customer_id": int(customer_id),
        "computed_through_date": computed_through_date,
        "velocity_4wk": float(velocity_4wk) if velocity_4wk is not None else None,
        "velocity_13wk": float(velocity_13wk) if velocity_13wk is not None else None,
        "velocity_52wk": float(velocity_52wk) if velocity_52wk is not None else None,
        "seasonal_index": float(seasonal_index),
        "is_promotional_period": False,
        "model_confidence": model_confidence,
        "import_job_id": int(import_job_id),
    }
    tbl = FactCustomerVelocity.__table__
    stmt = pg_insert(tbl).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[tbl.c.source_key],
        set_={
            "velocity_4wk": stmt.excluded.velocity_4wk,
            "velocity_13wk": stmt.excluded.velocity_13wk,
            "velocity_52wk": stmt.excluded.velocity_52wk,
            "seasonal_index": stmt.excluded.seasonal_index,
            "model_confidence": stmt.excluded.model_confidence,
            "computed_through_date": stmt.excluded.computed_through_date,
            "import_job_id": stmt.excluded.import_job_id,
            "updated_at": datetime.now(timezone.utc),
        },
    )
    session.execute(stmt)


def compute_distributor_velocity(
    db: Session,
    distributor_id: int,
    import_job_id: int,
) -> int:
    """Compute and upsert velocity rows for all product/customer pairs with sell-out history."""
    if not _table_exists(db, "fact_customer_velocity"):
        return 0

    dist_id = int(distributor_id)
    anchor = db.scalar(
        select(func.max(FactSalesSellout.transaction_date)).where(
            FactSalesSellout.distributor_id == dist_id,
        )
    )
    if anchor is None:
        return 0

    sellout_rows = db.execute(
        select(
            FactSalesSellout.product_id,
            FactSalesSellout.customer_id,
            FactSalesSellout.transaction_date,
            FactSalesSellout.units,
        ).where(FactSalesSellout.distributor_id == dist_id)
    ).all()

    grouped: dict[tuple[int, int], list[tuple[date, Decimal]]] = defaultdict(list)
    for product_id, customer_id, txn_date, units in sellout_rows:
        if product_id is None or customer_id is None or txn_date is None:
            continue
        grouped[(int(product_id), int(customer_id))].append(
            (txn_date, Decimal(str(units or 0)))
        )

    upserted = 0
    for (product_id, customer_id), txn_rows in grouped.items():
        sum_4 = _sum_units_in_window(txn_rows, anchor=anchor, window_days=28)
        sum_13 = _sum_units_in_window(txn_rows, anchor=anchor, window_days=91)
        sum_52 = _sum_units_in_window(txn_rows, anchor=anchor, window_days=364)
        velocity_4wk = sum_4 / Decimal("4") if sum_4 else None
        velocity_13wk = sum_13 / Decimal("13") if sum_13 else None
        velocity_52wk = sum_52 / Decimal("52") if sum_52 else None
        distinct_weeks = _distinct_iso_weeks(txn_rows)
        confidence = _model_confidence(distinct_weeks)
        seasonal = _seasonal_index(txn_rows)

        _upsert_velocity_row(
            db,
            distributor_id=dist_id,
            product_id=product_id,
            customer_id=customer_id,
            computed_through_date=anchor,
            velocity_4wk=velocity_4wk,
            velocity_13wk=velocity_13wk,
            velocity_52wk=velocity_52wk,
            seasonal_index=seasonal,
            model_confidence=confidence,
            import_job_id=int(import_job_id),
        )
        upserted += 1

    return upserted
