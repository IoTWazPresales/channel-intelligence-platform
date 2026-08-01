"""Add cpor_case.needs_reapproval for money-ceiling hard reapproval.

Revision ID: 20260801_0002
Revises: 20260801_0001
Create Date: 2026-08-01
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260801_0002"
down_revision: Union[str, Sequence[str], None] = "20260801_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cpor_case",
        sa.Column("needs_reapproval", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("cpor_case", "needs_reapproval")
