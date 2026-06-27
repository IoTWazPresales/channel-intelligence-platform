"""dim_customer.merged_into_customer_id — soft redirect after alias-scope merge.

Revision ID: 20260626_0051
Revises: 20260623_0050
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260626_0051"
down_revision: Union[str, Sequence[str], None] = "20260623_0050"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "dim_customer",
        sa.Column("merged_into_customer_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_dim_customer_merged_into_customer_id",
        "dim_customer",
        "dim_customer",
        ["merged_into_customer_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_dim_customer_merged_into_customer_id",
        "dim_customer",
        ["merged_into_customer_id"],
        unique=False,
        postgresql_where=sa.text("merged_into_customer_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_dim_customer_merged_into_customer_id",
        table_name="dim_customer",
        postgresql_where=sa.text("merged_into_customer_id IS NOT NULL"),
    )
    op.drop_constraint("fk_dim_customer_merged_into_customer_id", "dim_customer", type_="foreignkey")
    op.drop_column("dim_customer", "merged_into_customer_id")
