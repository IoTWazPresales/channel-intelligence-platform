"""Inbound shipment lineup-plan-quarter attribution (derived-on-read).

PO is the only lineup↔shipment link (``commercial_lineup_case_po``). Rows with no linked-PO
lineup are unattributed — never fuzzy-matched to a quarter.

Taxonomy (``docs/PLAN_VS_EXECUTED_SHIPPED_TAXONOMY.md``):
  pipeline — ``line_state='open_order'``
  shipped  — ``line_state='shipped'`` and ``pod_date IS NULL``
  landed   — ``pod_date IS NOT NULL`` (sub-state; may also be shipped)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Literal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commercial_lineup import (
    CommercialLineupCase,
    CommercialLineupCasePo,
    CommercialLineupLine,
)
from app.models.dimensions import DimProduct
from app.models.facts import FactInboundShipment
from app.services.commercial_planner.lineup_open_channel import effective_lineup_customer_id
from app.services.commercial_planner.lineup_period_canonical import (
    active_lineup_case_filters,
    active_lineup_line_filters,
    canonical_case_line_code,
    display_period_label_from_period_start,
    parse_period_filter_to_year_quarter,
    quarter_bounds_from_period_start,
    quarter_from_period_start,
    quarter_key_from_period_start,
)
from app.services.commercial_planner.open_channel_customer import (
    canonical_open_channel_customer_id,
    get_open_channel_canonical_and_aliases,
)
from app.services.commercial_planner.plan_vs_executed import enumerate_available_periods

logger = logging.getLogger(__name__)

LifecycleBucket = Literal["shipped", "pipeline", "landed"]
SlipDirection = Literal["slipped_in", "slipped_out"]


def quarter_key_from_date(d: date | None) -> str | None:
    if d is None:
        return None
    return quarter_key_from_period_start(d)


def period_ordinal(year: int, quarter: int) -> int:
    return year * 4 + quarter


def period_ordinal_from_quarter_key(key: str | None) -> int | None:
    if not key or not str(key).strip():
        return None
    s = str(key).strip().upper()
    if len(s) < 4 or "Q" not in s:
        return None
    try:
        yy = int(s.split("Q", 1)[0])
        q = int(s.split("Q", 1)[1])
        year = 2000 + yy if yy < 100 else yy
        return period_ordinal(year, q)
    except (ValueError, IndexError):
        return None


def quarter_after(a: str | None, b: str | None) -> bool:
    """True when quarter ``a`` is strictly after ``b``."""
    oa = period_ordinal_from_quarter_key(a)
    ob = period_ordinal_from_quarter_key(b)
    if oa is None or ob is None:
        return False
    return oa > ob


def lifecycle_bucket(line_state: str | None, pod_date: date | None) -> LifecycleBucket | None:
    if pod_date is not None:
        return "landed"
    if line_state == "open_order":
        return "pipeline"
    if line_state == "shipped":
        return "shipped"
    return None


def awaiting_pod_days(
    *,
    line_state: str | None,
    pod_date: date | None,
    ship_confirm_date: date | None,
    schedule_ship_date: date | None,
    reference: date | None = None,
) -> int | None:
    """Days since ship confirm for shipped rows still awaiting POD (unsigned-PI observable)."""
    if line_state != "shipped" or pod_date is not None:
        return None
    anchor = ship_confirm_date or schedule_ship_date
    if anchor is None:
        return None
    ref = reference or datetime.now(timezone.utc).date()
    return max(0, (ref - anchor).days)


def compute_slipped(
    plan_quarter: str | None,
    ship_quarter: str | None,
    landing_quarter: str | None,
) -> bool:
    if not plan_quarter:
        return False
    exec_q = landing_quarter or ship_quarter
    return quarter_after(exec_q, plan_quarter)


def is_slipped_out(
    plan_quarter: str | None,
    ship_quarter: str | None,
    landing_quarter: str | None,
    filter_quarter: str,
) -> bool:
    if plan_quarter != filter_quarter:
        return False
    exec_q = landing_quarter or ship_quarter
    return quarter_after(exec_q, plan_quarter)


def is_slipped_in(
    plan_quarter: str | None,
    landing_quarter: str | None,
    filter_quarter: str,
) -> bool:
    if not landing_quarter or landing_quarter != filter_quarter:
        return False
    if not plan_quarter:
        return False
    return quarter_after(filter_quarter, plan_quarter)


@dataclass
class _CaseAttribution:
    case_id: int
    plan_quarter: str
    plan_quarter_label: str
    business_unit: str | None


@dataclass
class AttributionContext:
    """Preloaded PO↔lineup attribution index for one request."""

    open_channel_customer_id: int | None
    open_channel_alias_ids: frozenset[int]
    po_to_cases: dict[int, list[_CaseAttribution]] = field(default_factory=dict)
    # (po_id, canon_customer_id|None, product_id) -> case_id
    line_match: dict[tuple[int, int | None, int], int] = field(default_factory=dict)
    ambiguous_po_count: int = 0

    def canon_customer(self, customer_id: int | None) -> int | None:
        return canonical_open_channel_customer_id(
            customer_id,
            canonical_id=self.open_channel_customer_id,
            alias_ids=set(self.open_channel_alias_ids),
        )


async def load_attribution_context(db: AsyncSession) -> AttributionContext:
    open_channel_customer_id, open_channel_alias_ids = await get_open_channel_canonical_and_aliases(db)
    ctx = AttributionContext(
        open_channel_customer_id=open_channel_customer_id,
        open_channel_alias_ids=frozenset(open_channel_alias_ids),
    )

    case_rows = (
        await db.execute(
            select(
                CommercialLineupCase.id,
                CommercialLineupCase.inferred_period_start,
                CommercialLineupCase.business_unit,
                CommercialLineupCase.product_line,
            ).where(
                CommercialLineupCase.inferred_period_start.isnot(None),
                *active_lineup_case_filters(),
            )
        )
    ).all()
    case_by_id: dict[int, _CaseAttribution] = {}
    for cid, ps, bu, pl in case_rows:
        if ps is None:
            continue
        stub = CommercialLineupCase(
            id=int(cid),
            business_unit=bu,
            product_line=pl,
            import_intent="current_working_lineup",
            source_context="commercial_planner",
            commercial_status="accepted",
        )
        case_by_id[int(cid)] = _CaseAttribution(
            case_id=int(cid),
            plan_quarter=quarter_key_from_period_start(ps),
            plan_quarter_label=display_period_label_from_period_start(ps),
            business_unit=canonical_case_line_code(stub),
        )

    link_rows = (
        await db.execute(
            select(CommercialLineupCasePo.purchase_order_id, CommercialLineupCasePo.case_id)
            .join(CommercialLineupCase, CommercialLineupCase.id == CommercialLineupCasePo.case_id)
            .where(*active_lineup_case_filters())
        )
    ).all()
    for po_id, case_id in link_rows:
        if po_id is None or case_id is None:
            continue
        ca = case_by_id.get(int(case_id))
        if ca is None:
            continue
        ctx.po_to_cases.setdefault(int(po_id), []).append(ca)

    line_rows = (
        await db.execute(
            select(CommercialLineupLine, CommercialLineupCasePo.purchase_order_id)
            .join(CommercialLineupCasePo, CommercialLineupCasePo.case_id == CommercialLineupLine.case_id)
            .join(CommercialLineupCase, CommercialLineupCase.id == CommercialLineupLine.case_id)
            .where(
                CommercialLineupLine.product_id.isnot(None),
                *active_lineup_line_filters(),
                *active_lineup_case_filters(),
            )
        )
    ).all()
    for ln, po_id in line_rows:
        if po_id is None or ln.product_id is None:
            continue
        eff_cust = ctx.canon_customer(
            effective_lineup_customer_id(ln, open_channel_customer_id=open_channel_customer_id)
        )
        key = (int(po_id), eff_cust, int(ln.product_id))
        existing = ctx.line_match.get(key)
        if existing is not None and existing != int(ln.case_id):
            continue
        ctx.line_match[key] = int(ln.case_id)

    for _po_id, cases in ctx.po_to_cases.items():
        quarters = {c.plan_quarter for c in cases}
        if len(quarters) > 1:
            ctx.ambiguous_po_count += 1

    return ctx


def resolve_plan_quarter(
    *,
    purchase_order_id: int | None,
    customer_id: int | None,
    product_id: int | None,
    product_line: str | None,
    business_unit: str | None,
    ctx: AttributionContext,
) -> tuple[str | None, str | None, str | None]:
    """Return (plan_quarter_key, plan_quarter_label, attribution_note)."""
    if purchase_order_id is None:
        return None, None, "no_po"
    po_id = int(purchase_order_id)
    cases = ctx.po_to_cases.get(po_id)
    if not cases:
        return None, None, "unattributed"

    canon_cust = ctx.canon_customer(customer_id)
    if product_id is not None:
        matched_case_id = ctx.line_match.get((po_id, canon_cust, int(product_id)))
        if matched_case_id is not None:
            ca = next((c for c in cases if c.case_id == matched_case_id), None)
            if ca:
                return ca.plan_quarter, ca.plan_quarter_label, "line_match"

    if len(cases) == 1:
        ca = cases[0]
        return ca.plan_quarter, ca.plan_quarter_label, "single_case"

    # Multiple cases: try BU disambiguation via product line
    pline = (product_line or business_unit or "").strip()
    if pline:
        bu_matches = [c for c in cases if c.business_unit and c.business_unit == pline]
        if len(bu_matches) == 1:
            ca = bu_matches[0]
            return ca.plan_quarter, ca.plan_quarter_label, "bu_match"

    return None, None, "ambiguous_multi_case"


def enrich_fact_lineup_fields(
    row: FactInboundShipment,
    *,
    ctx: AttributionContext,
    product_line: str | None = None,
    business_unit: str | None = None,
    reference_date: date | None = None,
) -> dict[str, Any]:
    plan_q, plan_label, attr_note = resolve_plan_quarter(
        purchase_order_id=row.purchase_order_id,
        customer_id=row.customer_id,
        product_id=row.product_id,
        product_line=product_line,
        business_unit=business_unit,
        ctx=ctx,
    )
    ship_q = quarter_key_from_date(row.ship_confirm_date)
    landing_q = quarter_key_from_date(row.pod_date)
    bucket = lifecycle_bucket(row.line_state, row.pod_date)
    slipped = compute_slipped(plan_q, ship_q, landing_q)
    return {
        "plan_quarter": plan_q,
        "plan_quarter_label": plan_label,
        "ship_quarter": ship_q,
        "landing_quarter": landing_q,
        "lifecycle_bucket": bucket,
        "slipped": slipped,
        "awaiting_pod_days": awaiting_pod_days(
            line_state=row.line_state,
            pod_date=row.pod_date,
            ship_confirm_date=row.ship_confirm_date,
            schedule_ship_date=row.schedule_ship_date,
            reference=reference_date,
        ),
        "lineup_attribution": "unattributed" if plan_q is None else "attributed",
        "attribution_note": attr_note,
    }


def row_matches_lineup_filters(
    enriched: dict[str, Any],
    *,
    plan_quarter: str | None,
    plan_quarter_label: str | None,
    lineup_attribution: str | None,
    lifecycle_bucket_filter: str | None,
    slip_direction: str | None,
) -> bool:
    if lineup_attribution == "unattributed":
        if enriched.get("plan_quarter") is not None:
            return False
    elif plan_quarter or plan_quarter_label:
        pq = enriched.get("plan_quarter")
        pl = enriched.get("plan_quarter_label")
        filt_key = plan_quarter or None
        filt_label = plan_quarter_label or None
        if filt_key and pq != filt_key:
            if not (filt_label and pl == filt_label):
                return False
        elif filt_label and pl != filt_label:
            return False
        if pq is None:
            return False

    if lifecycle_bucket_filter:
        if enriched.get("lifecycle_bucket") != lifecycle_bucket_filter:
            return False

    if slip_direction and plan_quarter:
        if slip_direction == "slipped_out":
            if not is_slipped_out(
                enriched.get("plan_quarter"),
                enriched.get("ship_quarter"),
                enriched.get("landing_quarter"),
                plan_quarter,
            ):
                return False
        elif slip_direction == "slipped_in":
            if not is_slipped_in(
                enriched.get("plan_quarter"),
                enriched.get("landing_quarter"),
                plan_quarter,
            ):
                return False

    return True


async def planned_units_for_quarter(
    db: AsyncSession,
    *,
    year: int,
    quarter: int,
    customer_id: int | None = None,
    business_unit: str | None = None,
) -> float:
    """Sum lineup line quantities for active cases in the plan quarter."""
    start = date(year, 3 * (quarter - 1) + 1, 1)
    end = quarter_bounds_from_period_start(start)[1]
    stmt = (
        select(func.coalesce(func.sum(CommercialLineupLine.quantity_units), 0))
        .join(CommercialLineupCase, CommercialLineupCase.id == CommercialLineupLine.case_id)
        .where(
            CommercialLineupCase.inferred_period_start >= start,
            CommercialLineupCase.inferred_period_start < end,
            *active_lineup_case_filters(),
            *active_lineup_line_filters(),
        )
    )
    if customer_id is not None:
        stmt = stmt.where(CommercialLineupLine.customer_id == int(customer_id))
    if business_unit and str(business_unit).strip():
        bu = str(business_unit).strip()
        stmt = stmt.where(
            or_(
                CommercialLineupCase.business_unit == bu,
                CommercialLineupCase.product_line == bu,
            )
        )
    return float((await db.scalar(stmt)) or 0)


async def lineup_quarter_summary(
    db: AsyncSession,
    *,
    plan_quarter: str,
    customer_id: int | None = None,
    business_unit: str | None = None,
) -> dict[str, Any]:
    """Summary for the active lineup plan-quarter filter (derived-on-read)."""
    year, quarter = parse_period_filter_to_year_quarter(plan_quarter)
    if year is None or quarter is None:
        return {"error": "invalid_plan_quarter", "plan_quarter": plan_quarter}

    ctx = await load_attribution_context(db)
    planned = await planned_units_for_quarter(
        db, year=year, quarter=quarter, customer_id=customer_id, business_unit=business_unit
    )

    product_meta: dict[int, tuple[str | None, str | None]] = {}
    fact_stmt = select(FactInboundShipment)
    if customer_id is not None:
        fact_stmt = fact_stmt.where(FactInboundShipment.customer_id == int(customer_id))
    rows = (await db.execute(fact_stmt)).scalars().all()
    prod_ids = {int(r.product_id) for r in rows if r.product_id is not None}
    if prod_ids:
        for pid, pl, bu in (
            await db.execute(
                select(DimProduct.id, DimProduct.product_line, DimProduct.business_unit).where(
                    DimProduct.id.in_(prod_ids)
                )
            )
        ).all():
            product_meta[int(pid)] = (pl, bu)

    totals = {
        "shipped_units": 0.0,
        "landed_units": 0.0,
        "pipeline_units": 0.0,
        "slipped_in_units": 0.0,
        "slipped_out_units": 0.0,
        "unattributed_units": 0.0,
    }
    filter_key = quarter_key_from_period_start(date(year, 3 * (quarter - 1) + 1, 1))

    for row in rows:
        if customer_id is not None and row.customer_id != customer_id:
            continue
        pl, bu = product_meta.get(int(row.product_id), (None, None)) if row.product_id else (None, None)
        if business_unit and str(business_unit).strip():
            bu_code = (pl or bu or "").strip()
            if bu_code != str(business_unit).strip():
                continue

        enriched = enrich_fact_lineup_fields(row, ctx=ctx, product_line=pl, business_unit=bu)
        qty = float(row.quantity or 0)
        pq = enriched.get("plan_quarter")
        bucket = enriched.get("lifecycle_bucket")

        if pq is None:
            totals["unattributed_units"] += qty
            continue
        if pq != filter_key:
            if is_slipped_in(pq, enriched.get("landing_quarter"), filter_key):
                totals["slipped_in_units"] += qty
            continue

        if bucket == "shipped":
            totals["shipped_units"] += qty
        elif bucket == "landed":
            totals["landed_units"] += qty
        elif bucket == "pipeline":
            totals["pipeline_units"] += qty

        if is_slipped_out(pq, enriched.get("ship_quarter"), enriched.get("landing_quarter"), filter_key):
            totals["slipped_out_units"] += qty

    return {
        "plan_quarter": filter_key,
        "plan_quarter_label": display_period_label_from_period_start(date(year, 3 * (quarter - 1) + 1, 1)),
        "planned_units": planned,
        **totals,
        "ambiguous_po_count": ctx.ambiguous_po_count,
        "attribution_rule": (
            "plan_quarter = lineup case period via PO link; disambiguate multi-case PO by "
            "(customer×product) lineup line match, else single-case fallback, else BU match; "
            "no-case PO = unattributed"
        ),
    }


async def po_ids_for_plan_quarter(
    db: AsyncSession,
    *,
    year: int,
    quarter: int,
    business_unit: str | None = None,
) -> set[int]:
    """PO ids linked to active lineup cases in the plan quarter (inclusive pre-filter)."""
    start = date(year, 3 * (quarter - 1) + 1, 1)
    end = quarter_bounds_from_period_start(start)[1]
    stmt = (
        select(CommercialLineupCasePo.purchase_order_id)
        .join(CommercialLineupCase, CommercialLineupCase.id == CommercialLineupCasePo.case_id)
        .where(
            CommercialLineupCase.inferred_period_start >= start,
            CommercialLineupCase.inferred_period_start < end,
            *active_lineup_case_filters(),
        )
    )
    if business_unit and str(business_unit).strip():
        bu = str(business_unit).strip()
        stmt = stmt.where(
            or_(
                CommercialLineupCase.business_unit == bu,
                CommercialLineupCase.product_line == bu,
            )
        )
    rows = (await db.execute(stmt)).scalars().all()
    return {int(x) for x in rows if x is not None}


def normalize_plan_quarter_filter(
    plan_quarter: str | None,
    plan_quarter_label: str | None,
) -> tuple[str | None, str | None]:
    """Return (compact_key e.g. 26Q2, display_label e.g. 2026 Q2)."""
    raw = (plan_quarter or plan_quarter_label or "").strip()
    if not raw:
        return None, None
    year, q = parse_period_filter_to_year_quarter(raw)
    if year is None or q is None:
        return raw.upper(), raw
    ps = date(year, 3 * (q - 1) + 1, 1)
    return quarter_key_from_period_start(ps), display_period_label_from_period_start(ps)


async def available_plan_periods(db: AsyncSession) -> list[dict[str, Any]]:
    """Same enumeration source as Plan vs Executed (PO Management coverage groups)."""
    return await enumerate_available_periods(db)
