"""Per-customer replenishment weeks of cover on the sell-through report config.

Revision ID: 20261019_0045
Revises: 20261019_0044
Create Date: 2026-10-19

Warren 2026-10-19: the weeks of cover at which a customer's SKU needs replenishing is set per
customer. ``replen_min_weeks_of_cover`` flags the SKU; ``replen_target_weeks_of_cover`` is the cover a
suggested order brings it back up to. Both nullable: empty means the application default (4 and 6).

Additive: two nullable columns on ``customer_report_config``; no existing row changes. Needs the
table owner (on cip: ``postgres``), so run it with DATABASE_URL_SYNC_MIGRATE set to the owner.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20261019_0045"
down_revision: Union[str, Sequence[str], None] = "20261019_0044"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "customer_report_config"
COLUMNS = (
    ("replen_min_weeks_of_cover", "numeric(6,2)"),
    ("replen_target_weeks_of_cover", "numeric(6,2)"),
)


def upgrade() -> None:
    for name, kind in COLUMNS:
        op.execute(f"ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS {name} {kind}")


def downgrade() -> None:
    for name, _kind in reversed(COLUMNS):
        op.execute(f"ALTER TABLE {TABLE} DROP COLUMN IF EXISTS {name}")
