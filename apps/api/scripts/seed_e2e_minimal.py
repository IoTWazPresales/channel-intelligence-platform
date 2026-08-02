"""Idempotent minimal seed for live Playwright e2e (BACKLOG-099).

Creates SKU-ALPHA-01 plus one sell-out fact so product delete shows
"Still referenced in: … Sell-out". Safe to re-run. Does not wipe.

Intended DB: disposable ``cip_e2e`` in CI — never ``cip``.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from sqlalchemy import select, text

from app.db.session_sync import SessionLocal
from app.models.dimensions import DimChannel, DimCustomer, DimDistributor, DimProduct
from app.models.facts import FactSalesSellout
from app.services.commercial_planner.open_channel_customer import OPEN_CHANNEL_CUSTOMER_CODE
from app.services.commercial_planner.unassigned_distributor import UNASSIGNED_DISTRIBUTOR_CODE

E2E_SKU = "SKU-ALPHA-01"
E2E_SELLOUT_KEY = "e2e-minimal-sellout-sku-alpha-01"


def main() -> None:
    with SessionLocal() as session:
        db = session.execute(text("SELECT current_database()")).scalar()
        if db == "cip":
            raise SystemExit(
                f"Refusing to seed e2e fixtures on database {db!r}. "
                "Point DATABASE_URL_SYNC at cip_e2e (or another disposable DB)."
            )

        channel = session.execute(select(DimChannel).where(DimChannel.code == "RET")).scalar_one_or_none()
        if channel is None:
            channel = DimChannel(code="RET", name="Retail")
            session.add(channel)
            session.flush()

        customer = session.execute(
            select(DimCustomer).where(DimCustomer.code == OPEN_CHANNEL_CUSTOMER_CODE)
        ).scalar_one_or_none()
        if customer is None:
            raise SystemExit(
                f"Missing dim_customer {OPEN_CHANNEL_CUSTOMER_CODE!r} — run alembic upgrade head first."
            )

        distributor = session.execute(
            select(DimDistributor).where(DimDistributor.code == UNASSIGNED_DISTRIBUTOR_CODE)
        ).scalar_one_or_none()
        if distributor is None:
            raise SystemExit(
                f"Missing dim_distributor {UNASSIGNED_DISTRIBUTOR_CODE!r} — run alembic upgrade head first."
            )

        product = session.execute(select(DimProduct).where(DimProduct.sku == E2E_SKU)).scalar_one_or_none()
        if product is None:
            product = DimProduct(
                sku=E2E_SKU,
                name="Alpha Pro 200 (e2e)",
                category="Audio",
                tenant_id="default",
            )
            session.add(product)
            session.flush()

        sellout = session.execute(
            select(FactSalesSellout).where(FactSalesSellout.source_key == E2E_SELLOUT_KEY)
        ).scalar_one_or_none()
        if sellout is None:
            today = date.today()
            session.add(
                FactSalesSellout(
                    source_key=E2E_SELLOUT_KEY,
                    product_id=product.id,
                    customer_id=customer.id,
                    channel_id=channel.id,
                    distributor_id=distributor.id,
                    period_start=today - timedelta(days=7),
                    transaction_date=today - timedelta(days=7),
                    units=10,
                    revenue=1000,
                    tenant_id="default",
                )
            )

        session.commit()
        print(f"e2e minimal seed OK on database={db} sku={E2E_SKU}")


if __name__ == "__main__":
    main()
