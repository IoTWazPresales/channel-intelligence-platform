"""Schema baseline squash — tip ORM create_all + view + system reference.

Revision ID: 20260801_0001
Revises:
Create Date: 2026-08-01

Replaces the pre-squash chain (archived under ``alembic/versions_legacy/``).
Fresh databases: ``alembic upgrade head`` alone — no ``stamp head``.

Existing ``cip`` already at tip schema: create ``fact_demand_forecast`` if missing,
migrate any ``fact_forecast`` rows, then ``alembic stamp 20260801_0001`` (do not
re-run create_all on a populated DB).
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text
from sqlalchemy.dialects import postgresql

from app.db.base import Base
from app.services.commercial_planner.reference_bootstrap import (
    ensure_commercial_planner_system_reference_data_sync,
)
from app.services.commercial_planner.open_channel_customer import OPEN_CHANNEL_CUSTOMER_CODE
from app.services.commercial_planner.unassigned_distributor import UNASSIGNED_DISTRIBUTOR_CODE

revision: str = "20260801_0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CURRENT_VIEW_SQL = """
CREATE VIEW shipment_evidence_current AS
SELECT DISTINCT ON (o.line_identity_key)
    o.id,
    o.line_identity_key,
    o.import_job_id,
    o.source_key,
    o.source_row_hash,
    o.evidence_line_id,
    o.valid_from,
    o.observed_at,
    o.superseded_by_id,
    o.source_sheet,
    o.source_row_number,
    o.report_type,
    o.line_state,
    o.raw_source_row,
    o.operating_unit,
    o.bill_to_raw,
    o.ship_to_raw,
    o.order_no,
    o.customer_po,
    COALESCE(sel.purchase_order_id, o.purchase_order_id) AS purchase_order_id,
    o.order_line,
    o.delivery_no,
    o.invoice_line,
    o.item_code,
    o.sales_model_name,
    o.customer_item,
    o.ean_code,
    o.upc_code,
    o.mpor_item_no,
    o.quantity,
    o.unit_price,
    o.amount,
    o.currency_code,
    o.ship_confirm_date,
    o.schedule_ship_date,
    o.promise_date,
    o.exwork_date,
    o.erd_date,
    o.est_pod_date,
    o.pod_date,
    COALESCE(sel.product_id, o.product_id) AS product_id,
    COALESCE(sel.product_resolution_status, o.product_resolution_status) AS product_resolution_status,
    COALESCE(sel.product_resolution_token, o.product_resolution_token) AS product_resolution_token,
    COALESCE(sel.product_resolution_detail, o.product_resolution_detail) AS product_resolution_detail,
    COALESCE(sel.distributor_id, o.distributor_id) AS distributor_id,
    COALESCE(sel.distributor_resolution_status, o.distributor_resolution_status) AS distributor_resolution_status,
    COALESCE(sel.distributor_resolution_token, o.distributor_resolution_token) AS distributor_resolution_token,
    o.customer_dealer_token,
    COALESCE(sel.resolved_customer_id, sel.customer_id, o.customer_id) AS customer_id,
    COALESCE(sel.customer_resolution_status, o.customer_resolution_status) AS customer_resolution_status,
    sel.resolved_customer_id,
    sel.resolved_distributor_id,
    sel.crad_date,
    o.created_at,
    o.updated_at
FROM shipment_evidence_observation o
LEFT JOIN shipment_evidence_line sel ON sel.id = o.evidence_line_id
ORDER BY o.line_identity_key, o.valid_from DESC NULLS LAST, o.id DESC
"""


def _register_all_models() -> None:
    import app.models as models_pkg

    pkg_path = Path(models_pkg.__file__).parent
    for info in pkgutil.iter_modules([str(pkg_path)]):
        if info.name.startswith("_"):
            continue
        importlib.import_module(f"app.models.{info.name}")


def _table_objects_excluding_views():
    return [t for t in Base.metadata.sorted_tables if not t.info.get("is_view")]


def upgrade() -> None:
    _register_all_models()
    bind = op.get_bind()
    insp = inspect(bind)
    existing = set(insp.get_table_names()) | set(insp.get_view_names())

    if "dim_product" not in existing:
        # Empty / fresh database — full schema from tip ORM.
        Base.metadata.create_all(bind=bind, tables=_table_objects_excluding_views())
        op.execute(sa.text("DROP VIEW IF EXISTS shipment_evidence_current"))
        op.execute(sa.text(_CURRENT_VIEW_SQL))
        # App role grants (local often connects as cip; create_all runs as migrate user).
        op.execute(
            sa.text(
                """
                DO $$
                BEGIN
                  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cip') THEN
                    EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO cip';
                    EXECUTE 'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO cip';
                    EXECUTE 'GRANT SELECT ON shipment_evidence_current TO cip';
                  END IF;
                END $$;
                """
            )
        )
        ensure_commercial_planner_system_reference_data_sync(bind)
        return

    # Populated DB (e.g. cip stamp path): additive only — demand-forecast contract.
    if "fact_demand_forecast" not in existing:
        op.create_table(
            "fact_demand_forecast",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.Text(), nullable=True),
            sa.Column("distributor_id", sa.Integer(), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("customer_id", sa.Integer(), nullable=False),
            sa.Column("period_start", sa.Date(), nullable=False),
            sa.Column("forecast_units", sa.Numeric(18, 4), nullable=False),
            sa.Column("lower_band", sa.Numeric(18, 4), nullable=True),
            sa.Column("upper_band", sa.Numeric(18, 4), nullable=True),
            sa.Column("method", sa.String(length=32), nullable=False),
            sa.Column("confidence_level", sa.String(length=16), nullable=False),
            sa.Column("velocity_basis", sa.String(length=64), nullable=True),
            sa.Column("seasonal_index", sa.Numeric(18, 6), nullable=True),
            sa.Column("analogue_product_id", sa.Integer(), nullable=True),
            sa.Column("analogue_basis", postgresql.JSONB(), nullable=True),
            sa.Column("is_override", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("source_key", sa.String(length=256), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=True,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=True,
            ),
            sa.ForeignKeyConstraint(["analogue_product_id"], ["dim_product.id"]),
            sa.ForeignKeyConstraint(["customer_id"], ["dim_customer.id"]),
            sa.ForeignKeyConstraint(["distributor_id"], ["dim_distributor.id"]),
            sa.ForeignKeyConstraint(["product_id"], ["dim_product.id"]),
            sa.PrimaryKeyConstraint("id", name="pk_fact_demand_forecast"),
            sa.UniqueConstraint(
                "distributor_id",
                "product_id",
                "customer_id",
                "period_start",
                name="uq_fact_demand_forecast_grain",
            ),
            sa.UniqueConstraint("source_key", name="uq_fact_demand_forecast_source_key"),
        )
        op.create_index("ix_fact_demand_forecast_tenant", "fact_demand_forecast", ["tenant_id"])
        op.create_index("ix_fact_demand_forecast_period", "fact_demand_forecast", ["period_start"])
        op.create_index(
            "ix_fact_demand_forecast_dist_prod",
            "fact_demand_forecast",
            ["distributor_id", "product_id"],
        )
        op.execute(
            sa.text(
                """
                DO $$
                BEGIN
                  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cip') THEN
                    EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON fact_demand_forecast TO cip';
                    EXECUTE 'GRANT USAGE, SELECT ON SEQUENCE fact_demand_forecast_id_seq TO cip';
                  END IF;
                END $$;
                """
            )
        )

    ensure_commercial_planner_system_reference_data_sync(bind)

    # Migrate legacy manual forecast rows (idempotent).
    bind.execute(
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
        {"unassigned": UNASSIGNED_DISTRIBUTOR_CODE, "open_channel": OPEN_CHANNEL_CUSTOMER_CODE},
    )


def downgrade() -> None:
    """Baseline downgrade drops the demand-forecast contract only when safe.

    Full schema teardown on a populated database is intentionally unsupported.
    """
    bind = op.get_bind()
    insp = inspect(bind)
    if "fact_demand_forecast" in insp.get_table_names():
        op.drop_table("fact_demand_forecast")
