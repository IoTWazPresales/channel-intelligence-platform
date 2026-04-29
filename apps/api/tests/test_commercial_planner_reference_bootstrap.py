"""Tests for commercial planner system reference dimension bootstrap (OPEN_CHANNEL, UNASSIGNED)."""

from __future__ import annotations

from sqlalchemy import func, select

from app.db.session_sync import SessionLocal
from app.models.dimensions import DimCustomer, DimDistributor
from app.services.commercial_planner.open_channel_customer import OPEN_CHANNEL_CUSTOMER_CODE
from app.services.commercial_planner.reference_bootstrap import ensure_commercial_planner_system_reference_data_sync
from app.services.commercial_planner.unassigned_distributor import UNASSIGNED_DISTRIBUTOR_CODE


def test_ensure_commercial_planner_system_reference_data_idempotent():
    """Two runs do not duplicate OPEN_CHANNEL / UNASSIGNED rows (requires real DB from SessionLocal)."""
    with SessionLocal() as session:
        conn = session.connection()
        ensure_commercial_planner_system_reference_data_sync(conn)
        session.commit()

    with SessionLocal() as session:
        n_oc = session.scalar(
            select(func.count()).select_from(DimCustomer).where(DimCustomer.code == OPEN_CHANNEL_CUSTOMER_CODE)
        )
        n_un = session.scalar(
            select(func.count()).select_from(DimDistributor).where(DimDistributor.code == UNASSIGNED_DISTRIBUTOR_CODE)
        )
        assert int(n_oc or 0) >= 1
        assert int(n_un or 0) >= 1

        conn = session.connection()
        ensure_commercial_planner_system_reference_data_sync(conn)
        session.commit()

        n_oc2 = session.scalar(
            select(func.count()).select_from(DimCustomer).where(DimCustomer.code == OPEN_CHANNEL_CUSTOMER_CODE)
        )
        n_un2 = session.scalar(
            select(func.count()).select_from(DimDistributor).where(DimDistributor.code == UNASSIGNED_DISTRIBUTOR_CODE)
        )
        assert n_oc2 == n_oc
        assert n_un2 == n_un
