"""Apply B1-01 squash on cip: create fact_demand_forecast + stamp baseline.

Requires CIP_APPLY_B1_01=1. Verifies current_database()=cip.
"""

from __future__ import annotations

import os

from sqlalchemy import create_engine, text

from app.core.config import get_settings
from app.db.sync_url import sqlalchemy_sync_engine_url
from app.services.commercial_planner.open_channel_customer import OPEN_CHANNEL_CUSTOMER_CODE
from app.services.commercial_planner.reference_bootstrap import (
    ensure_commercial_planner_system_reference_data_sync,
)
from app.services.commercial_planner.unassigned_distributor import UNASSIGNED_DISTRIBUTOR_CODE

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS fact_demand_forecast (
    id SERIAL NOT NULL,
    tenant_id TEXT,
    distributor_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    customer_id INTEGER NOT NULL,
    period_start DATE NOT NULL,
    forecast_units NUMERIC(18, 4) NOT NULL,
    lower_band NUMERIC(18, 4),
    upper_band NUMERIC(18, 4),
    method VARCHAR(32) NOT NULL,
    confidence_level VARCHAR(16) NOT NULL,
    velocity_basis VARCHAR(64),
    seasonal_index NUMERIC(18, 6),
    analogue_product_id INTEGER,
    analogue_basis JSONB,
    is_override BOOLEAN NOT NULL DEFAULT false,
    source_key VARCHAR(256),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT pk_fact_demand_forecast PRIMARY KEY (id),
    CONSTRAINT uq_fact_demand_forecast_grain UNIQUE (
        distributor_id, product_id, customer_id, period_start
    ),
    CONSTRAINT uq_fact_demand_forecast_source_key UNIQUE (source_key),
    CONSTRAINT fk_fact_demand_forecast_distributor_id_dim_distributor
        FOREIGN KEY (distributor_id) REFERENCES dim_distributor (id),
    CONSTRAINT fk_fact_demand_forecast_product_id_dim_product
        FOREIGN KEY (product_id) REFERENCES dim_product (id),
    CONSTRAINT fk_fact_demand_forecast_customer_id_dim_customer
        FOREIGN KEY (customer_id) REFERENCES dim_customer (id),
    CONSTRAINT fk_fact_demand_forecast_analogue_product_id_dim_product
        FOREIGN KEY (analogue_product_id) REFERENCES dim_product (id)
)
"""


def main() -> None:
    if os.environ.get("CIP_APPLY_B1_01") != "1":
        raise SystemExit("Refusing: set CIP_APPLY_B1_01=1 to apply on cip")

    settings = get_settings()
    url = sqlalchemy_sync_engine_url(
        settings.database_url_sync_migrate or settings.database_url_sync
    )
    eng = create_engine(url)
    with eng.begin() as conn:
        db = conn.execute(text("SELECT current_database()")).scalar()
        tip = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        print(f"before: database={db} alembic={tip}")
        if db != "cip":
            raise SystemExit(f"Refusing: database is {db!r}, expected cip")

        conn.execute(text(_CREATE_SQL))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_fact_demand_forecast_tenant ON fact_demand_forecast (tenant_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_fact_demand_forecast_period ON fact_demand_forecast (period_start)"))
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_fact_demand_forecast_dist_prod "
                "ON fact_demand_forecast (distributor_id, product_id)"
            )
        )
        conn.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON fact_demand_forecast TO cip"))
        conn.execute(text("GRANT USAGE, SELECT ON SEQUENCE fact_demand_forecast_id_seq TO cip"))
        ensure_commercial_planner_system_reference_data_sync(conn)
        conn.execute(
            text(
                """
                INSERT INTO fact_demand_forecast (
                    tenant_id, distributor_id, product_id, customer_id, period_start,
                    forecast_units, lower_band, upper_band, method, confidence_level,
                    is_override, created_at, updated_at
                )
                SELECT
                    NULL,
                    d.id,
                    f.product_id,
                    COALESCE(f.customer_id, c.id),
                    f.period_start,
                    f.forecast_units,
                    CASE WHEN f.is_override THEN f.forecast_units ELSE NULL END,
                    CASE WHEN f.is_override THEN f.forecast_units ELSE NULL END,
                    'manual',
                    CASE WHEN f.is_override THEN 'override' ELSE 'medium' END,
                    COALESCE(f.is_override, FALSE),
                    COALESCE(f.created_at, NOW()),
                    COALESCE(f.updated_at, NOW())
                FROM fact_forecast f
                CROSS JOIN LATERAL (
                    SELECT id FROM dim_distributor WHERE code = :unassigned LIMIT 1
                ) d
                CROSS JOIN LATERAL (
                    SELECT id FROM dim_customer WHERE code = :open_channel LIMIT 1
                ) c
                WHERE NOT EXISTS (
                    SELECT 1 FROM fact_demand_forecast x
                    WHERE x.distributor_id = d.id
                      AND x.product_id = f.product_id
                      AND x.customer_id = COALESCE(f.customer_id, c.id)
                      AND x.period_start = f.period_start
                )
                """
            ),
            {
                "unassigned": UNASSIGNED_DISTRIBUTOR_CODE,
                "open_channel": OPEN_CHANNEL_CUSTOMER_CODE,
            },
        )
        conn.execute(text("DELETE FROM alembic_version"))
        conn.execute(
            text("INSERT INTO alembic_version (version_num) VALUES ('20260801_0001')")
        )
        tip2 = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        has = conn.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_name='fact_demand_forecast'"
            )
        ).scalar()
        print(f"after: alembic={tip2} fact_demand_forecast={bool(has)}")
        assert tip2 == "20260801_0001"
        assert has
    print("CIP_B1_01_APPLY_OK")


if __name__ == "__main__":
    main()
