"""NS-1b — cpor_case.fx_mode + FX declaration audit columns.

Revision ID: 20260902_0020
Revises: 20260818_0019
Create Date: 2026-09-02

Additive only: nullable columns on cpor_case. No data loss. Reversible downgrade drops columns.

Idempotent: ``20260801_0001`` create_all already has these columns on a fresh database.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20260902_0020"
down_revision: Union[str, Sequence[str], None] = "20260818_0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE cpor_case ADD COLUMN IF NOT EXISTS fx_mode VARCHAR(16)")
    op.execute("ALTER TABLE cpor_case ADD COLUMN IF NOT EXISTS fx_declared_at TIMESTAMP WITH TIME ZONE")
    op.execute("ALTER TABLE cpor_case ADD COLUMN IF NOT EXISTS fx_declared_by VARCHAR(128)")
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'ck_cpor_case_fx_mode'
              AND conrelid = 'public.cpor_case'::regclass
          ) THEN
            ALTER TABLE cpor_case
              ADD CONSTRAINT ck_cpor_case_fx_mode
              CHECK (fx_mode IS NULL OR fx_mode IN ('booked', 'floating'));
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE cpor_case DROP CONSTRAINT IF EXISTS ck_cpor_case_fx_mode")
    op.execute("ALTER TABLE cpor_case DROP COLUMN IF EXISTS fx_declared_by")
    op.execute("ALTER TABLE cpor_case DROP COLUMN IF EXISTS fx_declared_at")
    op.execute("ALTER TABLE cpor_case DROP COLUMN IF EXISTS fx_mode")
