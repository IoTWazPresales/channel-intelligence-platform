"""Drop the old promotion-plan and pricing-recommendation tables.

Revision ID: 20261011_0032
Revises: 20261011_0031
Create Date: 2026-10-11

Live lineup and budget rows stay. Their promotion id columns stay as plain
integers. pricing_unknown_sku and fact_pricing stay.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20261011_0032"
down_revision: Union[str, Sequence[str], None] = "20261011_0031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE r record;
        BEGIN
          FOR r IN
            SELECT src.relname AS table_name, con.conname AS constraint_name
            FROM pg_constraint con
            JOIN pg_class src ON src.oid = con.conrelid
            JOIN pg_class dst ON dst.oid = con.confrelid
            JOIN pg_namespace nsp ON nsp.oid = src.relnamespace
            WHERE con.contype = 'f'
              AND dst.relname = 'dim_promotion'
              AND nsp.nspname = 'public'
              AND src.relname IN ('fact_lineup_plan_item', 'fact_budget_request')
          LOOP
            EXECUTE format('ALTER TABLE %I DROP CONSTRAINT %I', r.table_name, r.constraint_name);
          END LOOP;
        END $$
        """
    )
    op.execute("DROP TABLE IF EXISTS promo_plan_export_event")
    op.execute("DROP TABLE IF EXISTS promo_plan_export")
    op.execute("DROP TABLE IF EXISTS promo_readiness")
    op.execute("DROP TABLE IF EXISTS fact_promotion_performance")
    op.execute("DROP TABLE IF EXISTS fact_promotion_plan")
    op.execute("DROP TABLE IF EXISTS pricing_recommendation")
    op.execute("DROP TABLE IF EXISTS dim_promotion")


def downgrade() -> None:
    raise NotImplementedError("The dropped promotion scaffold is not restored.")
