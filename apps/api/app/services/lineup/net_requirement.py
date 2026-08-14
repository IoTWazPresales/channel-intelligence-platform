"""B2 net-requirement planning math (distributor × product grain).

Domain (COMMERCIAL_DOMAIN_RULES §3)::

    lineup qty = forecast demand
               − channel stock on hand
               − in-transit
               + target cover

A3 stock is distributor × product — forecast is rolled up to that grain before
subtraction (COMMERCIAL_SEMANTICS §4.5 B2 note). Customer share is retained as
an allocation hint only, never used to subtract stock atomically.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fact_demand_forecast import FactDemandForecast
from app.models.facts import FactInboundShipment
from app.services.channel_ops_config import REPLENISHMENT_WOC_THRESHOLD_WEEKS
from app.services.channel_ops_derived_stock import (
    derived_stock_by_dist_product,
    sellout_velocity_52wk_by_dist_product,
)
from app.services.lineup.cover_policy import (
    COVER_SOURCE_OVERRIDE,
    COVER_SOURCE_TENANT_DEFAULT,
    TENANT_DEFAULT_COVER_WEEKS,
    load_cover_weeks_by_customer,
    share_weighted_cover_weeks,
)

# Default target cover weeks — TENANT-VARIABLE (domain §3.2); query override allowed.
DEFAULT_TARGET_COVER_WEEKS = float(REPLENISHMENT_WOC_THRESHOLD_WEEKS)

_OPEN_PO_LINE_STATES = frozenset({"open_order", "pipeline"})


@dataclass(frozen=True)
class NetRequirementInputs:
    forecast_demand: float
    channel_stock: float
    in_transit: float
    target_cover_units: float
    bias_factor: float = 0.0  # mean signed (shipped-planned)/planned; applied to forecast


@dataclass(frozen=True)
class NetRequirementResult:
    forecast_demand: float
    bias_adjusted_forecast: float
    channel_stock: float
    in_transit: float
    target_cover_units: float
    net_requirement: float
    formula: str


def compute_net_requirement(inputs: NetRequirementInputs) -> NetRequirementResult:
    """Pure net-requirement arithmetic (unit-testable). Floor at zero."""
    bias = float(inputs.bias_factor or 0.0)
    # Positive bias = historically over-shipped vs plan → inflate next plan.
    adjusted = max(0.0, float(inputs.forecast_demand) * (1.0 + bias))
    raw = (
        adjusted
        - float(inputs.channel_stock)
        - float(inputs.in_transit)
        + float(inputs.target_cover_units)
    )
    net = max(0.0, raw)
    return NetRequirementResult(
        forecast_demand=float(inputs.forecast_demand),
        bias_adjusted_forecast=round(adjusted, 4),
        channel_stock=float(inputs.channel_stock),
        in_transit=float(inputs.in_transit),
        target_cover_units=float(inputs.target_cover_units),
        net_requirement=round(net, 4),
        formula=(
            "max(0, bias_adjusted_forecast − channel_stock − in_transit + target_cover); "
            "bias_adjusted_forecast = forecast × (1 + bias_factor)"
        ),
    )


def _period_end(horizon_weeks: int, *, as_of: date) -> date:
    return as_of + timedelta(weeks=max(1, int(horizon_weeks)))


async def _forecast_rollup_dist_product(
    db: AsyncSession,
    *,
    period_from: date,
    period_to: date,
    distributor_id: int | None = None,
    product_id: int | None = None,
) -> dict[tuple[int, int], float]:
    """Σ forecast_units by (distributor_id, product_id) over period window."""
    stmt = (
        select(
            FactDemandForecast.distributor_id,
            FactDemandForecast.product_id,
            func.coalesce(func.sum(FactDemandForecast.forecast_units), 0),
        )
        .where(
            FactDemandForecast.period_start >= period_from,
            FactDemandForecast.period_start < period_to,
        )
        .group_by(FactDemandForecast.distributor_id, FactDemandForecast.product_id)
    )
    if distributor_id is not None:
        stmt = stmt.where(FactDemandForecast.distributor_id == int(distributor_id))
    if product_id is not None:
        stmt = stmt.where(FactDemandForecast.product_id == int(product_id))
    rows = (await db.execute(stmt)).all()
    return {(int(d), int(p)): float(u or 0) for d, p, u in rows}


async def _customer_forecast_shares(
    db: AsyncSession,
    *,
    period_from: date,
    period_to: date,
    pairs: set[tuple[int, int]],
) -> dict[tuple[int, int], list[dict[str, Any]]]:
    """Per (dist, product): customer shares of forecast (allocation hint only)."""
    if not pairs:
        return {}
    dist_ids = {d for d, _ in pairs}
    prod_ids = {p for _, p in pairs}
    stmt = (
        select(
            FactDemandForecast.distributor_id,
            FactDemandForecast.product_id,
            FactDemandForecast.customer_id,
            func.coalesce(func.sum(FactDemandForecast.forecast_units), 0),
        )
        .where(
            FactDemandForecast.period_start >= period_from,
            FactDemandForecast.period_start < period_to,
            FactDemandForecast.distributor_id.in_(dist_ids),
            FactDemandForecast.product_id.in_(prod_ids),
        )
        .group_by(
            FactDemandForecast.distributor_id,
            FactDemandForecast.product_id,
            FactDemandForecast.customer_id,
        )
    )
    rows = (await db.execute(stmt)).all()
    by_pair: dict[tuple[int, int], list[tuple[int, float]]] = {}
    for d, p, c, u in rows:
        key = (int(d), int(p))
        if key not in pairs:
            continue
        by_pair.setdefault(key, []).append((int(c), float(u or 0)))

    out: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for key, parts in by_pair.items():
        total = sum(u for _, u in parts) or 0.0
        shares: list[dict[str, Any]] = []
        for cid, units in sorted(parts, key=lambda x: -x[1]):
            shares.append(
                {
                    "customer_id": cid,
                    "forecast_units": units,
                    "share": (units / total) if total > 0 else 0.0,
                }
            )
        out[key] = shares
    return out


async def _in_transit_by_dist_product(
    db: AsyncSession,
    *,
    distributor_id: int | None = None,
    product_id: int | None = None,
) -> dict[tuple[int, int], float]:
    """Shipped-not-landed + open-order/pipeline, only where purchase_order_id is set.

    Domain §3.3: no PO → no in-transit contribution.
    """
    dist_col = func.coalesce(
        FactInboundShipment.resolved_distributor_id,
        FactInboundShipment.distributor_id,
    )
    shipped_not_landed = and_(
        FactInboundShipment.line_state == "shipped",
        FactInboundShipment.pod_date.is_(None),
    )
    open_po = FactInboundShipment.line_state.in_(tuple(_OPEN_PO_LINE_STATES))
    stmt = (
        select(
            dist_col.label("distributor_id"),
            FactInboundShipment.product_id,
            func.coalesce(func.sum(FactInboundShipment.quantity), 0),
        )
        .where(
            FactInboundShipment.purchase_order_id.is_not(None),
            FactInboundShipment.product_id.is_not(None),
            dist_col.is_not(None),
            or_(shipped_not_landed, open_po),
        )
        .group_by(dist_col, FactInboundShipment.product_id)
    )
    if distributor_id is not None:
        stmt = stmt.where(dist_col == int(distributor_id))
    if product_id is not None:
        stmt = stmt.where(FactInboundShipment.product_id == int(product_id))
    rows = (await db.execute(stmt)).all()
    return {(int(d), int(p)): float(u or 0) for d, p, u in rows if d is not None and p is not None}


async def build_net_requirement_rows(
    db: AsyncSession,
    *,
    horizon_weeks: int = 13,
    target_cover_weeks: float | None = None,
    as_of: date | None = None,
    distributor_id: int | None = None,
    product_id: int | None = None,
    bias_by_bu: dict[str, float] | None = None,
    product_bu: dict[int, str] | None = None,
    include_customer_shares: bool = True,
    limit: int = 500,
) -> dict[str, Any]:
    """Read model: net requirement at distributor × product for the horizon.

    ``target_cover_weeks`` None = per-customer cover policy (D-045).
    An explicit number is an override for every customer (``cover_override``).
    Dist×product cover units = share-weighted weeks × weekly velocity.
    """
    as_of = as_of or date.today()
    period_to = _period_end(horizon_weeks, as_of=as_of)
    cover_override = target_cover_weeks is not None
    fallback_weeks = (
        float(target_cover_weeks) if cover_override else TENANT_DEFAULT_COVER_WEEKS
    )
    fallback_source = COVER_SOURCE_OVERRIDE if cover_override else COVER_SOURCE_TENANT_DEFAULT

    forecast_map = await _forecast_rollup_dist_product(
        db,
        period_from=as_of,
        period_to=period_to,
        distributor_id=distributor_id,
        product_id=product_id,
    )
    stock_map = await derived_stock_by_dist_product(db, distributor_id=distributor_id)
    stock_f = {k: float(v) for k, v in stock_map.items()}
    if product_id is not None:
        stock_f = {k: v for k, v in stock_f.items() if k[1] == int(product_id)}

    transit_map = await _in_transit_by_dist_product(
        db, distributor_id=distributor_id, product_id=product_id
    )
    vel_map = await sellout_velocity_52wk_by_dist_product(db, distributor_id=distributor_id)
    vel_f = {k: float(v) for k, v in vel_map.items()}
    if product_id is not None:
        vel_f = {k: v for k, v in vel_f.items() if k[1] == int(product_id)}

    keys = set(forecast_map) | set(stock_f) | set(transit_map)
    if product_id is not None:
        keys = {k for k in keys if k[1] == int(product_id)}
    if distributor_id is not None:
        keys = {k for k in keys if k[0] == int(distributor_id)}

    # Always load shares for cover weighting (D-045), even when the payload omits allocation.
    shares_map: dict[tuple[int, int], list[dict[str, Any]]] = {}
    if keys:
        shares_map = await _customer_forecast_shares(
            db, period_from=as_of, period_to=period_to, pairs=keys
        )
    customer_ids = {int(s["customer_id"]) for parts in shares_map.values() for s in parts}
    cover_by_customer = await load_cover_weeks_by_customer(
        db, customer_ids, override_weeks=target_cover_weeks
    )

    bias_by_bu = bias_by_bu or {}
    product_bu = product_bu or {}

    rows: list[dict[str, Any]] = []
    for key in sorted(keys, key=lambda k: (-forecast_map.get(k, 0.0), k[0], k[1])):
        did, pid = key
        fc = forecast_map.get(key, 0.0)
        stock = stock_f.get(key, 0.0)
        transit = transit_map.get(key, 0.0)
        weekly = vel_f.get(key, 0.0)
        shares = shares_map.get(key, [])
        row_weeks, cover_source = share_weighted_cover_weeks(
            shares,
            cover_by_customer,
            fallback_weeks=fallback_weeks,
            fallback_source=fallback_source,
        )
        target_units = float(row_weeks) * weekly
        bu = product_bu.get(pid)
        bias = float(bias_by_bu.get(bu, 0.0)) if bu else 0.0
        result = compute_net_requirement(
            NetRequirementInputs(
                forecast_demand=fc,
                channel_stock=stock,
                in_transit=transit,
                target_cover_units=target_units,
                bias_factor=bias,
            )
        )
        row: dict[str, Any] = {
            "distributor_id": did,
            "product_id": pid,
            "business_unit": bu,
            "horizon_weeks": int(horizon_weeks),
            "period_from": as_of.isoformat(),
            "period_to": period_to.isoformat(),
            "target_cover_weeks": round(float(row_weeks), 4),
            "cover_source": cover_source,
            "cover_override": cover_override,
            "weekly_velocity": weekly,
            "bias_factor": bias,
            "forecast_demand": result.forecast_demand,
            "bias_adjusted_forecast": result.bias_adjusted_forecast,
            "channel_stock": result.channel_stock,
            "in_transit": result.in_transit,
            "target_cover_units": round(result.target_cover_units, 4),
            "net_requirement": result.net_requirement,
            "grain": "distributor_product",
        }
        if include_customer_shares:
            allocated: list[dict[str, Any]] = []
            for s in shares:
                cid = int(s["customer_id"])
                c_weeks, c_src = cover_by_customer.get(
                    cid, (fallback_weeks, fallback_source)
                )
                allocated.append(
                    {
                        **s,
                        "target_cover_weeks": float(c_weeks),
                        "cover_source": c_src,
                        "suggested_lineup_units": round(
                            result.net_requirement * float(s["share"]), 4
                        ),
                    }
                )
            row["customer_allocation"] = allocated
        rows.append(row)
        if len(rows) >= int(limit):
            break

    return {
        "as_of": as_of.isoformat(),
        "horizon_weeks": int(horizon_weeks),
        "target_cover_weeks": (
            float(target_cover_weeks) if cover_override else TENANT_DEFAULT_COVER_WEEKS
        ),
        "cover_override": cover_override,
        "cover_policy": {
            "tenant_default_weeks": TENANT_DEFAULT_COVER_WEEKS,
            "override": cover_override,
            "override_weeks": float(target_cover_weeks) if cover_override else None,
        },
        "grain": "distributor_product",
        "row_count": len(rows),
        "formula": (
            "net = max(0, forecast×(1+bias) − derived_stock − in_transit(PO-linked) "
            "+ share_weighted_cover_weeks×weekly_velocity); stock subtract at dist×product only"
        ),
        "in_transit_rule": (
            "shipped∧pod_date IS NULL OR line_state∈{open_order,pipeline}; "
            "purchase_order_id required"
        ),
        "rows": rows,
        "data_unavailable": False,
    }
