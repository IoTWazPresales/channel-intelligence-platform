"""B1 demand forecast — velocity method at native grain.

Projects ``fact_customer_velocity`` into ``fact_demand_forecast`` at
distributor × product × customer × period. Does **not** collapse the customer
axis (unlike ``generate_distributor_forecasts`` → ``fact_dsi_forecast``).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.fact_customer_velocity import FactCustomerVelocity
from app.models.fact_demand_forecast import FactDemandForecast

logger = logging.getLogger(__name__)


def demand_forecast_velocity_source_key(
    *,
    distributor_id: int,
    product_id: int,
    customer_id: int,
    period_start: date,
) -> str:
    return (
        f"demand-forecast:velocity:{int(distributor_id)}:{int(product_id)}:"
        f"{int(customer_id)}:{period_start.isoformat()}"
    )


def _table_exists(session: Session, table_name: str) -> bool:
    from sqlalchemy import inspect as sa_inspect

    try:
        return bool(sa_inspect(session.get_bind()).has_table(table_name))
    except Exception:
        return False


def _bands(
    *,
    forecast_units: Decimal,
    velocity_52: Decimal,
    velocity_4wk: Decimal | None,
) -> tuple[Decimal, Decimal, Decimal]:
    """Return (units, lower, upper) using 4wk-vs-52wk variance (SEMANTICS B1-03)."""
    if velocity_4wk is not None and velocity_52 > 0:
        v4 = Decimal(str(velocity_4wk))
        variance_pct = abs(v4 - velocity_52) / velocity_52 if v4 > 0 else Decimal("0")
    else:
        variance_pct = Decimal("0")
    upper = forecast_units * (Decimal("1") + variance_pct)
    lower = max(Decimal("0"), forecast_units * (Decimal("1") - variance_pct))
    return forecast_units, lower, upper


def generate_velocity_demand_forecasts(
    db: Session,
    *,
    distributor_id: int | None = None,
    weeks_ahead: int = 13,
    skip_overrides: bool = True,
) -> dict[str, int]:
    """Upsert velocity-method rows into ``fact_demand_forecast``.

    Returns counts: ``considered``, ``upserted``, ``skipped_override``, ``skipped_no_velocity``.
    """
    if not _table_exists(db, "fact_demand_forecast"):
        return {"considered": 0, "upserted": 0, "skipped_override": 0, "skipped_no_velocity": 0}
    if not _table_exists(db, "fact_customer_velocity"):
        return {"considered": 0, "upserted": 0, "skipped_override": 0, "skipped_no_velocity": 0}

    q = select(FactCustomerVelocity)
    if distributor_id is not None:
        q = q.where(FactCustomerVelocity.distributor_id == int(distributor_id))
    rows = list(db.scalars(q).all())

    considered = 0
    upserted = 0
    skipped_override = 0
    skipped_no_velocity = 0

    override_keys: set[tuple[int, int, int, date]] = set()
    if skip_overrides:
        ov_q = select(
            FactDemandForecast.distributor_id,
            FactDemandForecast.product_id,
            FactDemandForecast.customer_id,
            FactDemandForecast.period_start,
        ).where(FactDemandForecast.is_override.is_(True))
        if distributor_id is not None:
            ov_q = ov_q.where(FactDemandForecast.distributor_id == int(distributor_id))
        for d, p, c, per in db.execute(ov_q).all():
            override_keys.add((int(d), int(p), int(c), per))

    tbl = FactDemandForecast.__table__

    for row in rows:
        considered += 1
        v52 = row.velocity_52wk
        if v52 is None or Decimal(str(v52)) <= 0:
            skipped_no_velocity += 1
            continue

        velocity_52 = Decimal(str(v52))
        seasonal = Decimal(str(row.seasonal_index or 1))
        base = velocity_52 * seasonal
        units, lower, upper = _bands(
            forecast_units=base,
            velocity_52=velocity_52,
            velocity_4wk=Decimal(str(row.velocity_4wk)) if row.velocity_4wk is not None else None,
        )
        conf = str(row.model_confidence or "low")
        if conf not in {"low", "medium", "high"}:
            conf = "low"
        anchor = row.computed_through_date
        dist_id = int(row.distributor_id)
        prod_id = int(row.product_id)
        cust_id = int(row.customer_id)

        for week in range(1, weeks_ahead + 1):
            period_start = anchor + timedelta(days=week * 7)
            grain = (dist_id, prod_id, cust_id, period_start)
            if grain in override_keys:
                skipped_override += 1
                continue

            source_key = demand_forecast_velocity_source_key(
                distributor_id=dist_id,
                product_id=prod_id,
                customer_id=cust_id,
                period_start=period_start,
            )
            values = {
                "tenant_id": None,
                "distributor_id": dist_id,
                "product_id": prod_id,
                "customer_id": cust_id,
                "period_start": period_start,
                "forecast_units": float(units),
                "lower_band": float(lower),
                "upper_band": float(upper),
                "method": "velocity",
                "confidence_level": conf,
                "velocity_basis": "52wk*seasonal",
                "seasonal_index": float(seasonal),
                "analogue_product_id": None,
                "analogue_basis": None,
                "is_override": False,
                "source_key": source_key,
            }
            stmt = pg_insert(tbl).values(**values)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_fact_demand_forecast_grain",
                set_={
                    "forecast_units": stmt.excluded.forecast_units,
                    "lower_band": stmt.excluded.lower_band,
                    "upper_band": stmt.excluded.upper_band,
                    "method": stmt.excluded.method,
                    "confidence_level": stmt.excluded.confidence_level,
                    "velocity_basis": stmt.excluded.velocity_basis,
                    "seasonal_index": stmt.excluded.seasonal_index,
                    "source_key": stmt.excluded.source_key,
                    "is_override": False,
                },
                where=(tbl.c.is_override.is_(False)),
            )
            result = db.execute(stmt)
            # rowcount can be 0 when WHERE is_override blocked the update
            if result.rowcount:
                upserted += 1

    logger.info(
        "velocity demand forecasts considered=%s upserted=%s skipped_override=%s skipped_no_velocity=%s",
        considered,
        upserted,
        skipped_override,
        skipped_no_velocity,
    )
    return {
        "considered": considered,
        "upserted": upserted,
        "skipped_override": skipped_override,
        "skipped_no_velocity": skipped_no_velocity,
    }


def sum_rollup(
    db: Session,
    *,
    group_by: str,
    period_start: date | None = None,
) -> list[dict]:
    """Sum ``forecast_units`` by axis. ``group_by`` ∈ product|distributor|customer|period."""
    from sqlalchemy import func

    col_map = {
        "product": FactDemandForecast.product_id,
        "distributor": FactDemandForecast.distributor_id,
        "customer": FactDemandForecast.customer_id,
        "period": FactDemandForecast.period_start,
    }
    if group_by not in col_map:
        raise ValueError(f"Unsupported group_by {group_by!r}")
    key_col = col_map[group_by]
    q = select(
        key_col.label("key"),
        func.sum(FactDemandForecast.forecast_units).label("forecast_units"),
        func.count().label("row_count"),
    ).group_by(key_col)
    if period_start is not None:
        q = q.where(FactDemandForecast.period_start == period_start)
    rows = db.execute(q).all()
    return [
        {"key": r.key.isoformat() if hasattr(r.key, "isoformat") else r.key, "forecast_units": float(r.forecast_units or 0), "row_count": int(r.row_count)}
        for r in rows
    ]
