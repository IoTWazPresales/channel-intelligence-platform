"""Rolled-back cip_test session and fictional rows for store and DC replenishment."""

from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.sync_url import sqlalchemy_sync_engine_url
from app.models.cpor import CporCase
from app.models.customer_report_config import CustomerReportConfig
from app.models.dimensions import CustomerLocation, DimCustomer, DimDistributor, DimProduct, DistributorLocation
from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.models.facts import FactInboundShipment, FactPromotionPlan

WEEK0 = date(2026, 1, 5)


@pytest.fixture
def session():
    engine = create_engine(sqlalchemy_sync_engine_url(get_settings().database_url_sync))
    with engine.connect() as conn:
        if conn.execute(text("select current_database()")).scalar() != "cip_test":
            pytest.skip("cip_test only")
        if not conn.execute(
            text("select to_regclass('site_candidate')")
        ).scalar():
            pytest.skip("20261103_0052 is not applied")
        conn.rollback()
        outer = conn.begin()
        db = Session(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield db
        finally:
            db.close()
            outer.rollback()
    engine.dispose()


class World:
    def __init__(self, db: Session):
        self.db = db
        self.token = uuid4().hex[:8]
        self.tenant = f"sdc-{self.token}"
        self._n = 0

    def code(self, prefix: str) -> str:
        return f"{prefix}-{self.token}"

    def customer(self, prefix: str, *, target: float | None = None, minimum: float | None = None, slow: float | None = None, unsold: float | None = None) -> DimCustomer:
        row = DimCustomer(tenant_id=self.tenant, code=self.code(prefix), name=self.code(prefix), is_key_account=False)
        self.db.add(row)
        self.db.flush()
        self.db.add(
            CustomerReportConfig(
                customer_id=row.id,
                reports_expected=False,
                replen_min_weeks_of_cover=minimum,
                replen_target_weeks_of_cover=target,
                slow_cover_multiple=slow,
                unsold_weeks=unsold,
            )
        )
        self.db.flush()
        return row

    def distributor(self, prefix: str = "SDC-D") -> DimDistributor:
        row = DimDistributor(tenant_id=self.tenant, code=self.code(prefix)[:32], name=self.code(prefix))
        self.db.add(row)
        self.db.flush()
        return row

    def product(self, prefix: str = "SDC-SKU") -> DimProduct:
        row = DimProduct(tenant_id=self.tenant, sku=self.code(prefix), name=self.code(prefix), product_line="LINE-A")
        self.db.add(row)
        self.db.flush()
        return row

    def distributor_location(self, distributor: DimDistributor, prefix: str) -> DistributorLocation:
        row = DistributorLocation(
            distributor_id=distributor.id,
            location_code=self.code(prefix)[:64],
            location_name=self.code(prefix),
            location_type="warehouse",
        )
        self.db.add(row)
        self.db.flush()
        return row

    def sell(
        self,
        customer: DimCustomer,
        product: DimProduct,
        start: date,
        units: float,
        *,
        soh: float | None = None,
        site: str | None = None,
    ) -> None:
        self._n += 1
        self.db.add(
            FactCustomerSellthrough(
                source_key=f"sdc-{self.token}-{self._n}",
                tenant_id=self.tenant,
                customer_id=customer.id,
                product_id=product.id,
                period_start_date=start,
                period_type="weekly",
                period_grain="week",
                units_sold=units,
                reported_soh=soh,
                site_label=site,
            )
        )

    def weeks(
        self,
        customer: DimCustomer,
        product: DimProduct,
        units: list[float],
        *,
        soh: float | None = None,
        site: str | None = None,
    ) -> None:
        for index, qty in enumerate(units):
            self.sell(customer, product, WEEK0 + timedelta(weeks=index), qty, soh=soh if index == len(units) - 1 else None, site=site)

    def shipment(
        self,
        *,
        customer: DimCustomer,
        distributor: DimDistributor,
        ship_to: str,
        confirm: date | None = None,
        pod: date | None = None,
        line_state: str = "open",
    ) -> None:
        self._n += 1
        key = f"sdc-ship-{self.token}-{self._n}"
        self.db.add(
            FactInboundShipment(
                tenant_id=self.tenant,
                source_key=key,
                fact_upsert_key=key,
                source_row_number=self._n,
                report_type="order",
                line_state=line_state,
                raw_source_row={},
                ship_to_raw=ship_to,
                product_resolution_status="unresolved",
                distributor_resolution_status="resolved",
                distributor_id=distributor.id,
                customer_id=customer.id,
                resolved_customer_id=customer.id,
                ship_confirm_date=confirm,
                pod_date=pod,
                status="scheduled",
            )
        )

    def deliveries(self, customer: DimCustomer, distributor: DimDistributor, ship_to: str, count: int, days: int = 14) -> None:
        base = date(2026, 3, 1)
        for index in range(count):
            confirm = base + timedelta(days=index)
            self.shipment(customer=customer, distributor=distributor, ship_to=ship_to, confirm=confirm, pod=confirm + timedelta(days=days))

    def counts(self) -> tuple[int, int, int]:
        promotions = self.db.execute(select(func.count()).select_from(FactPromotionPlan)).scalar_one()
        cases = self.db.execute(select(func.count()).select_from(CporCase)).scalar_one()
        locations = self.db.execute(select(func.count()).select_from(CustomerLocation)).scalar_one()
        return int(promotions), int(cases), int(locations)


@pytest.fixture
def world(session: Session) -> World:
    return World(session)
