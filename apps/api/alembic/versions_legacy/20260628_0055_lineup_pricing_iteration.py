"""commercial lineup: product_line/period/iteration on case; feedback/notes/pricing on line.

Revision ID: 20260628_0055
Revises: 20260628_0054
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20260628_0055"
down_revision: Union[str, Sequence[str], None] = "20260628_0054"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("commercial_lineup_case", sa.Column("product_line", sa.String(length=64), nullable=True))
    op.add_column("commercial_lineup_case", sa.Column("inferred_period_start", sa.Date(), nullable=True))
    op.add_column(
        "commercial_lineup_case",
        sa.Column("iteration_number", sa.Integer(), nullable=False, server_default="1"),
    )

    op.add_column("commercial_lineup_line", sa.Column("customer_feedback", sa.String(length=1024), nullable=True))
    op.add_column("commercial_lineup_line", sa.Column("internal_notes", sa.String(length=1024), nullable=True))
    op.add_column("commercial_lineup_line", sa.Column("pricing_chain_json", JSONB(), nullable=True))
    op.add_column("commercial_lineup_line", sa.Column("calc_dap_cost_currency", sa.Numeric(18, 4), nullable=True))
    op.add_column("commercial_lineup_line", sa.Column("calc_profit_total", sa.Numeric(18, 4), nullable=True))


def downgrade() -> None:
    op.drop_column("commercial_lineup_line", "calc_profit_total")
    op.drop_column("commercial_lineup_line", "calc_dap_cost_currency")
    op.drop_column("commercial_lineup_line", "pricing_chain_json")
    op.drop_column("commercial_lineup_line", "internal_notes")
    op.drop_column("commercial_lineup_line", "customer_feedback")

    op.drop_column("commercial_lineup_case", "iteration_number")
    op.drop_column("commercial_lineup_case", "inferred_period_start")
    op.drop_column("commercial_lineup_case", "product_line")
