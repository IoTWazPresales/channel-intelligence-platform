"""DSI distributor forecasts from ``fact_customer_velocity``."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.fact_customer_velocity import FactCustomerVelocity
from app.models.fact_dsi_forecast import FactDsiForecast

logger = logging.getLogger(__name__)

_CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}


def dsi_forecast_source_key(*, distributor_id: int, product_id: int, forecast_date: date) -> str:
    return f"dsi-forecast:{int(distributor_id)}:{int(product_id)}:{forecast_date.isoformat()}"


def _table_exists(session: Session, table_name: str) -> bool:
    from sqlalchemy import inspect as sa_inspect

    try:
        return bool(sa_inspect(session.get_bind()).has_table(table_name))
    except Exception:
        return False


def _pick_best_velocity_row(rows: list[FactCustomerVelocity]) -> FactCustomerVelocity:
    def _sort_key(row: FactCustomerVelocity) -> tuple[int, float]:
        conf = _CONFIDENCE_ORDER.get(str(row.model_confidence or "low"), 0)
        v52 = float(row.velocity_52wk or 0)
        return (conf, v52)

    return max(rows, key=_sort_key)


def _upsert_forecast_row(
    session: Session,
    *,
    distributor_id: int,
    product_id: int,
    forecast_date: date,
    forecast_units: Decimal,
    upper_band: Decimal,
    lower_band: Decimal,
    confidence_level: str,
    velocity_basis: str,
    import_job_id: int,
) -> None:
    source_key = dsi_forecast_source_key(
        distributor_id=distributor_id,
        product_id=product_id,
        forecast_date=forecast_date,
    )
    values = {
        "source_key": source_key,
        "distributor_id": int(distributor_id),
        "product_id": int(product_id),
        "forecast_date": forecast_date,
        "forecast_units": float(forecast_units),
        "upper_band": float(upper_band),
        "lower_band": float(lower_band),
        "confidence_level": confidence_level,
        "velocity_basis": velocity_basis,
        "generated_at": datetime.now(timezone.utc),
        "import_job_id": int(import_job_id),
    }
    tbl = FactDsiForecast.__table__
    stmt = pg_insert(tbl).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[tbl.c.source_key],
        set_={
            "forecast_units": stmt.excluded.forecast_units,
            "upper_band": stmt.excluded.upper_band,
            "lower_band": stmt.excluded.lower_band,
            "confidence_level": stmt.excluded.confidence_level,
            "velocity_basis": stmt.excluded.velocity_basis,
            "import_job_id": stmt.excluded.import_job_id,
            "generated_at": stmt.excluded.generated_at,
        },
    )
    session.execute(stmt)


def generate_distributor_forecasts(
    db: Session,
    distributor_id: int,
    import_job_id: int,
    *,
    weeks_ahead: int = 13,
) -> int:
    """Generate forward forecasts for products with medium/high velocity confidence."""
    if not _table_exists(db, "fact_dsi_forecast"):
        return 0

    dist_id = int(distributor_id)
    velocity_rows = list(
        db.scalars(
            select(FactCustomerVelocity).where(
                FactCustomerVelocity.distributor_id == dist_id,
                FactCustomerVelocity.model_confidence.in_(("medium", "high")),
            )
        ).all()
    )
    if not velocity_rows:
        return 0

    by_product: dict[int, list[FactCustomerVelocity]] = {}
    for row in velocity_rows:
        by_product.setdefault(int(row.product_id), []).append(row)

    upserted = 0
    for product_id, product_rows in by_product.items():
        best = _pick_best_velocity_row(product_rows)
        v52 = best.velocity_52wk
        if v52 is None or Decimal(str(v52)) <= 0:
            continue

        velocity_52 = Decimal(str(v52))
        seasonal = Decimal(str(best.seasonal_index or 1))
        base_velocity = velocity_52 * seasonal

        v4 = best.velocity_4wk
        if v4 is not None and velocity_52 > 0:
            v4_dec = Decimal(str(v4))
            if v4_dec > 0:
                variance_pct = abs(v4_dec - velocity_52) / velocity_52
            else:
                variance_pct = Decimal("0")
        else:
            variance_pct = Decimal("0")

        anchor = best.computed_through_date
        confidence_level = str(best.model_confidence)

        for week in range(1, weeks_ahead + 1):
            forecast_date = anchor + timedelta(days=week * 7)
            forecast_units = base_velocity
            upper_band = forecast_units * (Decimal("1") + variance_pct)
            lower_band = max(Decimal("0"), forecast_units * (Decimal("1") - variance_pct))
            _upsert_forecast_row(
                db,
                distributor_id=dist_id,
                product_id=int(product_id),
                forecast_date=forecast_date,
                forecast_units=forecast_units,
                upper_band=upper_band,
                lower_band=lower_band,
                confidence_level=confidence_level,
                velocity_basis="52wk*seasonal",
                import_job_id=int(import_job_id),
            )
            upserted += 1

    return upserted
