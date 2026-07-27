"""Shipping commercial KPI predicates — single source of truth with the contract doc.

See ``docs/SHIPPING_COMMERCIAL_KPI_CONTRACT.md``.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import ColumnElement, and_, func

from app.models.facts import FactInboundShipment

CURRENT_INCOMING_HORIZON_DAYS = 90
OVERDUE_STALE_DAYS = 180

COHORT_CURRENT_INCOMING = "current_incoming"
COHORT_OVERDUE = "overdue"
COHORT_ARRIVING_WEEK = "arriving_week"
COHORT_LANDED_WEEK = "landed_week"

VALID_COHORTS = frozenset(
    {
        COHORT_CURRENT_INCOMING,
        COHORT_OVERDUE,
        COHORT_ARRIVING_WEEK,
        COHORT_LANDED_WEEK,
    }
)

COHORT_DEFINITIONS: dict[str, str] = {
    COHORT_CURRENT_INCOMING: (
        f"scheduled · not landed · effective arrival (ETA else promise) "
        f"in [today, today+{CURRENT_INCOMING_HORIZON_DAYS}d]"
    ),
    COHORT_OVERDUE: (
        f"scheduled · not landed · promise passed but not older than "
        f"{OVERDUE_STALE_DAYS}d · still in current-incoming window via ETA"
    ),
    COHORT_ARRIVING_WEEK: "scheduled · not landed · ETA in current ISO week",
    COHORT_LANDED_WEEK: "received · POD date in current ISO week",
}


def effective_arrival_expr() -> ColumnElement[Any]:
    return func.coalesce(FactInboundShipment.eta_date, FactInboundShipment.promise_date)


def current_incoming_window(today: date) -> tuple[date, date]:
    return today, today + timedelta(days=CURRENT_INCOMING_HORIZON_DAYS)


def stale_promise_cutoff(today: date) -> date:
    return today - timedelta(days=OVERDUE_STALE_DAYS)


def predicate_current_incoming(today: date) -> ColumnElement[bool]:
    d0, d1 = current_incoming_window(today)
    eff = effective_arrival_expr()
    return and_(
        FactInboundShipment.status == "scheduled",
        FactInboundShipment.pod_date.is_(None),
        eff.is_not(None),
        eff >= d0,
        eff <= d1,
    )


def predicate_overdue(today: date) -> ColumnElement[bool]:
    """Promise passed, not landed, not stale, still current-incoming via ETA."""
    d0, d1 = current_incoming_window(today)
    stale_cut = stale_promise_cutoff(today)
    return and_(
        FactInboundShipment.status == "scheduled",
        FactInboundShipment.pod_date.is_(None),
        FactInboundShipment.promise_date.is_not(None),
        FactInboundShipment.promise_date < today,
        FactInboundShipment.promise_date >= stale_cut,
        FactInboundShipment.eta_date.is_not(None),
        FactInboundShipment.eta_date >= d0,
        FactInboundShipment.eta_date <= d1,
    )


def predicate_stale_promise(today: date) -> ColumnElement[bool]:
    stale_cut = stale_promise_cutoff(today)
    return and_(
        FactInboundShipment.status == "scheduled",
        FactInboundShipment.pod_date.is_(None),
        FactInboundShipment.promise_date.is_not(None),
        FactInboundShipment.promise_date < stale_cut,
    )


def predicate_arriving_week(week_start: date, week_end: date) -> ColumnElement[bool]:
    return and_(
        FactInboundShipment.status == "scheduled",
        FactInboundShipment.pod_date.is_(None),
        FactInboundShipment.eta_date.is_not(None),
        FactInboundShipment.eta_date >= week_start,
        FactInboundShipment.eta_date <= week_end,
    )


def predicate_landed_week(week_start: date, week_end: date) -> ColumnElement[bool]:
    return and_(
        FactInboundShipment.status == "received",
        FactInboundShipment.pod_date.is_not(None),
        FactInboundShipment.pod_date >= week_start,
        FactInboundShipment.pod_date <= week_end,
    )


def predicate_for_cohort(
    cohort: str | None,
    *,
    today: date,
    week_start: date,
    week_end: date,
) -> ColumnElement[bool] | None:
    if not cohort:
        return None
    key = str(cohort).strip().lower()
    if key == COHORT_CURRENT_INCOMING:
        return predicate_current_incoming(today)
    if key == COHORT_OVERDUE:
        return predicate_overdue(today)
    if key == COHORT_ARRIVING_WEEK:
        return predicate_arriving_week(week_start, week_end)
    if key == COHORT_LANDED_WEEK:
        return predicate_landed_week(week_start, week_end)
    return None


def normalize_cohort(raw: str | None) -> str | None:
    if raw is None or not str(raw).strip():
        return None
    key = str(raw).strip().lower()
    return key if key in VALID_COHORTS else None
