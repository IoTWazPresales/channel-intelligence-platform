"""CPOR cost-basis suggestion — preference order per spec §4.

Tier 1: CST unit_cost (read existing fact_customer_sellthrough only)
Tier 2: DSI sell-out units-weighted average
Tier 3: manual / no evidence

FLAG ≠ BLOCK. Never auto-rewrite a stored cost_basis (drift is detect-only).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models.commercial_planner import CommercialCustomerTerm
from app.models.cpor import CporCase, CporCaseLine
from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.models.facts import FactSalesSellout
from app.services.cpor.config import ASSUMED_SELLOUT_CURRENCY, DEFAULT_SELLOUT_LOOKBACK_DAYS
from app.services.cpor.waterfall import _as_decimal


@dataclass
class CostSuggestion:
    cost_basis: Decimal | None
    cost_source: str | None  # cst_reported | sellout_evidence | manual | None
    evidence: dict[str, Any] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)


def resolve_default_margin(session: Session, customer_id: int) -> tuple[Decimal | None, str | None]:
    """Pull customer_margin_pct from commercial_customer_term. No rebate resolver (reseller v1)."""
    row = session.scalar(
        select(CommercialCustomerTerm).where(CommercialCustomerTerm.customer_id == customer_id)
    )
    if row is None:
        return None, None
    return _as_decimal(row.customer_margin_pct), "customer_default"


def _lookback_start(
    session: Session,
    *,
    customer_id: int,
    product_id: int,
    as_of: date,
    exclude_case_id: int | None,
) -> tuple[date, str]:
    """Prior CPOR case window_end for same customer×product, else 180-day default."""
    stmt: Select = (
        select(CporCase.window_end)
        .join(CporCaseLine, CporCaseLine.case_id == CporCase.id)
        .where(
            CporCase.customer_id == customer_id,
            CporCaseLine.product_id == product_id,
            CporCase.window_end.is_not(None),
            CporCase.window_end < as_of,
        )
        .order_by(CporCase.window_end.desc())
        .limit(1)
    )
    if exclude_case_id is not None:
        stmt = stmt.where(CporCase.id != exclude_case_id)
    prior_end = session.scalar(stmt)
    if prior_end is not None:
        return prior_end, "prior_cpor_case"
    return as_of - timedelta(days=DEFAULT_SELLOUT_LOOKBACK_DAYS), "default_lookback_days"


def _tier1_cst(
    session: Session,
    *,
    customer_id: int,
    product_id: int,
    as_of: date,
) -> CostSuggestion | None:
    """Prefer unit_mac when present (Takealot MAC), else unit_cost. Tier order unchanged."""
    from sqlalchemy import or_

    row = session.execute(
        select(
            FactCustomerSellthrough.unit_mac,
            FactCustomerSellthrough.unit_cost,
            FactCustomerSellthrough.period_start_date,
            FactCustomerSellthrough.id,
        )
        .where(
            FactCustomerSellthrough.customer_id == customer_id,
            FactCustomerSellthrough.product_id == product_id,
            or_(
                FactCustomerSellthrough.unit_mac.is_not(None),
                FactCustomerSellthrough.unit_cost.is_not(None),
            ),
            FactCustomerSellthrough.period_start_date <= as_of,
        )
        .order_by(FactCustomerSellthrough.period_start_date.desc(), FactCustomerSellthrough.id.desc())
        .limit(1)
    ).first()
    if row is None:
        return None
    unit_mac, unit_cost, period_start, row_id = row
    if unit_mac is not None:
        chosen = unit_mac
        field_used = "unit_mac"
    else:
        chosen = unit_cost
        field_used = "unit_cost"
    evidence: dict[str, Any] = {
        "tier": "cst_reported",
        "as_of": period_start.isoformat(),
        "fact_id": int(row_id),
        "field_used": field_used,
        field_used: float(_as_decimal(chosen)),
    }
    if unit_mac is not None and unit_cost is not None:
        evidence["unit_mac"] = float(_as_decimal(unit_mac))
        evidence["unit_cost"] = float(_as_decimal(unit_cost))
    return CostSuggestion(
        cost_basis=_as_decimal(chosen),
        cost_source="cst_reported",
        evidence=evidence,
        flags=[],
    )


def _tier2_sellout(
    session: Session,
    *,
    customer_id: int,
    product_id: int,
    as_of: date,
    lookback_start: date,
    lookback_reason: str,
) -> CostSuggestion | None:
    rows = session.execute(
        select(
            FactSalesSellout.units,
            FactSalesSellout.unit_sellout_price_ex_tax_amount,
            FactSalesSellout.transaction_date,
            FactSalesSellout.currency_code,
        ).where(
            FactSalesSellout.customer_id == customer_id,
            FactSalesSellout.product_id == product_id,
            FactSalesSellout.unit_sellout_price_ex_tax_amount.is_not(None),
            FactSalesSellout.transaction_date >= lookback_start,
            FactSalesSellout.transaction_date <= as_of,
            FactSalesSellout.units > 0,
        )
    ).all()
    if not rows:
        return None

    flags: list[str] = []
    weighted_num = Decimal("0")
    weighted_den = Decimal("0")
    min_d: date | None = None
    max_d: date | None = None
    assumed_currency = False
    for units, price, tx_date, ccy in rows:
        u = _as_decimal(units)
        p = _as_decimal(price)
        weighted_num += u * p
        weighted_den += u
        if min_d is None or tx_date < min_d:
            min_d = tx_date
        if max_d is None or tx_date > max_d:
            max_d = tx_date
        ccy_s = (str(ccy).strip() if ccy is not None else "")
        if not ccy_s or ccy_s in {"0", "000", "null", "None"}:
            assumed_currency = True

    if weighted_den <= 0:
        return None

    avg = weighted_num / weighted_den
    if assumed_currency:
        flags.append("assumed_currency")

    return CostSuggestion(
        cost_basis=avg,
        cost_source="sellout_evidence",
        evidence={
            "tier": "sellout_evidence",
            "lookback_start": lookback_start.isoformat(),
            "lookback_reason": lookback_reason,
            "as_of": as_of.isoformat(),
            "date_range": {
                "min": min_d.isoformat() if min_d else None,
                "max": max_d.isoformat() if max_d else None,
            },
            "row_count": len(rows),
            "units_sum": float(weighted_den),
            "weighted_avg": float(avg),
            "assumed_sellout_currency": ASSUMED_SELLOUT_CURRENCY if assumed_currency else None,
        },
        flags=flags,
    )


def suggest_cost_basis(
    session: Session,
    *,
    customer_id: int,
    product_id: int,
    as_of: date | None = None,
    exclude_case_id: int | None = None,
    manual_cost: Decimal | float | int | str | None = None,
) -> CostSuggestion:
    """Preference: CST → sell-out WAVG → manual/none. Manual always available with deviation flag."""
    as_of = as_of or date.today()
    flags: list[str] = []
    tiers_seen: dict[str, Any] = {}

    t1 = _tier1_cst(session, customer_id=customer_id, product_id=product_id, as_of=as_of)
    if t1 is not None:
        tiers_seen["cst_reported"] = t1.evidence

    lookback_start, lookback_reason = _lookback_start(
        session,
        customer_id=customer_id,
        product_id=product_id,
        as_of=as_of,
        exclude_case_id=exclude_case_id,
    )
    t2 = _tier2_sellout(
        session,
        customer_id=customer_id,
        product_id=product_id,
        as_of=as_of,
        lookback_start=lookback_start,
        lookback_reason=lookback_reason,
    )
    if t2 is not None:
        tiers_seen["sellout_evidence"] = t2.evidence

    chosen: CostSuggestion | None = t1 or t2

    if manual_cost is not None:
        manual_dec = _as_decimal(manual_cost)
        evidence: dict[str, Any] = {
            "tier": "manual",
            "manual_cost": float(manual_dec),
            "as_of": as_of.isoformat(),
            "other_tiers": tiers_seen,
        }
        man_flags = list(flags)
        if chosen is not None and chosen.cost_basis is not None:
            delta = manual_dec - chosen.cost_basis
            evidence["deviation_from_evidence"] = {
                "evidence_tier": chosen.cost_source,
                "evidence_value": float(chosen.cost_basis),
                "manual_value": float(manual_dec),
                "delta": float(delta),
            }
            man_flags.append("manual_deviation_from_evidence")
            man_flags.extend(chosen.flags)
        return CostSuggestion(
            cost_basis=manual_dec,
            cost_source="manual",
            evidence=evidence,
            flags=man_flags,
        )

    if chosen is None:
        return CostSuggestion(
            cost_basis=None,
            cost_source=None,
            evidence={"tier": None, "as_of": as_of.isoformat(), "other_tiers": tiers_seen},
            flags=["no_cost_evidence"],
        )

    # Inter-tier deviation when both present and CST chosen over sell-out
    if t1 is not None and t2 is not None and t1.cost_basis is not None and t2.cost_basis is not None:
        delta = t1.cost_basis - t2.cost_basis
        chosen.evidence["inter_tier_deviation"] = {
            "chosen": "cst_reported",
            "other": "sellout_evidence",
            "chosen_value": float(t1.cost_basis),
            "other_value": float(t2.cost_basis),
            "delta": float(delta),
        }
        if abs(delta) > Decimal("0.01"):
            chosen.flags.append("inter_tier_deviation")
        chosen.evidence["other_tiers"] = {"sellout_evidence": t2.evidence}

    return chosen


def detect_cost_basis_drift(
    stored_cost_basis: Decimal | float | int | str | None,
    fresh: CostSuggestion,
    *,
    stored_as_of: date | None = None,
) -> dict[str, Any] | None:
    """Compare stored cost_basis to a fresh suggestion. Never rewrites. U3 calls on approve/active."""
    if stored_cost_basis is None or fresh.cost_basis is None:
        return None
    old = _as_decimal(stored_cost_basis)
    new = fresh.cost_basis
    if old == new:
        return None
    return {
        "flag": "cost_basis_drift",
        "old_cost_basis": float(old),
        "new_suggestion": float(new),
        "new_source": fresh.cost_source,
        "stored_as_of": stored_as_of.isoformat() if stored_as_of else None,
        "fresh_evidence": fresh.evidence,
        "delta": float(new - old),
    }
