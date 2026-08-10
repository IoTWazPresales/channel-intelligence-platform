"""B4 — promotion plan builder draft (compose A2 + B1 + B2).

Compose is the primary surface. Optional create-from-draft writes a **draft** CPOR case
via the existing case/line path (no parallel economics ledger).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupLine
from app.models.commercial_planner import CommercialSkuAssumption
from app.models.cpor import CporCase, CporCaseLine
from app.models.dimensions import DimProduct
from app.models.fact_demand_forecast import FactDemandForecast
from app.models.lineup import FactLineupPlanItem
from app.services import commercial_tenant_profile as tenant_profile
from app.services.commercial_planner.lineup_period_canonical import (
    normalize_period_label,
    period_label_sql_variants,
    period_labels_equivalent,
)
from app.services.cpor.norms_and_comparable import build_comparable_cases
from app.services.lineup.profit_reservation import compute_profit_with_reservation


def _positive_srp(*candidates: float | None) -> float | None:
    for raw in candidates:
        if raw is None:
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return None


def _forecast_volume_sync(
    session: Session,
    *,
    product_id: int | None,
    customer_id: int | None,
    horizon_weeks: int = 13,
) -> dict[str, Any]:
    as_of = date.today()
    period_to = as_of + timedelta(weeks=max(1, horizon_weeks))
    stmt = select(func.coalesce(func.sum(FactDemandForecast.forecast_units), 0)).where(
        FactDemandForecast.period_start >= as_of,
        FactDemandForecast.period_start < period_to,
    )
    if product_id is not None:
        stmt = stmt.where(FactDemandForecast.product_id == int(product_id))
    if customer_id is not None:
        stmt = stmt.where(FactDemandForecast.customer_id == int(customer_id))
    units = float(session.execute(stmt).scalar() or 0)
    return {
        "horizon_weeks": horizon_weeks,
        "period_from": as_of.isoformat(),
        "period_to": period_to.isoformat(),
        "forecast_units": units,
        "source": "fact_demand_forecast",
        "grain_filters": {"product_id": product_id, "customer_id": customer_id},
    }


def _srp_evidence_by_product_sync(session: Session, product_ids: set[int]) -> dict[int, float]:
    if not product_ids:
        return {}
    rows = session.execute(
        select(
            CommercialLineupLine.product_id,
            CommercialLineupLine.dap_evidence_local,
            CommercialLineupLine.msrp_local,
            CommercialLineupLine.id,
        )
        .where(CommercialLineupLine.product_id.in_(tuple(product_ids)))
        .order_by(CommercialLineupLine.id.desc())
    ).all()
    out: dict[int, float] = {}
    for pid, dap, msrp, _lid in rows:
        if pid is None:
            continue
        key = int(pid)
        if key in out:
            continue
        srp = _positive_srp(
            float(dap) if dap is not None else None,
            float(msrp) if msrp is not None else None,
        )
        if srp is not None:
            out[key] = srp
    return out


def derive_planned_reservation_sync(
    session: Session,
    *,
    period_label: str | None = None,
    limit: int = 5000,
) -> dict[str, Any]:
    """B2 money-track planned reservation (sync) for B4 budget check — never fabricate SRP."""
    items = list(session.scalars(select(FactLineupPlanItem).limit(limit)).all())
    if period_label:
        want = normalize_period_label(period_label)
        items = [i for i in items if period_labels_equivalent(i.period_label, want)]

    product_ids: set[int] = set()
    raw: list[tuple[int, float, float | None]] = []
    if items:
        for item in items:
            pid = int(item.product_id)
            product_ids.add(pid)
            raw.append((pid, float(item.planned_volume_units or 0), None))
        srp_map = _srp_evidence_by_product_sync(session, product_ids)
        raw = [(pid, qty, srp_map.get(pid)) for pid, qty, _ in raw]
    else:
        cases = list(
            session.execute(select(CommercialLineupCase.id, CommercialLineupCase.period_label).limit(200)).all()
        )
        if period_label:
            cases = [(cid, pl) for cid, pl in cases if period_labels_equivalent(pl, period_label)]
        case_ids = [int(cid) for cid, _ in cases]
        if case_ids:
            for line in session.scalars(
                select(CommercialLineupLine)
                .where(
                    CommercialLineupLine.case_id.in_(tuple(case_ids)),
                    CommercialLineupLine.product_id.isnot(None),
                )
                .limit(limit)
            ).all():
                pid = int(line.product_id)  # type: ignore[arg-type]
                product_ids.add(pid)
                srp = _positive_srp(
                    float(line.dap_evidence_local) if line.dap_evidence_local is not None else None,
                    float(line.msrp_local) if line.msrp_local is not None else None,
                )
                raw.append((pid, float(line.quantity_units or 0), srp))

    sku_by_pid: dict[int, CommercialSkuAssumption] = {}
    if product_ids:
        for sku in session.scalars(
            select(CommercialSkuAssumption).where(CommercialSkuAssumption.product_id.in_(tuple(product_ids)))
        ).all():
            sku_by_pid[int(sku.product_id)] = sku

    reserved = 0.0
    revenue = 0.0
    planned_n = 0
    skipped_missing_sku = 0
    skipped_missing_srp = 0
    for pid, qty, srp in raw:
        if qty <= 0:
            continue
        sku = sku_by_pid.get(pid)
        if sku is None:
            skipped_missing_sku += 1
            continue
        if srp is None or srp <= 0:
            skipped_missing_srp += 1
            continue
        economics = compute_profit_with_reservation(
            net_requirement_units=qty,
            target_srp_local=float(srp),
            promo_srp_local=None,
            controlled_cost_amount=float(sku.controlled_cost_amount),
            reserve_total_pct=float(sku.reserve_total_pct),
            promo_reserve_split_pct=float(sku.promo_reserve_split_pct),
            vat_rate_pct=float(sku.vat_rate_pct),
            fx_plan_currency_per_cost_currency=float(sku.fx_plan_currency_per_cost_currency),
        )
        reserved += float((economics.get("reservation") or {}).get("total") or 0)
        revenue += float(economics.get("oem_sell_in_per_unit") or 0) * qty
        planned_n += 1

    sku_n = int(session.execute(select(func.count()).select_from(CommercialSkuAssumption)).scalar() or 0)
    return {
        "planned_reservation_usd": round(reserved, 4),
        "planned_revenue_usd": round(revenue, 4),
        "planned_line_count": planned_n,
        "sku_assumption_count": sku_n,
        "skipped_missing_sku": skipped_missing_sku,
        "skipped_missing_srp": skipped_missing_srp,
        "reservation_source": tenant_profile.RESERVATION_SOURCE,
        "from_lineup_derived": planned_n > 0,
    }


def build_promo_plan_draft(
    session: Session,
    *,
    seed_case_id: int,
    product_id: int | None = None,
    customer_id: int | None = None,
    planned_support_usd: float | None = None,
    planned_revenue_usd: float | None = None,
    period_label: str | None = None,
    horizon_weeks: int = 13,
    comparable_limit: int = 10,
) -> dict[str, Any]:
    """Compose a promotion-plan draft for operator review / case authoring."""
    seed = session.get(CporCase, seed_case_id)
    seed_customer_id = int(seed.customer_id) if seed is not None else customer_id
    effective_customer = customer_id if customer_id is not None else seed_customer_id

    comparables = build_comparable_cases(session, case_id=seed_case_id, limit=comparable_limit)
    volume = _forecast_volume_sync(
        session,
        product_id=product_id,
        customer_id=effective_customer,
        horizon_weeks=horizon_weeks,
    )

    derived = derive_planned_reservation_sync(session, period_label=period_label)
    reserved = float(planned_support_usd) if planned_support_usd is not None else float(
        derived["planned_reservation_usd"] or 0
    )
    planned_rev = (
        float(planned_revenue_usd)
        if planned_revenue_usd is not None
        else float(derived["planned_revenue_usd"] or 0)
    )

    drawn_stmt = select(
        func.coalesce(func.sum(CporCaseLine.ttl_support_usd), 0),
        func.count(CporCaseLine.id),
    )
    if period_label:
        variants = period_label_sql_variants(period_label)
        if variants:
            drawn_stmt = drawn_stmt.where(CporCaseLine.pod_quarter.in_(tuple(variants)))
        else:
            drawn_stmt = drawn_stmt.where(CporCaseLine.pod_quarter == period_label)
    drawn_usd, line_n = session.execute(drawn_stmt).one()
    drawn = float(drawn_usd or 0)
    remaining = reserved - drawn
    support_pct = (reserved / planned_rev) if planned_rev > 0 and reserved else None

    if reserved > 0 and drawn > reserved:
        money_status = "over"
    elif reserved > 0:
        money_status = "ok"
    elif int(derived.get("sku_assumption_count") or 0) == 0:
        money_status = "missing_sku_economics"
    elif int(derived.get("skipped_missing_srp") or 0) > 0:
        money_status = "missing_srp"
    else:
        money_status = "no_planned_reservation"

    over_budget_warn = money_status == "over"
    snap = tenant_profile.profile_snapshot()
    over_action = str(snap.get("over_budget_action") or tenant_profile.OVER_BUDGET_ACTION)
    hard = bool(snap.get("hard_enforce_budget", tenant_profile.HARD_ENFORCE_BUDGET)) or (
        over_action == "block"
    )

    budget = {
        "hard_enforce": hard,
        "constraint_type": snap.get("constraint_axis", tenant_profile.CONSTRAINT_AXIS),
        "binding_axis": snap.get("constraint_axis", tenant_profile.CONSTRAINT_AXIS),
        "over_budget_action": over_action,
        "tenant_profile": snap,
        "tracks": {
            "money": {
                "planned_reservation_usd": round(reserved, 4),
                "drawn_cpor_usd": round(drawn, 4),
                "remaining_usd": round(remaining, 4),
                "status": money_status,
                "binding": tenant_profile.CONSTRAINT_AXIS in ("money", "dual"),
            },
            "support_pct": {
                "planned_support_pct_of_sell_in": support_pct,
                "binding": tenant_profile.CONSTRAINT_AXIS in ("support_pct", "dual"),
            },
        },
        "cpor_line_count": int(line_n or 0),
        "period_label": period_label,
        "period_label_normalized": normalize_period_label(period_label),
        "reservation_source": tenant_profile.RESERVATION_SOURCE,
        "q002_reservation_source": tenant_profile.RESERVATION_SOURCE,
        "planned_from_lineup_derived": bool(derived.get("from_lineup_derived"))
        and planned_support_usd is None,
        "derive_diagnostics": {
            "skipped_missing_sku": derived.get("skipped_missing_sku"),
            "skipped_missing_srp": derived.get("skipped_missing_srp"),
            "planned_line_count": derived.get("planned_line_count"),
            "sku_assumption_count": derived.get("sku_assumption_count"),
        },
        "over_budget_warn": over_budget_warn,
        "create_blocked": bool(hard and over_budget_warn),
    }

    top = (comparables.get("items") or [])[:3]
    suggested_estimate = float(volume["forecast_units"])
    if suggested_estimate <= 0 and top:
        ests = [float(t.get("estimate_qty") or 0) for t in top]
        ests = [e for e in ests if e > 0]
        if ests:
            suggested_estimate = sum(ests) / len(ests)

    seed_lines: list[dict[str, Any]] = []
    if seed is not None:
        for line in session.scalars(
            select(CporCaseLine).where(CporCaseLine.case_id == seed.id).limit(20)
        ).all():
            seed_lines.append(
                {
                    "line_id": int(line.id),
                    "product_id": int(line.product_id),
                    "distributor_id": int(line.distributor_id) if line.distributor_id is not None else None,
                    "srp": float(line.srp) if line.srp is not None else None,
                    "estimate_qty": float(line.estimate_qty or 0),
                    "pod_quarter": line.pod_quarter,
                }
            )

    return {
        "draft": True,
        "seed_case_id": seed_case_id,
        "seed_case_found": seed is not None,
        "seed_customer_id": seed_customer_id,
        "seed_promotion_type": seed.promotion_type if seed is not None else None,
        "seed_window_start": seed.window_start.isoformat() if seed is not None else None,
        "seed_window_end": seed.window_end.isoformat() if seed is not None else None,
        "seed_lines": seed_lines,
        "comparables": {
            "count": len(comparables.get("items") or []),
            "top": top,
            "error": comparables.get("error"),
        },
        "volume": volume,
        "suggested_estimate_qty": round(float(suggested_estimate), 4),
        "budget_check": budget,
        "next_step": (
            "POST /cpor/intelligence/promo-plan-draft/create-case to write a draft CPOR case, "
            "or create manually via /cpor/cases"
        ),
        "notes": [
            f"Reservation source={tenant_profile.RESERVATION_SOURCE}; "
            f"binding_axis={tenant_profile.CONSTRAINT_AXIS}; "
            f"over_action={tenant_profile.OVER_BUDGET_ACTION} (hard_enforce="
            f"{tenant_profile.HARD_ENFORCE_BUDGET})",
            "Volume from fact_demand_forecast (B1); comparable volume is fallback only",
            "Budget uses B2 lineup-derived reservation when planned_support_usd omitted",
        ],
    }


def create_case_from_promo_draft(
    session: Session,
    *,
    seed_case_id: int,
    product_id: int | None = None,
    period_label: str | None = None,
    planned_support_usd: float | None = None,
    planned_revenue_usd: float | None = None,
    horizon_weeks: int = 13,
    confirm_over_budget: bool = False,
    actor: str | None = None,
    generate_case_code,
    record_event,
    recompute_case_line,
    resolve_default_margin,
    suggest_cost_basis,
) -> dict[str, Any]:
    """Create a draft CPOR case from B4 compose output (uses existing line recompute)."""
    draft = build_promo_plan_draft(
        session,
        seed_case_id=seed_case_id,
        product_id=product_id,
        period_label=period_label,
        planned_support_usd=planned_support_usd,
        planned_revenue_usd=planned_revenue_usd,
        horizon_weeks=horizon_weeks,
    )
    seed = session.get(CporCase, seed_case_id)
    if seed is None:
        raise ValueError("seed_case_not_found")

    budget = draft["budget_check"]
    if budget.get("create_blocked") and not confirm_over_budget:
        raise ValueError(
            "over_budget_requires_confirm — pass confirm_over_budget=true "
            f"(action={budget.get('over_budget_action')})"
        )

    lines = draft.get("seed_lines") or []
    chosen = None
    if product_id is not None:
        chosen = next((l for l in lines if int(l["product_id"]) == int(product_id)), None)
    if chosen is None and lines:
        chosen = lines[0]
    if chosen is None:
        raise ValueError("seed_case_has_no_lines — pick a seed with lines or pass product_id after adding lines")

    pid = int(chosen["product_id"])
    prod = session.get(DimProduct, pid)
    if prod is None:
        raise ValueError(f"unknown_product_id={pid}")

    srp = chosen.get("srp")
    if srp is None or float(srp) <= 0:
        raise ValueError("seed_line_missing_srp")

    estimate = float(draft.get("suggested_estimate_qty") or 0)
    if estimate <= 0:
        estimate = float(chosen.get("estimate_qty") or 0)
    if estimate <= 0:
        raise ValueError("no_positive_estimate_qty")

    from app.services.cpor.promotion_type_vocab import CPOR_CHANNEL_SET

    channel = (seed.channel or "reseller").strip().lower()
    if channel not in CPOR_CHANNEL_SET:
        channel = "reseller"

    actor_s = actor or "b4_promo_draft"
    code = generate_case_code(session)
    case = CporCase(
        case_code=code,
        case_name=f"B4 draft from {seed.case_code}",
        tenant_id=seed.tenant_id,
        customer_id=seed.customer_id,
        promotion_type=seed.promotion_type,
        window_start=seed.window_start,
        window_end=seed.window_end,
        status="draft",
        roe_snapshot=seed.roe_snapshot,
        currency_code=seed.currency_code or "ZAR",
        channel=channel,
        notes=(
            f"Created from B4 promo-plan-draft seed={seed_case_id}; "
            f"budget_status={budget.get('tracks', {}).get('money', {}).get('status')}; "
            f"over_warn={budget.get('over_budget_warn')}; "
            f"seed_channel={seed.channel}"
        ),
        created_by=actor_s,
        export_version=1,
        workflow_status="draft",
    )
    session.add(case)
    session.flush()

    margin, margin_source = resolve_default_margin(session, case.customer_id)
    if margin is None:
        margin = 0.12
        margin_source = "b4_default"

    as_of = date.today()
    sug = suggest_cost_basis(
        session,
        customer_id=case.customer_id,
        product_id=pid,
        as_of=as_of,
        exclude_case_id=case.id,
        manual_cost=None,
    )
    cost_basis = float(sug.cost_basis) if sug.cost_basis is not None else None
    cost_source = sug.cost_source
    cost_evidence = {**sug.evidence, "flags": sug.flags}

    line = CporCaseLine(
        case_id=case.id,
        product_id=pid,
        distributor_id=chosen.get("distributor_id"),
        pod_quarter=(
            period_label
            or chosen.get("pod_quarter")
            or f"{str(seed.window_start.year)[2:]}Q{(seed.window_start.month - 1) // 3 + 1}"
        ),
        srp=float(srp),
        vat_rate=0.15,
        dealer_margin_pct=float(margin),
        margin_source=margin_source or "customer_default",
        cost_basis=cost_basis,
        cost_source=cost_source,
        cost_evidence_json=cost_evidence,
        estimate_qty=estimate,
        remark="b4_promo_plan_draft",
    )
    session.add(line)
    session.flush()
    rep = recompute_case_line(session, line, case=case, actor=actor_s, write_event=False)
    record_event(
        session,
        case_id=case.id,
        event_type="created",
        actor=actor_s,
        payload={"case_code": code, "from": "b4_promo_plan_draft", "seed_case_id": seed_case_id},
    )
    record_event(
        session,
        case_id=case.id,
        event_type="line_created",
        actor=actor_s,
        payload={"line_id": line.id, "recompute_flags": rep.get("flags"), "source": "b4"},
    )
    session.commit()
    session.refresh(case)
    session.refresh(line)

    return {
        "created": True,
        "case_id": int(case.id),
        "case_code": case.case_code,
        "line_id": int(line.id),
        "estimate_qty": float(line.estimate_qty or 0),
        "over_budget_warn": bool(budget.get("over_budget_warn")),
        "budget_status": budget.get("tracks", {}).get("money", {}).get("status"),
        "draft": draft,
        "href": f"/commercial-planner/cpor-cases/{case.id}",
    }
