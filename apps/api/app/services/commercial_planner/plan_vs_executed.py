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
from app.models.dimensions import DimProduct
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
ProductGroupBy = Literal["description", "sku", "sales_model"]

# BACKLOG-066: duplicate-ingestion periods — detected at read time via check_lineup_duplicate_ingestion.

_BUCKET_EXECUTED = ("matched", "short", "over")
_BUCKET_OFF_PLAN = ("unplanned", "amended")
_BUCKET_PENDING = ("unshipped",)


def scorecard_tie_out_fields(scorecard: dict[str, Any]) -> dict[str, Any]:
    """Normalized KPI slice for golden tie-out assertions."""
    return {
        "planned_units": scorecard["planned_units"],
        "shipped_units_in_plan": scorecard["shipped_units_in_plan"],
        "pipeline_units_in_plan": scorecard["pipeline_units_in_plan"],
        "fill_rate": scorecard["fill_rate"],
        "short_exposure_units": scorecard["short_exposure_units"],
        "deal_stock_units": scorecard["deal_stock_units"],
        "unplanned_intake_units": scorecard["unplanned_intake_units"],
        "no_po_blind_spot": scorecard["no_po_blind_spot"],
    }


def resolve_product_display(row: dict[str, Any], group_by: ProductGroupBy = "description") -> dict[str, Any]:
    """Human-readable product primary/secondary — description → sales_model → SKU; never bare internal id."""
    description = (
        (row.get("product_marketing_name") or row.get("product_description") or row.get("product_name") or "")
        .strip()
    )
    sales_model = (row.get("product_sales_model") or "").strip()
    sku = (row.get("product_sku") or "").strip()
    label_fallback = not bool(description)

    if group_by == "sku":
        primary = sku or sales_model or description or "—"
        secondary_parts = [p for p in (description, sales_model) if p and p != primary]
        return {
            "entity_primary": primary,
            "entity_secondary": " · ".join(secondary_parts) if secondary_parts else None,
            "label_fallback": not description and not sales_model,
        }
    if group_by == "sales_model":
        primary = sales_model or description or sku or "Unspecified sales model"
        secondary_parts = [p for p in (description, sku) if p and p != primary]
        return {
            "entity_primary": primary,
            "entity_secondary": " · ".join(secondary_parts) if secondary_parts else None,
            "label_fallback": not description,
        }
    primary = description or sales_model or sku or "—"
    if not description:
        label_fallback = True
    secondary_parts = [p for p in (sales_model, sku) if p]
    return {
        "entity_primary": primary,
        "entity_secondary": " · ".join(secondary_parts) if secondary_parts else None,
        "label_fallback": label_fallback,
    }


def _product_lens_key_label(row: dict[str, Any], group_by: ProductGroupBy) -> tuple[Any, str]:
    """Product exception lens grouping key + human-readable label."""
    display = resolve_product_display(row, group_by)
    pid = row.get("product_id")
    if group_by == "sku":
        return pid, display["entity_primary"]
    if group_by == "sales_model":
        sm = (row.get("product_sales_model") or "").strip() or "Unspecified sales model"
        return sm, display["entity_primary"]
    return pid, display["entity_primary"]


async def _attach_product_catalog_fields(db: AsyncSession, rows: list[dict[str, Any]]) -> None:
    pids = sorted({int(r["product_id"]) for r in rows if r.get("product_id") is not None})
    if not pids:
        return
    catalog: dict[int, dict[str, Any]] = {}
    for pid, sku, smn, name, mname in (
        await db.execute(
            select(
                DimProduct.id,
                DimProduct.sku,
                DimProduct.sales_model_name,
                DimProduct.name,
                DimProduct.marketing_name,
            ).where(DimProduct.id.in_(pids))
        )
    ).all():
        catalog[int(pid)] = {
            "product_sku": str(sku) if sku else None,
            "product_sales_model": str(smn).strip() if smn else None,
            "product_description": str(name) if name else None,
            "product_marketing_name": str(mname).strip() if mname else None,
        }
    for row in rows:
        meta = catalog.get(int(row["product_id"])) if row.get("product_id") is not None else None
        if meta:
            row.update(meta)


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
    return periods_from_coverage(cov)


def periods_from_coverage(cov: dict[str, Any]) -> list[dict[str, Any]]:
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


def resolve_default_period(
    all_periods: list[dict[str, Any]],
    *,
    coverage_groups: list[dict[str, Any]] | None = None,
) -> str | None:
    """Latest observed quarter with linked PO reconciliation (skips near-empty unlinked latest)."""
    if not all_periods:
        return None
    linked_quarters: set[tuple[int, int]] = set()
    for g in coverage_groups or []:
        if g.get("status") == "linked" and int(g.get("linked_po_count") or 0) > 0:
            linked_quarters.add((int(g["year"]), int(g["quarter"])))
    for p in all_periods:
        key = (int(p["year"]), int(p["quarter"]))
        if key in linked_quarters:
            return str(p["label"])
    return str(all_periods[0]["label"])


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
    """Rank metric in units mode only; value ranking uses ``_row_plan_value_for_field`` via buckets."""
    if rank_by == "units":
        if field == "short":
            return max(float(row.get("planned_units") or 0) - float(row.get("shipped_units") or 0), 0)
        if field == "over":
            return max(float(row.get("shipped_units") or 0) - float(row.get("planned_units") or 0), 0)
        if field == "unplanned":
            return float(row.get("shipped_units") or 0)
        if field == "no_po":
            return float(row.get("planned_units") or 0)
    plan = _row_plan_value_for_field(row, field)
    return plan if plan is not None else 0.0


def _row_plan_value_for_field(row: dict[str, Any], field: str) -> float | None:
    """Plan-currency exposure for an exception row — ``None`` when bridge absent (never units)."""
    val = row.get("value") or {}
    if field == "short":
        p = float(row.get("planned_units") or 0)
        s = float(row.get("shipped_units") or 0)
        units = max(p - s, 0)
        if p <= 0 or units <= 0:
            return None
        pv = val.get("planned_value_plan")
        if pv is None:
            return None
        fpv = float(pv)
        if fpv <= 0:
            return None
        return fpv * (units / p)
    if field == "over":
        p = float(row.get("planned_units") or 0)
        s = float(row.get("shipped_units") or 0)
        units = max(s - p, 0)
        if units <= 0 or s <= 0:
            return None
        sv = val.get("shipped_value_plan")
        if sv is None:
            return None
        return float(sv) * (units / s)
    if field == "unplanned":
        s = float(row.get("shipped_units") or 0)
        if s <= 0:
            return None
        sv = val.get("shipped_value_plan")
        if sv is None:
            return None
        return float(sv)
    if field == "no_po":
        p = float(row.get("planned_units") or 0)
        if p <= 0:
            return None
        pv = val.get("planned_value_plan")
        if pv is None:
            return None
        fpv = float(pv)
        return fpv if fpv > 0 else None
    return None


def _row_cost_value_for_field(row: dict[str, Any], field: str) -> float | None:
    """Cost-currency exposure — ``None`` when bridge absent (never units, never plan fallback)."""
    val = row.get("value") or {}
    if field == "short":
        p = float(row.get("planned_units") or 0)
        s = float(row.get("shipped_units") or 0)
        units = max(p - s, 0)
        if p <= 0 or units <= 0:
            return None
        pv = val.get("planned_value_cost")
        if pv is None:
            return None
        fpv = float(pv)
        if fpv <= 0:
            return None
        return fpv * (units / p)
    if field == "over":
        p = float(row.get("planned_units") or 0)
        s = float(row.get("shipped_units") or 0)
        units = max(s - p, 0)
        if units <= 0 or s <= 0:
            return None
        sv = val.get("shipped_value_cost")
        if sv is None:
            return None
        return float(sv) * (units / s)
    if field == "unplanned":
        s = float(row.get("shipped_units") or 0)
        if s <= 0:
            return None
        sv = val.get("shipped_value_cost")
        if sv is None:
            return None
        return float(sv)
    if field == "no_po":
        p = float(row.get("planned_units") or 0)
        if p <= 0:
            return None
        pv = val.get("planned_value_cost")
        if pv is None:
            return None
        fpv = float(pv)
        return fpv if fpv > 0 else None
    return None


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

    # Pipeline (open_order) is forward/inbound, never in fill. Tile = open_order units on
    # in-plan rows. Pending split: an in-plan line with nothing shipped is "inbound/pipeline"
    # when it has open_order inbound, else "cold". See PLAN_VS_EXECUTED_SHIPPED_TAXONOMY.md.
    pipeline_units_in_plan = sum(float(r.get("pipeline_units") or 0) for r in in_plan)
    pending_rows = [r for r in in_plan if float(r.get("shipped_units") or 0) == 0]
    inbound_pipeline_rows = [r for r in pending_rows if float(r.get("pipeline_units") or 0) > 0]
    cold_rows = [r for r in pending_rows if float(r.get("pipeline_units") or 0) == 0]

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
        "pipeline_units_in_plan": pipeline_units_in_plan,
        "short_exposure_units": short_units,
        "deal_stock_units": deal_stock_units,
        "unplanned_intake_units": unplanned_units,
        "no_po_blind_spot": {
            "line_count": no_po_line_count,
            "planned_units": no_po_units,
            "planned_value_plan": no_po_value_plan,
        },
        "pending_split": {
            "inbound_pipeline_lines": len(inbound_pipeline_rows),
            "inbound_pipeline_units": sum(float(r.get("pipeline_units") or 0) for r in inbound_pipeline_rows),
            "cold_lines": len(cold_rows),
            "cold_planned_units": sum(float(r["planned_units"]) for r in cold_rows),
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
    await _attach_product_catalog_fields(db, out)
    return out


def _aggregate_exceptions(
    rows: list[dict[str, Any]],
    *,
    rank_by: RankBy,
    product_group_by: ProductGroupBy = "description",
) -> dict[str, list[dict[str, Any]]]:
    """Ranked exception lists for customer, product, and BU lenses (full list; UI paginates)."""

    def _bucket() -> dict[str, Any]:
        return {
            "units": 0.0,
            "value": 0.0,
            "value_n": 0,
            "value_cost": 0.0,
            "value_cost_n": 0,
            "label": "",
            "entity_primary": "",
            "entity_secondary": None,
            "label_fallback": False,
            "line_count": 0,
            "customer_id": None,
            "product_id": None,
            "sales_model": None,
            "business_unit_label": None,
        }

    def _add_values(
        bucket: dict[Any, dict[str, Any]],
        key: Any,
        row: dict[str, Any],
        cat_field: str,
    ) -> None:
        pv = _row_plan_value_for_field(row, cat_field)
        if pv is not None:
            bucket[key]["value"] += pv
            bucket[key]["value_n"] += 1
        vc = _row_cost_value_for_field(row, cat_field)
        if vc is not None:
            bucket[key]["value_cost"] += vc
            bucket[key]["value_cost_n"] += 1

    def _lens_agg(
        key_fn,
        label_fn,
        meta_fn,
    ) -> dict[str, list[dict[str, Any]]]:
        short: dict[Any, dict[str, Any]] = defaultdict(_bucket)
        over: dict[Any, dict[str, Any]] = defaultdict(_bucket)
        unplanned: dict[Any, dict[str, Any]] = defaultdict(_bucket)
        no_po: dict[Any, dict[str, Any]] = defaultdict(_bucket)

        for r in rows:
            p = float(r.get("planned_units") or 0)
            s = float(r.get("shipped_units") or 0)
            key = key_fn(r)
            lbl = label_fn(r)
            meta = meta_fn(r, key)
            display = meta.pop("_display", None)
            if display:
                entity_primary = display["entity_primary"]
                entity_secondary = display.get("entity_secondary")
                label_fallback = bool(display.get("label_fallback"))
            else:
                entity_primary = lbl
                entity_secondary = meta.get("business_unit_label")
                label_fallback = False

            if p > 0:
                short_u = max(p - s, 0)
                if short_u > 0:
                    short[key]["units"] += short_u
                    _add_values(short, key, r, "short")
                    short[key]["label"] = entity_primary
                    short[key]["entity_primary"] = entity_primary
                    short[key]["entity_secondary"] = entity_secondary
                    short[key]["label_fallback"] = label_fallback
                    short[key].update({k: v for k, v in meta.items() if v is not None})
                over_u = max(s - p, 0)
                if over_u > 0:
                    over[key]["units"] += over_u
                    _add_values(over, key, r, "over")
                    over[key]["label"] = entity_primary
                    over[key]["entity_primary"] = entity_primary
                    over[key]["entity_secondary"] = entity_secondary
                    over[key]["label_fallback"] = label_fallback
                    over[key].update({k: v for k, v in meta.items() if v is not None})
                if r.get("awaiting_po"):
                    no_po[key]["units"] += p
                    _add_values(no_po, key, r, "no_po")
                    no_po[key]["line_count"] += 1
                    no_po[key]["label"] = entity_primary
                    no_po[key]["entity_primary"] = entity_primary
                    no_po[key]["entity_secondary"] = entity_secondary
                    no_po[key]["label_fallback"] = label_fallback
                    no_po[key].update({k: v for k, v in meta.items() if v is not None})
            elif s > 0:
                unplanned[key]["units"] += s
                _add_values(unplanned, key, r, "unplanned")
                unplanned[key]["label"] = entity_primary
                unplanned[key]["entity_primary"] = entity_primary
                unplanned[key]["entity_secondary"] = entity_secondary
                unplanned[key]["label_fallback"] = label_fallback
                unplanned[key].update({k: v for k, v in meta.items() if v is not None})

        def _ranked(d: dict[Any, dict[str, Any]], metric: str) -> list[dict[str, Any]]:
            if metric == "value":
                ranked = sorted(
                    d.items(),
                    key=lambda kv: (kv[1]["value_n"] > 0, kv[1]["value"]),
                    reverse=True,
                )
            else:
                ranked = sorted(d.items(), key=lambda kv: kv[1]["units"], reverse=True)
            out_items: list[dict[str, Any]] = []
            for k, v in ranked:
                if metric == "units" and v["units"] <= 0:
                    continue
                if metric == "value" and v["units"] <= 0:
                    continue
                out_items.append(
                    {
                        "key": k,
                        "label": v["label"],
                        "entity_primary": v.get("entity_primary") or v["label"],
                        "entity_secondary": v.get("entity_secondary"),
                        "label_fallback": bool(v.get("label_fallback")),
                        "units": v["units"],
                        "value_plan": v["value"] if v["value_n"] > 0 else None,
                        "value_cost": v["value_cost"] if v["value_cost_n"] > 0 else None,
                        "line_count": v.get("line_count") or 0,
                        "customer_id": v.get("customer_id"),
                        "product_id": v.get("product_id"),
                        "sales_model": v.get("sales_model"),
                        "business_unit_label": v.get("business_unit_label"),
                    }
                )
            return out_items

        metric = "value" if rank_by == "value" else "units"
        return {
            "short_ships": _ranked(short, metric),
            "over_ships": _ranked(over, metric),
            "unplanned_intake": _ranked(unplanned, metric),
            "no_po_blind_spots": _ranked(no_po, metric),
        }

    def _customer_meta(r: dict[str, Any], key: Any) -> dict[str, Any]:
        return {
            "customer_id": key if isinstance(key, int) else r.get("customer_id"),
            "business_unit_label": r.get("business_unit_label"),
            "_display": {
                "entity_primary": r.get("customer_label") or "Unattributed",
                "entity_secondary": None,
                "label_fallback": False,
            },
        }

    def _product_meta(r: dict[str, Any], key: Any) -> dict[str, Any]:
        meta: dict[str, Any] = {
            "business_unit_label": r.get("business_unit_label"),
            "_display": resolve_product_display(r, product_group_by),
        }
        if product_group_by == "sales_model":
            meta["sales_model"] = key if isinstance(key, str) else r.get("product_sales_model")
        else:
            meta["product_id"] = key if isinstance(key, int) else r.get("product_id")
        return meta

    def _bu_meta(r: dict[str, Any], key: Any) -> dict[str, Any]:
        bu = key if isinstance(key, str) else r.get("business_unit_label")
        return {
            "business_unit_label": bu,
            "_display": {
                "entity_primary": bu or "Unspecified BU",
                "entity_secondary": None,
                "label_fallback": False,
            },
        }

    return {
        "customer": _lens_agg(
            lambda r: r.get("customer_id"),
            lambda r: r.get("customer_label") or "Unattributed",
            _customer_meta,
        ),
        "product": _lens_agg(
            lambda r: _product_lens_key_label(r, product_group_by)[0],
            lambda r: _product_lens_key_label(r, product_group_by)[1],
            _product_meta,
        ),
        "bu": _lens_agg(
            lambda r: r.get("business_unit_label"),
            lambda r: r.get("business_unit_label") or "Unclassified",
            _bu_meta,
        ),
    }


def _affected_duplicate_ingestion_labels(rows: list[dict[str, Any]], cluster_samples: list[dict[str, Any]]) -> list[str]:
    """Period labels in scope that still have active duplicate-ingestion clusters."""
    if not cluster_samples:
        return []
    from datetime import date

    affected_keys: set[tuple[int, int]] = set()
    for cluster in cluster_samples:
        ps = cluster.get("inferred_period_start")
        if not ps:
            continue
        try:
            d = date.fromisoformat(str(ps)[:10])
        except ValueError:
            continue
        affected_keys.add(quarter_from_period_start(d))
    return sorted(
        str(r["quarter_label"])
        for r in rows
        if (int(r["year"]), int(r["quarter"])) in affected_keys
    )


async def _load_duplicate_ingestion_samples(db: AsyncSession) -> list[dict[str, Any]]:
    from app.db.session_sync import SessionLocal
    from app.services.data_integrity_audit import check_lineup_duplicate_ingestion

    def _run() -> list[dict[str, Any]]:
        with SessionLocal() as sync_db:
            result = check_lineup_duplicate_ingestion(sync_db, sample_limit=500)
            return list(result.samples or [])

    import asyncio

    return await asyncio.to_thread(_run)


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
                "pipeline_units_in_plan": sc["pipeline_units_in_plan"],
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
    product_group_by: ProductGroupBy = "description",
    drill_customer_id: int | None = None,
    drill_product_id: int | None = None,
    drill_sales_model: str | None = None,
    drill_bu: str | None = None,
) -> dict[str, Any]:
    try:
        cov = await coverage(db)
        all_periods = periods_from_coverage(cov)
        default_period = resolve_default_period(all_periods, coverage_groups=cov.get("groups"))
        effective_from = period_from or default_period
        effective_to = period_to or default_period
        bu_filter = product_line or drill_bu

        rows = await collect_execution_rows(
            db,
            period_from=effective_from,
            period_to=effective_to,
            product_line=bu_filter,
        )
    except Exception:
        logger.exception("plan_vs_executed collect failed")
        return {"data_unavailable": True}

    scorecard = compute_scorecard_from_execution_rows(rows)
    exceptions = _aggregate_exceptions(rows, rank_by=rank_by, product_group_by=product_group_by)

    period_slots = _period_slots_in_range(
        all_periods,
        period_from=effective_from,
        period_to=effective_to,
    )
    trend = await _compute_trend(
        db,
        product_line=bu_filter,
        period_slots=period_slots,
    )

    drill_rows_source = list(rows)
    if drill_customer_id is not None:
        drill_rows_source = [r for r in drill_rows_source if r.get("customer_id") == drill_customer_id]
    if drill_product_id is not None:
        drill_rows_source = [r for r in drill_rows_source if r.get("product_id") == drill_product_id]
    if drill_sales_model:
        norm = drill_sales_model.strip().lower()
        drill_rows_source = [
            r
            for r in drill_rows_source
            if ((r.get("product_sales_model") or "").strip().lower() or "unspecified sales model") == norm
        ]

    drill_rows = []
    for r in drill_rows_source:
        val = r.get("value") or {}
        display = resolve_product_display(r, product_group_by)
        drill_rows.append(
            {
                "case_id": r.get("case_id"),
                "period_label": r.get("quarter_label"),
                "business_unit_label": r.get("business_unit_label"),
                "customer_id": r.get("customer_id"),
                "customer_label": r.get("customer_label"),
                "product_id": r.get("product_id"),
                "product_name": r.get("product_name"),
                "product_sku": r.get("product_sku"),
                "product_description": r.get("product_description"),
                "product_marketing_name": r.get("product_marketing_name"),
                "product_sales_model": r.get("product_sales_model"),
                "entity_primary": display["entity_primary"],
                "entity_secondary": display.get("entity_secondary"),
                "label_fallback": display.get("label_fallback"),
                "planned_units": r.get("planned_units"),
                "shipped_units": r.get("shipped_units"),
                "pipeline_units": r.get("pipeline_units") or 0,
                "units_flag": r.get("units_flag"),
                "awaiting_po": r.get("awaiting_po"),
                "planned_value_plan": val.get("planned_value_plan"),
                "shipped_value_plan": val.get("shipped_value_plan"),
                "shipped_value_cost": val.get("shipped_value_cost"),
                "value": val,
            }
        )

    drill_context: dict[str, Any] = {
        "customer_id": drill_customer_id,
        "product_id": drill_product_id,
        "sales_model": drill_sales_model,
        "customer_label": None,
        "product_display": None,
    }
    if drill_customer_id is not None and drill_rows:
        drill_context["customer_label"] = drill_rows[0].get("customer_label")
    elif drill_product_id is not None and drill_rows:
        drill_context["product_display"] = {
            "entity_primary": drill_rows[0].get("entity_primary"),
            "entity_secondary": drill_rows[0].get("entity_secondary"),
            "label_fallback": drill_rows[0].get("label_fallback"),
        }
    elif drill_sales_model and drill_rows:
        drill_context["product_display"] = {
            "entity_primary": drill_rows[0].get("entity_primary"),
            "entity_secondary": drill_rows[0].get("entity_secondary"),
            "label_fallback": drill_rows[0].get("label_fallback"),
        }

    dup_clusters = await _load_duplicate_ingestion_samples(db)
    backlog_066 = _affected_duplicate_ingestion_labels(rows, dup_clusters)

    return {
        "period_range": {
            "from": effective_from,
            "to": effective_to,
        },
        "default_period": default_period,
        "product_line_filter": bu_filter,
        "product_group_by": product_group_by,
        "rank_by": rank_by,
        "drill": drill_context,
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
