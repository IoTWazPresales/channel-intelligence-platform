"""Latest cover row per pair. cip_test only; the transaction rolls back."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.sync_url import sqlalchemy_sync_engine_url
from app.models.derived import WeeksOfCoverObservation
from app.models.dimensions import DimDistributor, DimProduct
from app.services.woc_observation_read import latest_woc_observation_stmt

TENANT = "n0108-latest-observation"
ASOF = date(2026, 10, 1)
EARLIER = date(2026, 9, 1)
T0 = datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)
T1 = datetime(2026, 10, 2, 8, 0, tzinfo=timezone.utc)


@pytest.fixture
def session():
    engine = create_engine(sqlalchemy_sync_engine_url(get_settings().database_url_sync))
    with engine.connect() as conn:
        if conn.execute(text("select current_database()")).scalar() != "cip_test":
            pytest.skip("cip_test only")
        conn.rollback()
        outer = conn.begin()
        db = Session(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield db
        finally:
            db.close()
            outer.rollback()
    engine.dispose()


def _pair(db: Session) -> tuple[int, int, int]:
    distributor_ids = [int(row) for row in db.scalars(select(DimDistributor.id).order_by(DimDistributor.id).limit(2))]
    product_ids = [int(row) for row in db.scalars(select(DimProduct.id).order_by(DimProduct.id).limit(2))]
    if len(distributor_ids) < 1 or len(product_ids) < 2:
        pytest.skip("cip_test needs a distributor and two products")
    return distributor_ids[0], product_ids[0], product_ids[1]


def _row(
    *,
    distributor_id: int,
    product_id: int,
    key: str,
    trigger: str,
    cover_as_of: date,
    observed_at: datetime,
    stock: float,
) -> WeeksOfCoverObservation:
    return WeeksOfCoverObservation(
        tenant_id=TENANT,
        distributor_id=distributor_id,
        product_id=product_id,
        snapshot_date=cover_as_of,
        cover_as_of_date=cover_as_of,
        observed_at=observed_at,
        trigger=trigger,
        reported_soh=stock,
        sell_out_since=0,
        landed_since=0,
        derived_stock=stock,
        weekly_velocity=1,
        weeks_of_cover=stock,
        replenishment_flag=False,
        replenishment_threshold_weeks=4,
        params={"probe": key},
        formula_version="A3-02.v1",
        data_vintage={"probe": key},
        source_key=f"woc:{TENANT}:{key}",
    )


def test_latest_row_follows_cover_date_then_apply_then_observed_at(session: Session) -> None:
    distributor_id, product_a, product_b = _pair(session)
    session.add_all(
        [
            # Older cover date loses even though it was observed later.
            _row(
                distributor_id=distributor_id,
                product_id=product_a,
                key="old-apply",
                trigger="dsi_apply",
                cover_as_of=EARLIER,
                observed_at=T1,
                stock=1,
            ),
            # Same latest date: backfill loses to apply even when observed later.
            _row(
                distributor_id=distributor_id,
                product_id=product_a,
                key="backfill-later",
                trigger="as_of_backfill",
                cover_as_of=ASOF,
                observed_at=T1,
                stock=2,
            ),
            _row(
                distributor_id=distributor_id,
                product_id=product_a,
                key="apply-winner",
                trigger="shipment_apply",
                cover_as_of=ASOF,
                observed_at=T0,
                stock=3,
            ),
            # Two applies on the same date: the later observation wins.
            _row(
                distributor_id=distributor_id,
                product_id=product_b,
                key="apply-early",
                trigger="dsi_apply",
                cover_as_of=ASOF,
                observed_at=T0,
                stock=4,
            ),
            _row(
                distributor_id=distributor_id,
                product_id=product_b,
                key="apply-late",
                trigger="dsi_apply",
                cover_as_of=ASOF,
                observed_at=T1,
                stock=5,
            ),
        ]
    )
    session.flush()

    rows = session.scalars(latest_woc_observation_stmt(tenant_id=TENANT)).all()
    by_product = {int(row.product_id): row for row in rows}
    assert set(by_product) == {product_a, product_b}
    assert by_product[product_a].source_key.endswith("apply-winner")
    assert float(by_product[product_a].derived_stock) == 3
    assert by_product[product_b].source_key.endswith("apply-late")
    assert float(by_product[product_b].derived_stock) == 5

    one = session.scalars(
        latest_woc_observation_stmt(tenant_id=TENANT, distributor_id=distributor_id, product_id=product_a)
    ).all()
    assert [row.source_key for row in one] == [by_product[product_a].source_key]

    other_distributor = session.scalar(
        select(DimDistributor.id).where(DimDistributor.id != distributor_id).order_by(DimDistributor.id).limit(1)
    )
    if other_distributor is not None:
        empty = session.scalars(
            latest_woc_observation_stmt(tenant_id=TENANT, distributor_id=int(other_distributor))
        ).all()
        assert empty == []
