"""Add tenant_id isolation columns to core facts/dims (P2-3).

Revision ID: 20260801_0005
Revises: 20260801_0004
Create Date: 2026-08-01

Backfills existing rows to tenant 'default'. New inserts inherit DEFAULT.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260801_0005"
down_revision: Union[str, Sequence[str], None] = "20260801_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Commercial truth + identity anchors that must not leak across tenants.
_TABLES: tuple[str, ...] = (
    "fact_sales_sellout",
    "fact_inbound_shipment",
    "fact_inventory_distributor",
    "fact_inventory_customer",
    "fact_customer_sellthrough",
    "fact_demand_forecast",
    "cpor_case",
    "import_job",
    "dim_product",
    "dim_customer",
    "dim_distributor",
)


def _add_tenant_id(table: str) -> None:
    op.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = '{table}' AND column_name = 'tenant_id'
              ) THEN
                ALTER TABLE {table}
                  ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'default';
              ELSE
                UPDATE {table} SET tenant_id = 'default' WHERE tenant_id IS NULL OR btrim(tenant_id) = '';
                ALTER TABLE {table} ALTER COLUMN tenant_id SET DEFAULT 'default';
                ALTER TABLE {table} ALTER COLUMN tenant_id SET NOT NULL;
              END IF;
            END $$;
            """
        )
    )
    op.execute(sa.text(f"CREATE INDEX IF NOT EXISTS ix_{table}_tenant_id ON {table} (tenant_id)"))


def upgrade() -> None:
    for table in _TABLES:
        _add_tenant_id(table)


def downgrade() -> None:
    # Keep columns on downgrade — dropping tenant_id from large facts is destructive.
    # Explicit no-op; recreate only via forward repair if needed.
    pass
