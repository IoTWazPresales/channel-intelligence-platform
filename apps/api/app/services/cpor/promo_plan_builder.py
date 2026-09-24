"""B4 — promotion plan builder draft (compose A2 + B1 + B2 + 15C per-line grid).

Compose is the primary surface. Optional create-from-draft writes a **draft** CPOR case
via the existing case/line path (no parallel economics ledger). Unit 15C emits per-line
intake-weighted MAC + history units; create carries operator edits (D-051–D-053).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupLine
from app.models.commercial_planner import CommercialSkuAssumption
from app.models.cpor import CporCase, CporCaseLine
from app.models.dimensions import DimCustomer, DimProduct
from app.models.fact_demand_forecast import FactDemandForecast
from app.models.lineup import FactLineupPlanItem
from app.services import commercial_tenant_profile as tenant_profile
from app.services.commercial_planner.lineup_period_canonical import (
    active_lineup_case_filters,
    active_lineup_line_filters,
    normalize_period_label,
    parse_period_filter_to_year_quarter,
    period_label_sql_variants,
    period_labels_equivalent,
    quarter_bounds_from_period_start,
    quarter_from_period_start,
)
from app.services.cpor.intake_weighted_mac import suggest_intake_weighted_mac
from app.services.cpor.intelligence_scope import where_commercial_intelligence
from app.services.cpor.norms_and_comparable import (
    build_comparable_cases,
    normalize_quarter_label,
    quarter_index,
)
from app.services.cpor.promotion_type_vocab import CPOR_PROMOTION_TYPE_SET
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
PRODUCT_SET_LINEUP = "commercial_lineup_line"
PRODUCT_SET_CUSTOMER_HISTORY = "same_customer_cpor_case_line"
PRODUCT_SET_SEED = "seed_case_lines"
PRODUCT_SET_EXPLICIT = "line_specs"
DEFAULT_PROPOSAL_PROMOTION_TYPE = "Sell out PP"


def window_from_period_label(period_label: str | None) -> tuple[date, date]:
    """Inclusive quarter window for a period token (``2026Q2`` / ``2026 Q2`` / ``26Q2``)."""
    if not period_label or not str(period_label).strip():
        raise ValueError("unparseable_period_label")
    year, q = parse_period_filter_to_year_quarter(period_label)
    if year is None or q is None:
        raise ValueError(f"unparseable_period_label={period_label!r}")
    start_month = 3 * (int(q) - 1) + 1
    start = date(int(year), start_month, 1)
    q_start, q_end_excl = quarter_bounds_from_period_start(start)
    return q_start, q_end_excl - timedelta(days=1)


def _lineup_case_matches_period(case: CommercialLineupCase, period_label: str) -> bool:
    if period_labels_equivalent(case.period_label, period_label):
        return True
    if case.inferred_period_start is None:
        return False
    filt_year, filt_q = parse_period_filter_to_year_quarter(period_label)
    case_year, case_q = quarter_from_period_start(case.inferred_period_start)
    if filt_year is not None and filt_year != case_year:
        return False
    if filt_q is not None and filt_q != case_q:
        return False
    return filt_year is not None or filt_q is not None


def _dedupe_specs(specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[tuple[int, int | None], dict[str, Any]] = {}
    for spec in specs:
        key = (int(spec["product_id"]), spec.get("distributor_id"))
        prev = best.get(key)
        if prev is None:
            best[key] = spec
            continue
        prev_srp = float(prev.get("srp") or 0)
        new_srp = float(spec.get("srp") or 0)
        if prev_srp <= 0 < new_srp:
            best[key] = spec
        elif new_srp > 0 and float(spec.get("estimate_qty") or 0) > float(prev.get("estimate_qty") or 0):
            best[key] = spec
    return list(best.values())


def _specs_from_lineup(session: Session, *, customer_id: int, period_label: str) -> list[dict[str, Any]]:
    cases = list(session.scalars(select(CommercialLineupCase).where(*active_lineup_case_filters())).all())
    case_ids = [int(c.id) for c in cases if _lineup_case_matches_period(c, period_label)]
    if not case_ids:
        return []
    lines = session.scalars(
        select(CommercialLineupLine).where(
            CommercialLineupLine.case_id.in_(tuple(case_ids)),
            CommercialLineupLine.customer_id == int(customer_id),
            CommercialLineupLine.product_id.isnot(None),
            *active_lineup_line_filters(),
        )
    ).all()
    out: list[dict[str, Any]] = []
    for line in lines:
        srp = _positive_srp(
            float(line.dap_evidence_local) if line.dap_evidence_local is not None else None,
            float(line.msrp_local) if line.msrp_local is not None else None,
            float(line.promo_price_evidence_local) if line.promo_price_evidence_local is not None else None,
        )
        did = int(line.distributor_id) if line.distributor_id is not None else None
        out.append(
            {
                "seed_line_id": None,
                "product_id": int(line.product_id),
                "distributor_id": did,
                "srp": srp,
                "estimate_qty": float(line.quantity_units or 0),
                "pod_quarter": normalize_period_label(period_label),
                "cover_override": None,
            }
        )
    return _dedupe_specs(out)


def _specs_from_customer_history(session: Session, *, customer_id: int, period_label: str) -> list[dict[str, Any]]:
    cases = list(
        session.scalars(
            select(CporCase)
            .where(
                CporCase.customer_id == int(customer_id),
                CporCase.superseded_by_case_id.is_(None),
                where_commercial_intelligence(),
                CporCase.status.in_(("ended", "settled", "draft", "proposed", "approved", "active")),
            )
            .order_by(CporCase.id.desc())
        ).all()
    )
    if not cases:
        return []
    case_ids = [int(c.id) for c in cases]
    lines = session.scalars(
        select(CporCaseLine)
        .where(CporCaseLine.case_id.in_(tuple(case_ids)), CporCaseLine.product_id.isnot(None))
        .order_by(CporCaseLine.id.desc())
    ).all()
    case_rank = {cid: i for i, cid in enumerate(case_ids)}
    lines = sorted(lines, key=lambda ln: (case_rank.get(int(ln.case_id), 10_000), -int(ln.id)))
    out: list[dict[str, Any]] = []
    for line in lines:
        srp = _positive_srp(float(line.srp) if line.srp is not None else None)
        did = int(line.distributor_id) if line.distributor_id is not None else None
        out.append(
            {
                "seed_line_id": None,
                "product_id": int(line.product_id),
                "distributor_id": did,
                "srp": srp,
                "estimate_qty": float(line.estimate_qty or 0),
                "pod_quarter": normalize_period_label(period_label) or line.pod_quarter,
                "cover_override": None,
            }
        )
    return _dedupe_specs(out)


def product_specs_for_customer_period(
    session: Session, *, customer_id: int, period_label: str
) -> tuple[list[dict[str, Any]], str | None]:
    lineup = _specs_from_lineup(session, customer_id=customer_id, period_label=period_label)
    if lineup:
        return lineup, PRODUCT_SET_LINEUP
    history = _specs_from_customer_history(session, customer_id=customer_id, period_label=period_label)
    if history:
        return history, PRODUCT_SET_CUSTOMER_HISTORY
    return [], None


def build_same_customer_comparables(
    session: Session,
    *,
    customer_id: int,
    period_label: str | None,
    limit: int = 10,
    exclude_case_id: int | None = None,
) -> dict[str, Any]:
    """Same-customer historical cases only. Never ranks other customers."""
    n = normalize_period_label(period_label)
    target_q = normalize_quarter_label(n) if n else None
    t_idx = quarter_index(target_q) if target_q else None
    cases = list(
        session.scalars(
            select(CporCase)
            .where(
                CporCase.customer_id == int(customer_id),
                CporCase.superseded_by_case_id.is_(None),
                where_commercial_intelligence(),
            )
            .options(joinedload(CporCase.lines))
        )
        .unique()
        .all()
    )
    ranked: list[dict[str, Any]] = []
    for case in cases:
        if exclude_case_id is not None and int(case.id) == int(exclude_case_id):
            continue
        est = 0.0
        quarters: list[str] = []
        for line in case.lines or []:
            try:
                e = float(line.estimate_qty or 0)
            except (TypeError, ValueError):
                e = 0.0
            if e > 0:
                est += e
            q = normalize_quarter_label(getattr(line, "pod_quarter", None), fallback=case.window_start)
            if q:
                quarters.append(q)
        q_seed = max(set(quarters), key=quarters.count) if quarters else normalize_quarter_label(
            None, fallback=case.window_start
        )
        q_idx = quarter_index(q_seed) if q_seed else None
        if t_idx is not None and q_idx is not None:
            q_prox = 1.0 / (1.0 + abs(q_idx - t_idx))
        else:
            q_prox = 0.0
        ranked.append(
            {
                "case_id": int(case.id),
                "case_code": case.case_code,
                "customer_id": int(case.customer_id),
                "promotion_type": case.promotion_type,
                "status": case.status,
                "window_start": case.window_start.isoformat() if case.window_start else None,
                "window_end": case.window_end.isoformat() if case.window_end else None,
                "quarter": q_seed,
                "estimate_qty": round(est, 4),
                "score": q_prox,
            }
        )
    ranked.sort(key=lambda r: (-float(r["score"]), -float(r["estimate_qty"])))
    return {
        "items": ranked[: max(1, min(int(limit), 50))],
        "error": None,
        "same_customer_only": True,
    }


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
    customer_id: int | None = None,
    period_label: str | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    if line_specs is not None:
        return [_normalize_line_spec(s) for s in line_specs], PRODUCT_SET_EXPLICIT
    specs: list[dict[str, Any]] = []
    source: str | None = None
    if seed is not None:
        stmt = select(CporCaseLine).where(CporCaseLine.case_id == seed.id)
        if product_id is not None:
            stmt = stmt.where(CporCaseLine.product_id == int(product_id))
        stmt = stmt.order_by(CporCaseLine.id.asc())
        for line in session.scalars(stmt).all():
            specs.append(_spec_from_seed_line(line))
        if specs:
            source = PRODUCT_SET_SEED
    elif customer_id is not None and period_label:
        specs, source = product_specs_for_customer_period(
            session, customer_id=int(customer_id), period_label=period_label
        )
        if product_id is not None:
            specs = [s for s in specs if int(s["product_id"]) == int(product_id)]
    for extra in extra_lines or []:
        specs.append(_normalize_line_spec(extra))
        if source is None:
            source = PRODUCT_SET_EXPLICIT
    return specs, source


def _compose_suggestion_row(
    session: Session,
    *,
    seed: CporCase | None,
    spec: dict[str, Any],
    customer_id: int | None,
    horizon_weeks: int,
    period_label: str | None,
    top_comparables: list[dict[str, Any]],
    window_start: date | None = None,
    window_end: date | None = None,
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

    if window_start is None:
        window_start = seed.window_start if seed is not None else date.today()
    if window_end is None:
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
        "product_sales_model_name": prod.sales_model_name if prod is not None else None,
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
    seed_case_id: int | None = None,
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

    Seed case id remains the B4 path. Customer + period proposes without a seed.
    Returns per-line suggestion rows (D-051). Server is stateless on dirty flags (D-052).
    """
    if seed_case_id is None and (customer_id is None or not period_label):
        raise ValueError("missing_seed_or_customer_period")

    seed = session.get(CporCase, int(seed_case_id)) if seed_case_id is not None else None
    seed_customer_id = int(seed.customer_id) if seed is not None else customer_id
    effective_customer = customer_id if customer_id is not None else seed_customer_id

    window_start: date | None = seed.window_start if seed is not None else None
    window_end: date | None = seed.window_end if seed is not None else None
    if window_start is None and period_label:
        window_start, window_end = window_from_period_label(period_label)

    if seed_case_id is not None:
        comparables = build_comparable_cases(session, case_id=int(seed_case_id), limit=comparable_limit)
    elif effective_customer is not None:
        comparables = build_same_customer_comparables(
            session,
            customer_id=int(effective_customer),
            period_label=period_label,
            limit=comparable_limit,
        )
    else:
        comparables = {"items": [], "error": "no_customer", "same_customer_only": True}
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
    specs, product_set_source = _collect_line_specs(
        session,
        seed=seed,
        product_id=product_id,
        extra_lines=extra_lines,
        line_specs=line_specs,
        customer_id=int(effective_customer) if effective_customer is not None else None,
        period_label=period_label,
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
            window_start=window_start,
            window_end=window_end,
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
        "seed_window_start": seed.window_start.isoformat() if seed is not None else (
            window_start.isoformat() if window_start else None
        ),
        "seed_window_end": seed.window_end.isoformat() if seed is not None else (
            window_end.isoformat() if window_end else None
        ),
        "window_start": window_start.isoformat() if window_start else None,
        "window_end": window_end.isoformat() if window_end else None,
        "customer_id": int(effective_customer) if effective_customer is not None else None,
        "product_set_source": product_set_source,
        "seed_lines": seed_lines,
        "lines": suggestion_rows,
        "comparables": {
            "count": len(comparables.get("items") or []),
            "top": top,
            "error": comparables.get("error"),
            "same_customer_only": bool(comparables.get("same_customer_only")),
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
            "Customer+period product set is lineup then same-customer history; never other customers",
            "Competitor prices and listing joins are not inputs to this compose",
        ],
        "uncovered": [
            "fact_competitor_price",
            "listing_joined_to_line",
            "weeks_of_cover_observation_as_target_cover",
            "cross_customer_analogue",
            "uplift_from_claim_evidence",
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
    seed_case_id: int | None = None,
    customer_id: int | None = None,
    promotion_type: str | None = None,
    tenant_id: str = "default",
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
    if seed_case_id is None and (customer_id is None or not period_label):
        raise ValueError("missing_seed_or_customer_period")
    draft = build_promo_plan_draft(
        session,
        seed_case_id=seed_case_id,
        customer_id=customer_id,
        product_id=product_id if lines is None else None,
        period_label=period_label,
        planned_support_usd=planned_support_usd,
        planned_revenue_usd=planned_revenue_usd,
        horizon_weeks=horizon_weeks,
        line_specs=None,
    )
    seed = session.get(CporCase, int(seed_case_id)) if seed_case_id is not None else None
    if seed_case_id is not None and seed is None:
        raise ValueError("seed_case_not_found")
    if seed is None:
        if customer_id is None:
            raise ValueError("missing_seed_or_customer_period")
        cust = session.get(DimCustomer, int(customer_id))
        if cust is None:
            raise ValueError("customer_not_found")

    budget = draft["budget_check"]
    if budget.get("create_blocked") and not confirm_over_budget:
        raise ValueError(
            "over_budget_requires_confirm — pass confirm_over_budget=true "
            f"(action={budget.get('over_budget_action')})"
        )

    write_specs = _write_specs_from_draft_or_payload(draft=draft, lines=lines, product_id=product_id)
    if not write_specs:
        raise ValueError("no_lines_to_create — lineup/history empty for this customer and period, or pass lines[]")

    seen_grains: set[tuple[int, int | None, str]] = set()
    for spec in write_specs:
        grain = _grain_key(int(spec["product_id"]), spec.get("distributor_id"), spec.get("pod_quarter") or period_label)
        if grain in seen_grains:
            raise ValueError(f"duplicate_line_grain product_id={grain[0]} distributor_id={grain[1]} pod_quarter={grain[2]}")
        seen_grains.add(grain)

    from app.services.cpor.promotion_type_vocab import CPOR_CHANNEL_SET

    if seed is not None:
        channel = (seed.channel or "reseller").strip().lower()
        promo = seed.promotion_type
        win_start, win_end = seed.window_start, seed.window_end
        tenant = seed.tenant_id
        cid = int(seed.customer_id)
        origin = "proposed_by_cip"
        case_name = f"B4 draft from {seed.case_code}"
        notes = (
            f"Created from B4 promo-plan-draft seed={seed_case_id}; "
            f"budget_status={budget.get('tracks', {}).get('money', {}).get('status')}; "
            f"over_warn={budget.get('over_budget_warn')}; "
            f"seed_channel={seed.channel}; line_count={len(write_specs)}"
        )
        roe = seed.roe_snapshot
        currency = seed.currency_code or "ZAR"
    else:
        channel = "reseller"
        promo = (promotion_type or DEFAULT_PROPOSAL_PROMOTION_TYPE).strip()
        if promo not in CPOR_PROMOTION_TYPE_SET:
            raise ValueError(f"unknown_promotion_type={promo}")
        win_start, win_end = window_from_period_label(period_label)
        tenant = tenant_id or "default"
        cid = int(customer_id)  # type: ignore[arg-type]
        origin = "proposed_by_cip"
        case_name = f"Proposed {period_label}"
        notes = (
            f"Created from customer+period compose customer_id={cid} period={period_label}; "
            f"product_set_source={draft.get('product_set_source')}; "
            f"budget_status={budget.get('tracks', {}).get('money', {}).get('status')}; "
            f"line_count={len(write_specs)}"
        )
        roe = None
        currency = "ZAR"

    if channel not in CPOR_CHANNEL_SET:
        channel = "reseller"

    actor_s = actor or "b4_promo_draft"
    code = generate_case_code(session)
    case = CporCase(
        case_code=code,
        case_name=case_name,
        tenant_id=tenant,
        customer_id=cid,
        promotion_type=promo,
        window_start=win_start,
        window_end=win_end,
        status="draft",
        origin=origin,
        roe_snapshot=roe,
        currency_code=currency,
        channel=channel,
        notes=notes,
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
    default_pod = period_label or (
        f"{str(case.window_start.year)[2:]}Q{(case.window_start.month - 1) // 3 + 1}"
        if case.window_start is not None
        else None
    )

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
            window_start=case.window_start,
            window_end=case.window_end,
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
            window_start=case.window_start,
            window_end=case.window_end,
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
