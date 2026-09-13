"""Read-only Planning headline grains. Callers must print current_database() first."""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant_scope import tenant_id_from_user
from app.models.commercial_lineup import CommercialLineupCase
from app.services.commercial_planner.lineup_period_canonical import (
    active_lineup_case_filters,
)

logger = logging.getLogger(__name__)

_ACTIVE_STATUS_SQL = "('cancelled', 'superseded')"


def _empty(dbname: str | None, tenant: str) -> dict[str, Any]:
    return {
        "database": dbname,
        "tenant_id": tenant,
        "data_unavailable": True,
        "labels": {},
        "captions": {},
        "number_class": {},
    }


def _period_caption(labels: list[str]) -> str:
    cleaned = [p for p in labels if p]
    if not cleaned:
        return "no period_label on active cases"
    shown = cleaned[:6]
    extra = len(cleaned) - len(shown)
    text_labels = ", ".join(shown)
    if extra > 0:
        text_labels = f"{text_labels} (+{extra} more)"
    return text_labels


def _customer_plan_shipped(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[Any, dict[str, Any]] = defaultdict(
        lambda: {"customer": "Unattributed", "customer_id": None, "plan": 0.0, "shipped": 0.0}
    )
    for r in rows:
        cid = r.get("customer_id")
        label = (r.get("customer_label") or "").strip() or "Unattributed"
        key = cid if cid is not None else f"t:{label}"
        b = buckets[key]
        b["customer"] = label
        b["customer_id"] = cid
        b["plan"] += float(r.get("planned_units") or 0)
        b["shipped"] += float(r.get("shipped_units") or 0)
    out = [v for v in buckets.values() if v["plan"] > 0 or v["shipped"] > 0]
    out.sort(key=lambda r: (-r["plan"], r["customer"]))
    return out[:8]


async def _shipped_vs_plan(db: AsyncSession) -> dict[str, Any]:
    """Same grain as Execution vs plan (plan_vs_executed collect + scorecard)."""
    from app.services.commercial_planner.plan_vs_executed import (
        collect_execution_rows,
        compute_scorecard_from_execution_rows,
        lineup_linked_year_quarters,
        periods_from_coverage,
        resolve_default_period,
    )
    from app.services.commercial_planner.po_management import coverage as po_coverage

    cov = await po_coverage(db)
    all_periods = periods_from_coverage(cov)
    lineup_quarters = await lineup_linked_year_quarters(db)
    default_period = resolve_default_period(
        all_periods,
        coverage_groups=cov.get("groups"),
        lineup_linked_quarters=lineup_quarters,
    )
    rows = await collect_execution_rows(
        db,
        period_from=default_period,
        period_to=default_period,
    )
    scorecard = compute_scorecard_from_execution_rows(rows)
    fill = scorecard.get("fill_rate")
    planned = float(scorecard.get("planned_units") or 0)
    shipped_in = float(scorecard.get("shipped_units_in_plan") or 0)
    return {
        "period": default_period,
        "fill_rate": fill,
        "planned_units_execution": planned,
        "shipped_units_in_plan": shipped_in,
        "by_customer": _customer_plan_shipped(rows),
    }


async def planning_overview(db: AsyncSession, user: dict | None) -> dict[str, Any]:
    tenant = tenant_id_from_user(user)
    dbname = (await db.execute(text("SELECT current_database()"))).scalar()
    case_filters = active_lineup_case_filters()

    try:
        cases = int(
            (
                await db.execute(
                    select(func.count()).select_from(CommercialLineupCase).where(*case_filters)
                )
            ).scalar()
            or 0
        )
        period_rows = (
            await db.execute(
                select(CommercialLineupCase.period_label)
                .where(*case_filters)
                .where(CommercialLineupCase.period_label.isnot(None))
                .distinct()
            )
        ).scalars().all()
        period_labels = sorted({str(p) for p in period_rows if p})

        line_row = (
            await db.execute(
                text(
                    f"""
                    SELECT
                      count(*)::int AS lines,
                      coalesce(sum(l.quantity_units), 0) AS plan_units,
                      count(*) FILTER (
                        WHERE l.product_id IS NOT NULL AND sa.product_id IS NOT NULL
                      )::int AS sku_ok,
                      count(*) FILTER (
                        WHERE l.customer_id IS NOT NULL AND ct.customer_id IS NOT NULL
                      )::int AS terms_ok,
                      count(*) FILTER (
                        WHERE l.distributor_id IS NOT NULL
                      )::int AS dist_ok,
                      count(*) FILTER (
                        WHERE sa.controlled_cost_amount IS NOT NULL
                          AND sa.controlled_cost_amount > 0
                      )::int AS cost_ok
                    FROM commercial_lineup_line l
                    JOIN commercial_lineup_case c ON c.id = l.case_id
                    LEFT JOIN commercial_sku_assumption sa ON sa.product_id = l.product_id
                    LEFT JOIN commercial_customer_term ct ON ct.customer_id = l.customer_id
                    WHERE c.superseded_by_case_id IS NULL
                      AND c.commercial_status NOT IN {_ACTIVE_STATUS_SQL}
                      AND l.row_status IS DISTINCT FROM 'superseded'
                    """
                )
            )
        ).mappings().one()

        econ_row = (
            await db.execute(
                text(
                    """
                    SELECT
                      count(*)::int AS plan_lines,
                      count(*) FILTER (
                        WHERE calc_flags IS NOT NULL
                          AND jsonb_typeof(calc_flags) = 'array'
                          AND jsonb_array_length(calc_flags) > 0
                      )::int AS flagged
                    FROM commercial_plan_line
                    """
                )
            )
        ).mappings().one()
    except Exception:
        logger.exception("planning_overview lineup/economics query failed")
        return _empty(dbname, tenant)

    lines = int(line_row["lines"] or 0)
    plan_units = float(line_row["plan_units"] or 0)
    sku_ok = int(line_row["sku_ok"] or 0)
    terms_ok = int(line_row["terms_ok"] or 0)
    dist_ok = int(line_row["dist_ok"] or 0)
    cost_ok = int(line_row["cost_ok"] or 0)
    try:
        not_ready = int(
            (
                await db.execute(
                    text(
                        f"""
                        SELECT count(*)::int
                        FROM commercial_lineup_line l
                        JOIN commercial_lineup_case c ON c.id = l.case_id
                        LEFT JOIN commercial_sku_assumption sa ON sa.product_id = l.product_id
                        LEFT JOIN commercial_customer_term ct ON ct.customer_id = l.customer_id
                        WHERE c.superseded_by_case_id IS NULL
                          AND c.commercial_status NOT IN {_ACTIVE_STATUS_SQL}
                          AND l.row_status IS DISTINCT FROM 'superseded'
                          AND (
                            l.product_id IS NULL OR sa.product_id IS NULL
                            OR l.customer_id IS NULL OR ct.customer_id IS NULL
                            OR l.distributor_id IS NULL
                            OR sa.controlled_cost_amount IS NULL
                            OR sa.controlled_cost_amount <= 0
                          )
                        """
                    )
                )
            ).scalar()
            or 0
        )
    except Exception:
        logger.exception("planning_overview not-ready query failed")
        return _empty(dbname, tenant)

    readiness_ok = max(lines - not_ready, 0)
    plan_lines = int(econ_row["plan_lines"] or 0)
    flagged = int(econ_row["flagged"] or 0)
    economics_ok = max(plan_lines - flagged, 0)

    execution: dict[str, Any] = {
        "period": None,
        "fill_rate": None,
        "planned_units_execution": None,
        "shipped_units_in_plan": None,
        "by_customer": [],
        "unavailable": True,
    }
    try:
        execution = {**await _shipped_vs_plan(db), "unavailable": False}
    except Exception:
        logger.exception("planning_overview execution grain failed")

    fill = execution.get("fill_rate")
    fill_pct = round(float(fill) * 100) if fill is not None else None
    exec_period = execution.get("period") or "no default execution period"
    shipped_in = execution.get("shipped_units_in_plan")
    planned_exec = execution.get("planned_units_execution")

    period_text = _period_caption(period_labels)

    return {
        "database": dbname,
        "tenant_id": tenant,
        "data_unavailable": False,
        "cases": cases,
        "lines": lines,
        "plan_units": plan_units,
        "period_labels": period_labels,
        "readiness_missing": not_ready,
        "readiness_ok": readiness_ok,
        "readiness": {
            "sku_assumptions_ok": sku_ok,
            "customer_terms_ok": terms_ok,
            "distributor_attribution_ok": dist_ok,
            "cost_basis_ok": cost_ok,
            "sku_assumptions_ratio": (sku_ok / lines) if lines else None,
            "customer_terms_ratio": (terms_ok / lines) if lines else None,
            "distributor_attribution_ratio": (dist_ok / lines) if lines else None,
            "cost_basis_ratio": (cost_ok / lines) if lines else None,
        },
        "economics_flagged": flagged,
        "economics_ok": economics_ok,
        "plan_lines": plan_lines,
        "fill_rate": fill,
        "execution_period": execution.get("period"),
        "execution_unavailable": bool(execution.get("unavailable")),
        "shipped_units_in_plan": shipped_in,
        "planned_units_execution": planned_exec,
        "by_customer": execution.get("by_customer") or [],
        "labels": {
            "cases": "Lineup cases",
            "plan_units": "Plan units",
            "shipped_vs_plan": "Shipped vs plan",
            "readiness_missing": "Lines not ready",
            "economics_flagged": "Economics flagged",
        },
        "captions": {
            "cases": (
                f"{lines} commercial_lineup_line on active commercial_lineup_case "
                f"({period_text}). Not fact_lineup_plan_item (relocated N-0009 workspace)."
            ),
            "plan_units": (
                "sum(commercial_lineup_line.quantity_units) on active cases; "
                "not commercial_plan_line.target_units"
            ),
            "shipped_vs_plan": (
                f"Fill rate min(shipped, planned)/planned on Execution vs plan grain "
                f"({exec_period})"
                + (
                    f" — {shipped_in:g} shipped-in-plan of {planned_exec:g} planned"
                    if shipped_in is not None and planned_exec is not None
                    else ""
                )
                + ". Not lab shipped/plan fixture and not P09."
            ),
            "readiness_missing": (
                "Active lineup lines missing SKU assumption, customer terms, "
                "distributor_id, or controlled_cost_amount > 0"
            ),
            "economics_flagged": (
                f"{economics_ok} ok · commercial_plan_line.calc_flags non-empty "
                f"({plan_lines} planner lines). Different table from lineup lines."
            ),
        },
        "number_class": {
            "cases": "iii",
            "plan_units": "iii",
            "shipped_vs_plan": "iii" if not execution.get("unavailable") else "unavailable",
            "readiness_missing": "iii",
            "economics_flagged": "iii",
        },
        "fill_rate_pct": fill_pct,
    }
