"""BACKLOG-061-U3 — no_code_disposition on dim_customer + dim_distributor (AUTHOR ONLY).

Revision ID: 20260710_0071
Revises: 20260710_0070

Nullable disposition column — NOT a customer_status value (provisional reuse depends on unverified).
Distributor column authored now; wiring is a later unit. Do NOT apply to cip without Warren.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260710_0071"
down_revision: Union[str, Sequence[str], None] = "20260710_0070"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "dim_customer",
        sa.Column("no_code_disposition", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "dim_distributor",
        sa.Column("no_code_disposition", sa.String(length=16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("dim_distributor", "no_code_disposition")
    op.drop_column("dim_customer", "no_code_disposition")
