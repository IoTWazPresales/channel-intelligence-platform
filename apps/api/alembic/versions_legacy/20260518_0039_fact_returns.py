"""DSI returns fact table (negative sell-out quantities routed on apply).

Revision ID: 20260518_0039
Revises: 20260518_0038

``source_key`` grain mirrors sell-out: distributor + product + customer + transaction_date +
invoice_no (empty string when absent). Prefix ``dsi-return:``. On conflict, update
``return_quantity`` and ``unit_price`` only — ``import_job_id`` stays with the first job.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260518_0039"
down_revision: Union[str, Sequence[str], None] = "20260518_0038"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fact_returns",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_key", sa.String(length=256), nullable=False),
        sa.Column("staging_line_id", sa.Integer(), nullable=True),
        sa.Column("distributor_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column(
            "invoice_no",
            sa.String(length=128),
            nullable=False,
            server_default="",
        ),
        sa.Column("return_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("import_job_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["customer_id"], ["dim_customer.id"]),
        sa.ForeignKeyConstraint(["distributor_id"], ["dim_distributor.id"]),
        sa.ForeignKeyConstraint(["import_job_id"], ["import_job.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["product_id"], ["dim_product.id"]),
        sa.ForeignKeyConstraint(
            ["staging_line_id"],
            ["import_distributor_si_staging_line.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_key", name="uq_fact_returns_source_key"),
    )
    op.create_index("ix_fact_returns_import_job_id", "fact_returns", ["import_job_id"])


def downgrade() -> None:
    op.drop_index("ix_fact_returns_import_job_id", table_name="fact_returns")
    op.drop_table("fact_returns")
