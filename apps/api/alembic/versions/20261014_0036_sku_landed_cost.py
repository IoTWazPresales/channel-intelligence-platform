"""Add an optional landed cost per SKU beside PM controlled cost.

Revision ID: 20261014_0036
Revises: 20261012_0035
Create Date: 2026-10-14

N-0080: the headline margin is measured against PM controlled cost. Landed cost is a
separate figure shown beside it and never folded into the margin. Same currency as
controlled_cost_currency_code. Null means not recorded. Additive; existing rows unchanged.

Idempotent: ``20260801_0001`` create_all already has the column.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20261014_0036"
down_revision: Union[str, Sequence[str], None] = "20261012_0035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE commercial_sku_assumption ADD COLUMN IF NOT EXISTS landed_cost_amount NUMERIC(18, 4)"
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'ck_commercial_sku_assumption_landed_cost_positive'
              AND conrelid = 'public.commercial_sku_assumption'::regclass
          ) THEN
            ALTER TABLE commercial_sku_assumption
              ADD CONSTRAINT ck_commercial_sku_assumption_landed_cost_positive
              CHECK (landed_cost_amount IS NULL OR landed_cost_amount > 0);
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE commercial_sku_assumption DROP CONSTRAINT IF EXISTS ck_commercial_sku_assumption_landed_cost_positive"
    )
    op.execute("ALTER TABLE commercial_sku_assumption DROP COLUMN IF EXISTS landed_cost_amount")
