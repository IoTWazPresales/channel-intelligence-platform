"""Add cpor_case.needs_reapproval for money-ceiling hard reapproval.

Revision ID: 20260801_0002
Revises: 20260801_0001
Create Date: 2026-08-01

Idempotent: tip-ORM ``20260801_0001`` create_all may already have the column.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "20260801_0002"
down_revision: Union[str, Sequence[str], None] = "20260801_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in inspect(bind).get_columns("cpor_case")}
    if "needs_reapproval" in cols:
        return
    op.add_column(
        "cpor_case",
        sa.Column("needs_reapproval", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in inspect(bind).get_columns("cpor_case")}
    if "needs_reapproval" not in cols:
        return
    op.drop_column("cpor_case", "needs_reapproval")
