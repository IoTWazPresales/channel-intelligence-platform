"""Add an optional landed cost per SKU beside PM controlled cost.

Revision ID: 20261014_0036
Revises: 20261012_0035
Create Date: 2026-10-14

N-0080: the headline margin is measured against PM controlled cost. Landed cost is a
separate figure shown beside it and never folded into the margin. Same currency as
controlled_cost_currency_code. Null means not recorded. Additive; existing rows unchanged.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261014_0036"
down_revision: Union[str, Sequence[str], None] = "20261012_0035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "commercial_sku_assumption",
        sa.Column("landed_cost_amount", sa.Numeric(18, 4), nullable=True),
    )
    op.create_check_constraint(
        "ck_commercial_sku_assumption_landed_cost_positive",
        "commercial_sku_assumption",
        "landed_cost_amount IS NULL OR landed_cost_amount > 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_commercial_sku_assumption_landed_cost_positive",
        "commercial_sku_assumption",
        type_="check",
    )
    op.drop_column("commercial_sku_assumption", "landed_cost_amount")
