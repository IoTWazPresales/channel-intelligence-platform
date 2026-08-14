"""Intake-weighted MAC composer (Unit 15A / D-042–D-044, D-049–D-050).

Lives in the CPOR cost engine: reuses `_tier1_cst` / `suggest_cost_basis` fallback
and `detect_cost_basis_drift`. Suggested MAC blend is CST on-hand + in-window
PO-linked inbound `unit_price` only.

Not in the blend:
- DSI sell-out Amount (display `sellout_value_display_only`)
- buy-plan / lineup qty (display `planned_supply_no_native_cost`)
- disti WAC / Total Average Cost (not ingested — display proxy from inbound
  unit_price with `dsi_wac_not_ingested` + `disti_cost_is_intake_proxy`)
- DAP

Approved `cost_basis` is never rewritten here.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.facts import FactBuyPlan, FactInboundShipment, FactSalesSellout
from app.models.lineup import FactLineupPlanItem
from app.services.channel_ops_derived_stock import compute_derived_for_pair_sync
from app.services.cpor.cost_suggestion import (
    CostSuggestion,
    _tier1_cst,
    suggest_cost_basis,
)
from app.services.cpor.waterfall import _as_decimal


def _f(value: Decimal | float | int | None) -> float | None:
    if value is None:
        return None
    return float(_as_decimal(value))


def _leg(
    *,
    qty: Decimal | float | int,
    unit_cost: Decimal | float | int | None,
    as_of: date | None,
    flags: list[str],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "qty": float(_as_decimal(qty)),
        "unit_cost": _f(unit_cost) if unit_cost is not None else None,
        "as_of": as_of.isoformat() if as_of else None,
        "flags": list(flags),
    }
    if extra:
        out.update(extra)
    return out


def _on_hand_qty(
    session: Session,
    *,
    distributor_id: int | None,
    product_id: int,
    as_of: date,
) -> tuple[Decimal, date | None, list[str]]:
    """Bucket A qty = A3 derived disti SOH. Never retailer reported_soh."""
    flags: list[str] = []
    if distributor_id is None:
        flags.append("no_soh_evidence")
        return Decimal("0"), None, flags
    components = compute_derived_for_pair_sync(
        session,
        distributor_id=int(distributor_id),
        product_id=int(product_id),
        as_of=as_of,
    )
    if components is None:
        flags.append("no_soh_evidence")
        return Decimal("0"), None, flags
    qty = components.derived_stock
    if qty <= 0:
        flags.append("no_soh_evidence")
        return Decimal("0"), components.snapshot_date, flags
    return qty, components.snapshot_date, flags


def _intake_wavg(
    session: Session,
    *,
    distributor_id: int | None,
    product_id: int,
    window_start: date,
    window_end: date,
) -> tuple[Decimal, Decimal | None, date | None, list[str]]:
    """Bucket B: PO-linked inbound unit_price with landing date in the promo window."""
    flags: list[str] = []
    landing = func.coalesce(
        FactInboundShipment.pod_date,
        FactInboundShipment.est_pod_date,
        FactInboundShipment.erd_date,
    )
    dist_col = func.coalesce(
        FactInboundShipment.resolved_distributor_id,
        FactInboundShipment.distributor_id,
    )
    clauses = [
        FactInboundShipment.purchase_order_id.is_not(None),
        FactInboundShipment.product_id == int(product_id),
        FactInboundShipment.unit_price.is_not(None),
        FactInboundShipment.unit_price > 0,
        FactInboundShipment.quantity.is_not(None),
        FactInboundShipment.quantity > 0,
        landing.is_not(None),
        landing >= window_start,
        landing <= window_end,
    ]
    if distributor_id is not None:
        clauses.append(dist_col == int(distributor_id))
    rows = session.execute(
        select(
            FactInboundShipment.quantity,
            FactInboundShipment.unit_price,
            landing.label("landing_date"),
        ).where(and_(*clauses))
    ).all()
    if not rows:
        flags.append("no_intake_evidence")
        return Decimal("0"), None, None, flags

    num = Decimal("0")
    den = Decimal("0")
    min_d: date | None = None
    max_d: date | None = None
    for qty_raw, price_raw, landing_date in rows:
        qty = _as_decimal(qty_raw)
        price = _as_decimal(price_raw)
        num += qty * price
        den += qty
        if landing_date is not None:
            if min_d is None or landing_date < min_d:
                min_d = landing_date
            if max_d is None or landing_date > max_d:
                max_d = landing_date
    if den <= 0:
        flags.append("no_intake_evidence")
        return Decimal("0"), None, None, flags
    flags.append("intake_is_oem_sell_in_evidence")
    as_of = max_d or min_d
    return den, (num / den), as_of, flags


def _forward_supply_qty(
    session: Session,
    *,
    distributor_id: int | None,
    product_id: int,
    window_start: date,
    window_end: date,
) -> Decimal:
    """Buy-plan + lineup planned qty overlapping the window. Display only."""
    buy_clauses = [
        FactBuyPlan.product_id == int(product_id),
        FactBuyPlan.recommended_window_start <= window_end,
        FactBuyPlan.recommended_window_end >= window_start,
    ]
    if distributor_id is not None:
        buy_clauses.append(
            or_(
                FactBuyPlan.distributor_id == int(distributor_id),
                FactBuyPlan.distributor_id.is_(None),
            )
        )
    buy = session.scalar(
        select(func.coalesce(func.sum(FactBuyPlan.recommended_qty), 0)).where(and_(*buy_clauses))
    )
    lineup_clauses = [
        FactLineupPlanItem.product_id == int(product_id),
        FactLineupPlanItem.period_start >= window_start,
        FactLineupPlanItem.period_start <= window_end,
    ]
    lineup = session.scalar(
        select(func.coalesce(func.sum(FactLineupPlanItem.planned_volume_units), 0)).where(
            and_(*lineup_clauses)
        )
    )
    return _as_decimal(buy) + _as_decimal(lineup)


def _latest_sellout_unit_amount(
    session: Session,
    *,
    distributor_id: int | None,
    product_id: int,
    as_of: date,
) -> tuple[Decimal | None, date | None]:
    """Latest disti→customer sell-out Amount. Never cost."""
    stmt = (
        select(
            FactSalesSellout.unit_sellout_price_ex_tax_amount,
            FactSalesSellout.transaction_date,
        )
        .where(
            FactSalesSellout.product_id == int(product_id),
            FactSalesSellout.unit_sellout_price_ex_tax_amount.is_not(None),
            FactSalesSellout.transaction_date <= as_of,
        )
        .order_by(FactSalesSellout.transaction_date.desc(), FactSalesSellout.id.desc())
        .limit(1)
    )
    if distributor_id is not None:
        stmt = stmt.where(FactSalesSellout.distributor_id == int(distributor_id))
    row = session.execute(stmt).first()
    if row is None or row[0] is None:
        return None, None
    return _as_decimal(row[0]), row[1]


def _disti_cost_proxy_wavg(
    session: Session,
    *,
    distributor_id: int | None,
    product_id: int,
) -> tuple[Decimal | None, date | None, list[str]]:
    """Inbound unit_price WAVG as a stand-in for uningested disti WAC.

    Display / support-promise leg only — never blended into suggested MAC.
    """
    flags = ["dsi_wac_not_ingested"]
    if distributor_id is None:
        return None, None, flags
    dist_col = func.coalesce(
        FactInboundShipment.resolved_distributor_id,
        FactInboundShipment.distributor_id,
    )
    rows = session.execute(
        select(
            FactInboundShipment.quantity,
            FactInboundShipment.unit_price,
            FactInboundShipment.pod_date,
        ).where(
            dist_col == int(distributor_id),
            FactInboundShipment.product_id == int(product_id),
            FactInboundShipment.purchase_order_id.is_not(None),
            FactInboundShipment.unit_price.is_not(None),
            FactInboundShipment.unit_price > 0,
            FactInboundShipment.quantity.is_not(None),
            FactInboundShipment.quantity > 0,
        )
    ).all()
    if not rows:
        return None, None, flags
    num = Decimal("0")
    den = Decimal("0")
    max_pod: date | None = None
    for qty_raw, price_raw, pod in rows:
        qty = _as_decimal(qty_raw)
        num += qty * _as_decimal(price_raw)
        den += qty
        if pod is not None and (max_pod is None or pod > max_pod):
            max_pod = pod
    if den <= 0:
        return None, None, flags
    flags.append("disti_cost_is_intake_proxy")
    return num / den, max_pod, flags


def _blend(
    parts: list[tuple[Decimal, Decimal]],
) -> Decimal | None:
    num = Decimal("0")
    den = Decimal("0")
    for qty, cost in parts:
        if qty > 0 and cost is not None:
            num += qty * cost
            den += qty
    if den <= 0:
        return None
    return num / den


def suggest_intake_weighted_mac(
    session: Session,
    *,
    customer_id: int,
    product_id: int,
    distributor_id: int | None,
    window_start: date,
    window_end: date,
    as_of: date | None = None,
    exclude_case_id: int | None = None,
) -> CostSuggestion:
    """Suggested MAC = (Aq·CST_MAC + Bq·inbound_unit_price) / (Aq+Bq).

    Empty B → `suggest_cost_basis` + `no_intake_evidence`. Display legs are
    evidence-only and never enter `cost_basis`.
    """
    as_of = as_of or date.today()
    flags: list[str] = []

    qty_a, as_of_a, flags_a = _on_hand_qty(
        session, distributor_id=distributor_id, product_id=product_id, as_of=as_of
    )
    flags.extend(flags_a)

    t1 = _tier1_cst(session, customer_id=customer_id, product_id=product_id, as_of=as_of)
    cst_mac = t1.cost_basis if t1 is not None else None
    cst_as_of = None
    if t1 is not None and t1.evidence.get("as_of"):
        try:
            cst_as_of = date.fromisoformat(str(t1.evidence["as_of"]))
        except ValueError:
            cst_as_of = as_of_a
    if cst_mac is None:
        flags.append("no_cst_mac")
    if qty_a > 0:
        flags.append("cross_grain_valuation")

    qty_b, cost_b, as_of_b, flags_b = _intake_wavg(
        session,
        distributor_id=distributor_id,
        product_id=product_id,
        window_start=window_start,
        window_end=window_end,
    )
    flags.extend(flags_b)

    bucket_a = _leg(
        qty=qty_a,
        unit_cost=cst_mac,
        as_of=as_of_a or cst_as_of,
        flags=[f for f in flags_a] + (["cross_grain_valuation"] if qty_a > 0 else [])
        + (["no_cst_mac"] if cst_mac is None else []),
        extra={
            "cost_field": t1.evidence.get("field_used") if t1 else None,
            "grain": "distributor_product_qty_x_customer_cst_mac",
        },
    )
    bucket_b = _leg(
        qty=qty_b,
        unit_cost=cost_b,
        as_of=as_of_b,
        flags=list(flags_b),
        extra={"cost_field": "fact_inbound_shipment.unit_price"},
    )

    supply_qty = _forward_supply_qty(
        session,
        distributor_id=distributor_id,
        product_id=product_id,
        window_start=window_start,
        window_end=window_end,
    )
    planned_flags = ["planned_supply_no_native_cost"]
    planned_leg = _leg(
        qty=supply_qty,
        unit_cost=cst_mac,
        as_of=cst_as_of,
        flags=planned_flags,
        extra={"role": "display_supply"},
    )

    sellout_unit, sellout_as_of = _latest_sellout_unit_amount(
        session, distributor_id=distributor_id, product_id=product_id, as_of=as_of
    )
    sellout_value = (qty_a * sellout_unit) if (qty_a > 0 and sellout_unit is not None) else None
    sellout_flags = ["sellout_value_display_only"] if sellout_unit is not None else []
    sellout_leg = {
        "qty": float(qty_a),
        "unit_amount": _f(sellout_unit),
        "value": _f(sellout_value),
        "as_of": sellout_as_of.isoformat() if sellout_as_of else None,
        "flags": sellout_flags,
        "field": "unit_sellout_price_ex_tax_amount",
        "role": "display_value",
    }
    flags.extend(sellout_flags)

    proxy, proxy_as_of, proxy_flags = _disti_cost_proxy_wavg(
        session, distributor_id=distributor_id, product_id=product_id
    )
    flags.extend(proxy_flags)
    indicative_gap = None
    if sellout_unit is not None and proxy is not None:
        indicative_gap = sellout_unit - proxy
    disti_cost_leg = {
        "unit_cost_proxy": _f(proxy),
        "as_of": proxy_as_of.isoformat() if proxy_as_of else None,
        "flags": list(proxy_flags),
        "role": "display_support_promise",
        "indicative_gap_vs_sellout_amount": _f(indicative_gap),
        "note": "Disti WAC is not ingested; inbound unit_price WAVG is a proxy only.",
    }

    blend_parts: list[tuple[Decimal, Decimal]] = []
    if qty_a > 0 and cst_mac is not None:
        blend_parts.append((qty_a, cst_mac))
    if qty_b > 0 and cost_b is not None:
        blend_parts.append((qty_b, cost_b))

    blended = _blend(blend_parts)
    collapsed_to_snapshot = qty_b <= 0
    snapshot: CostSuggestion | None = None
    if collapsed_to_snapshot:
        snapshot = suggest_cost_basis(
            session,
            customer_id=customer_id,
            product_id=product_id,
            as_of=as_of,
            exclude_case_id=exclude_case_id,
        )
        cost_basis = snapshot.cost_basis
        cost_source = snapshot.cost_source
        flags.extend(snapshot.flags)
        if "no_intake_evidence" not in flags:
            flags.append("no_intake_evidence")
    else:
        cost_basis = blended
        cost_source = "intake_weighted" if blended is not None else None
        if blended is None:
            snapshot = suggest_cost_basis(
                session,
                customer_id=customer_id,
                product_id=product_id,
                as_of=as_of,
                exclude_case_id=exclude_case_id,
            )
            cost_basis = snapshot.cost_basis
            cost_source = snapshot.cost_source
            flags.extend(snapshot.flags)

    # Dedupe flags, preserve order
    seen: set[str] = set()
    ordered_flags: list[str] = []
    for f in flags:
        if f not in seen:
            seen.add(f)
            ordered_flags.append(f)

    evidence: dict[str, Any] = {
        "composer": "intake_weighted_mac",
        "as_of": as_of.isoformat(),
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "bucket_a_on_hand": bucket_a,
        "bucket_b_intake": bucket_b,
        "planned_supply": planned_leg,
        "sellout_value": sellout_leg,
        "disti_cost": disti_cost_leg,
        "blend": {
            "formula": "(Aq·CST_MAC + Bq·inbound_unit_price) / (Aq+Bq)",
            "cost_basis": _f(cost_basis),
            "collapsed_to_snapshot": collapsed_to_snapshot,
        },
        "not_in_blend": [
            "sellout_value_display_only",
            "planned_supply_no_native_cost",
            "dsi_wac_not_ingested",
            "dap",
        ],
    }
    if t1 is not None:
        evidence["cst_tier"] = t1.evidence
    if snapshot is not None:
        evidence["snapshot_fallback"] = {
            "cost_source": snapshot.cost_source,
            "cost_basis": _f(snapshot.cost_basis),
            "evidence": snapshot.evidence,
        }

    return CostSuggestion(
        cost_basis=cost_basis,
        cost_source=cost_source,
        evidence=evidence,
        flags=ordered_flags,
    )
