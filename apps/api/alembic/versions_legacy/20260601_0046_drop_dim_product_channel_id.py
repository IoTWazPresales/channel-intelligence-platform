"""Drop dim_product.channel_id (Option A: channel is not a Product Master attribute).

Channel is a go-to-market dimension of transactions / pricing / lineup / customer, not an
intrinsic product property. It already lives on fact_*, price lists, dim_customer, lineup, and
DSI staging. Per-product channel placement was removed from the Product Master workflow first
(code), and this migration removes the now-unused column. The single product that had a
channel_id was backed up before the drop (scripts/_dim_product_channel_backup.json).

Revision ID: 20260601_0046
Revises: 20260518_0045
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from _alembic_revision_helpers import get_inspector, has_column

revision: str = "20260601_0046"
down_revision: Union[str, Sequence[str], None] = "20260518_0045"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insp = get_inspector(op.get_bind())
    if has_column(insp, "dim_product", "channel_id"):
        # In PostgreSQL, dropping the column also drops the dependent FK constraint + index.
        op.drop_column("dim_product", "channel_id")


def downgrade() -> None:
    insp = get_inspector(op.get_bind())
    if not has_column(insp, "dim_product", "channel_id"):
        op.add_column(
            "dim_product",
            sa.Column("channel_id", sa.Integer(), nullable=True),
        )
        op.create_foreign_key(
            "dim_product_channel_id_fkey",
            "dim_product",
            "dim_channel",
            ["channel_id"],
            ["id"],
        )
