"""Customer SOH check source (D-062 / BACKLOG-135, N-0049).

The customer's weekly SOH is the **check** on derived customer MAC, never its
input (D-062). CST apply lands ``reported_soh`` / ``unit_mac`` / ``unit_cost`` on
``fact_customer_sellthrough``; that is the only source read here.
``fact_inventory_customer`` has no import writer and is not a source.

Rule (customer x product, as of date D):
- period = latest ``period_start_date`` <= D among CST rows with ``reported_soh``;
- ``soh_units`` = sum of ``reported_soh`` over that period's rows (all sites);
- ``soh_unit_cost`` = ``reported_soh``-weighted average of ``unit_mac`` else
  ``unit_cost`` (same preference as CPOR tier-1 cost) over rows carrying both;
- ``delta`` = derived MAC - ``soh_unit_cost``. Reported only; no tolerance flag.
Flags: ``zero_soh`` (reported 0 on hand: no cost to check), ``no_soh_cost`` (SOH
units without any cost field). ``vat_basis`` is passed through, not converted.
No CST SOH row for the pair -> ``status: unavailable`` (never zero stock).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.services.cpor.waterfall import _as_decimal

SOURCE_TABLE = "fact_customer_sellthrough"


def summarise_soh_rows(
    rows: Iterable[Any],
    *,
    as_of: date,
    derived_mac: Decimal | float | int | str | None = None,
) -> dict[str, Any]:
    """Rows: (id, period_start_date, period_type, reported_soh, unit_mac, unit_cost, vat_basis) of one period."""
    rows = list(rows)
    out: dict[str, Any] = {"source": SOURCE_TABLE, "as_of": as_of.isoformat()}
    if not rows:
        out.update(
            status="unavailable",
            reason=f"customer SOH unavailable — no {SOURCE_TABLE} row with reported_soh on or before {as_of.isoformat()}",
            flags=["no_customer_soh"],
        )
        return out

    flags: list[str] = []
    units = Decimal("0")
    num = Decimal("0")
    den = Decimal("0")
    fields: set[str] = set()
    vat_bases: set[str] = set()
    for _id, _period, _ptype, soh, unit_mac, unit_cost, vat_basis in rows:
        if vat_basis:
            vat_bases.add(str(vat_basis))
        soh_d = _as_decimal(soh)
        units += soh_d
        cost = unit_mac if unit_mac is not None else unit_cost
        if cost is None:
            continue
        fields.add("unit_mac" if unit_mac is not None else "unit_cost")
        num += soh_d * _as_decimal(cost)
        den += soh_d

    soh_cost = num / den if den > 0 else None
    if units == 0:
        flags.append("zero_soh")  # nothing on hand: no SOH-weighted cost to check against
    if not fields:
        flags.append("no_soh_cost")
    out.update(
        status="available",
        period_start_date=rows[0][1].isoformat(),
        period_type=rows[0][2],
        row_count=len(rows),
        soh_units=float(units),
        soh_unit_cost=float(soh_cost) if soh_cost is not None else None,
        cost_field=("mixed" if len(fields) > 1 else next(iter(fields))) if fields else None,
        vat_basis=(next(iter(vat_bases)) if len(vat_bases) == 1 else sorted(vat_bases)) or None,
        flags=flags,
    )
    if derived_mac is not None:
        out["derived_mac"] = float(_as_decimal(derived_mac))
        if soh_cost is not None:
            out["delta"] = float(_as_decimal(derived_mac) - soh_cost)
    return out


def customer_soh_check(
    session: Session,
    *,
    customer_id: int,
    product_id: int,
    as_of: date,
    derived_mac: Decimal | float | int | str | None = None,
) -> dict[str, Any]:
    """Latest CST SOH for the pair as of ``as_of``, compared to ``derived_mac`` when given. Read-only."""
    pair = (
        FactCustomerSellthrough.customer_id == int(customer_id),
        FactCustomerSellthrough.product_id == int(product_id),
        FactCustomerSellthrough.reported_soh.is_not(None),
    )
    latest = (
        select(func.max(FactCustomerSellthrough.period_start_date))
        .where(*pair, FactCustomerSellthrough.period_start_date <= as_of)
        .scalar_subquery()
    )
    rows = session.execute(
        select(
            FactCustomerSellthrough.id,
            FactCustomerSellthrough.period_start_date,
            FactCustomerSellthrough.period_type,
            FactCustomerSellthrough.reported_soh,
            FactCustomerSellthrough.unit_mac,
            FactCustomerSellthrough.unit_cost,
            FactCustomerSellthrough.vat_basis,
        )
        .where(*pair, FactCustomerSellthrough.period_start_date == latest)
        .order_by(FactCustomerSellthrough.id.asc())
    ).all()
    return summarise_soh_rows(rows, as_of=as_of, derived_mac=derived_mac)
