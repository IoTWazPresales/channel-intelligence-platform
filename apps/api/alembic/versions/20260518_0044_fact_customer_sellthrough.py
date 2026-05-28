"""Customer sell-through fact table (chain + store grain).

Revision ID: 20260518_0044
Revises: 20260518_0043

- ``fact_customer_sellthrough`` with ``source_key`` upsert and partial unique grains.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from _alembic_revision_helpers import get_inspector, has_index, has_table, unique_constraint_exists

revision: str = "20260518_0044"
down_revision: Union[str, Sequence[str], None] = "20260518_0043"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = get_inspector(bind)

    if not has_table(insp, "fact_customer_sellthrough"):
        op.create_table(
            "fact_customer_sellthrough",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("source_key", sa.String(length=256), nullable=False),
            sa.Column("customer_id", sa.Integer(), nullable=False),
            sa.Column("customer_location_id", sa.Integer(), nullable=True),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("period_start_date", sa.Date(), nullable=False),
            sa.Column("period_type", sa.String(length=8), nullable=False),
            sa.Column("units_sold", sa.Numeric(18, 4), nullable=False),
            sa.Column("raw_mtd_units", sa.Numeric(18, 4), nullable=True),
            sa.Column(
                "is_mtd_estimate",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column("unit_sell_price", sa.Numeric(18, 4), nullable=True),
            sa.Column("unit_cost", sa.Numeric(18, 4), nullable=True),
            sa.Column("reported_soh", sa.Numeric(18, 4), nullable=True),
            sa.Column("import_job_id", sa.Integer(), nullable=True),
            sa.Column("raw_source_row", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
            sa.ForeignKeyConstraint(["customer_location_id"], ["customer_location.id"]),
            sa.ForeignKeyConstraint(["product_id"], ["dim_product.id"]),
            sa.ForeignKeyConstraint(["import_job_id"], ["import_job.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )

    insp = get_inspector(bind)
    if not unique_constraint_exists(insp, "fact_customer_sellthrough", "uq_fact_customer_sellthrough_source_key"):
        op.create_unique_constraint(
            "uq_fact_customer_sellthrough_source_key",
            "fact_customer_sellthrough",
            ["source_key"],
        )

    insp = get_inspector(bind)
    if not has_index(insp, "fact_customer_sellthrough", "uq_fact_customer_sellthrough_chain_grain"):
        op.execute(
            sa.text(
                """
                CREATE UNIQUE INDEX uq_fact_customer_sellthrough_chain_grain
                ON fact_customer_sellthrough (customer_id, product_id, period_start_date)
                WHERE customer_location_id IS NULL
                """
            )
        )

    insp = get_inspector(bind)
    if not has_index(insp, "fact_customer_sellthrough", "uq_fact_customer_sellthrough_site_grain"):
        op.execute(
            sa.text(
                """
                CREATE UNIQUE INDEX uq_fact_customer_sellthrough_site_grain
                ON fact_customer_sellthrough (customer_id, customer_location_id, product_id, period_start_date)
                WHERE customer_location_id IS NOT NULL
                """
            )
        )

    insp = get_inspector(bind)
    if not has_index(insp, "fact_customer_sellthrough", "ix_fact_customer_sellthrough_customer_period"):
        op.create_index(
            "ix_fact_customer_sellthrough_customer_period",
            "fact_customer_sellthrough",
            ["customer_id", "period_start_date"],
        )

    insp = get_inspector(bind)
    if not has_index(insp, "fact_customer_sellthrough", "ix_fact_customer_sellthrough_product_period"):
        op.create_index(
            "ix_fact_customer_sellthrough_product_period",
            "fact_customer_sellthrough",
            ["product_id", "period_start_date"],
        )

    insp = get_inspector(bind)
    if not has_index(insp, "fact_customer_sellthrough", "ix_fact_customer_sellthrough_location_product_period"):
        op.create_index(
            "ix_fact_customer_sellthrough_location_product_period",
            "fact_customer_sellthrough",
            ["customer_location_id", "product_id", "period_start_date"],
            postgresql_where=sa.text("customer_location_id IS NOT NULL"),
        )

    insp = get_inspector(bind)
    if not has_index(insp, "fact_customer_sellthrough", "ix_fact_customer_sellthrough_import_job"):
        op.create_index(
            "ix_fact_customer_sellthrough_import_job",
            "fact_customer_sellthrough",
            ["import_job_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = get_inspector(bind)
    if has_table(insp, "fact_customer_sellthrough"):
        op.drop_table("fact_customer_sellthrough")
