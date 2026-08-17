"""Read current weeks-of-cover from the observation series (BACKLOG-097).

Latest per (distributor, product): cover_as_of_date DESC, apply beats as_of_backfill
on ties, then observed_at DESC. No silent live-SQL fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import case, inspect as sa_inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.derived import WeeksOfCoverObservation


@dataclass(frozen=True)
class WocObservationRow:
    distributor_id: int
    product_id: int
    snapshot_date: date | None
    cover_as_of_date: date
    reported_soh: float
    sell_out_since: float
    landed_since: float
    derived_stock: float
    weekly_velocity: float | None
    weeks_of_cover: float | None
    replenishment_flag: bool
    replenishment_threshold_weeks: float
    trigger: str
    formula_version: str
    params: dict[str, Any]
    data_vintage: dict[str, Any]
    import_job_id: int | None


def _as_float(raw: Any) -> float:
    return float(raw or 0)


def _as_opt_float(raw: Any) -> float | None:
    if raw is None:
        return None
    return float(raw)


async def woc_observation_table_exists(db: AsyncSession) -> bool:
    try:
        conn = await db.connection()

        def _check(sync_conn: Any) -> bool:
            return bool(sa_inspect(sync_conn).has_table("weeks_of_cover_observation"))

        return bool(await conn.run_sync(_check))
    except Exception:
        return False


async def latest_woc_observations(
    db: AsyncSession,
    *,
    tenant_id: str | None = None,
    distributor_id: int | None = None,
    product_id: int | None = None,
) -> list[WocObservationRow]:
    """DISTINCT ON (distributor_id, product_id) current cover tape."""
    if not await woc_observation_table_exists(db):
        return []

    tid = (tenant_id or "default").strip() or "default"
    backfill_rank = case(
        (WeeksOfCoverObservation.trigger == "as_of_backfill", 1),
        else_=0,
    )
    stmt = (
        select(WeeksOfCoverObservation)
        .where(WeeksOfCoverObservation.tenant_id == tid)
        .distinct(
            WeeksOfCoverObservation.distributor_id,
            WeeksOfCoverObservation.product_id,
        )
        .order_by(
            WeeksOfCoverObservation.distributor_id,
            WeeksOfCoverObservation.product_id,
            WeeksOfCoverObservation.cover_as_of_date.desc(),
            backfill_rank.asc(),
            WeeksOfCoverObservation.observed_at.desc(),
        )
    )
    if distributor_id is not None:
        stmt = stmt.where(WeeksOfCoverObservation.distributor_id == int(distributor_id))
    if product_id is not None:
        stmt = stmt.where(WeeksOfCoverObservation.product_id == int(product_id))
    rows = (await db.scalars(stmt)).all()
    out: list[WocObservationRow] = []
    for row in rows:
        out.append(
            WocObservationRow(
                distributor_id=int(row.distributor_id),
                product_id=int(row.product_id),
                snapshot_date=row.snapshot_date,
                cover_as_of_date=row.cover_as_of_date,
                reported_soh=_as_float(row.reported_soh),
                sell_out_since=_as_float(row.sell_out_since),
                landed_since=_as_float(row.landed_since),
                derived_stock=_as_float(row.derived_stock),
                weekly_velocity=_as_opt_float(row.weekly_velocity),
                weeks_of_cover=_as_opt_float(row.weeks_of_cover),
                replenishment_flag=bool(row.replenishment_flag),
                replenishment_threshold_weeks=_as_float(row.replenishment_threshold_weeks),
                trigger=str(row.trigger),
                formula_version=str(row.formula_version),
                params=dict(row.params or {}),
                data_vintage=dict(row.data_vintage or {}),
                import_job_id=int(row.import_job_id) if row.import_job_id is not None else None,
            )
        )
    return out


def observations_to_stock_vel(
    rows: list[WocObservationRow],
) -> tuple[dict[tuple[int, int], float], dict[tuple[int, int], float]]:
    stock: dict[tuple[int, int], float] = {}
    vel: dict[tuple[int, int], float] = {}
    for row in rows:
        key = (row.distributor_id, row.product_id)
        stock[key] = row.derived_stock
        if row.weekly_velocity is not None:
            vel[key] = row.weekly_velocity
    return stock, vel
