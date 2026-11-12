"""Customer SOH check source (D-062 / BACKLOG-135, N-0049; D-0038 tolerance).

The customer's weekly SOH is the **check** on derived customer MAC, never its
input (D-062). CST apply lands ``reported_soh`` / ``unit_mac`` / ``unit_cost`` on
``fact_customer_sellthrough``; that is the only source read here.
``fact_inventory_customer`` has no import writer and is not a source.

Rule (customer x product, as of date D):
- period = latest ``period_start_date`` <= D among CST rows with ``reported_soh``;
- ``soh_units`` = sum of ``reported_soh`` over that period's rows (all sites —
  stock wherever it sits; D-0038);
- ``soh_unit_cost`` = ex-VAT ``reported_soh``-weighted average of ``unit_mac`` else
  ``unit_cost`` (same preference as CPOR tier-1 cost). Incl-VAT costs are divided
  by 1.15 first. A cost with an unknown VAT basis is left out;
- ``delta`` = ex-VAT derived MAC - ``soh_unit_cost``. When both sides exist, flag
  ``soh_tolerance`` if abs(delta) / abs(derived MAC) exceeds the tenant
  tolerance (default 10%; D-0038). A stored MAC passed with ``derived_mac_vat``
  uses the same rule: incl-VAT is divided by 1.15, and an unknown basis
  withholds the gap. Omitting ``derived_mac_vat`` compares the passed number,
  which is already the ex-VAT operand (a manual cost). Accounts with SOH units
  but no cost stay units-only: no invented cost, no cost-tolerance flag.
Flags: ``zero_soh`` (reported 0 on hand: no cost to check), ``no_soh_cost`` (SOH
units without any cost field), ``soh_tolerance`` (cost gap beyond tolerance),
``vat_basis_unknown`` (a cost whose basis is missing or neither ex-VAT nor incl-VAT).
``vat_basis`` on the result stays the source value. The compared cost is ex-VAT.
No CST SOH row for the pair -> ``status: unavailable`` (never zero stock).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Iterable

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.services.cpor.waterfall import _as_decimal

SOURCE_TABLE = "fact_customer_sellthrough"
# D-0038 default; live reads prefer commercial_tenant_profile.soh_tolerance_pct.
DEFAULT_SOH_TOLERANCE_PCT = Decimal("0.10")
# Decided 2026-11-10: the SOH check compares ex-VAT. Incl-VAT costs divide by 1.15.
VAT_INCL_DIVISOR = Decimal("1.15")
COMPARED_VAT = "ex_vat"
FLAG_SOH_TOLERANCE = "soh_tolerance"
FLAG_VAT_BASIS_UNKNOWN = "vat_basis_unknown"
# Omitting derived_mac_vat means the caller already passed an ex-VAT operand.
_MAC_VAT_OMITTED = object()


def _vat_kind(basis: str | None) -> str:
    """``ex`` / ``inc`` / ``unknown``. Only the bases the sell-through files actually store."""
    raw = str(basis or "").strip().lower()
    if raw == "ex_vat" or raw.startswith("ex_"):
        return "ex"
    if raw.startswith("inc"):
        return "inc"
    return "unknown"


def _compared_mac(raw: Decimal, vat: Any, flags: list[str]) -> Decimal | None:
    """Ex-VAT operand, or None when a supplied basis is unknown and the gap must be withheld."""
    if vat is _MAC_VAT_OMITTED:
        return raw
    kind = _vat_kind(None if vat is None else str(vat))
    if kind == "unknown":
        if FLAG_VAT_BASIS_UNKNOWN not in flags:
            flags.append(FLAG_VAT_BASIS_UNKNOWN)
        return None
    if kind == "inc":
        return raw / VAT_INCL_DIVISOR
    return raw


def _cst_vat_basis_for_amount(
    session: Session,
    *,
    customer_id: int,
    product_id: int,
    as_of: date,
    cost_basis: Decimal | float | int | str | None,
) -> str | None:
    """VAT basis of the latest CST cost row when its chosen amount is still the stored cost.

    A different amount means this row is not the stored figure, so the basis stays unknown.
    """
    if cost_basis is None:
        return None
    row = session.execute(
        select(
            FactCustomerSellthrough.unit_mac,
            FactCustomerSellthrough.unit_cost,
            FactCustomerSellthrough.vat_basis,
        )
        .where(
            FactCustomerSellthrough.customer_id == int(customer_id),
            FactCustomerSellthrough.product_id == int(product_id),
            or_(
                FactCustomerSellthrough.unit_mac.is_not(None),
                FactCustomerSellthrough.unit_cost.is_not(None),
            ),
            FactCustomerSellthrough.period_start_date <= as_of,
        )
        .order_by(
            FactCustomerSellthrough.period_start_date.desc(),
            FactCustomerSellthrough.id.desc(),
        )
        .limit(1)
    ).first()
    if row is None:
        return None
    unit_mac, unit_cost, vat_basis = row
    chosen = unit_mac if unit_mac is not None else unit_cost
    if chosen is None or _as_decimal(chosen) != _as_decimal(cost_basis):
        return None
    return None if vat_basis is None else str(vat_basis)


def resolve_stored_mac_vat(
    session: Session,
    *,
    cost_source: str | None,
    cost_evidence: dict | None,
    cost_basis: Decimal | float | int | str | None,
    customer_id: int,
    product_id: int,
    as_of: date,
) -> tuple[bool, str | None]:
    """``(apply, basis)`` for a stored case-line cost.

    ``(False, None)`` compares the stored number as given (manual, or no source).
    ``(True, basis)`` runs the ex-VAT rule. Sell-out evidence is already ex-tax.
    A CST-sourced cost uses the source row's ``vat_basis``. A missing basis, or a
    current CST row whose amount is no longer the stored cost, withholds the gap.
    """
    source = str(cost_source or "").strip()
    if source == "sellout_evidence":
        return True, "ex_vat"
    if source != "cst_reported":
        return False, None
    evidence = cost_evidence if isinstance(cost_evidence, dict) else {}
    fact_id = evidence.get("fact_id")
    if fact_id is not None:
        try:
            fact_key = int(fact_id)
        except (TypeError, ValueError):
            fact_key = None
        if fact_key is not None:
            row = session.get(FactCustomerSellthrough, fact_key)
            if row is not None:
                basis = getattr(row, "vat_basis", None)
                return True, None if basis is None else str(basis)
    return True, _cst_vat_basis_for_amount(
        session,
        customer_id=customer_id,
        product_id=product_id,
        as_of=as_of,
        cost_basis=cost_basis,
    )


def _resolve_tolerance_pct(
    tolerance_pct: Decimal | float | int | str | None,
    *,
    tenant_id: str = "default",
) -> Decimal:
    if tolerance_pct is not None:
        return _as_decimal(tolerance_pct)
    from app.services.commercial_tenant_profile import soh_tolerance_pct

    return _as_decimal(soh_tolerance_pct(tenant_id))


def summarise_soh_rows(
    rows: Iterable[Any],
    *,
    as_of: date,
    derived_mac: Decimal | float | int | str | None = None,
    derived_mac_vat: Any = _MAC_VAT_OMITTED,
    tolerance_pct: Decimal | float | int | str | None = None,
    tenant_id: str = "default",
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
    unknown_cost = False
    for _id, _period, _ptype, soh, unit_mac, unit_cost, vat_basis in rows:
        if vat_basis:
            vat_bases.add(str(vat_basis))
        soh_d = _as_decimal(soh)
        units += soh_d
        cost = unit_mac if unit_mac is not None else unit_cost
        if cost is None:
            continue
        fields.add("unit_mac" if unit_mac is not None else "unit_cost")
        kind = _vat_kind(None if vat_basis is None else str(vat_basis))
        if kind == "unknown":
            # A cost with no known basis must not be treated as ex-VAT or incl-VAT.
            unknown_cost = True
            continue
        cost_d = _as_decimal(cost)
        if kind == "inc":
            cost_d = cost_d / VAT_INCL_DIVISOR
        num += soh_d * cost_d
        den += soh_d

    soh_cost = num / den if den > 0 else None
    if units == 0:
        flags.append("zero_soh")  # nothing on hand: no SOH-weighted cost to check against
    if not fields:
        flags.append("no_soh_cost")
    if unknown_cost:
        flags.append(FLAG_VAT_BASIS_UNKNOWN)
    out.update(
        status="available",
        period_start_date=rows[0][1].isoformat(),
        period_type=rows[0][2],
        row_count=len(rows),
        soh_units=float(units),
        soh_unit_cost=float(soh_cost) if soh_cost is not None else None,
        soh_cost_vat=COMPARED_VAT if soh_cost is not None else None,
        cost_field=("mixed" if len(fields) > 1 else next(iter(fields))) if fields else None,
        vat_basis=(next(iter(vat_bases)) if len(vat_bases) == 1 else sorted(vat_bases)) or None,
        flags=flags,
    )
    if derived_mac is not None:
        raw_mac = _as_decimal(derived_mac)
        mac = _compared_mac(raw_mac, derived_mac_vat, flags)
        if mac is None:
            # Supplied basis is unknown: keep the stored number and do not invent a gap.
            out["derived_mac"] = float(raw_mac)
            return out
        out["derived_mac"] = float(mac)
        if (
            derived_mac_vat is not _MAC_VAT_OMITTED
            and _vat_kind(None if derived_mac_vat is None else str(derived_mac_vat)) == "inc"
        ):
            out["derived_mac_input"] = float(raw_mac)
            out["derived_mac_input_vat"] = str(derived_mac_vat)
        if soh_cost is not None:
            delta = mac - soh_cost
            out["delta"] = float(delta)
            tol = _resolve_tolerance_pct(tolerance_pct, tenant_id=tenant_id)
            out["tolerance_pct"] = float(tol)
            denom = abs(mac)
            if denom > 0:
                gap = abs(delta) / denom
                out["gap_pct"] = float(gap)
                if gap > tol:
                    flags.append(FLAG_SOH_TOLERANCE)
            elif abs(delta) > 0:
                # Zero derived MAC with a non-zero SOH cost: always outside tolerance.
                out["gap_pct"] = None
                flags.append(FLAG_SOH_TOLERANCE)
            else:
                out["gap_pct"] = 0.0
            # flags list is already bound into out["flags"] from the earlier update.
    return out


def customer_soh_check(
    session: Session,
    *,
    customer_id: int,
    product_id: int,
    as_of: date,
    derived_mac: Decimal | float | int | str | None = None,
    derived_mac_vat: Any = _MAC_VAT_OMITTED,
    tolerance_pct: Decimal | float | int | str | None = None,
    tenant_id: str = "default",
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
    return summarise_soh_rows(
        rows,
        as_of=as_of,
        derived_mac=derived_mac,
        derived_mac_vat=derived_mac_vat,
        tolerance_pct=tolerance_pct,
        tenant_id=tenant_id,
    )
