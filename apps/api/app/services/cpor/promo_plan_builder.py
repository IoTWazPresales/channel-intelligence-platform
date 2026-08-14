"""B4 — promotion plan builder draft (compose A2 + B1 + B2 + 15C per-line grid).

Compose is the primary surface. Optional create-from-draft writes a **draft** CPOR case
via the existing case/line path (no parallel economics ledger). Unit 15C emits per-line
intake-weighted MAC + history units; create carries operator edits (D-051–D-053).
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
from app.services.cpor.intake_weighted_mac import suggest_intake_weighted_mac
from app.services.cpor.norms_and_comparable import build_comparable_cases
from app.services.lineup.cover_policy import resolve_target_cover_weeks_sync
from app.services.lineup.profit_reservation import compute_profit_with_reservation

EDITABLE_PLANNER_FIELDS = (
    "estimate_qty",
    "cost_basis",
    "srp",
    "cover_weeks",
    "distributor_id",
    "pod_quarter",
)
COST_SOURCE_MANUAL = "manual"
COST_SOURCE_INTAKE_WEIGHTED = "intake_weighted"


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


def _intake_payload(sug: Any) -> dict[str, Any]:
    evidence = dict(sug.evidence or {})
    return {
        "cost_basis": float(sug.cost_basis) if sug.cost_basis is not None else None,
        "cost_source": sug.cost_source,
        "evidence": evidence,
        "flags": list(sug.flags or []),
        "bucket_a_on_hand": evidence.get("bucket_a_on_hand"),
        "bucket_b_intake": evidence.get("bucket_b_intake"),
        "planned_supply": evidence.get("planned_supply"),
        "sellout_value": evidence.get("sellout_value"),
        "disti_cost": evidence.get("disti_cost"),
        "blend": evidence.get("blend"),
        "not_in_blend": evidence.get("not_in_blend")
        or [
            "sellout_value_display_only",
            "planned_supply_no_native_cost",
            "dsi_wac_not_ingested",
            "dap",
        ],
    }


def _row_key(
    *,
    product_id: int,
    distributor_id: int | None,
    pod_quarter: str | None,
    seed_line_id: int | None,
) -> str:
    dist = "" if distributor_id is None else str(int(distributor_id))
    qtr = pod_quarter or ""
    seed = "new" if seed_line_id is None else str(int(seed_line_id))
    return f"{int(product_id)}:{dist}:{qtr}:{seed}"


def _spec_from_seed_line(line: CporCaseLine) -> dict[str, Any]:
    return {
        "seed_line_id": int(line.id),
        "product_id": int(line.product_id),
        "distributor_id": int(line.distributor_id) if line.distributor_id is not None else None,
        "srp": float(line.srp) if line.srp is not None else None,
        "estimate_qty": float(line.estimate_qty or 0),
        "pod_quarter": line.pod_quarter,
        "cover_override": None,
    }


def _normalize_line_spec(raw: dict[str, Any]) -> dict[str, Any]:
    pid = int(raw["product_id"])
    did = raw.get("distributor_id")
    cover = raw.get("cover_override")
    return {
        "seed_line_id": int(raw["seed_line_id"]) if raw.get("seed_line_id") is not None else None,
        "product_id": pid,
        "distributor_id": int(did) if did is not None else None,
        "srp": float(raw["srp"]) if raw.get("srp") is not None else None,
        "estimate_qty": float(raw["estimate_qty"] or 0) if raw.get("estimate_qty") is not None else 0.0,
        "pod_quarter": raw.get("pod_quarter"),
        "cover_override": float(cover) if cover is not None else None,
    }


def _collect_line_specs(
    session: Session,
    *,
    seed: CporCase | None,
    product_id: int | None,
    extra_lines: list[dict[str, Any]] | None,
    line_specs: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    if line_specs is not None:
        return [_normalize_line_spec(s) for s in line_specs]
    specs: list[dict[str, Any]] = []
    if seed is not None:
        stmt = select(CporCaseLine).where(CporCaseLine.case_id == seed.id)
        if product_id is not None:
            stmt = stmt.where(CporCaseLine.product_id == int(product_id))
        stmt = stmt.order_by(CporCaseLine.id.asc())
        for line in session.scalars(stmt).all():
            specs.append(_spec_from_seed_line(line))
    for extra in extra_lines or []:
        specs.append(_normalize_line_spec(extra))
    return specs


def _compose_suggestion_row(
    session: Session,
    *,
    seed: CporCase | None,
    spec: dict[str, Any],
    customer_id: int | None,
    horizon_weeks: int,
    period_label: str | None,
    top_comparables: list[dict[str, Any]],
) -> dict[str, Any]:
    pid = int(spec["product_id"])
    did = spec.get("distributor_id")
    cover_override = spec.get("cover_override")
    prod = session.get(DimProduct, pid)
    if customer_id is not None:
        weeks, cover_source = resolve_target_cover_weeks_sync(
            session, int(customer_id), override_weeks=cover_override
        )
    else:
        weeks, cover_source = (None, "unknown")

    window_start = seed.window_start if seed is not None else date.today()
    window_end = seed.window_end if seed is not None else date.today()
    as_of = date.today()
    intake = None
    if customer_id is not None:
        intake = suggest_intake_weighted_mac(
            session,
            customer_id=int(customer_id),
            product_id=pid,
            distributor_id=int(did) if did is not None else None,
            window_start=window_start,
            window_end=window_end,
            as_of=as_of,
            exclude_case_id=int(seed.id) if seed is not None else None,
        )
    intake_json = _intake_payload(intake) if intake is not None else {
        "cost_basis": None,
        "cost_source": None,
        "evidence": {},
        "flags": ["no_customer_for_mac"],
        "bucket_a_on_hand": None,
        "bucket_b_intake": None,
        "planned_supply": None,
        "sellout_value": None,
        "disti_cost": None,
        "blend": None,
        "not_in_blend": [],
    }

    volume = _forecast_volume_sync(
        session,
        product_id=pid,
        customer_id=customer_id,
        horizon_weeks=horizon_weeks,
    )
    suggested_qty = float(volume.get("forecast_units") or 0)
    if suggested_qty <= 0 and top_comparables:
        ests = [float(t.get("estimate_qty") or 0) for t in top_comparables]
        ests = [e for e in ests if e > 0]
        if ests:
            suggested_qty = sum(ests) / len(ests)
    if suggested_qty <= 0:
        suggested_qty = float(spec.get("estimate_qty") or 0)

    srp = spec.get("srp")
    pod_quarter = spec.get("pod_quarter") or (
        period_label
        or (
            f"{str(seed.window_start.year)[2:]}Q{(seed.window_start.month - 1) // 3 + 1}"
            if seed is not None
            else None
        )
    )
    seed_line_id = spec.get("seed_line_id")
    return {
        "row_key": _row_key(
            product_id=pid,
            distributor_id=int(did) if did is not None else None,
            pod_quarter=pod_quarter,
            seed_line_id=int(seed_line_id) if seed_line_id is not None else None,
        ),
        "seed_line_id": int(seed_line_id) if seed_line_id is not None else None,
        "product_id": pid,
        "product_sku": prod.sku if prod is not None else None,
        "product_name": prod.name if prod is not None else None,
        "distributor_id": int(did) if did is not None else None,
        "customer_id": int(customer_id) if customer_id is not None else None,
        "pod_quarter": pod_quarter,
        "srp": float(srp) if srp is not None else None,
        "suggested_estimate_qty": round(float(suggested_qty), 4),
        "suggested_cost_basis": intake_json.get("cost_basis"),
        "suggested_cost_source": intake_json.get("cost_source"),
        "cover": {
            "weeks": round(float(weeks), 4) if weeks is not None else None,
            "source": cover_source,
            "override_weeks": float(cover_override) if cover_override is not None else None,
        },
        "volume": volume,
        "intake_weighted": intake_json,
        "flags": list(intake_json.get("flags") or []),
        "editable_fields": list(EDITABLE_PLANNER_FIELDS),
        "display_only_fields": [
            "bucket_a_on_hand",
            "bucket_b_intake",
            "planned_supply",
            "sellout_value",
            "disti_cost",
            "blend",
        ],
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
    extra_lines: list[dict[str, Any]] | None = None,
    line_specs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compose a promotion-plan draft for operator review / case authoring.

    Returns per-line suggestion rows (D-051). Server is stateless on dirty flags (D-052).
    """
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
    specs = _collect_line_specs(
        session,
        seed=seed,
        product_id=product_id,
        extra_lines=extra_lines,
        line_specs=line_specs,
    )
    suggestion_rows = [
        _compose_suggestion_row(
            session,
            seed=seed,
            spec=spec,
            customer_id=effective_customer,
            horizon_weeks=horizon_weeks,
            period_label=period_label,
            top_comparables=top,
        )
        for spec in specs
    ]
    suggested_estimate = sum(float(r.get("suggested_estimate_qty") or 0) for r in suggestion_rows)
    if suggested_estimate <= 0:
        suggested_estimate = float(volume["forecast_units"] or 0)
        if suggested_estimate <= 0 and top:
            ests = [float(t.get("estimate_qty") or 0) for t in top]
            ests = [e for e in ests if e > 0]
            if ests:
                suggested_estimate = sum(ests) / len(ests)

    seed_lines: list[dict[str, Any]] = []
    if seed is not None:
        for line in session.scalars(
            select(CporCaseLine).where(CporCaseLine.case_id == seed.id).order_by(CporCaseLine.id.asc())
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
        "lines": suggestion_rows,
        "comparables": {
            "count": len(comparables.get("items") or []),
            "top": top,
            "error": comparables.get("error"),
        },
        "volume": volume,
        "suggested_estimate_qty": round(float(suggested_estimate), 4),
        "budget_check": budget,
        "next_step": (
            "POST /cpor/intelligence/promo-plan-draft/create-case with lines[] to write a draft CPOR case"
        ),
        "notes": [
            f"Reservation source={tenant_profile.RESERVATION_SOURCE}; "
            f"binding_axis={tenant_profile.CONSTRAINT_AXIS}; "
            f"over_action={tenant_profile.OVER_BUDGET_ACTION} (hard_enforce="
            f"{tenant_profile.HARD_ENFORCE_BUDGET})",
            "Per-line volume from fact_demand_forecast (B1); comparable volume is fallback only",
            "Per-line MAC from suggest_intake_weighted_mac (no second engine)",
            "Cover is session cover_override only — never writes commercial_customer_term",
            "Budget uses B2 lineup-derived reservation when planned_support_usd omitted",
            "Dirty-flag is client-owned; Refresh must not clobber dirty cells",
        ],
    }


def _grain_key(product_id: int, distributor_id: int | None, pod_quarter: str | None) -> tuple[int, int | None, str]:
    return (int(product_id), int(distributor_id) if distributor_id is not None else None, str(pod_quarter or ""))


def _write_specs_from_draft_or_payload(
    *,
    draft: dict[str, Any],
    lines: list[dict[str, Any]] | None,
    product_id: int | None,
) -> list[dict[str, Any]]:
    if lines is not None:
        return list(lines)
    rows = list(draft.get("lines") or [])
    if product_id is not None:
        rows = [r for r in rows if int(r["product_id"]) == int(product_id)]
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "product_id": int(row["product_id"]),
                "distributor_id": row.get("distributor_id"),
                "srp": row.get("srp"),
                "estimate_qty": row.get("suggested_estimate_qty") or 0,
                "cost_basis": row.get("suggested_cost_basis"),
                "pod_quarter": row.get("pod_quarter"),
                "cover_override": (row.get("cover") or {}).get("override_weeks"),
                "dirty_fields": [],
                "seed_line_id": row.get("seed_line_id"),
            }
        )
    return out


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
    lines: list[dict[str, Any]] | None = None,
    generate_case_code,
    record_event,
    recompute_case_line,
    resolve_default_margin,
    suggest_cost_basis,
) -> dict[str, Any]:
    """Create a draft CPOR case from B4 compose / planner grid (existing case/line path).

    Payload ``lines[]`` is authoritative (D-053). ``suggest_cost_basis`` is unused for draft
    cost — Approve still snapshots it. Cover overrides are not persisted to customer terms (D-054).
    """
    del suggest_cost_basis  # draft cost comes from intake composer or manual dirty MAC
    draft = build_promo_plan_draft(
        session,
        seed_case_id=seed_case_id,
        product_id=product_id if lines is None else None,
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

    write_specs = _write_specs_from_draft_or_payload(draft=draft, lines=lines, product_id=product_id)
    if not write_specs:
        raise ValueError("seed_case_has_no_lines — pick a seed with lines or pass lines[]")

    seen_grains: set[tuple[int, int | None, str]] = set()
    for spec in write_specs:
        grain = _grain_key(int(spec["product_id"]), spec.get("distributor_id"), spec.get("pod_quarter") or period_label)
        if grain in seen_grains:
            raise ValueError(f"duplicate_line_grain product_id={grain[0]} distributor_id={grain[1]} pod_quarter={grain[2]}")
        seen_grains.add(grain)

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
            f"seed_channel={seed.channel}; line_count={len(write_specs)}"
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

    created_lines: list[CporCaseLine] = []
    line_reports: list[dict[str, Any]] = []
    as_of = date.today()
    default_pod = period_label or f"{str(seed.window_start.year)[2:]}Q{(seed.window_start.month - 1) // 3 + 1}"

    for spec in write_specs:
        pid = int(spec["product_id"])
        prod = session.get(DimProduct, pid)
        if prod is None:
            raise ValueError(f"unknown_product_id={pid}")
        srp = spec.get("srp")
        if srp is None or float(srp) <= 0:
            raise ValueError(f"seed_line_missing_srp product_id={pid}")
        estimate = float(spec.get("estimate_qty") or 0)
        if estimate <= 0:
            raise ValueError(f"no_positive_estimate_qty product_id={pid}")

        dirty = {str(f) for f in (spec.get("dirty_fields") or [])}
        did = spec.get("distributor_id")
        pod = spec.get("pod_quarter") or default_pod
        intake = suggest_intake_weighted_mac(
            session,
            customer_id=case.customer_id,
            product_id=pid,
            distributor_id=int(did) if did is not None else None,
            window_start=seed.window_start,
            window_end=seed.window_end,
            as_of=as_of,
            exclude_case_id=case.id,
        )
        intake_json = _intake_payload(intake)
        supplied_cost = spec.get("cost_basis")
        if "cost_basis" in dirty and supplied_cost is not None:
            cost_basis = float(supplied_cost)
            cost_source = COST_SOURCE_MANUAL
        else:
            cost_basis = float(intake.cost_basis) if intake.cost_basis is not None else None
            cost_source = COST_SOURCE_INTAKE_WEIGHTED
        cover_override = spec.get("cover_override")
        cost_evidence = {
            **intake_json["evidence"],
            "flags": list(intake_json.get("flags") or []),
            "planner": {
                "dirty_fields": sorted(dirty),
                "cost_source": cost_source,
                "cover_override": float(cover_override) if cover_override is not None else None,
                "cover_not_persisted_to_customer_term": True,
            },
        }

        line = CporCaseLine(
            case_id=case.id,
            product_id=pid,
            distributor_id=int(did) if did is not None else None,
            pod_quarter=pod,
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
            event_type="line_created",
            actor=actor_s,
            payload={
                "line_id": line.id,
                "recompute_flags": rep.get("flags"),
                "source": "b4",
                "cost_source": cost_source,
                "dirty_fields": sorted(dirty),
            },
        )
        created_lines.append(line)
        line_reports.append(
            {
                "line_id": int(line.id),
                "product_id": pid,
                "estimate_qty": float(line.estimate_qty or 0),
                "cost_basis": float(line.cost_basis) if line.cost_basis is not None else None,
                "cost_source": line.cost_source,
                "dirty_fields": sorted(dirty),
            }
        )

    record_event(
        session,
        case_id=case.id,
        event_type="created",
        actor=actor_s,
        payload={
            "case_code": code,
            "from": "b4_promo_plan_draft",
            "seed_case_id": seed_case_id,
            "line_count": len(created_lines),
        },
    )
    session.commit()
    session.refresh(case)
    first = created_lines[0]
    session.refresh(first)

    return {
        "created": True,
        "case_id": int(case.id),
        "case_code": case.case_code,
        "line_id": int(first.id),
        "line_ids": [int(l.id) for l in created_lines],
        "lines": line_reports,
        "estimate_qty": float(first.estimate_qty or 0),
        "over_budget_warn": bool(budget.get("over_budget_warn")),
        "budget_status": budget.get("tracks", {}).get("money", {}).get("status"),
        "draft": draft,
        "href": f"/commercial-planner/cpor-cases/{case.id}",
    }
