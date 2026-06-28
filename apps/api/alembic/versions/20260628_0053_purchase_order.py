"""purchase_order entity table.

Revision ID: 20260628_0053
Revises: 20260628_0052
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260628_0053"
down_revision: Union[str, Sequence[str], None] = "20260628_0052"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "purchase_order",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("po_number_raw", sa.String(length=128), nullable=False),
        sa.Column("po_number_norm", sa.String(length=128), nullable=False),
        sa.Column("distributor_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="observed", nullable=False),
        sa.Column("dismiss_reason_code", sa.String(length=64), nullable=True),
        sa.Column("source", sa.String(length=64), server_default="shipment_materialized", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["distributor_id"], ["dim_distributor.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("po_number_norm", "distributor_id", name="uq_purchase_order_norm_distributor"),
    )
    op.create_index("ix_purchase_order_po_number_norm", "purchase_order", ["po_number_norm"], unique=False)
    op.create_index(op.f("ix_purchase_order_distributor_id"), "purchase_order", ["distributor_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_purchase_order_distributor_id"), table_name="purchase_order")
    op.drop_index("ix_purchase_order_po_number_norm", table_name="purchase_order")
    op.drop_table("purchase_order")
