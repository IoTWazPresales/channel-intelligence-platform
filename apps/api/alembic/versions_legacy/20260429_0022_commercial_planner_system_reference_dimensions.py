"""Ensure OPEN_CHANNEL customer + UNASSIGNED distributor (commercial planner system reference).

Revision ID: 20260429_0022
Revises: 20260428_0021
Create Date: 2026-04-29

Idempotent data migration: controlled dimension rows required by Commercial Planner sync.
Not tied to demo seed; runs on every ``alembic upgrade head`` so fresh databases are usable.
"""

from typing import Sequence, Union

from alembic import op

from app.services.commercial_planner.reference_bootstrap import ensure_commercial_planner_system_reference_data_sync

revision: str = "20260429_0022"
down_revision: Union[str, Sequence[str], None] = "20260428_0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    ensure_commercial_planner_system_reference_data_sync(conn)


def downgrade() -> None:
    """Do not remove controlled rows — other data may reference them."""
    pass
