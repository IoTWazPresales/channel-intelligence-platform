"""B2 budget position — dual track (money + support-%), profile-driven binding axis.

Domain §1.8 / Q-001: money is binding for current tenant; support-% informational.
Hard enforce stays off until over-budget reapproval workflow ships.

Planned reservation is **derived** from lineup draft lines × SKU economics (Q-002),
not loaded from historical budget facts. CPOR drawdown filters by ``pod_quarter``
matching ``period_label`` (string join — no FK).

SRP for reservation math comes from plan/lineup authoring evidence
(``dap_evidence_local`` / ``msrp_local``), never from ``CommercialSkuAssumption``
(which has cost + reserve % only — no SRP column).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commercial_planner import CommercialSkuAssumption
from app.models.cpor import CporCaseLine
from app.models.lineup import FactLineupPlanItem
from app.services import commercial_tenant_profile as tenant_profile
from app.services.lineup.profit_reservation import compute_profit_with_reservation

from app.services.commercial_planner.lineup_period_canonical import (
    normalize_period_label,
    period_label_sql_variants,
    period_labels_equivalent,
)


def _positive_srp(*candidates: float | None) -> float | None:
    """First positive SRP candidate; never fabricate."""
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


async def _srp_evidence_by_product(
    db: AsyncSession,
    product_ids: set[int],
) -> dict[int, float]:
    """Map product_id → SRP from commercial lineup evidence (dap preferred, else msrp)."""
    if not product_ids:
        return {}
    from app.models.commercial_lineup import CommercialLineupLine

    stmt = (
        select(
            CommercialLineupLine.product_id,
            CommercialLineupLine.dap_evidence_local,
            CommercialLineupLine.msrp_local,
            CommercialLineupLine.id,
        )
        .where(
            CommercialLineupLine.product_id.in_(tuple(product_ids)),
        )
        .order_by(CommercialLineupLine.id.desc())
    )
    out: dict[int, float] = {}
    for pid, dap, msrp, _lid in (await db.execute(stmt)).all():
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


async def derive_planned_reservations_from_lineup(
    db: AsyncSession,
    *,
    period_label: str | None = None,
    limit: int = 5000,
) -> list[dict[str, Any]]:
    """Build planned reservation rows from draft lineup items, else commercial lineup lines.

    Returns planned rows. Skip diagnostics are attached on the list via
    ``__dict__``-style attribute ``_derive_diagnostics`` for ``build_budget_position``.
    Prefer :func:`derive_planned_reservations_with_diagnostics` when callers need counts.
    """
    planned, _diag = await derive_planned_reservations_with_diagnostics(
        db, period_label=period_label, limit=limit
    )
    return planned


async def derive_planned_reservations_with_diagnostics(
    db: AsyncSession,
    *,
    period_label: str | None = None,
    limit: int = 5000,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build planned reservations + skip diagnostics (missing SKU / missing SRP)."""
    diagnostics: dict[str, Any] = {
        "skipped_missing_sku": 0,
        "skipped_missing_srp": 0,
        "skipped_zero_qty": 0,
        "srp_basis": "commercial_lineup_dap_or_msrp",
        "note": (
            "SRP from lineup authoring evidence only; "
            "CommercialSkuAssumption has no target_srp_local"
        ),
    }

    stmt = select(FactLineupPlanItem).limit(limit)
    items = list((await db.scalars(stmt)).all())
    if period_label:
        want = normalize_period_label(period_label)
        items = [i for i in items if period_labels_equivalent(i.period_label, want)]

    product_ids: set[int] = set()
    # (product_id, customer_id, qty, period_label, source_id, srp_or_none)
    raw_lines: list[tuple[int | None, int | None, float, str | None, int | None, float | None]] = []

    if items:
        for item in items:
            product_ids.add(int(item.product_id))
            raw_lines.append(
                (
                    int(item.product_id),
                    int(item.customer_id),
                    float(item.planned_volume_units or 0),
                    item.period_label,
                    int(item.id),
                    None,  # resolve via commercial lineup evidence below
                )
            )
        srp_by_pid = await _srp_evidence_by_product(db, product_ids)
        raw_lines = [
            (pid, cid, qty, plabel, source_id, srp_by_pid.get(pid) if pid is not None else None)
            for pid, cid, qty, plabel, source_id, _ in raw_lines
        ]
    else:
        # Fallback: commercial lineup (imported) — still no historical budget facts.
        from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupLine

        case_stmt = select(CommercialLineupCase.id, CommercialLineupCase.period_label)
        cases = list((await db.execute(case_stmt.limit(200))).all())
        if period_label:
            cases = [(cid, pl) for cid, pl in cases if period_labels_equivalent(pl, period_label)]
        case_period = {int(cid): plabel for cid, plabel in cases}
        if case_period:
            line_stmt = select(CommercialLineupLine).where(
                CommercialLineupLine.case_id.in_(tuple(case_period.keys())),
                CommercialLineupLine.product_id.isnot(None),
            ).limit(limit)
            for line in (await db.scalars(line_stmt)).all():
                pid = int(line.product_id) if line.product_id is not None else None
                if pid is None:
                    continue
                product_ids.add(pid)
                srp = _positive_srp(
                    float(line.dap_evidence_local) if line.dap_evidence_local is not None else None,
                    float(line.msrp_local) if line.msrp_local is not None else None,
                )
                raw_lines.append(
                    (
                        pid,
                        int(line.customer_id) if line.customer_id is not None else None,
                        float(line.quantity_units or 0),
                        case_period.get(int(line.case_id)),
                        int(line.id),
                        srp,
                    )
                )

    if not raw_lines:
        return [], diagnostics

    sku_by_pid: dict[int, CommercialSkuAssumption] = {}
    if product_ids:
        for sku in (
            await db.scalars(
                select(CommercialSkuAssumption).where(
                    CommercialSkuAssumption.product_id.in_(tuple(product_ids))
                )
            )
        ).all():
            sku_by_pid[int(sku.product_id)] = sku

    planned: list[dict[str, Any]] = []
    for product_id, customer_id, qty, plabel, source_id, srp in raw_lines:
        if product_id is None or qty <= 0:
            diagnostics["skipped_zero_qty"] += 1
            continue
        sku = sku_by_pid.get(product_id)
        if sku is None:
            diagnostics["skipped_missing_sku"] += 1
            continue
        if srp is None or srp <= 0:
            diagnostics["skipped_missing_srp"] += 1
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
        reserved = float((economics.get("reservation") or {}).get("total") or 0)
        revenue = float(economics.get("oem_sell_in_per_unit") or 0) * qty
        planned.append(
            {
                "product_id": product_id,
                "customer_id": customer_id,
                "reserved_amount": reserved,
                "revenue": revenue,
                "source_line_id": source_id,
                "period_label": plabel,
                "target_srp_local": float(srp),
                "srp_source": "commercial_lineup_evidence",
            }
        )
    return planned, diagnostics


async def build_budget_position(
    db: AsyncSession,
    *,
    planned_reservations: list[dict[str, Any]] | None = None,
    period_label: str | None = None,
    auto_derive_from_lineup: bool = True,
) -> dict[str, Any]:
    """Aggregate planned reservations vs CPOR line spend (dual track).

    ``planned_reservations`` items: ``{product_id?, customer_id?, reserved_amount, revenue?}``.
    When omitted/empty and ``auto_derive_from_lineup``, derive from draft lineup × SKU economics.
    """
    planned = list(planned_reservations or [])
    derived = False
    derive_diag: dict[str, Any] = {
        "skipped_missing_sku": 0,
        "skipped_missing_srp": 0,
        "skipped_zero_qty": 0,
    }
    if auto_derive_from_lineup and not planned:
        planned, derive_diag = await derive_planned_reservations_with_diagnostics(
            db, period_label=period_label
        )
        derived = bool(planned)

    reserved_money = sum(float(p.get("reserved_amount") or 0) for p in planned)
    planned_revenue = sum(float(p.get("revenue") or 0) for p in planned)
    reserved_pct = (reserved_money / planned_revenue) if planned_revenue > 0 else None

    drawn_usd_f = 0.0
    drawn_zar_f = 0.0
    line_count = 0
    cpor_ok = True
    try:
        stmt = select(
            func.coalesce(func.sum(CporCaseLine.ttl_support_usd), 0),
            func.coalesce(func.sum(CporCaseLine.ttl_support), 0),
            func.count(CporCaseLine.id),
        )
        if period_label:
            variants = period_label_sql_variants(period_label)
            if variants:
                stmt = stmt.where(CporCaseLine.pod_quarter.in_(tuple(variants)))
            else:
                stmt = stmt.where(CporCaseLine.pod_quarter == period_label)
        drawn_usd, drawn_zar, n = (await db.execute(stmt)).one()
        drawn_usd_f = float(drawn_usd or 0)
        drawn_zar_f = float(drawn_zar or 0)
        line_count = int(n or 0)
        cpor_ok = True
    except Exception:
        cpor_ok = False
        drawn_usd_f = 0.0
        drawn_zar_f = 0.0
        line_count = 0

    remaining_money = reserved_money - drawn_usd_f
    money_util = (drawn_usd_f / reserved_money) if reserved_money > 0 else None

    try:
        sku_n = int(
            (await db.execute(select(func.count()).select_from(CommercialSkuAssumption))).scalar()
            or 0
        )
    except Exception:
        sku_n = 0

    if reserved_money > 0 and drawn_usd_f > reserved_money:
        money_status = "over"
    elif reserved_money > 0:
        money_status = "ok"
    elif sku_n == 0:
        money_status = "missing_sku_economics"
    elif int(derive_diag.get("skipped_missing_srp") or 0) > 0 and not planned:
        money_status = "missing_srp"
    else:
        money_status = "no_planned_reservation"

    profile = tenant_profile.profile_snapshot()
    return {
        "as_of": date.today().isoformat(),
        "period_label": period_label,
        "period_label_normalized": normalize_period_label(period_label),
        "hard_enforce": bool(tenant_profile.HARD_ENFORCE_BUDGET),
        "constraint_type": tenant_profile.CONSTRAINT_AXIS,
        "binding_axis": tenant_profile.CONSTRAINT_AXIS,
        "over_budget_action": tenant_profile.OVER_BUDGET_ACTION,
        "tenant_profile": profile,
        "tracks": {
            "money": {
                "planned_reservation_usd": round(reserved_money, 4),
                "drawn_cpor_usd": round(drawn_usd_f, 4),
                "drawn_cpor_zar_display": round(drawn_zar_f, 4),
                "remaining_usd": round(remaining_money, 4),
                "utilisation": money_util,
                "status": money_status,
                "binding": tenant_profile.CONSTRAINT_AXIS in ("money", "dual"),
            },
            "support_pct": {
                "planned_support_pct_of_sell_in": reserved_pct,
                "note": "Informational for money-binding tenants; planned % from reservation÷sell-in",
                "binding": tenant_profile.CONSTRAINT_AXIS in ("support_pct", "dual"),
            },
        },
        "cpor_line_count": line_count,
        "cpor_data_available": cpor_ok,
        "sku_assumption_count": sku_n,
        "planned_line_count": len(planned),
        "planned_from_lineup_derived": derived,
        "derive_diagnostics": derive_diag,
        "basis": (
            "planned=fact_lineup_plan_item×SKU economics×lineup SRP evidence (Q-002); "
            "drawn=cpor_case_line.ttl_support_usd filtered by pod_quarter≈period_label"
        ),
        "reservation_source": tenant_profile.RESERVATION_SOURCE,
        "q002_reservation_source": tenant_profile.RESERVATION_SOURCE,
    }
