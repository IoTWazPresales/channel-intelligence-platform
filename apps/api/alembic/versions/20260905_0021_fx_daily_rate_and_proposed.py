"""Booked FX rate model — daily rate table + proposed-rate columns on cpor_case.

Revision ID: 20260905_0021
Revises: 20260902_0020
Create Date: 2026-09-05

Additive only. Does not rewrite roe_snapshot (booked/declared case rate).
Reversible downgrade drops the new table and columns.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260905_0021"
down_revision: Union[str, Sequence[str], None] = "20260902_0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fx_daily_rate",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("rate_date", sa.Date(), nullable=False),
        sa.Column(
            "quote_pair",
            sa.String(length=16),
            nullable=False,
            server_default="USDZAR",
        ),
        sa.Column("rate", sa.Numeric(18, 6), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_fallback", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_fx_daily_rate_rate_date", "fx_daily_rate", ["rate_date"])
    op.create_unique_constraint(
        "uq_fx_daily_rate_date_quote",
        "fx_daily_rate",
        ["rate_date", "quote_pair"],
    )

    op.add_column(
        "cpor_case",
        sa.Column("fx_proposed_rate", sa.Numeric(18, 6), nullable=True),
    )
    op.add_column(
        "cpor_case",
        sa.Column("fx_proposed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "cpor_case",
        sa.Column("fx_proposed_by", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "cpor_case",
        sa.Column("fx_proposed_source", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("cpor_case", "fx_proposed_source")
    op.drop_column("cpor_case", "fx_proposed_by")
    op.drop_column("cpor_case", "fx_proposed_at")
    op.drop_column("cpor_case", "fx_proposed_rate")
    op.drop_constraint("uq_fx_daily_rate_date_quote", "fx_daily_rate", type_="unique")
    op.drop_index("ix_fx_daily_rate_rate_date", table_name="fx_daily_rate")
    op.drop_table("fx_daily_rate")
