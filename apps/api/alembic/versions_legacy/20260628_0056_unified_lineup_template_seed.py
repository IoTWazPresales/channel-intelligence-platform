"""Idempotent seed: unified_lineup import template + unified_lineup_system source.

Revision ID: 20260628_0056
Revises: 20260628_0055
Create Date: 2026-06-28

First-class unified multi-file lineup importer (Import-Centre surface). Mirrors the
current_lineup seed pattern; idempotent so re-runs / fresh checkouts converge.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.services.commercial_planner.current_lineup_seed import ensure_lineup_import_seed_sync

revision: str = "20260628_0056"
down_revision: Union[str, Sequence[str], None] = "20260628_0055"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    ensure_lineup_import_seed_sync(
        conn, template_slug="unified_lineup", source_code="unified_lineup_system"
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM source_definition WHERE code = 'unified_lineup_system'"))
    conn.execute(sa.text("DELETE FROM import_template WHERE slug = 'unified_lineup'"))
