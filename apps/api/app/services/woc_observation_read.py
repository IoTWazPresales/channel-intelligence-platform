"""Read current weeks-of-cover from the observation series (BACKLOG-097).

Latest per (distributor, product): cover_as_of_date DESC, apply beats as_of_backfill
on ties, then observed_at DESC. No silent live-SQL fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import case, inspect as sa_inspect, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

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


_WOC_TABLE_PRESENT: bool | None = None


async def woc_observation_table_exists(db: AsyncSession) -> bool:
    """True once the cover tape is present. A miss is not cached: tests create it later."""
    global _WOC_TABLE_PRESENT
    if _WOC_TABLE_PRESENT is True:
        return True
    try:
        conn = await db.connection()

        def _check(sync_conn: Any) -> bool:
            return bool(sa_inspect(sync_conn).has_table("weeks_of_cover_observation"))

        present = bool(await conn.run_sync(_check))
    except Exception:
        return False
    if present:
        _WOC_TABLE_PRESENT = True
    return present


def _backfill_rank(entity: Any):
    """Apply observations sort ahead of ``as_of_backfill`` when the cover date ties."""
    return case((entity.trigger == "as_of_backfill", 1), else_=0)


def _latest_from(
    *,
    tenant_id: str,
    distributor_id: int | None = None,
    product_id: int | None = None,
):
    """Pair list plus the one-row lateral. Callers choose which columns to read."""
    obs = WeeksOfCoverObservation
    filters = [obs.tenant_id == tenant_id]
    if distributor_id is not None:
        filters.append(obs.distributor_id == int(distributor_id))
    if product_id is not None:
        filters.append(obs.product_id == int(product_id))
    pairs = (
        select(obs.distributor_id, obs.product_id)
        .where(*filters)
        .distinct()
        .subquery("woc_pairs")
    )
    one = aliased(obs)
    lateral = (
        select(one)
        .where(
            one.tenant_id == tenant_id,
            one.distributor_id == pairs.c.distributor_id,
            one.product_id == pairs.c.product_id,
        )
        .order_by(
            one.distributor_id,
            one.product_id,
            one.cover_as_of_date.desc(),
            _backfill_rank(one).asc(),
            one.observed_at.desc(),
        )
        .limit(1)
        .lateral("woc_latest")
    )
    picked = aliased(obs, lateral)
    return pairs, lateral, picked


def latest_woc_observation_stmt(
    *,
    tenant_id: str,
    distributor_id: int | None = None,
    product_id: int | None = None,
):
    """Latest row per distributor×product without sorting the whole wide tape.

    ``ix_woc_observation_current`` lists the pairs (tenant, distributor, product).
    A LATERAL limit 1 then keeps the same row DISTINCT ON kept: cover date
    descending, an apply row ahead of an as-of backfill, then observed_at
    descending. The pair list is narrow; only the winning row is read in full.
    """
    pairs, lateral, picked = _latest_from(
        tenant_id=tenant_id,
        distributor_id=distributor_id,
        product_id=product_id,
    )
    return (
        select(picked)
        .select_from(pairs)
        .join(lateral, true())
        .order_by(pairs.c.distributor_id, pairs.c.product_id)
    )


def latest_woc_stock_stmt(
    *,
    tenant_id: str,
    distributor_id: int | None = None,
    product_id: int | None = None,
):
    """Stock and velocity of the latest row. The brief does not need the rest of the tape."""
    pairs, lateral, picked = _latest_from(
        tenant_id=tenant_id,
        distributor_id=distributor_id,
        product_id=product_id,
    )
    return (
        select(
            picked.distributor_id,
            picked.product_id,
            picked.derived_stock,
            picked.weekly_velocity,
        )
        .select_from(pairs)
        .join(lateral, true())
    )


async def latest_woc_observations(
    db: AsyncSession,
    *,
    tenant_id: str | None = None,
    distributor_id: int | None = None,
    product_id: int | None = None,
) -> list[WocObservationRow]:
    """Current cover tape: one observation per (distributor, product)."""
    if not await woc_observation_table_exists(db):
        return []

    tid = (tenant_id or "default").strip() or "default"
    stmt = latest_woc_observation_stmt(
        tenant_id=tid,
        distributor_id=distributor_id,
        product_id=product_id,
    )
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


async def latest_woc_stock_velocity(
    db: AsyncSession,
    *,
    tenant_id: str | None = None,
) -> list[tuple[int, int, float, float | None]]:
    """Latest derived stock and weekly velocity per distributor×product."""
    if not await woc_observation_table_exists(db):
        return []
    tid = (tenant_id or "default").strip() or "default"
    rows = (await db.execute(latest_woc_stock_stmt(tenant_id=tid))).all()
    return [
        (int(row.distributor_id), int(row.product_id), _as_float(row.derived_stock), _as_opt_float(row.weekly_velocity))
        for row in rows
    ]


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
