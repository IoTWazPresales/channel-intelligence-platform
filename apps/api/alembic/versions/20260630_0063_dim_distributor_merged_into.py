"""dim_distributor.merged_into_distributor_id — soft redirect after full merge.

Revision ID: 20260630_0063
Revises: 20260630_0061
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260630_0063"
down_revision: Union[str, Sequence[str], None] = "20260630_0061"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "dim_distributor",
        sa.Column("distributor_status", sa.String(length=32), server_default="active", nullable=False),
    )
    op.add_column(
        "dim_distributor",
        sa.Column("merged_into_distributor_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_dim_distributor_merged_into_distributor_id",
        "dim_distributor",
        "dim_distributor",
        ["merged_into_distributor_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_dim_distributor_merged_into_distributor_id",
        "dim_distributor",
        ["merged_into_distributor_id"],
        unique=False,
        postgresql_where=sa.text("merged_into_distributor_id IS NOT NULL"),
    )
    op.add_column(
        "dim_distributor",
        sa.Column("merge_note", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("dim_distributor", "merge_note")
    op.drop_index(
        "ix_dim_distributor_merged_into_distributor_id",
        table_name="dim_distributor",
        postgresql_where=sa.text("merged_into_distributor_id IS NOT NULL"),
    )
    op.drop_constraint("fk_dim_distributor_merged_into_distributor_id", "dim_distributor", type_="foreignkey")
    op.drop_column("dim_distributor", "merged_into_distributor_id")
    op.drop_column("dim_distributor", "distributor_status")
