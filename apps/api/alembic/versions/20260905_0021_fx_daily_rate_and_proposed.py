"""Booked FX rate model — daily rate table + proposed-rate columns on cpor_case.

Revision ID: 20260905_0021
Revises: 20260902_0020
Create Date: 2026-09-05

Additive only. Does not rewrite roe_snapshot (booked/declared case rate).
Reversible downgrade drops the new table and columns.

Idempotent: ``20260801_0001`` create_all already has the table and columns.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20260905_0021"
down_revision: Union[str, Sequence[str], None] = "20260902_0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Same column types op.create_table emitted (SERIAL id, VARCHAR defaults).
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS fx_daily_rate (
            id SERIAL NOT NULL,
            rate_date DATE NOT NULL,
            quote_pair VARCHAR(16) DEFAULT 'USDZAR' NOT NULL,
            rate NUMERIC(18, 6) NOT NULL,
            source VARCHAR(64) NOT NULL,
            fetched_at TIMESTAMP WITH TIME ZONE NOT NULL,
            is_fallback BOOLEAN DEFAULT false NOT NULL,
            PRIMARY KEY (id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_fx_daily_rate_rate_date ON fx_daily_rate (rate_date)"
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'uq_fx_daily_rate_date_quote'
              AND conrelid = 'public.fx_daily_rate'::regclass
          ) THEN
            ALTER TABLE fx_daily_rate
              ADD CONSTRAINT uq_fx_daily_rate_date_quote UNIQUE (rate_date, quote_pair);
          END IF;
        END $$;
        """
    )
    op.execute("ALTER TABLE cpor_case ADD COLUMN IF NOT EXISTS fx_proposed_rate NUMERIC(18, 6)")
    op.execute("ALTER TABLE cpor_case ADD COLUMN IF NOT EXISTS fx_proposed_at TIMESTAMP WITH TIME ZONE")
    op.execute("ALTER TABLE cpor_case ADD COLUMN IF NOT EXISTS fx_proposed_by VARCHAR(128)")
    op.execute("ALTER TABLE cpor_case ADD COLUMN IF NOT EXISTS fx_proposed_source VARCHAR(64)")


def downgrade() -> None:
    op.execute("ALTER TABLE cpor_case DROP COLUMN IF EXISTS fx_proposed_source")
    op.execute("ALTER TABLE cpor_case DROP COLUMN IF EXISTS fx_proposed_by")
    op.execute("ALTER TABLE cpor_case DROP COLUMN IF EXISTS fx_proposed_at")
    op.execute("ALTER TABLE cpor_case DROP COLUMN IF EXISTS fx_proposed_rate")
    op.execute("ALTER TABLE fx_daily_rate DROP CONSTRAINT IF EXISTS uq_fx_daily_rate_date_quote")
    op.execute("DROP INDEX IF EXISTS ix_fx_daily_rate_rate_date")
    op.execute("DROP TABLE IF EXISTS fx_daily_rate")
