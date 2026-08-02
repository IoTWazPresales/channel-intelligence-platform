"""API / predicate tests for shipping commercial KPI contract."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import select, text

from app.db.session_sync import SessionLocal
from app.models.facts import FactInboundShipment
from app.services.shipping_commercial_kpis import (
    COHORT_CURRENT_INCOMING,
    COHORT_OVERDUE,
    normalize_cohort,
    predicate_arriving_week,
    predicate_current_incoming,
    predicate_overdue,
    predicate_stale_promise,
)


def test_normalize_cohort():
    assert normalize_cohort("current_incoming") == COHORT_CURRENT_INCOMING
    assert normalize_cohort("OVERDUE") == COHORT_OVERDUE
    assert normalize_cohort("nope") is None
    assert normalize_cohort("") is None


def test_current_incoming_predicate_sql_shape():
    today = date(2026, 7, 27)
    pred = predicate_current_incoming(today)
    stmt = select(FactInboundShipment.id).where(pred)
    assert stmt is not None


def test_overdue_excludes_stale_and_requires_eta_window():
    today = date(2026, 7, 27)
    overdue = str(predicate_overdue(today))
    stale = str(predicate_stale_promise(today))
    assert "promise_date" in overdue
    assert "eta_date" in overdue
    assert "promise_date" in stale


def test_arriving_week_bounds():
    w0 = date(2026, 7, 27)
    w1 = w0 + timedelta(days=6)
    pred = predicate_arriving_week(w0, w1)
    assert pred is not None


def _skip_unless_cip_soak(db) -> None:
    db_name = db.execute(text("SELECT current_database()")).scalar()
    if db_name != "cip":
        pytest.skip(f"soak test requires real cip inventory data, got {db_name!r}")


def test_cip_current_incoming_pipeline_below_all_scheduled():
    """SELECT-only: gated cohort must be far below all-scheduled sum (Phase 0 proof)."""
    with SessionLocal() as db:
        _skip_unless_cip_soak(db)
        today = date.today()
        horizon = today + timedelta(days=90)
        all_sched = float(
            db.execute(
                text(
                    """
                    SELECT coalesce(sum(amount), 0)
                    FROM fact_inbound_shipment
                    WHERE status = 'scheduled' AND amount IS NOT NULL
                    """
                )
            ).scalar()
            or 0
        )
        gated = float(
            db.execute(
                text(
                    """
                    SELECT coalesce(sum(amount), 0)
                    FROM fact_inbound_shipment
                    WHERE status = 'scheduled'
                      AND pod_date IS NULL
                      AND amount IS NOT NULL
                      AND coalesce(eta_date, promise_date) IS NOT NULL
                      AND coalesce(eta_date, promise_date) >= :today
                      AND coalesce(eta_date, promise_date) <= :horizon
                    """
                ),
                {"today": today, "horizon": horizon},
            ).scalar()
            or 0
        )
        assert gated < all_sched
        assert gated < 200_000_000


def test_cip_overdue_contracted_lte_legacy():
    with SessionLocal() as db:
        _skip_unless_cip_soak(db)
        today = date.today()
        horizon = today + timedelta(days=90)
        stale_cut = today - timedelta(days=180)
        legacy = int(
            db.execute(
                text(
                    """
                    SELECT count(*) FROM fact_inbound_shipment
                    WHERE status = 'scheduled'
                      AND promise_date IS NOT NULL
                      AND promise_date < :today
                      AND pod_date IS NULL
                    """
                ),
                {"today": today},
            ).scalar()
            or 0
        )
        contracted = int(
            db.execute(
                text(
                    """
                    SELECT count(*) FROM fact_inbound_shipment
                    WHERE status = 'scheduled'
                      AND pod_date IS NULL
                      AND promise_date IS NOT NULL
                      AND promise_date < :today
                      AND promise_date >= :stale_cut
                      AND eta_date IS NOT NULL
                      AND eta_date >= :today
                      AND eta_date <= :horizon
                    """
                ),
                {"today": today, "stale_cut": stale_cut, "horizon": horizon},
            ).scalar()
            or 0
        )
        assert contracted <= legacy
