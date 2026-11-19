"""Final wave (a): a new customer's line-up, proposed from database SKUs and approved on screen.

Generic platform capability: nothing here names a customer, retailer, distributor, site or product.

Two seed sources (the user picks one, Warren 2026-11-18):

``pm_bottom_cost``
    Active master-catalogue items that have a PM bottom cost, i.e. a ``commercial_sku_assumption``
    row with a non-null ``controlled_cost_amount`` (the same PM cost the margin chain and the
    ``missing_pm_bottom`` flag use).

``previous_lineups``
    The distinct SKUs of the 3 most recent line-up periods. If the customer has line-up rows of its
    own, those are the periods used (``customer_own``). Otherwise the master line-up's 3 most
    recent periods across all customers are used (``master``). Superseded and cancelled cases and
    superseded rows are excluded, using the same filters as every other line-up consumer.

Only reporting customers qualify. "Reporting" has the same meaning as in listing discovery and the
CST upload: ``customer_report_config.reports_expected`` is true. A customer with no config row is
not a reporting customer.

Nothing is invented: lines start with empty quantity (0 on ``fact_lineup_plan_item``, which is the
writer default) and no price or cost is written. Approval reuses ``apply_lineup_approval`` (budget
ledger, which writes nothing for a zero quantity) and, in the endpoint,
``record_lineup_approval_event`` (audit trail), all inside one transaction.

``bulk_upsert_lineup_items`` is not used for the write because it commits on its own, which would
break the single-transaction guarantee. The rows have the same shape that writer produces.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupLine
from app.models.commercial_planner import CommercialSkuAssumption
from app.models.customer_report_config import CustomerReportConfig
from app.models.dimensions import DimCustomer, DimProduct
from app.models.lineup import FactLineupPlanItem
from app.services.commercial_planner.lineup_period_canonical import (
    active_lineup_case_filters,
    active_lineup_line_filters,
    display_period_label_from_period_start,
    quarter_bounds_from_period_start,
)

SOURCE_PM_BOTTOM_COST = "pm_bottom_cost"
SOURCE_PREVIOUS_LINEUPS = "previous_lineups"
SOURCES = (SOURCE_PM_BOTTOM_COST, SOURCE_PREVIOUS_LINEUPS)

FALLBACK_CUSTOMER_OWN = "customer_own"
FALLBACK_MASTER = "master"

PREVIOUS_PERIOD_COUNT = 3

BASIS_TEXT = {
    SOURCE_PM_BOTTOM_COST: (
        "Active master-catalogue items that have a PM bottom cost. Each line shows that cost."
    ),
    FALLBACK_CUSTOMER_OWN: (
        "The distinct SKUs from this customer's own {n} most recent line-up periods "
        "(superseded and cancelled line-ups excluded)."
    ),
    FALLBACK_MASTER: (
        "This customer has no line-up rows of its own, so the distinct SKUs from the master "
        "line-up's {n} most recent periods across all customers are used "
        "(superseded and cancelled line-ups excluded)."
    ),
}


class ProposalError(Exception):
    """A refusal the endpoint turns into an HTTP error with a stable machine-readable code."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ProposedLine:
    product_id: int
    sku: str
    label: str
    seed_source: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "product_id": self.product_id,
            "sku": self.sku,
            "label": self.label,
            "seed_source": self.seed_source,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class SeedScope:
    fallback: str
    periods: list[date]
    rows: list[tuple[int, date]]


# --- pure selection rules -----------------------------------------------------------------------


def _quarter_start(d: date) -> date:
    return quarter_bounds_from_period_start(d)[0]


def pick_recent_quarters(
    periods: Iterable[date | None], *, up_to: date, n: int = PREVIOUS_PERIOD_COUNT
) -> list[date]:
    """Distinct calendar-quarter starts, newest first, none later than ``up_to``'s quarter."""
    ceiling = _quarter_start(up_to)
    quarters = {_quarter_start(p) for p in periods if p is not None}
    return sorted((q for q in quarters if q <= ceiling), reverse=True)[:n]


def _rows_in(
    rows: Iterable[tuple[int, date | None]], periods: list[date]
) -> list[tuple[int, date]]:
    wanted = set(periods)
    out: list[tuple[int, date]] = []
    for product_id, period in rows:
        if period is None:
            continue
        quarter = _quarter_start(period)
        if quarter in wanted:
            out.append((int(product_id), quarter))
    return out


def choose_previous_lineup_scope(
    own_rows: Iterable[tuple[int, date | None]],
    master_rows: Iterable[tuple[int, date | None]],
    *,
    up_to: date,
    n: int = PREVIOUS_PERIOD_COUNT,
) -> SeedScope:
    """Own history when the customer has any (at or before the target period), else master."""
    own_rows = list(own_rows)
    own_periods = pick_recent_quarters((p for _, p in own_rows), up_to=up_to, n=n)
    if own_periods:
        return SeedScope(FALLBACK_CUSTOMER_OWN, own_periods, _rows_in(own_rows, own_periods))
    master_rows = list(master_rows)
    master_periods = pick_recent_quarters((p for _, p in master_rows), up_to=up_to, n=n)
    return SeedScope(FALLBACK_MASTER, master_periods, _rows_in(master_rows, master_periods))


def _label(product: Any) -> str:
    for attr in ("marketing_name", "sales_model_name", "name"):
        value = getattr(product, attr, None)
        if value and str(value).strip():
            return str(value).strip()
    return str(getattr(product, "sku", ""))


def previous_lineup_lines(
    scope: SeedScope, products_by_id: Mapping[int, Any]
) -> list[ProposedLine]:
    periods_by_product: dict[int, set[date]] = defaultdict(set)
    for product_id, quarter in scope.rows:
        periods_by_product[int(product_id)].add(quarter)
    lines: list[ProposedLine] = []
    for product_id, quarters in periods_by_product.items():
        product = products_by_id.get(product_id)
        if product is None:
            continue
        lines.append(
            ProposedLine(
                product_id=product_id,
                sku=str(product.sku),
                label=_label(product),
                seed_source=SOURCE_PREVIOUS_LINEUPS,
                evidence={
                    "kind": SOURCE_PREVIOUS_LINEUPS,
                    "scope": scope.fallback,
                    "periods": [q.isoformat() for q in sorted(quarters, reverse=True)],
                },
            )
        )
    return sorted(lines, key=lambda ln: (ln.sku.lower(), ln.product_id))


def pm_bottom_cost_lines(rows: Iterable[tuple[Any, Any, str | None]]) -> list[ProposedLine]:
    lines: list[ProposedLine] = []
    for product, cost, currency in rows:
        if cost is None:
            continue
        lines.append(
            ProposedLine(
                product_id=int(product.id),
                sku=str(product.sku),
                label=_label(product),
                seed_source=SOURCE_PM_BOTTOM_COST,
                evidence={
                    "kind": SOURCE_PM_BOTTOM_COST,
                    "pm_bottom_cost": float(cost),
                    "currency": currency,
                },
            )
        )
    return sorted(lines, key=lambda ln: (ln.sku.lower(), ln.product_id))


def validate_source(source: str | None) -> str:
    if source not in SOURCES:
        raise ProposalError(400, "invalid_source", f"source must be one of: {', '.join(SOURCES)}")
    return str(source)


def validate_selection(proposed_ids: Iterable[int], selected_ids: Iterable[int]) -> list[int]:
    chosen = sorted({int(p) for p in selected_ids})
    if not chosen:
        raise ProposalError(400, "no_products_selected", "Select at least one line to approve.")
    allowed = {int(p) for p in proposed_ids}
    outside = [p for p in chosen if p not in allowed]
    if outside:
        raise ProposalError(
            400,
            "product_not_in_proposal",
            f"These products are not in the proposal for this source and period: {outside}.",
        )
    return chosen


# --- database reads -------------------------------------------------------------------------------


def ensure_reporting_customer(db: Session, customer_id: int) -> None:
    """Same meaning as listing discovery: ``customer_report_config.reports_expected`` is true."""
    flag = db.scalar(
        select(CustomerReportConfig.reports_expected).where(
            CustomerReportConfig.customer_id == customer_id
        )
    )
    if not flag:
        raise ProposalError(
            409,
            "customer_not_reporting",
            "Line-ups are only built for reporting customers (reports expected). "
            "Mark this customer as reporting first.",
        )


async def reporting_customer_ids(db: AsyncSession) -> set[int]:
    """Customers whose reports are expected (the reporting-only gate for line-up pulls)."""
    rows = await db.execute(
        select(CustomerReportConfig.customer_id).where(
            CustomerReportConfig.reports_expected.is_(True)
        )
    )
    return {int(r) for r in rows.scalars().all()}


def list_reporting_customers(db: Session) -> list[dict[str, Any]]:
    """Customers a new-customer line-up can be proposed for (reports expected, not merged away)."""
    rows = db.execute(
        select(DimCustomer.id, DimCustomer.name)
        .join(CustomerReportConfig, CustomerReportConfig.customer_id == DimCustomer.id)
        .where(
            CustomerReportConfig.reports_expected.is_(True),
            DimCustomer.merged_into_customer_id.is_(None),
        )
        .order_by(func.lower(DimCustomer.name), DimCustomer.id)
    ).all()
    return [{"id": int(cid), "name": name} for cid, name in rows]


def customer_has_lineup_rows_for_period(db: Session, customer_id: int, period_start: date) -> bool:
    """Any line-up row for the customer in the calendar quarter of ``period_start``."""
    start, end = quarter_bounds_from_period_start(period_start)
    fact = db.scalar(
        select(func.count())
        .select_from(FactLineupPlanItem)
        .where(
            FactLineupPlanItem.customer_id == customer_id,
            FactLineupPlanItem.period_start >= start,
            FactLineupPlanItem.period_start < end,
        )
    )
    if fact:
        return True
    master = db.scalar(
        select(func.count())
        .select_from(CommercialLineupLine)
        .join(CommercialLineupCase, CommercialLineupCase.id == CommercialLineupLine.case_id)
        .where(
            CommercialLineupLine.customer_id == customer_id,
            CommercialLineupCase.inferred_period_start >= start,
            CommercialLineupCase.inferred_period_start < end,
            *active_lineup_case_filters(),
            *active_lineup_line_filters(),
        )
    )
    return bool(master)


def _lineup_product_periods(
    db: Session, *, tenant_id: str, ceiling_exclusive: date, customer_id: int | None
) -> list[tuple[int, date]]:
    stmt = (
        select(CommercialLineupLine.product_id, CommercialLineupCase.inferred_period_start)
        .join(CommercialLineupCase, CommercialLineupCase.id == CommercialLineupLine.case_id)
        .join(DimProduct, DimProduct.id == CommercialLineupLine.product_id)
        .where(
            CommercialLineupLine.product_id.is_not(None),
            CommercialLineupCase.inferred_period_start.is_not(None),
            CommercialLineupCase.inferred_period_start < ceiling_exclusive,
            DimProduct.tenant_id == tenant_id,
            *active_lineup_case_filters(),
            *active_lineup_line_filters(),
        )
        .distinct()
    )
    if customer_id is not None:
        stmt = stmt.where(CommercialLineupLine.customer_id == customer_id)
    return [(int(pid), period) for pid, period in db.execute(stmt).all()]


def build_proposal(
    db: Session, *, customer_id: int, source: str, period_start: date
) -> dict[str, Any]:
    source = validate_source(source)
    customer = db.get(DimCustomer, customer_id)
    if customer is None:
        raise ProposalError(404, "customer_not_found", "Customer not found.")
    ensure_reporting_customer(db, customer_id)
    if customer_has_lineup_rows_for_period(db, customer_id, period_start):
        raise ProposalError(
            409,
            "lineup_exists_for_period",
            "This customer already has line-up rows for that period. "
            "Edit the existing line-up instead of proposing a new one.",
        )
    tenant_id = customer.tenant_id
    fallback: str | None = None
    periods_used: list[str] = []
    n = PREVIOUS_PERIOD_COUNT

    if source == SOURCE_PM_BOTTOM_COST:
        rows = db.execute(
            select(
                DimProduct,
                CommercialSkuAssumption.controlled_cost_amount,
                CommercialSkuAssumption.controlled_cost_currency_code,
            )
            .join(CommercialSkuAssumption, CommercialSkuAssumption.product_id == DimProduct.id)
            .where(
                CommercialSkuAssumption.controlled_cost_amount.is_not(None),
                DimProduct.is_active.is_(True),
                DimProduct.tenant_id == tenant_id,
            )
        ).all()
        lines = pm_bottom_cost_lines((p, cost, cur) for p, cost, cur in rows)
        basis = BASIS_TEXT[SOURCE_PM_BOTTOM_COST]
    else:
        ceiling_exclusive = quarter_bounds_from_period_start(period_start)[1]
        own = _lineup_product_periods(
            db, tenant_id=tenant_id, ceiling_exclusive=ceiling_exclusive, customer_id=customer_id
        )
        master = (
            []
            if own
            else _lineup_product_periods(
                db, tenant_id=tenant_id, ceiling_exclusive=ceiling_exclusive, customer_id=None
            )
        )
        scope = choose_previous_lineup_scope(own, master, up_to=period_start, n=n)
        ids = sorted({pid for pid, _ in scope.rows})
        products: dict[int, Any] = {}
        if ids:
            products = {
                int(p.id): p
                for p in db.scalars(
                    select(DimProduct).where(
                        DimProduct.id.in_(ids),
                        DimProduct.is_active.is_(True),
                        DimProduct.tenant_id == tenant_id,
                    )
                ).all()
            }
        lines = previous_lineup_lines(scope, products)
        fallback = scope.fallback
        periods_used = [q.isoformat() for q in scope.periods]
        basis = BASIS_TEXT[scope.fallback].format(n=n)

    return {
        "customer": {"id": int(customer.id), "code": customer.code, "name": customer.name},
        "period_start": period_start.isoformat(),
        "period_label": display_period_label_from_period_start(period_start),
        "source": source,
        "fallback": fallback,
        "periods_used": periods_used,
        "basis": basis,
        "line_count": len(lines),
        "lines": [ln.as_dict() for ln in lines],
    }


# --- the write (all but the audit event and the commit, which the endpoint owns) -----------


def write_new_customer_lineup(
    db: Session,
    *,
    customer_id: int,
    source: str,
    period_start: date,
    product_ids: Iterable[int],
    actor: str | None,
) -> dict[str, Any]:
    """Create the customer's approved line-up rows for the chosen products. Does not commit."""
    from app.services.budget_ledger import apply_lineup_approval

    proposal = build_proposal(db, customer_id=customer_id, source=source, period_start=period_start)
    chosen = validate_selection((ln["product_id"] for ln in proposal["lines"]), product_ids)
    lines_by_id = {ln["product_id"]: ln for ln in proposal["lines"]}
    customer = db.get(DimCustomer, customer_id)
    assert customer is not None  # build_proposal checked
    label = proposal["period_label"]
    note = f"new_customer_proposal source={source}" + (
        f" scope={proposal['fallback']}" if proposal["fallback"] else ""
    )

    case = CommercialLineupCase(
        period_label=label,
        inferred_period_start=period_start,
        commercial_status="accepted",
        accepted_at=datetime.now(tz=UTC),
        accepted_by=actor,
        import_intent="current_working_lineup",
        source_context="lineup_new_customer",
        notes=f"New-customer line-up approved on screen. {note}",
    )
    db.add(case)
    db.flush()

    created: list[dict[str, Any]] = []
    for product_id in chosen:
        line = lines_by_id[product_id]
        db.add(
            CommercialLineupLine(
                case_id=case.id,
                product_id=product_id,
                customer_id=customer_id,
                customer_token=customer.code,
                sku_raw=line["sku"],
                quantity_units=None,
                row_status="imported",
                diagnostic_codes=[f"new_customer_proposal:{source}"],
            )
        )
        item = FactLineupPlanItem(
            customer_id=customer_id,
            channel_id=None,
            period_start=period_start,
            period_label=label,
            product_id=product_id,
            planned_volume_units=0.0,
            approval_status="draft",
            notes=note,
        )
        db.add(item)
        db.flush()
        item.approval_status = "approved"
        apply_lineup_approval(db, item, "draft", "approved", actor=actor)
        created.append({"item_id": int(item.id), "product_id": product_id, "sku": line["sku"]})

    return {
        "customer_id": customer_id,
        "source": source,
        "fallback": proposal["fallback"],
        "periods_used": proposal["periods_used"],
        "period_start": period_start.isoformat(),
        "period_label": label,
        "commercial_case_id": int(case.id),
        "created": created,
    }
