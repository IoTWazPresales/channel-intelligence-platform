"""Customer-allocated and open-channel SOH reconciliation fact table.

Revision ID: 20260518_0041
Revises: 20260518_0040

- ``fact_inventory_reconciliation`` with deterministic ``source_key`` upsert grain.
- Key format: ``dsi-recon:{distributor_id}:{product_id}:{customer_id|0}:{period_end_date}``
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from _alembic_revision_helpers import get_inspector, has_index, has_table, unique_constraint_exists

revision: str = "20260518_0041"
down_revision: Union[str, Sequence[str], None] = "20260518_0040"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = get_inspector(bind)

    if not has_table(insp, "fact_inventory_reconciliation"):
        op.create_table(
            "fact_inventory_reconciliation",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("source_key", sa.String(length=256), nullable=False),
            sa.Column("distributor_id", sa.Integer(), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("customer_id", sa.Integer(), nullable=True),
            sa.Column("period_end_date", sa.Date(), nullable=False),
            sa.Column("snapshot_date", sa.Date(), nullable=False),
            sa.Column("allocation_type", sa.String(length=32), nullable=False),
            sa.Column("calculated_units", sa.Numeric(18, 4), nullable=False),
            sa.Column("reported_units", sa.Numeric(18, 4), nullable=True),
            sa.Column("variance_units", sa.Numeric(18, 4), nullable=True),
            sa.Column("variance_pct", sa.Numeric(18, 6), nullable=True),
            sa.Column("reconciliation_status", sa.String(length=32), nullable=False),
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
            sa.ForeignKeyConstraint(["customer_id"], ["dim_customer.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["distributor_id"], ["dim_distributor.id"]),
            sa.ForeignKeyConstraint(["import_job_id"], ["import_job.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["product_id"], ["dim_product.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    insp = get_inspector(bind)
    if not unique_constraint_exists(
        insp, "fact_inventory_reconciliation", "uq_fact_inventory_reconciliation_source_key"
    ):
        op.create_unique_constraint(
            "uq_fact_inventory_reconciliation_source_key",
            "fact_inventory_reconciliation",
            ["source_key"],
        )

    insp = get_inspector(bind)
    if not has_index(insp, "fact_inventory_reconciliation", "ix_fact_inventory_reconciliation_dist_period"):
        op.create_index(
            "ix_fact_inventory_reconciliation_dist_period",
            "fact_inventory_reconciliation",
            ["distributor_id", "period_end_date"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = get_inspector(bind)
    if has_table(insp, "fact_inventory_reconciliation"):
        op.drop_table("fact_inventory_reconciliation")
