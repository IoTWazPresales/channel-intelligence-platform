"""Customer stock gap: reported on-hand beside the position CIP expects (N-0110).

The customer report's on-hand is the stock position. CIP stores an expected position
beside it and flags the difference. Neither number is rewritten::

    expected = previous reported on-hand
             + inbound receipts with a proof-of-delivery date, shipped, already matched
               to this customer, delivered after the previous report and by this one
             - units sold in the periods after the previous report up to this one
    gap      = this report's on-hand - expected

A shipment with no customer match stays out. In transit and on order are carried
beside on-hand and never added into it. The unit gap is shown on every compared row;
a row is highlighted when ``|gap| >= stock_gap_highlight_units`` (tenant setting,
absolute units). The distributor 10 percent variance is not used here.

Grain: customer x product, summed across the customer's sites for a report period.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Iterable

from sqlalchemy import and_, delete, func, select
from sqlalchemy.orm import Session

from app.models.customer_stock_position import CustomerStockPosition
from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.models.facts import FactInboundShipment
from app.services.imports.parsers.customer_sell_through_grain import period_end

ZERO = Decimal("0")


@dataclass
class ReportPeriod:
    """One customer report period for one product (all sites summed)."""

    product_id: int
    grain: str
    start: date
    end: date
    units_sold: Decimal = ZERO
    on_hand: Decimal | None = None
    in_transit: Decimal | None = None
    on_order: Decimal | None = None
    period_week: int | None = None
    period_year: int | None = None
    import_job_id: int | None = None


@dataclass
class Receipt:
    product_id: int
    pod_date: date
    units: Decimal


@dataclass
class Position:
    period: ReportPeriod
    status: str
    previous_end: date | None = None
    previous_on_hand: Decimal | None = None
    receipts: Decimal | None = None
    units_sold_since: Decimal | None = None
    expected: Decimal | None = None
    gap: Decimal | None = None
    notes: list[str] = field(default_factory=list)


def grain_of(period_grain: str | None, period_type: str | None) -> str:
    if period_grain in ("day", "week", "month"):
        return period_grain
    pt = (period_type or "weekly").strip().lower()
    if pt.startswith("month"):
        return "month"
    if pt.startswith("da"):
        return "day"
    return "week"


def _add(a: Decimal | None, b: Any) -> Decimal | None:
    if b is None:
        return a
    return (a or ZERO) + Decimal(str(b))


def compute_positions(periods: Iterable[ReportPeriod], receipts: Iterable[Receipt]) -> list[Position]:
    """Pure: one position per report period that carries on-hand, in end-date order.

    Units sold count when a period ends after the previous report and by this one, so
    a sales-only period between two stock reports still reduces the expected position.
    """
    by_product: dict[int, list[ReportPeriod]] = {}
    for p in periods:
        by_product.setdefault(p.product_id, []).append(p)
    receipts_by_product: dict[int, list[Receipt]] = {}
    for r in receipts:
        receipts_by_product.setdefault(r.product_id, []).append(r)

    out: list[Position] = []
    for product_id, plist in sorted(by_product.items()):
        plist.sort(key=lambda p: (p.end, p.start, p.grain))
        stock_points = [p for p in plist if p.on_hand is not None]
        prev: ReportPeriod | None = None
        for point in stock_points:
            if prev is None:
                out.append(Position(period=point, status="first_report"))
                prev = point
                continue
            sold = sum(
                (p.units_sold for p in plist if prev.end < p.end <= point.end),
                ZERO,
            )
            landed = sum(
                (r.units for r in receipts_by_product.get(product_id, []) if prev.end < r.pod_date <= point.end),
                ZERO,
            )
            expected = (prev.on_hand or ZERO) + landed - sold
            gap = (point.on_hand or ZERO) - expected
            out.append(
                Position(
                    period=point,
                    status="compared",
                    previous_end=prev.end,
                    previous_on_hand=prev.on_hand,
                    receipts=landed,
                    units_sold_since=sold,
                    expected=expected,
                    gap=gap,
                )
            )
            prev = point
    return out


def gap_reason(gap: Decimal | float | None, in_transit: Decimal | float | None = None) -> str:
    """Plain words for what a gap can mean. Never a verdict."""
    if gap is None:
        return "First report for this product. Nothing to compare yet."
    g = Decimal(str(gap))
    if g == 0:
        return "Matches the expected position."
    if g < 0:
        text = "Short: stock not delivered, lost, or sold outside the file."
        if in_transit is not None and Decimal(str(in_transit)) > 0:
            text += f" {Decimal(str(in_transit)).normalize():f} in transit may explain part of it."
        return text
    return "Over: a receipt CIP does not have, a return, or overlapping periods."


def is_highlighted(gap: Decimal | float | None, threshold_units: float | int | Decimal) -> bool:
    if gap is None:
        return False
    return abs(Decimal(str(gap))) >= Decimal(str(threshold_units))


def load_report_periods(
    db: Session,
    *,
    tenant_id: str,
    customer_id: int,
    product_ids: list[int] | None = None,
) -> list[ReportPeriod]:
    q = select(
        FactCustomerSellthrough.product_id,
        FactCustomerSellthrough.period_grain,
        FactCustomerSellthrough.period_type,
        FactCustomerSellthrough.period_start_date,
        FactCustomerSellthrough.period_week,
        FactCustomerSellthrough.period_year,
        FactCustomerSellthrough.units_sold,
        FactCustomerSellthrough.reported_soh,
        FactCustomerSellthrough.in_transit_units,
        FactCustomerSellthrough.on_order_units,
        FactCustomerSellthrough.import_job_id,
    ).where(
        FactCustomerSellthrough.tenant_id == tenant_id,
        FactCustomerSellthrough.customer_id == int(customer_id),
    )
    if product_ids:
        q = q.where(FactCustomerSellthrough.product_id.in_([int(p) for p in product_ids]))
    grouped: dict[tuple[int, str, date], ReportPeriod] = {}
    for row in db.execute(q).all():
        grain = grain_of(row.period_grain, row.period_type)
        key = (int(row.product_id), grain, row.period_start_date)
        rp = grouped.get(key)
        if rp is None:
            rp = ReportPeriod(
                product_id=int(row.product_id),
                grain=grain,
                start=row.period_start_date,
                end=period_end(row.period_start_date, grain),
                period_week=row.period_week,
                period_year=row.period_year,
            )
            grouped[key] = rp
        rp.units_sold += Decimal(str(row.units_sold or 0))
        rp.on_hand = _add(rp.on_hand, row.reported_soh)
        rp.in_transit = _add(rp.in_transit, row.in_transit_units)
        rp.on_order = _add(rp.on_order, row.on_order_units)
        if row.import_job_id is not None:
            rp.import_job_id = max(int(row.import_job_id), rp.import_job_id or 0)
    return list(grouped.values())


def load_matched_receipts(
    db: Session,
    *,
    tenant_id: str,
    customer_id: int,
    product_ids: list[int] | None = None,
) -> list[Receipt]:
    """Shipped lines with a POD date already matched to this customer. Unmatched lines stay out."""
    q = (
        select(
            FactInboundShipment.product_id,
            FactInboundShipment.pod_date,
            func.coalesce(func.sum(FactInboundShipment.quantity), 0),
        )
        .where(
            FactInboundShipment.tenant_id == tenant_id,
            FactInboundShipment.resolved_customer_id == int(customer_id),
            FactInboundShipment.product_id.isnot(None),
            FactInboundShipment.pod_date.isnot(None),
            func.lower(FactInboundShipment.line_state) == "shipped",
        )
        .group_by(FactInboundShipment.product_id, FactInboundShipment.pod_date)
    )
    if product_ids:
        q = q.where(FactInboundShipment.product_id.in_([int(p) for p in product_ids]))
    return [
        Receipt(product_id=int(pid), pod_date=pod, units=Decimal(str(qty or 0)))
        for pid, pod, qty in db.execute(q).all()
    ]


def recompute_customer_stock_positions(
    db: Session,
    *,
    tenant_id: str,
    customer_id: int,
    product_ids: list[int] | None = None,
) -> int:
    """Replace this customer's stored positions (for ``product_ids``, or all). Returns rows written."""
    tid = (tenant_id or "default").strip() or "default"
    periods = load_report_periods(db, tenant_id=tid, customer_id=customer_id, product_ids=product_ids)
    if product_ids is None:
        product_ids = sorted({p.product_id for p in periods})
    receipts = load_matched_receipts(db, tenant_id=tid, customer_id=customer_id, product_ids=product_ids)
    positions = compute_positions(periods, receipts)

    stmt = delete(CustomerStockPosition).where(
        CustomerStockPosition.tenant_id == tid,
        CustomerStockPosition.customer_id == int(customer_id),
    )
    if product_ids:
        stmt = stmt.where(CustomerStockPosition.product_id.in_([int(p) for p in product_ids]))
    db.execute(stmt)

    now = datetime.now(timezone.utc)
    for pos in positions:
        p = pos.period
        db.add(
            CustomerStockPosition(
                tenant_id=tid,
                customer_id=int(customer_id),
                product_id=p.product_id,
                period_grain=p.grain,
                period_start_date=p.start,
                period_end_date=p.end,
                period_week=p.period_week,
                period_year=p.period_year,
                report_import_job_id=p.import_job_id,
                reported_on_hand=p.on_hand,
                units_sold=pos.units_sold_since if pos.units_sold_since is not None else p.units_sold,
                in_transit_units=p.in_transit,
                on_order_units=p.on_order,
                previous_period_end_date=pos.previous_end,
                previous_on_hand=pos.previous_on_hand,
                receipts_units=pos.receipts,
                expected_on_hand=pos.expected,
                gap_units=pos.gap,
                status=pos.status,
                computed_at=now,
            )
        )
    db.flush()
    return len(positions)


def recompute_all_customer_stock_positions(db: Session, *, tenant_id: str) -> dict[str, int]:
    """Recompute every customer with stock-bearing rows (late POD data, a manual refresh)."""
    tid = (tenant_id or "default").strip() or "default"
    customer_ids = [
        int(c)
        for (c,) in db.execute(
            select(FactCustomerSellthrough.customer_id)
            .where(
                FactCustomerSellthrough.tenant_id == tid,
                FactCustomerSellthrough.reported_soh.isnot(None),
            )
            .distinct()
        ).all()
    ]
    written = 0
    for cid in customer_ids:
        written += recompute_customer_stock_positions(db, tenant_id=tid, customer_id=cid)
    return {"customers": len(customer_ids), "positions": written}


def list_stock_positions(
    db: Session,
    *,
    tenant_id: str,
    threshold_units: float,
    customer_id: int | None = None,
    product_id: int | None = None,
    highlighted_only: bool = False,
    limit: int = 2000,
) -> list[dict[str, Any]]:
    from app.models.dimensions import DimCustomer, DimProduct

    tid = (tenant_id or "default").strip() or "default"
    q = (
        select(CustomerStockPosition, DimCustomer.code, DimCustomer.name, DimProduct.sku, DimProduct.name)
        .join(DimCustomer, DimCustomer.id == CustomerStockPosition.customer_id)
        .join(DimProduct, DimProduct.id == CustomerStockPosition.product_id)
        .where(CustomerStockPosition.tenant_id == tid)
    )
    if customer_id is not None:
        q = q.where(CustomerStockPosition.customer_id == int(customer_id))
    if product_id is not None:
        q = q.where(CustomerStockPosition.product_id == int(product_id))
    if highlighted_only:
        q = q.where(
            and_(
                CustomerStockPosition.gap_units.isnot(None),
                func.abs(CustomerStockPosition.gap_units) >= threshold_units,
            )
        )
    q = q.order_by(CustomerStockPosition.period_end_date.desc(), CustomerStockPosition.id).limit(int(limit))

    def num(v: Any) -> float | None:
        return float(v) if v is not None else None

    out: list[dict[str, Any]] = []
    for pos, ccode, cname, sku, pname in db.execute(q).all():
        out.append(
            {
                "id": int(pos.id),
                "customer_id": int(pos.customer_id),
                "customer_code": ccode,
                "customer_name": cname,
                "product_id": int(pos.product_id),
                "sku": sku,
                "product_name": pname,
                "period_grain": pos.period_grain,
                "period_start_date": pos.period_start_date.isoformat(),
                "period_end_date": pos.period_end_date.isoformat(),
                "period_week": pos.period_week,
                "period_year": pos.period_year,
                "reported_on_hand": num(pos.reported_on_hand),
                "previous_on_hand": num(pos.previous_on_hand),
                "previous_period_end_date": (
                    pos.previous_period_end_date.isoformat() if pos.previous_period_end_date else None
                ),
                "receipts_units": num(pos.receipts_units),
                "units_sold": num(pos.units_sold),
                "expected_on_hand": num(pos.expected_on_hand),
                "gap_units": num(pos.gap_units),
                "in_transit_units": num(pos.in_transit_units),
                "on_order_units": num(pos.on_order_units),
                "status": pos.status,
                "highlighted": is_highlighted(pos.gap_units, threshold_units),
                "reason": gap_reason(pos.gap_units, pos.in_transit_units),
                "report_import_job_id": pos.report_import_job_id,
                "computed_at": pos.computed_at.isoformat() if pos.computed_at else None,
            }
        )
    return out
