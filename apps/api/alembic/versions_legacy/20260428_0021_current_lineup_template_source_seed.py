"""Idempotent seed: current_lineup import template + current_lineup_system source.

Revision ID: 20260428_0021
Revises: 20260427_0020
Create Date: 2026-04-28

Fixes existing databases that have commercial_lineup_case tables but never received
current_lineup_system via an earlier DEFAULT_SOURCES iteration (migration 20260426_0013
only runs once per environment).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.services.commercial_planner.current_lineup_seed import ensure_current_lineup_import_seed_sync

revision: str = "20260428_0021"
down_revision: Union[str, Sequence[str], None] = "20260427_0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    ensure_current_lineup_import_seed_sync(conn)


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM source_definition WHERE code = 'current_lineup_system'"))
