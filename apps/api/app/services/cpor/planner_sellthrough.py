"""Customer sell-through is the only source for the promotion planner (Warren 2026-11-19).

Price, cost, stock and expected units for the planner come from ``fact_customer_sellthrough``
for one customer and one product: units sold, ``unit_sell_price``, ``unit_cost``, ``unit_mac``
and ``reported_soh``. Line-ups, demand forecasts, shopper listings, competitor prices, distributor
cover, shipments, buy plans, distributor sell-out, SKU assumptions and earlier cases are not read
here and are not a fallback. A figure sell-through does not carry is returned as ``None`` with a
reason; it is never filled from another source and never replaced by a zero.

Definitions (one place, so every planner path agrees):

* **Run rate**: mean weekly units over the customer's most recent reported weeks. The window is
  ``run_rate_weeks()`` (default 8, env ``PLANNER_SELLTHROUGH_RUN_RATE_WEEKS``). "Reported weeks"
  are the distinct weekly periods the customer has sent, counted back from its own latest week,
  so a customer whose last file is old still has a run rate. Site rows in one week add up; when
  any row names a site, chain rows with no site are the collapsed grain and are left out.
* **Stock**: each site's latest ``reported_soh`` inside the same window, counted once.
* **Cover**: stock divided by the run rate. Missing when the run rate is zero or unknown.
* **Price**: ``unit_sell_price`` of the latest reported week that has a positive price. When
  several sites report that week, the row with the most units sold is used.
* **SRP** (Opus R-04): the price as VAT-inclusive shelf price, which is what ``CporCaseLine.srp``
  and the waterfall expect. Incl-VAT prices are used as reported. Ex-VAT prices are grossed up
  by the tenant's own VAT rate; with no rate set the SRP is missing (``vat_rate_not_configured``).
  A price whose VAT basis is unknown gives no SRP (``price_vat_basis_unknown``).
* **Cost**: ``unit_mac`` of the latest reported week that has a positive ``unit_mac`` or
  ``unit_cost``; ``unit_cost`` when that week's ``unit_mac`` is missing or not positive.
* **Expected units**: run rate times the planning horizon in weeks.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.fact_customer_sellthrough import FactCustomerSellthrough as ST
from app.services.commercial_tenant_profile import _env_int
from app.services.store_dc.rules import is_weekly, norm_label, weekly_rate, weeks_of_cover

RUN_RATE_WEEKS_ENV = "PLANNER_SELLTHROUGH_RUN_RATE_WEEKS"
DEFAULT_RUN_RATE_WEEKS = 8
MAX_RUN_RATE_WEEKS = 52

VOLUME_SOURCE = "customer_sellthrough_run_rate"
SOURCE_LABEL = "customer_sellthrough"

# Reasons a figure is missing. The planner screens show these as "Not available yet".
NO_SELLTHROUGH = "no_customer_sellthrough"
NO_WEEKLY = "no_weekly_sellthrough_reported"
NO_PRICE = "no_positive_unit_sell_price_reported"
NO_COST = "no_unit_mac_or_unit_cost_reported"
NO_SOH = "no_reported_stock"
NO_RATE = "run_rate_is_zero"
NO_CUSTOMER = "no_customer"
PRICE_VAT_UNKNOWN = "price_vat_basis_unknown"
VAT_RATE_UNSET = "vat_rate_not_configured"


def _vat_kind(basis: Any) -> str:
    from app.services.cpor.customer_soh_check import _vat_kind as kind

    return kind(None if basis is None else str(basis))


def srp_from_price(
    price: float | None, vat_basis: Any, vat_rate: float | None
) -> tuple[float | None, str | None]:
    """VAT-inclusive SRP from a reported price, or (None, reason). Never guesses a rate."""
    if price is None:
        return None, None
    kind = _vat_kind(vat_basis)
    if kind == "inc":
        return float(price), None
    if kind == "unknown":
        return None, PRICE_VAT_UNKNOWN
    if vat_rate is None:
        return None, VAT_RATE_UNSET
    return round(float(price) * (1.0 + float(vat_rate)), 4), None


def run_rate_weeks() -> int:
    """Run-rate window in reported weeks: env / settings, default 8, bounded 1..52."""
    return _env_int(RUN_RATE_WEEKS_ENV, DEFAULT_RUN_RATE_WEEKS, lo=1, hi=MAX_RUN_RATE_WEEKS)


def _positive(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _iso(value: Any) -> str | None:
    return (
        value.isoformat()
        if hasattr(value, "isoformat")
        else (None if value is None else str(value))
    )


def weekly_units_and_stock(
    rows: Iterable[Any],
) -> tuple[dict[Any, float], dict[str, tuple[Any, float]]]:
    """Weekly units and latest site stock from (period, grain, kind, units, soh, site)."""
    rows = list(rows)
    weekly: dict[Any, float] = {}
    latest_soh: dict[str, tuple[Any, float]] = {}
    has_sites = any(norm_label(row[5]) for row in rows)
    for row in rows:
        period, grain, kind, units, soh, site = row[0], row[1], row[2], row[3], row[4], row[5]
        site_key = norm_label(site)
        if has_sites and not site_key:
            continue
        if soh is not None:
            previous = latest_soh.get(site_key)
            if previous is None or period >= previous[0]:
                latest_soh[site_key] = (period, float(soh))
        if is_weekly(grain, kind):
            weekly[period] = weekly.get(period, 0.0) + float(units or 0)
    return weekly, latest_soh


def run_rate_from_weekly(weekly: dict[Any, float], window_weeks: int) -> tuple[float | None, int]:
    periods = sorted(weekly)[-max(1, int(window_weeks)) :]
    if not periods:
        return None, 0
    return weekly_rate([weekly[p] for p in periods]), len(periods)


def figures_from_rows(
    window_rows: Iterable[Any],
    price_row: tuple[Any, Any] | None,
    cost_row: tuple[Any, Any, Any] | None,
    *,
    window_weeks: int,
    vat_rate: float | None = None,
) -> dict[str, Any]:
    """Every planner figure for one customer and product.

    ``window_rows``: ``(period, grain, kind, units, soh, site)`` inside the run-rate window.
    ``price_row``: ``(period, unit_sell_price[, vat_basis])`` of the latest positive price, or ``None``.
    ``vat_rate``: the tenant's configured VAT rate, used only to gross an ex-VAT price up to SRP.
    ``cost_row``: ``(period, unit_mac, unit_cost[, fact_id, vat_basis])`` of the latest week with a
    positive cost, or ``None``.
    """
    window_rows = list(window_rows)
    has_any = bool(window_rows) or price_row is not None or cost_row is not None
    weekly, latest_soh = weekly_units_and_stock(window_rows)
    rate, used = run_rate_from_weekly(weekly, window_weeks)
    soh = sum(item[1] for item in latest_soh.values()) if latest_soh else None
    weeks = weeks_of_cover(soh, rate)

    if rate is not None:
        units_reason = None
    else:
        units_reason = NO_WEEKLY if window_rows else NO_SELLTHROUGH
    if soh is not None:
        soh_reason = None
    else:
        soh_reason = NO_SOH if window_rows else NO_SELLTHROUGH
    if weeks is not None:
        cover_reason = None
    elif rate is None:
        cover_reason = units_reason
    elif rate <= 0:
        cover_reason = NO_RATE
    else:
        cover_reason = soh_reason

    price = _positive(price_row[1]) if price_row is not None else None
    price_reason = None if price is not None else (NO_PRICE if has_any else NO_SELLTHROUGH)
    price_vat_basis = price_row[2] if price is not None and len(price_row) > 2 else None
    srp, srp_reason = srp_from_price(price, price_vat_basis, vat_rate)
    if price is None:
        srp_reason = price_reason

    cost: float | None = None
    cost_field: str | None = None
    cost_as_of = None
    cost_fact_id = None
    cost_vat_basis = None
    if cost_row is not None:
        mac = _positive(cost_row[1])
        unit_cost = _positive(cost_row[2])
        if mac is not None:
            cost, cost_field = mac, "unit_mac"
        elif unit_cost is not None:
            cost, cost_field = unit_cost, "unit_cost"
        if cost is not None:
            cost_as_of = _iso(cost_row[0])
            cost_fact_id = cost_row[3] if len(cost_row) > 3 else None
            cost_vat_basis = cost_row[4] if len(cost_row) > 4 else None
    cost_reason = None if cost is not None else (NO_COST if has_any else NO_SELLTHROUGH)

    last_week = max(weekly) if weekly else None
    return {
        "source": SOURCE_LABEL,
        "price": price,
        "price_as_of": _iso(price_row[0]) if price is not None else None,
        "price_reason": price_reason,
        "price_vat_basis": price_vat_basis,
        "srp": srp,
        "srp_reason": srp_reason,
        "cost": cost,
        "cost_field": cost_field,
        "cost_as_of": cost_as_of,
        "cost_fact_id": cost_fact_id,
        "cost_vat_basis": cost_vat_basis,
        "cost_reason": cost_reason,
        "weekly_rate": None if rate is None else float(rate),
        "weeks_used": used,
        "window_weeks": int(window_weeks),
        "units_reason": units_reason,
        "soh_units": None if soh is None else float(soh),
        "soh_reason": soh_reason,
        "cover_weeks": None if weeks is None else float(weeks),
        "cover_reason": cover_reason,
        "last_reported_week": _iso(last_week),
    }


def volume_from_figures(
    figures: dict[str, Any], *, horizon_weeks: int, as_of: date | None = None
) -> dict[str, Any]:
    """Run rate times horizon weeks. Missing, with a reason, when no run rate."""
    start = as_of or date.today()
    horizon = max(1, int(horizon_weeks))
    rate = figures.get("weekly_rate")
    available = rate is not None
    return {
        "horizon_weeks": horizon,
        "period_from": start.isoformat(),
        "period_to": (start + timedelta(weeks=horizon)).isoformat(),
        "forecast_units": float(rate) * horizon if available else None,
        "weekly_run_rate": None if rate is None else float(rate),
        "run_rate_weeks_used": int(figures.get("weeks_used") or 0),
        "run_rate_window_weeks": figures.get("window_weeks"),
        "source": VOLUME_SOURCE,
        "available": available,
        "reason": None if available else figures.get("units_reason"),
    }


# --- reads -------------------------------------------------------------------------------


def _weekly_clause() -> Any:
    return or_(
        func.lower(func.coalesce(ST.period_grain, "")) == "week",
        func.lower(func.coalesce(ST.period_type, "")).in_(("week", "weekly")),
    )


def _scope(tenant_id: str, customer_id: int) -> list[Any]:
    return [ST.tenant_id == tenant_id, ST.customer_id == int(customer_id)]


def window_cutoff(
    session: Session, *, tenant_id: str, customer_id: int, window_weeks: int
) -> date | None:
    """Window start: the Nth most recent weekly period this customer reported.

    A customer with no weekly rows falls back to its latest period of any grain (stock only).
    """
    periods = session.execute(
        select(ST.period_start_date)
        .where(*_scope(tenant_id, customer_id), _weekly_clause())
        .distinct()
        .order_by(ST.period_start_date.desc())
        .limit(max(1, int(window_weeks)))
    ).all()
    if periods:
        return periods[-1][0]
    latest = session.execute(
        select(func.max(ST.period_start_date)).where(*_scope(tenant_id, customer_id))
    ).first()
    return latest[0] if latest and latest[0] is not None else None


def products_in_window(
    session: Session, *, tenant_id: str, customer_id: int, cutoff: date | None
) -> list[int]:
    """Products this customer sold or held stock of inside the window."""
    if cutoff is None:
        return []
    rows = session.execute(
        select(ST.product_id)
        .where(
            *_scope(tenant_id, customer_id),
            ST.period_start_date >= cutoff,
            or_(ST.units_sold > 0, ST.reported_soh > 0),
        )
        .distinct()
        .order_by(ST.product_id)
    ).all()
    return [int(row[0]) for row in rows]


@dataclass
class SellthroughBook:
    """Sell-through reads for one customer and a set of products, done once."""

    customer_id: int | None
    window_weeks: int
    cutoff: date | None = None
    vat_rate: float | None = None
    window_rows: dict[int, list[Any]] = field(default_factory=dict)
    price_rows: dict[int, tuple[Any, ...]] = field(default_factory=dict)
    cost_rows: dict[int, tuple[Any, ...]] = field(default_factory=dict)

    def figures(self, product_id: int) -> dict[str, Any]:
        pid = int(product_id)
        if self.customer_id is None:
            out = figures_from_rows([], None, None, window_weeks=self.window_weeks)
            for key in (
                "price_reason",
                "srp_reason",
                "cost_reason",
                "units_reason",
                "soh_reason",
                "cover_reason",
            ):
                out[key] = NO_CUSTOMER
            return out
        return figures_from_rows(
            self.window_rows.get(pid, []),
            self.price_rows.get(pid),
            self.cost_rows.get(pid),
            window_weeks=self.window_weeks,
            vat_rate=self.vat_rate,
        )


def read_book(
    session: Session,
    *,
    tenant_id: str,
    customer_id: int | None,
    product_ids: Iterable[int],
    window_weeks: int | None = None,
    cutoff: date | None = None,
    cutoff_known: bool = False,
    want: Iterable[str] = ("window", "price", "cost"),
) -> SellthroughBook:
    """Read window rows, latest price and latest cost for the products. All from sell-through.

    ``want`` limits the reads to the parts the caller shows: ``window`` (run rate, stock, cover),
    ``price`` and ``cost``. A part that is not asked for stays empty and reads as missing.
    """
    parts = set(want)
    weeks = int(window_weeks) if window_weeks is not None else run_rate_weeks()
    book = SellthroughBook(
        customer_id=None if customer_id is None else int(customer_id), window_weeks=weeks
    )
    ids = sorted({int(p) for p in product_ids})
    if customer_id is None or not ids:
        return book
    if "window" in parts and not cutoff_known:
        cutoff = window_cutoff(
            session, tenant_id=tenant_id, customer_id=int(customer_id), window_weeks=weeks
        )
    book.cutoff = cutoff
    scope = _scope(tenant_id, int(customer_id))
    if "window" in parts and cutoff is not None:
        for row in session.execute(
            select(
                ST.product_id,
                ST.period_start_date,
                ST.period_grain,
                ST.period_type,
                ST.units_sold,
                ST.reported_soh,
                ST.site_label,
            ).where(*scope, ST.product_id.in_(ids), ST.period_start_date >= cutoff)
        ).all():
            book.window_rows.setdefault(int(row[0]), []).append(tuple(row[1:]))
    if "price" in parts:
        for row in session.execute(
            select(ST.product_id, ST.period_start_date, ST.unit_sell_price, ST.vat_basis)
            .where(*scope, ST.product_id.in_(ids), _weekly_clause(), ST.unit_sell_price > 0)
            .distinct(ST.product_id)
            .order_by(
                ST.product_id, ST.period_start_date.desc(), ST.units_sold.desc(), ST.id.desc()
            )
        ).all():
            book.price_rows[int(row[0])] = (row[1], row[2], row[3])
        from app.services.commercial_tenant_profile import configured_vat_rate_pct

        book.vat_rate = configured_vat_rate_pct(tenant_id)
    if "cost" in parts:
        for row in session.execute(
            select(
                ST.product_id, ST.period_start_date, ST.unit_mac, ST.unit_cost, ST.id, ST.vat_basis
            )
            .where(
                *scope,
                ST.product_id.in_(ids),
                _weekly_clause(),
                or_(ST.unit_mac > 0, ST.unit_cost > 0),
            )
            .distinct(ST.product_id)
            .order_by(
                ST.product_id, ST.period_start_date.desc(), ST.units_sold.desc(), ST.id.desc()
            )
        ).all():
            book.cost_rows[int(row[0])] = tuple(row[1:])
    return book
