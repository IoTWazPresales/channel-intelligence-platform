"""BACKLOG-089 — cost per incremental unit (promo) vs baseline sell-through.

Formula (when baseline PASS):
  cost_per_incremental_unit_usd = support_usd / max(0, result_qty − baseline_qty)

Never invent lift: weak/insufficient baseline → null metric + FLAG status.
A2-06 (support ÷ result_qty) remains a separate metric.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.cpor import CporCase, CporCaseLine
from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.services.commercial_tenant_profile import incremental_baseline_config


def _case_window_days(case: CporCase) -> int:
    try:
        return max(1, (case.window_end - case.window_start).days + 1)
    except Exception:
        return 1


def _baseline_units_for_line(
    session: Session,
    *,
    customer_id: int,
    product_id: int,
    case: CporCase,
    lookback_days: int,
) -> dict[str, Any]:
    """prior_window_same_sku_customer: sum CST units in lookback before window_start, scale to case length."""
    end = case.window_start - timedelta(days=1)
    start = end - timedelta(days=max(1, lookback_days) - 1)
    qty = session.scalar(
        select(func.coalesce(func.sum(FactCustomerSellthrough.units_sold), 0)).where(
            FactCustomerSellthrough.customer_id == int(customer_id),
            FactCustomerSellthrough.product_id == int(product_id),
            FactCustomerSellthrough.period_start_date >= start,
            FactCustomerSellthrough.period_start_date <= end,
        )
    )
    obs = session.scalar(
        select(func.count()).select_from(FactCustomerSellthrough).where(
            FactCustomerSellthrough.customer_id == int(customer_id),
            FactCustomerSellthrough.product_id == int(product_id),
            FactCustomerSellthrough.period_start_date >= start,
            FactCustomerSellthrough.period_start_date <= end,
        )
    )
    raw = float(qty or 0)
    obs_n = int(obs or 0)
    # Extrapolate lookback sum → expected units over case window length.
    scale = _case_window_days(case) / float(max(1, lookback_days))
    baseline_qty = raw * scale
    return {
        "baseline_qty": baseline_qty,
        "lookback_units": raw,
        "obs_count": obs_n,
        "lookback_start": start.isoformat(),
        "lookback_end": end.isoformat(),
        "scale": scale,
    }


def evaluate_case_incremental_cost(
    session: Session,
    case: CporCase,
    *,
    tenant_id: str = "default",
) -> dict[str, Any]:
    """Portfolio/case explainable incremental unit cost (FLAG when baseline weak)."""
    cfg = incremental_baseline_config(tenant_id)
    method = str(cfg["baseline_method"])
    lookback = int(cfg["baseline_lookback_days"])
    min_obs = int(cfg["min_baseline_obs"])

    lines = list(
        session.scalars(select(CporCaseLine).where(CporCaseLine.case_id == int(case.id))).all()
    )
    support_usd = sum(float(ln.ttl_support_usd or 0) for ln in lines)
    support_zar = sum(float(ln.ttl_support or 0) for ln in lines)
    result_qty = sum(float(ln.result_qty or 0) for ln in lines)

    out: dict[str, Any] = {
        "case_id": int(case.id),
        "case_code": case.case_code,
        "customer_id": case.customer_id,
        "baseline_method": method,
        "baseline_lookback_days": lookback,
        "min_baseline_obs": min_obs,
        "support_usd": support_usd,
        "support_zar": support_zar,
        "result_qty": result_qty,
        "cost_per_incremental_unit_usd": None,
        "cost_per_incremental_unit_zar": None,
        "baseline_qty": None,
        "lift_qty": None,
        "baseline_status": "insufficient",
        "message": "",
        "line_baselines": [],
    }

    if case.customer_id is None:
        out["message"] = "Case has no customer_id — cannot match sell-through baseline."
        return out

    if not lines:
        out["message"] = "Case has no lines."
        return out

    # Only lines with product_id contribute to baseline; others FLAG in factors.
    total_baseline = 0.0
    obs_total = 0
    line_details: list[dict[str, Any]] = []
    for ln in lines:
        if ln.product_id is None:
            line_details.append(
                {
                    "line_id": int(ln.id),
                    "product_id": None,
                    "baseline_status": "no_product",
                }
            )
            continue
        if method != "prior_window_same_sku_customer":
            # v1 ships one method; others reserved for later without inventing numbers.
            line_details.append(
                {
                    "line_id": int(ln.id),
                    "product_id": int(ln.product_id),
                    "baseline_status": "method_unimplemented",
                }
            )
            continue
        bl = _baseline_units_for_line(
            session,
            customer_id=int(case.customer_id),
            product_id=int(ln.product_id),
            case=case,
            lookback_days=lookback,
        )
        total_baseline += float(bl["baseline_qty"])
        obs_total += int(bl["obs_count"])
        line_details.append({"line_id": int(ln.id), "product_id": int(ln.product_id), **bl})

    out["line_baselines"] = line_details
    out["baseline_qty"] = total_baseline
    lift = result_qty - total_baseline
    out["lift_qty"] = lift

    if obs_total < min_obs:
        out["baseline_status"] = "insufficient"
        out["message"] = (
            f"Baseline observations {obs_total} < min_baseline_obs {min_obs} — "
            "cost_per_incremental_unit left null (FLAG)."
        )
        return out

    if lift <= 0:
        out["baseline_status"] = "no_lift"
        out["message"] = (
            f"No positive lift (result_qty {result_qty} ≤ baseline {total_baseline}) — "
            "incremental cost null (FLAG)."
        )
        return out

    out["baseline_status"] = "ok"
    out["cost_per_incremental_unit_usd"] = support_usd / lift if lift else None
    out["cost_per_incremental_unit_zar"] = support_zar / lift if lift and support_zar else None
    out["message"] = (
        f"Lift {lift:.2f} units over baseline {total_baseline:.2f} "
        f"(method={method}, lookback={lookback}d, obs={obs_total})."
    )
    return out


def build_portfolio_incremental_summary(session: Session, *, tenant_id: str = "default") -> dict[str, Any]:
    """Summarize incremental metrics across open/non-superseded cases (FLAG-first)."""
    cases = list(
        session.scalars(
            select(CporCase)
            .where(CporCase.superseded_by_case_id.is_(None))
            .order_by(CporCase.id.desc())
            .limit(200)
        ).all()
    )
    rows = [evaluate_case_incremental_cost(session, c, tenant_id=tenant_id) for c in cases]
    ok = [r for r in rows if r.get("baseline_status") == "ok" and r.get("cost_per_incremental_unit_usd") is not None]
    return {
        "metric": "cost_per_incremental_unit",
        "note": "Distinct from A2-06 support_per_unit_sold (support÷result_qty).",
        "cases_evaluated": len(rows),
        "cases_ok": len(ok),
        "cases_flagged": len(rows) - len(ok),
        "avg_cost_per_incremental_unit_usd": (
            sum(float(r["cost_per_incremental_unit_usd"]) for r in ok) / len(ok) if ok else None
        ),
        "items": rows[:50],
        "baseline_config": incremental_baseline_config(tenant_id),
        "as_of": date.today().isoformat(),
    }
