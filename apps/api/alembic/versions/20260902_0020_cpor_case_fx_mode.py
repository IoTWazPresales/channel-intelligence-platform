"""NS-1b — cpor_case.fx_mode + FX declaration audit columns.

Revision ID: 20260902_0020
Revises: 20260818_0019
Create Date: 2026-09-02

Additive only: nullable columns on cpor_case. No data loss. Reversible downgrade drops columns.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260902_0020"
down_revision: Union[str, Sequence[str], None] = "20260818_0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cpor_case",
        sa.Column("fx_mode", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "cpor_case",
        sa.Column(
            "fx_declared_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "cpor_case",
        sa.Column("fx_declared_by", sa.String(length=128), nullable=True),
    )
    op.create_check_constraint(
        "ck_cpor_case_fx_mode",
        "cpor_case",
        "fx_mode IS NULL OR fx_mode IN ('booked', 'floating')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_cpor_case_fx_mode", "cpor_case", type_="check")
    op.drop_column("cpor_case", "fx_declared_by")
    op.drop_column("cpor_case", "fx_declared_at")
    op.drop_column("cpor_case", "fx_mode")
