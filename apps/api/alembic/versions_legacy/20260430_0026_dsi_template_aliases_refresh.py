"""Refresh distributor_inventory expected_columns (DSI header aliases).

Revision ID: 20260430_0026
Revises: 20260430_0025
Create Date: 2026-04-30
"""

from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.services.imports.template_definitions import IMPORT_TEMPLATE_ROWS

revision: str = "20260430_0026"
down_revision: Union[str, Sequence[str], None] = "20260430_0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    row = next(t for t in IMPORT_TEMPLATE_ROWS if t["slug"] == "distributor_inventory")
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE import_template
            SET expected_columns = CAST(:expected_columns AS jsonb),
                updated_at = now()
            WHERE slug = 'distributor_inventory'
            """
        ),
        {"expected_columns": json.dumps(row["expected_columns"])},
    )


def downgrade() -> None:
    pass
