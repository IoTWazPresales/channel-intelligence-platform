"""Customers phase 1 control table fields.

Revision ID: 20260426_0012
Revises: 20260425_0011
Create Date: 2026-04-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260426_0012"
down_revision: Union[str, Sequence[str], None] = "20260425_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "dim_customer",
        sa.Column("customer_status", sa.String(length=32), nullable=False, server_default="active"),
    )
    op.add_column("dim_customer", sa.Column("partner_tier", sa.String(length=32), nullable=True))
    op.add_column(
        "dim_customer",
        sa.Column("account_owner_internal", sa.String(length=128), nullable=True),
    )
    op.add_column("dim_customer", sa.Column("notes_summary", sa.String(length=512), nullable=True))
    op.add_column("dim_customer", sa.Column("preferred_distributor_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_dim_customer_preferred_distributor_id_dim_distributor",
        "dim_customer",
        "dim_distributor",
        ["preferred_distributor_id"],
        ["id"],
    )

    op.execute(
        "UPDATE dim_customer SET customer_status = 'active' "
        "WHERE customer_status IS NULL OR TRIM(customer_status) = ''"
    )
    op.alter_column("dim_customer", "customer_status", server_default=None)


def downgrade() -> None:
    op.drop_constraint(
        "fk_dim_customer_preferred_distributor_id_dim_distributor",
        "dim_customer",
        type_="foreignkey",
    )
    op.drop_column("dim_customer", "preferred_distributor_id")
    op.drop_column("dim_customer", "notes_summary")
    op.drop_column("dim_customer", "account_owner_internal")
    op.drop_column("dim_customer", "partner_tier")
    op.drop_column("dim_customer", "customer_status")
