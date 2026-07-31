"""Refresh distributor_inventory expected_columns (D-022 / BACKLOG-082 header policy).

Revision ID: 20260730_0075
Revises: 20260727_0074
Create Date: 2026-07-30

Does NOT auto-apply. Warren must approve `alembic upgrade` after verifying
`SELECT current_database() = 'cip'`.
"""

from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.services.imports.template_definitions import IMPORT_TEMPLATE_ROWS

revision: str = "20260730_0075"
down_revision: Union[str, Sequence[str], None] = "20260727_0074"
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
