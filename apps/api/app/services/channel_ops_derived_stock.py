"""Derived channel stock read model (CPOR Batch 2).

Formula (Warren-confirmed)::

    derived = latest reported SOH snapshot
            − DSI sell-out units with transaction_date > snapshot_date
            + fact_inbound_shipment units with pod_date > snapshot_date
              and line_state = 'shipped' (POD-landed only)

pipeline / open_order lines NEVER count. Variance vs the next reported snapshot
is surfaced as a FLAG — never silently corrected.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Sequence

from sqlalchemy import Select, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.facts import FactInboundShipment, FactInventoryDistributor, FactSalesSellout

# Align with dsi_soh_reconciliation FLAG band (detect-only; never auto-correct).
VARIANCE_FLAG_PCT = Decimal("0.10")
# Weeks-of-cover: treat near-zero velocity as n/a (avoid absurd cover numbers).
VELOCITY_NEAR_ZERO = Decimal("0.01")


@dataclass(frozen=True)
class DerivedStockComponents:
    distributor_id: int
    product_id: int
    snapshot_date: date | None
    reported_soh: Decimal
    sell_out_since: Decimal
    landed_since: Decimal
    derived_stock: Decimal


@dataclass(frozen=True)
class SnapshotVarianceFlag:
    """Reported-vs-derived at a later snapshot (FLAG only — never corrects)."""

    prior_snapshot_date: date
    next_snapshot_date: date
    reported_next: Decimal
    predicted_at_next: Decimal
    variance_units: Decimal
    variance_pct: Decimal | None
    flagged: bool


def compute_derived_stock(
    *,
    reported_soh: Decimal | float | int,
    sell_out_since: Decimal | float | int,
    landed_since: Decimal | float | int,
) -> Decimal:
    """Pure derived-stock arithmetic (unit-testable without DB)."""
    return (
        Decimal(str(reported_soh))
        - Decimal(str(sell_out_since))
        + Decimal(str(landed_since))
    )


def compute_snapshot_variance(
    *,
    reported_next: Decimal | float | int,
    predicted_at_next: Decimal | float | int,
    flag_pct: Decimal = VARIANCE_FLAG_PCT,
) -> tuple[Decimal, Decimal | None, bool]:
    """Return (variance_units, variance_pct|None, flagged).

    FLAG when |variance|/|predicted| > flag_pct (or when predicted is 0 and
    reported differs). Never mutates either number.
    """
    reported = Decimal(str(reported_next))
    predicted = Decimal(str(predicted_at_next))
    variance = reported - predicted
    if predicted == 0:
        pct: Decimal | None = None
        flagged = variance != 0
        return variance, pct, flagged
    pct = variance / abs(predicted)
    flagged = abs(pct) > flag_pct
    return variance, pct, flagged


def weeks_of_cover_or_none(
    stock: Decimal | float | int | None,
    velocity: Decimal | float | int | None,
    *,
    near_zero: Decimal = VELOCITY_NEAR_ZERO,
) -> float | None:
    """Return weeks of cover, or None when velocity is missing/near-zero."""
    if stock is None or velocity is None:
        return None
    vel = Decimal(str(velocity))
    if vel <= near_zero:
        return None
    return float(Decimal(str(stock)) / vel)


VELOCITY_WINDOW_DAYS = 364
VELOCITY_WEEK_DIVISOR = Decimal("52")


async def sellout_velocity_52wk_by_dist_product(
    db: AsyncSession,
    *,
    distributor_id: int | None = None,
) -> dict[tuple[int, int], float]:
    """Weekly avg sell-out units over 364d, grain distributor × product only.

    Matches DSI velocity window math (sum units in window / 52) without customer grain.
    """
    anchor_q = select(func.max(FactSalesSellout.transaction_date)).where(
        FactSalesSellout.distributor_id.isnot(None),
        FactSalesSellout.product_id.isnot(None),
    )
    if distributor_id is not None:
        anchor_q = anchor_q.where(FactSalesSellout.distributor_id == int(distributor_id))
    anchor = await db.scalar(anchor_q)
    if anchor is None:
        return {}

    window_start = anchor - timedelta(days=VELOCITY_WINDOW_DAYS)
    q = (
        select(
            FactSalesSellout.distributor_id,
            FactSalesSellout.product_id,
            func.coalesce(func.sum(FactSalesSellout.units), 0),
        )
        .where(
            FactSalesSellout.transaction_date >= window_start,
            FactSalesSellout.transaction_date <= anchor,
            FactSalesSellout.distributor_id.isnot(None),
            FactSalesSellout.product_id.isnot(None),
        )
        .group_by(FactSalesSellout.distributor_id, FactSalesSellout.product_id)
    )
    if distributor_id is not None:
        q = q.where(FactSalesSellout.distributor_id == int(distributor_id))
    rows = (await db.execute(q)).all()
    out: dict[tuple[int, int], float] = {}
    for dist_id, product_id, units in rows:
        if dist_id is None or product_id is None:
            continue
        total = Decimal(str(units or 0))
        if total <= 0:
            continue
        out[(int(dist_id), int(product_id))] = float(total / VELOCITY_WEEK_DIVISOR)
    return out


def yoy_pct_or_none(
    current: Decimal | float | int | None,
    prior: Decimal | float | int | None,
) -> float | None:
    """QoQ/YoY percentage with denominator sanity (zero/missing prior → None)."""
    if current is None or prior is None:
        return None
    p = Decimal(str(prior))
    if p <= 0:
        return None
    return float((Decimal(str(current)) - p) / p)


def _latest_snapshot_subquery(
    distributor_id: int | None = None,
) -> Select[Any]:
    """Distinct (distributor_id, product_id) with max(as_of_date)."""
    q = select(
        FactInventoryDistributor.distributor_id.label("distributor_id"),
        FactInventoryDistributor.product_id.label("product_id"),
        func.max(FactInventoryDistributor.as_of_date).label("snapshot_date"),
    ).group_by(
        FactInventoryDistributor.distributor_id,
        FactInventoryDistributor.product_id,
    )
    if distributor_id is not None:
        q = q.where(FactInventoryDistributor.distributor_id == int(distributor_id))
    return q.subquery()


def _shipped_landed_filter(
    distributor_id: int,
    product_id: int,
    snapshot_date: date,
):
    return and_(
        FactInboundShipment.distributor_id == int(distributor_id),
        FactInboundShipment.product_id == int(product_id),
        FactInboundShipment.pod_date.isnot(None),
        FactInboundShipment.pod_date > snapshot_date,
        func.lower(FactInboundShipment.line_state) == "shipped",
    )


def compute_derived_for_pair_sync(
    session: Session,
    *,
    distributor_id: int,
    product_id: int,
    as_of: date | None = None,
) -> DerivedStockComponents | None:
    """Sync read of derived stock for one (distributor, product)."""
    snap = session.execute(
        select(
            FactInventoryDistributor.as_of_date,
            FactInventoryDistributor.on_hand_units,
        )
        .where(
            FactInventoryDistributor.distributor_id == int(distributor_id),
            FactInventoryDistributor.product_id == int(product_id),
        )
        .order_by(FactInventoryDistributor.as_of_date.desc())
        .limit(1)
    ).one_or_none()
    if snap is None:
        return None
    snapshot_date: date = snap[0]
    reported = Decimal(str(snap[1] or 0))

    sell_q = select(func.coalesce(func.sum(FactSalesSellout.units), 0)).where(
        FactSalesSellout.distributor_id == int(distributor_id),
        FactSalesSellout.product_id == int(product_id),
        FactSalesSellout.transaction_date > snapshot_date,
    )
    if as_of is not None:
        sell_q = sell_q.where(FactSalesSellout.transaction_date <= as_of)
    sell_out = Decimal(str(session.scalar(sell_q) or 0))

    land_q = select(func.coalesce(func.sum(FactInboundShipment.quantity), 0)).where(
        _shipped_landed_filter(distributor_id, product_id, snapshot_date)
    )
    if as_of is not None:
        land_q = land_q.where(FactInboundShipment.pod_date <= as_of)
    landed = Decimal(str(session.scalar(land_q) or 0))

    return DerivedStockComponents(
        distributor_id=int(distributor_id),
        product_id=int(product_id),
        snapshot_date=snapshot_date,
        reported_soh=reported,
        sell_out_since=sell_out,
        landed_since=landed,
        derived_stock=compute_derived_stock(
            reported_soh=reported, sell_out_since=sell_out, landed_since=landed
        ),
    )


def variance_at_latest_snapshot_sync(
    session: Session,
    *,
    distributor_id: int,
    product_id: int,
) -> SnapshotVarianceFlag | None:
    """If ≥2 snapshots exist, FLAG reported-vs-derived at the latest date."""
    rows = session.execute(
        select(
            FactInventoryDistributor.as_of_date,
            FactInventoryDistributor.on_hand_units,
        )
        .where(
            FactInventoryDistributor.distributor_id == int(distributor_id),
            FactInventoryDistributor.product_id == int(product_id),
        )
        .order_by(FactInventoryDistributor.as_of_date.desc())
        .limit(2)
    ).all()
    if len(rows) < 2:
        return None
    next_date, reported_next_raw = rows[0][0], rows[0][1]
    prior_date, reported_prior_raw = rows[1][0], rows[1][1]
    reported_next = Decimal(str(reported_next_raw or 0))
    reported_prior = Decimal(str(reported_prior_raw or 0))

    sell_out = Decimal(
        str(
            session.scalar(
                select(func.coalesce(func.sum(FactSalesSellout.units), 0)).where(
                    FactSalesSellout.distributor_id == int(distributor_id),
                    FactSalesSellout.product_id == int(product_id),
                    FactSalesSellout.transaction_date > prior_date,
                    FactSalesSellout.transaction_date <= next_date,
                )
            )
            or 0
        )
    )
    landed = Decimal(
        str(
            session.scalar(
                select(func.coalesce(func.sum(FactInboundShipment.quantity), 0)).where(
                    FactInboundShipment.distributor_id == int(distributor_id),
                    FactInboundShipment.product_id == int(product_id),
                    FactInboundShipment.pod_date.isnot(None),
                    FactInboundShipment.pod_date > prior_date,
                    FactInboundShipment.pod_date <= next_date,
                    func.lower(FactInboundShipment.line_state) == "shipped",
                )
            )
            or 0
        )
    )
    predicted = compute_derived_stock(
        reported_soh=reported_prior, sell_out_since=sell_out, landed_since=landed
    )
    variance, pct, flagged = compute_snapshot_variance(
        reported_next=reported_next, predicted_at_next=predicted
    )
    return SnapshotVarianceFlag(
        prior_snapshot_date=prior_date,
        next_snapshot_date=next_date,
        reported_next=reported_next,
        predicted_at_next=predicted,
        variance_units=variance,
        variance_pct=pct,
        flagged=flagged,
    )


async def sum_derived_channel_stock(
    db: AsyncSession,
    *,
    distributor_id: int | None = None,
) -> tuple[int, int]:
    """Sum derived latest stock across (distributor, product).

    Returns (total_derived_units_rounded, pair_count).
    Never sums raw snapshots across periods.
    """
    latest = _latest_snapshot_subquery(distributor_id)
    inv_rows = (
        await db.execute(
            select(
                FactInventoryDistributor.distributor_id,
                FactInventoryDistributor.product_id,
                FactInventoryDistributor.as_of_date,
                FactInventoryDistributor.on_hand_units,
            ).join(
                latest,
                and_(
                    FactInventoryDistributor.distributor_id == latest.c.distributor_id,
                    FactInventoryDistributor.product_id == latest.c.product_id,
                    FactInventoryDistributor.as_of_date == latest.c.snapshot_date,
                ),
            )
        )
    ).all()
    if not inv_rows:
        return 0, 0

    total = Decimal("0")
    for dist_id, prod_id, snap_date, on_hand in inv_rows:
        reported = Decimal(str(on_hand or 0))
        sell_out = Decimal(
            str(
                await db.scalar(
                    select(func.coalesce(func.sum(FactSalesSellout.units), 0)).where(
                        FactSalesSellout.distributor_id == int(dist_id),
                        FactSalesSellout.product_id == int(prod_id),
                        FactSalesSellout.transaction_date > snap_date,
                    )
                )
                or 0
            )
        )
        landed = Decimal(
            str(
                await db.scalar(
                    select(func.coalesce(func.sum(FactInboundShipment.quantity), 0)).where(
                        _shipped_landed_filter(int(dist_id), int(prod_id), snap_date)
                    )
                )
                or 0
            )
        )
        total += compute_derived_stock(
            reported_soh=reported, sell_out_since=sell_out, landed_since=landed
        )
    return int(total), len(inv_rows)


async def derived_stock_rows_for_distributor(
    db: AsyncSession,
    *,
    distributor_id: int,
    product_id: int | None = None,
) -> list[dict[str, Any]]:
    """Per-product derived stock rows for Channel Ops inventory tab."""
    latest = _latest_snapshot_subquery(int(distributor_id))
    q = (
        select(
            FactInventoryDistributor.distributor_id,
            FactInventoryDistributor.product_id,
            FactInventoryDistributor.as_of_date,
            FactInventoryDistributor.on_hand_units,
            FactInventoryDistributor.calculated_soh,
            FactInventoryDistributor.soh_variance,
            FactInventoryDistributor.reconciliation_status,
        )
        .join(
            latest,
            and_(
                FactInventoryDistributor.distributor_id == latest.c.distributor_id,
                FactInventoryDistributor.product_id == latest.c.product_id,
                FactInventoryDistributor.as_of_date == latest.c.snapshot_date,
            ),
        )
        .where(FactInventoryDistributor.distributor_id == int(distributor_id))
    )
    if product_id is not None:
        q = q.where(FactInventoryDistributor.product_id == int(product_id))
    rows = (await db.execute(q)).all()
    out: list[dict[str, Any]] = []
    for r in rows:
        dist_id, prod_id, snap_date, on_hand = int(r[0]), int(r[1]), r[2], r[3]
        reported = Decimal(str(on_hand or 0))
        sell_out = Decimal(
            str(
                await db.scalar(
                    select(func.coalesce(func.sum(FactSalesSellout.units), 0)).where(
                        FactSalesSellout.distributor_id == dist_id,
                        FactSalesSellout.product_id == prod_id,
                        FactSalesSellout.transaction_date > snap_date,
                    )
                )
                or 0
            )
        )
        landed = Decimal(
            str(
                await db.scalar(
                    select(func.coalesce(func.sum(FactInboundShipment.quantity), 0)).where(
                        _shipped_landed_filter(dist_id, prod_id, snap_date)
                    )
                )
                or 0
            )
        )
        derived = compute_derived_stock(
            reported_soh=reported, sell_out_since=sell_out, landed_since=landed
        )
        out.append(
            {
                "distributor_id": dist_id,
                "product_id": prod_id,
                "snapshot_date": snap_date.isoformat() if snap_date else None,
                "reported_soh": float(reported),
                "sell_out_since": float(sell_out),
                "landed_since": float(landed),
                "derived_stock": float(derived),
                "calculated_soh": float(r[4]) if r[4] is not None else None,
                "variance_units": float(r[5]) if r[5] is not None else None,
                "reconciliation_status": r[6],
            }
        )
    return out


def format_validation_printout(
    db_name: str,
    rows: Sequence[DerivedStockComponents],
    variances: Sequence[SnapshotVarianceFlag | None],
) -> str:
    """Human-readable cip validation block for Batch 2 report."""
    lines = [f"current_database()={db_name}"]
    for comp, var in zip(rows, variances, strict=False):
        lines.append(
            f"dist={comp.distributor_id} product={comp.product_id} "
            f"snapshot={comp.snapshot_date} reported={comp.reported_soh} "
            f"sell_out_since={comp.sell_out_since} landed_since={comp.landed_since} "
            f"derived={comp.derived_stock}"
        )
        if var is not None:
            lines.append(
                f"  variance_flag prior={var.prior_snapshot_date}->{var.next_snapshot_date} "
                f"reported_next={var.reported_next} predicted={var.predicted_at_next} "
                f"var={var.variance_units} pct={var.variance_pct} flagged={var.flagged}"
            )
    return "\n".join(lines)
