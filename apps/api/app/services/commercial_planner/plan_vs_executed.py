"""Plan vs Executed intelligence read model (derived-on-read).

Aggregates reconcile_case product rows across linked lineup cases in a period range.
Uses the same per-product_line projection helpers as PO Management backlog — never
whole-case attribution when a BU filter is applied.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupCasePo
from app.services.commercial_planner.lineup_period_canonical import (
    active_lineup_case_filters,
    parse_period_filter_to_year_quarter,
    quarter_from_period_start,
    quarter_key_from_period_start,
)
from app.services.commercial_planner.lineup_po_reconciliation import UNITS_FLAGS, reconcile_case
from app.services.commercial_planner.po_management import (
    canonical_product_line_code,
    coverage,
    product_row_matches_group_line,
)

logger = logging.getLogger(__name__)

RankBy = Literal["units", "value"]

# BACKLOG-066: duplicate-ingestion periods with inflated planned units within a BU group.
BACKLOG_066_PERIODS: frozenset[tuple[int, int]] = frozenset({(2025, 1), (2024, 4)})

_BUCKET_EXECUTED = ("matched", "short", "over")
_BUCKET_OFF_PLAN = ("unplanned", "amended")
_BUCKET_PENDING = ("unshipped",)

_EXCEPTION_TOP_N = 10


def _period_ordinal(year: int, quarter: int) -> int:
    return year * 4 + quarter


def _period_in_range(
    year: int,
    quarter: int,
    *,
    from_year: int | None,
    from_quarter: int | None,
    to_year: int | None,
    to_quarter: int | None,
) -> bool:
    o = _period_ordinal(year, quarter)
    if from_year is not None and from_quarter is not None:
        if o < _period_ordinal(from_year, from_quarter):
            return False
    if to_year is not None and to_quarter is not None:
        if o > _period_ordinal(to_year, to_quarter):
            return False
    return True


def _parse_period_bounds(
    period_from: str | None,
    period_to: str | None,
) -> tuple[int | None, int | None, int | None, int | None]:
    fy, fq = parse_period_filter_to_year_quarter(period_from)
    ty, tq = parse_period_filter_to_year_quarter(period_to)
    return fy, fq, ty, tq


async def enumerate_available_periods(db: AsyncSession) -> list[dict[str, Any]]:
    """Full period history — same observed-PO quarter span as PO Management coverage groups."""
    cov = await coverage(db)
    if cov.get("data_unavailable"):
        return []
    seen: dict[tuple[int, int], str] = {}
    for g in cov.get("groups") or []:
        y, q = int(g.get("year") or 0), int(g.get("quarter") or 0)
        if y == 0:
            continue
        seen.setdefault((y, q), str(g["quarter_label"]))
    return [
        {"year": y, "quarter": q, "label": lbl}
        for (y, q), lbl in sorted(seen.items(), key=lambda kv: _period_ordinal(kv[0][0], kv[0][1]), reverse=True)
    ]


def _period_slots_in_range(
    all_periods: list[dict[str, Any]],
    *,
    period_from: str | None,
    period_to: str | None,
) -> list[tuple[int, int, str]]:
    fy, fq, ty, tq = _parse_period_bounds(period_from, period_to)
    slots: list[tuple[int, int, str]] = []
    for p in all_periods:
        y, q, lbl = int(p["year"]), int(p["quarter"]), str(p["label"])
        if _period_in_range(y, q, from_year=fy, from_quarter=fq, to_year=ty, to_quarter=tq):
            slots.append((y, q, lbl))
    return sorted(slots, key=lambda x: _period_ordinal(x[0], x[1]))


def _row_value_for_rank(row: dict[str, Any], *, rank_by: RankBy, field: str) -> float:
    """Rank metric in plan currency when value mode and FX available; else units."""
    if rank_by == "units":
        return float(row.get(field) or 0)
    val = row.get("value") or {}
    if field == "short":
        p = float(row.get("planned_units") or 0)
        s = float(row.get("shipped_units") or 0)
        units = max(p - s, 0)
        if p > 0 and units > 0:
            ratio = units / p
            pv = float(val.get("planned_value_plan") or 0)
            if pv > 0:
                return pv * ratio
        return units
    if field == "over":
        p = float(row.get("planned_units") or 0)
        s = float(row.get("shipped_units") or 0)
        units = max(s - p, 0)
        if p > 0 and units > 0:
            sv = val.get("shipped_value_plan")
            if sv is not None and s > 0:
                return float(sv) * (units / s)
        return units
    if field == "unplanned":
        s = float(row.get("shipped_units") or 0)
        sv = val.get("shipped_value_plan")
        if sv is not None and s > 0:
            return float(sv)
        return s
    if field == "no_po":
        p = float(row.get("planned_units") or 0)
        pv = float(val.get("planned_value_plan") or 0)
        return pv if pv > 0 else p
    return float(row.get(field) or 0)


def compute_scorecard_from_execution_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Pure KPI aggregation per PLAN_VS_EXECUTED_SPEC §5."""
    in_plan = [r for r in rows if float(r.get("planned_units") or 0) > 0]
    off_plan = [
        r
        for r in rows
        if float(r.get("planned_units") or 0) == 0 and float(r.get("shipped_units") or 0) > 0
    ]

    sum_p = sum(float(r["planned_units"]) for r in in_plan)
    sum_s_in_plan = sum(float(r["shipped_units"]) for r in in_plan)
    sum_s_all = sum(float(r.get("shipped_units") or 0) for r in rows)
    sum_min = sum(min(float(r["shipped_units"]), float(r["planned_units"])) for r in in_plan)

    fill_rate = sum_min / sum_p if sum_p > 0 else None
    line_hit_rate = (
        sum(1 for r in in_plan if float(r["shipped_units"]) >= float(r["planned_units"])) / len(in_plan)
        if in_plan
        else None
    )

    short_units = sum(max(float(r["planned_units"]) - float(r["shipped_units"]), 0) for r in in_plan)
    deal_stock_units = sum(max(float(r["shipped_units"]) - float(r["planned_units"]), 0) for r in in_plan)
    unplanned_units = sum(float(r["shipped_units"]) for r in off_plan)

    no_po_rows = [r for r in in_plan if r.get("awaiting_po")]
    no_po_line_count = len(no_po_rows)
    no_po_units = sum(float(r["planned_units"]) for r in no_po_rows)

    short_value_plan = 0.0
    deal_stock_value_plan = 0.0
    unplanned_value_plan = 0.0
    no_po_value_plan = 0.0
    planned_value_plan = 0.0
    shipped_value_plan = 0.0
    shipped_value_cost = 0.0
    fx_partial = False

    for r in in_plan:
        p = float(r["planned_units"])
        s = float(r["shipped_units"])
        val = r.get("value") or {}
        pv = float(val.get("planned_value_plan") or 0)
        planned_value_plan += pv
        shipped_value_cost += float(val.get("shipped_value_cost") or 0)
        if val.get("value_status") != "ok":
            fx_partial = True
        sv_plan = val.get("shipped_value_plan")
        if sv_plan is not None:
            shipped_value_plan += float(sv_plan)
            if p > 0:
                short_u = max(p - s, 0)
                if short_u > 0:
                    short_value_plan += float(sv_plan) * (short_u / s) if s > 0 else pv * (short_u / p)
                over_u = max(s - p, 0)
                if over_u > 0:
                    deal_stock_value_plan += float(sv_plan) * (over_u / s)
        else:
            fx_partial = True
        if r.get("awaiting_po"):
            no_po_value_plan += pv

    for r in off_plan:
        val = r.get("value") or {}
        shipped_value_cost += float(val.get("shipped_value_cost") or 0)
        sv_plan = val.get("shipped_value_plan")
        if sv_plan is not None:
            unplanned_value_plan += float(sv_plan)
            shipped_value_plan += float(sv_plan)
        else:
            fx_partial = True

    flag_summary = {f: 0 for f in UNITS_FLAGS if f != "po_no_match"}
    awaiting_po_line_count = 0
    for r in rows:
        flag = r.get("units_flag")
        if flag in flag_summary:
            flag_summary[flag] += 1
        if r.get("awaiting_po") and float(r.get("planned_units") or 0) > 0:
            awaiting_po_line_count += 1

    buckets = {
        "executed_vs_plan": sum(flag_summary.get(f, 0) for f in _BUCKET_EXECUTED),
        "off_plan": sum(flag_summary.get(f, 0) for f in _BUCKET_OFF_PLAN),
        "pending": flag_summary.get("unshipped", 0) + awaiting_po_line_count,
    }

    return {
        "fill_rate": fill_rate,
        "line_hit_rate": line_hit_rate,
        "planned_units": sum_p,
        "shipped_units_in_plan": sum_s_in_plan,
        "shipped_units_total": sum_s_all,
        "short_exposure_units": short_units,
        "deal_stock_units": deal_stock_units,
        "unplanned_intake_units": unplanned_units,
        "no_po_blind_spot": {
            "line_count": no_po_line_count,
            "planned_units": no_po_units,
            "planned_value_plan": no_po_value_plan,
        },
        "value": {
            "planned_value_plan": planned_value_plan,
            "shipped_value_plan": shipped_value_plan,
            "shipped_value_cost": shipped_value_cost,
            "short_exposure_value_plan": short_value_plan,
            "deal_stock_value_plan": deal_stock_value_plan,
            "unplanned_intake_value_plan": unplanned_value_plan,
            "fx_partial": fx_partial,
        },
        "flag_summary": flag_summary,
        "buckets": buckets,
        "awaiting_po_line_count": awaiting_po_line_count,
    }


def _enrich_execution_row(
    product_row: dict[str, Any],
    *,
    case_id: int,
    year: int,
    quarter: int,
    quarter_label: str,
    customer_labels: dict[int | None, str],
) -> dict[str, Any]:
    cust_id = product_row.get("customer_id")
    bu = canonical_product_line_code(product_row.get("product_line"), product_row.get("business_unit"))
    return {
        **product_row,
        "case_id": case_id,
        "year": year,
        "quarter": quarter,
        "quarter_label": quarter_label,
        "business_unit_label": bu,
        "customer_label": customer_labels.get(cust_id)
        or ("Unattributed" if cust_id is None else f"Customer #{cust_id}"),
    }


async def _linked_cases(db: AsyncSession) -> list[CommercialLineupCase]:
    rows = (
        await db.execute(
            select(CommercialLineupCase)
            .join(CommercialLineupCasePo, CommercialLineupCasePo.case_id == CommercialLineupCase.id)
            .where(*active_lineup_case_filters())
            .distinct()
        )
    ).scalars().all()
    return list(rows)


async def collect_execution_rows(
    db: AsyncSession,
    *,
    period_from: str | None = None,
    period_to: str | None = None,
    product_line: str | None = None,
) -> list[dict[str, Any]]:
    """Union reconcile_case product rows for linked cases in the period range."""
    fy, fq, ty, tq = _parse_period_bounds(period_from, period_to)
    out: list[dict[str, Any]] = []

    for case in await _linked_cases(db):
        if case.inferred_period_start is None:
            continue
        year, quarter = quarter_from_period_start(case.inferred_period_start)
        if not _period_in_range(year, quarter, from_year=fy, from_quarter=fq, to_year=ty, to_quarter=tq):
            continue
        quarter_label = quarter_key_from_period_start(case.inferred_period_start)
        try:
            recon = await reconcile_case(db, int(case.id))
        except Exception:
            logger.exception("plan_vs_executed reconcile_case failed case_id=%s", case.id)
            continue
        if recon.get("data_unavailable"):
            continue

        label_by_customer = {cs.get("customer_id"): cs.get("label") for cs in (recon.get("customers") or [])}
        products = list(recon.get("products") or [])
        if product_line:
            products = [p for p in products if product_row_matches_group_line(p, product_line)]

        for row in products:
            if float(row.get("planned_units") or 0) == 0 and float(row.get("shipped_units") or 0) == 0:
                continue
            out.append(
                _enrich_execution_row(
                    row,
                    case_id=int(case.id),
                    year=year,
                    quarter=quarter,
                    quarter_label=quarter_label,
                    customer_labels=label_by_customer,
                )
            )
    return out


def _aggregate_exceptions(
    rows: list[dict[str, Any]],
    *,
    rank_by: RankBy,
) -> dict[str, list[dict[str, Any]]]:
    """Ranked exception lists for customer, product, and BU lenses."""

    def _lens_agg(
        key_fn,
        label_fn,
    ) -> dict[str, list[dict[str, Any]]]:
        short: dict[Any, dict[str, Any]] = defaultdict(lambda: {"units": 0.0, "value": 0.0, "label": ""})
        over: dict[Any, dict[str, Any]] = defaultdict(lambda: {"units": 0.0, "value": 0.0, "label": ""})
        unplanned: dict[Any, dict[str, Any]] = defaultdict(lambda: {"units": 0.0, "value": 0.0, "label": ""})
        no_po: dict[Any, dict[str, Any]] = defaultdict(lambda: {"units": 0.0, "value": 0.0, "label": "", "line_count": 0})

        for r in rows:
            p = float(r.get("planned_units") or 0)
            s = float(r.get("shipped_units") or 0)
            key = key_fn(r)
            lbl = label_fn(r)
            if p > 0:
                short_u = max(p - s, 0)
                if short_u > 0:
                    short[key]["units"] += short_u
                    short[key]["value"] += _row_value_for_rank(r, rank_by=rank_by, field="short")
                    short[key]["label"] = lbl
                over_u = max(s - p, 0)
                if over_u > 0:
                    over[key]["units"] += over_u
                    over[key]["value"] += _row_value_for_rank(r, rank_by=rank_by, field="over")
                    over[key]["label"] = lbl
                if r.get("awaiting_po"):
                    no_po[key]["units"] += p
                    no_po[key]["value"] += _row_value_for_rank(r, rank_by=rank_by, field="no_po")
                    no_po[key]["line_count"] += 1
                    no_po[key]["label"] = lbl
            elif s > 0:
                unplanned[key]["units"] += s
                unplanned[key]["value"] += _row_value_for_rank(r, rank_by=rank_by, field="unplanned")
                unplanned[key]["label"] = lbl

        def _top(d: dict[Any, dict[str, Any]], metric: str) -> list[dict[str, Any]]:
            ranked = sorted(d.items(), key=lambda kv: kv[1][metric], reverse=True)[:_EXCEPTION_TOP_N]
            return [
                {"key": k, "label": v["label"], "units": v["units"], "value_plan": v["value"], "line_count": v.get("line_count")}
                for k, v in ranked
                if v[metric] > 0
            ]

        metric = "value" if rank_by == "value" else "units"
        return {
            "short_ships": _top(short, metric),
            "over_ships": _top(over, metric),
            "unplanned_intake": _top(unplanned, metric),
            "no_po_blind_spots": _top(no_po, metric),
        }

    return {
        "customer": _lens_agg(lambda r: r.get("customer_id"), lambda r: r.get("customer_label") or "Unattributed"),
        "product": _lens_agg(
            lambda r: r.get("product_id"),
            lambda r: r.get("product_name") or f"Product #{r.get('product_id')}",
        ),
        "bu": _lens_agg(
            lambda r: r.get("business_unit_label"),
            lambda r: r.get("business_unit_label") or "Unclassified",
        ),
    }


def _affected_backlog_066_labels(rows: list[dict[str, Any]]) -> list[str]:
    labels: set[str] = set()
    for r in rows:
        if (int(r["year"]), int(r["quarter"])) in BACKLOG_066_PERIODS:
            labels.add(str(r["quarter_label"]))
    return sorted(labels)


async def _compute_trend(
    db: AsyncSession,
    *,
    product_line: str | None,
    period_slots: list[tuple[int, int, str]],
) -> list[dict[str, Any]]:
    """Per-quarter scorecard series across the selected period range."""
    trend: list[dict[str, Any]] = []
    for year, quarter, label in period_slots:
        q_rows = await collect_execution_rows(
            db,
            period_from=label,
            period_to=label,
            product_line=product_line,
        )
        sc = compute_scorecard_from_execution_rows(q_rows)
        trend.append(
            {
                "period_label": label,
                "year": year,
                "quarter": quarter,
                "fill_rate": sc["fill_rate"],
                "line_hit_rate": sc["line_hit_rate"],
                "planned_units": sc["planned_units"],
                "shipped_units_in_plan": sc["shipped_units_in_plan"],
                "short_exposure_units": sc["short_exposure_units"],
                "deal_stock_units": sc["deal_stock_units"],
                "unplanned_intake_units": sc["unplanned_intake_units"],
                "no_po_planned_units": sc["no_po_blind_spot"]["planned_units"],
            }
        )
    return trend


async def plan_vs_executed_read_model(
    db: AsyncSession,
    *,
    period_from: str | None = None,
    period_to: str | None = None,
    product_line: str | None = None,
    rank_by: RankBy = "units",
    drill_customer_id: int | None = None,
    drill_product_id: int | None = None,
    drill_bu: str | None = None,
) -> dict[str, Any]:
    try:
        all_periods = await enumerate_available_periods(db)
        default_period = all_periods[0]["label"] if all_periods else None
        effective_from = period_from or default_period
        effective_to = period_to or default_period

        rows = await collect_execution_rows(
            db,
            period_from=effective_from,
            period_to=effective_to,
            product_line=product_line or drill_bu,
        )
    except Exception:
        logger.exception("plan_vs_executed collect failed")
        return {"data_unavailable": True}

    if drill_customer_id is not None:
        rows = [r for r in rows if r.get("customer_id") == drill_customer_id]
    if drill_product_id is not None:
        rows = [r for r in rows if r.get("product_id") == drill_product_id]
    if drill_bu and not product_line:
        rows = [r for r in rows if r.get("business_unit_label") == drill_bu]

    scorecard = compute_scorecard_from_execution_rows(rows)
    exceptions = _aggregate_exceptions(rows, rank_by=rank_by)

    period_slots = _period_slots_in_range(
        all_periods,
        period_from=effective_from,
        period_to=effective_to,
    )
    trend = await _compute_trend(
        db,
        product_line=product_line or drill_bu,
        period_slots=period_slots,
    )

    drill_rows = [
        {
            "case_id": r.get("case_id"),
            "period_label": r.get("quarter_label"),
            "business_unit_label": r.get("business_unit_label"),
            "customer_id": r.get("customer_id"),
            "customer_label": r.get("customer_label"),
            "product_id": r.get("product_id"),
            "product_name": r.get("product_name"),
            "planned_units": r.get("planned_units"),
            "shipped_units": r.get("shipped_units"),
            "units_flag": r.get("units_flag"),
            "awaiting_po": r.get("awaiting_po"),
            "value": r.get("value"),
        }
        for r in rows
    ]

    backlog_066 = _affected_backlog_066_labels(rows)

    return {
        "period_range": {
            "from": effective_from,
            "to": effective_to,
        },
        "default_period": default_period,
        "product_line_filter": product_line or drill_bu,
        "rank_by": rank_by,
        "available_periods": all_periods,
        "scorecard": scorecard,
        "exceptions": exceptions,
        "trend": trend,
        "drill_rows": drill_rows,
        "data_quality": {
            "backlog_066_affected_periods": backlog_066,
            "backlog_066_message": (
                "Planned units may be double-counted within a BU for periods affected by "
                "duplicate lineup ingestion (BACKLOG-066 / cases #39–#40). Treat fill-rate and "
                "planned totals with caution until steward supersession repair lands."
                if backlog_066
                else None
            ),
        },
        "scope_notes": {
            "out_of_scope": [
                "Sell-through / aging stock — see DSI sell-out and SOH velocity.",
                "Cancelled vs never-shipped — unshipped means planned with no linked-PO shipment yet.",
                "Branch/location-tagged intake — deferred.",
                "FX completeness — value metrics annotate partial coverage only.",
            ],
        },
        "data_unavailable": False,
    }
