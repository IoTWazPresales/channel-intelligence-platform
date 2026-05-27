"""DSI customer velocity fact table and sell-out query index.

Revision ID: 20260518_0042
Revises: 20260518_0041

- ``fact_customer_velocity`` with one current row per (distributor, product, customer).
- Partial index on ``fact_sales_sellout`` for velocity aggregation queries.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from _alembic_revision_helpers import get_inspector, has_index, has_table, unique_constraint_exists

revision: str = "20260518_0042"
down_revision: Union[str, Sequence[str], None] = "20260518_0041"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = get_inspector(bind)

    if not has_table(insp, "fact_customer_velocity"):
        op.create_table(
            "fact_customer_velocity",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("source_key", sa.String(length=256), nullable=False),
            sa.Column("distributor_id", sa.Integer(), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("customer_id", sa.Integer(), nullable=False),
            sa.Column("computed_through_date", sa.Date(), nullable=False),
            sa.Column("velocity_4wk", sa.Numeric(18, 4), nullable=True),
            sa.Column("velocity_13wk", sa.Numeric(18, 4), nullable=True),
            sa.Column("velocity_52wk", sa.Numeric(18, 4), nullable=True),
            sa.Column("seasonal_index", sa.Numeric(18, 6), nullable=True),
            sa.Column(
                "is_promotional_period",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column("model_confidence", sa.String(length=16), nullable=False),
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
            sa.PrimaryKeyConstraint("id"),
        )

    insp = get_inspector(bind)
    if not unique_constraint_exists(
        insp, "fact_customer_velocity", "uq_fact_customer_velocity_source_key"
    ):
        op.create_unique_constraint(
            "uq_fact_customer_velocity_source_key",
            "fact_customer_velocity",
            ["source_key"],
        )

    insp = get_inspector(bind)
    if not unique_constraint_exists(insp, "fact_customer_velocity", "uq_fact_customer_velocity_grain"):
        op.create_unique_constraint(
            "uq_fact_customer_velocity_grain",
            "fact_customer_velocity",
            ["distributor_id", "product_id", "customer_id"],
        )

    insp = get_inspector(bind)
    if not has_index(insp, "fact_customer_velocity", "ix_fact_customer_velocity_dist"):
        op.create_index(
            "ix_fact_customer_velocity_dist",
            "fact_customer_velocity",
            ["distributor_id"],
        )

    insp = get_inspector(bind)
    if not has_index(insp, "fact_customer_velocity", "ix_fact_customer_velocity_dist_prod_cust"):
        op.create_index(
            "ix_fact_customer_velocity_dist_prod_cust",
            "fact_customer_velocity",
            ["distributor_id", "product_id", "customer_id"],
        )

    insp = get_inspector(bind)
    if has_table(insp, "fact_sales_sellout") and not has_index(
        insp, "fact_sales_sellout", "ix_fact_sales_sellout_dsi_velocity"
    ):
        op.create_index(
            "ix_fact_sales_sellout_dsi_velocity",
            "fact_sales_sellout",
            ["distributor_id", "product_id", "customer_id", "transaction_date"],
            postgresql_where=sa.text("distributor_id IS NOT NULL"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = get_inspector(bind)
    if has_table(insp, "fact_sales_sellout") and has_index(
        insp, "fact_sales_sellout", "ix_fact_sales_sellout_dsi_velocity"
    ):
        op.drop_index("ix_fact_sales_sellout_dsi_velocity", table_name="fact_sales_sellout")
    if has_table(insp, "fact_customer_velocity"):
        op.drop_table("fact_customer_velocity")
