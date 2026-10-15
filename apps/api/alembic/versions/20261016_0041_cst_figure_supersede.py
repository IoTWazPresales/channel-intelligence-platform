"""Customer sell-through: supersede each figure on its own; name weeks with no on-hand.

Revision ID: 20261016_0041
Revises: 20261015_0040
Create Date: 2026-10-16

N-0111 (Warren 2026-10-16). A newer load replaces only the figures it carries: units sold,
on-hand, in-transit and on-order are superseded independently, so a stock-only file never
wipes sales and a sales-only file never wipes stock.

- ``fact_customer_sellthrough.figure_import_jobs``: which load set each figure
  (``{"units_sold": 12, "reported_soh": 15}``). Empty on existing rows; the code reads an
  empty map as "every figure the row holds came from ``import_job_id``", so no row is rewritten.
- ``fact_customer_sellthrough_superseded.figures``: the figures a superseded record gave up.
  NULL on existing records (the whole row was superseded).
- ``customer_stock_position.reported_on_hand`` becomes nullable and the status check takes
  ``no_on_hand`` (a week with no reported on-hand, stored as its own row so the gap tab can
  name it) and ``chain_restart`` (the report the stock chain restarts at).

Additive; existing rows unchanged.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20261016_0041"
down_revision: Union[str, Sequence[str], None] = "20261015_0040"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE fact_customer_sellthrough "
        "ADD COLUMN IF NOT EXISTS figure_import_jobs jsonb NOT NULL DEFAULT '{}'::jsonb"
    )
    op.execute("ALTER TABLE fact_customer_sellthrough_superseded ADD COLUMN IF NOT EXISTS figures text[]")
    op.execute("ALTER TABLE customer_stock_position ALTER COLUMN reported_on_hand DROP NOT NULL")
    op.execute("ALTER TABLE customer_stock_position DROP CONSTRAINT IF EXISTS ck_customer_stock_position_status")
    op.execute(
        "ALTER TABLE customer_stock_position ADD CONSTRAINT ck_customer_stock_position_status "
        "CHECK (status IN ('compared', 'first_report', 'no_on_hand', 'chain_restart'))"
    )


def downgrade() -> None:
    # Positions are derived and rebuilt by Recompute. The N-0111 statuses are removed before the
    # older status check and the required on-hand come back.
    op.execute("DELETE FROM customer_stock_position WHERE status IN ('no_on_hand', 'chain_restart')")
    op.execute("ALTER TABLE customer_stock_position DROP CONSTRAINT IF EXISTS ck_customer_stock_position_status")
    op.execute(
        "ALTER TABLE customer_stock_position ADD CONSTRAINT ck_customer_stock_position_status "
        "CHECK (status IN ('compared', 'first_report'))"
    )
    op.execute("ALTER TABLE customer_stock_position ALTER COLUMN reported_on_hand SET NOT NULL")
    op.execute("ALTER TABLE fact_customer_sellthrough_superseded DROP COLUMN IF EXISTS figures")
    op.execute("ALTER TABLE fact_customer_sellthrough DROP COLUMN IF EXISTS figure_import_jobs")
