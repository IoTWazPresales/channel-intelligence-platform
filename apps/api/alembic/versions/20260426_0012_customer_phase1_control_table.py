"""Customers phase 1 control table fields.

Revision ID: 20260426_0012
Revises: 20260425_0011
Create Date: 2026-04-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from _alembic_revision_helpers import fk_exists, get_inspector, has_column

revision: str = "20260426_0012"
down_revision: Union[str, Sequence[str], None] = "20260425_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = get_inspector(bind)
    # 20260412_0001 uses ORM create_all; dim_customer may already include these columns.
    if not has_column(insp, "dim_customer", "customer_status"):
        op.add_column(
            "dim_customer",
            sa.Column("customer_status", sa.String(length=32), nullable=False, server_default="active"),
        )
    if not has_column(insp, "dim_customer", "partner_tier"):
        op.add_column("dim_customer", sa.Column("partner_tier", sa.String(length=32), nullable=True))
    if not has_column(insp, "dim_customer", "account_owner_internal"):
        op.add_column(
            "dim_customer",
            sa.Column("account_owner_internal", sa.String(length=128), nullable=True),
        )
    if not has_column(insp, "dim_customer", "notes_summary"):
        op.add_column("dim_customer", sa.Column("notes_summary", sa.String(length=512), nullable=True))
    if not has_column(insp, "dim_customer", "preferred_distributor_id"):
        op.add_column("dim_customer", sa.Column("preferred_distributor_id", sa.Integer(), nullable=True))

    insp = get_inspector(bind)
    fk_name = "fk_dim_customer_preferred_distributor_id_dim_distributor"
    if not fk_exists(insp, "dim_customer", fk_name):
        op.create_foreign_key(
            fk_name,
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
    bind = op.get_bind()
    insp = get_inspector(bind)
    fk_name = "fk_dim_customer_preferred_distributor_id_dim_distributor"
    if fk_exists(insp, "dim_customer", fk_name):
        op.drop_constraint(fk_name, "dim_customer", type_="foreignkey")
    insp = get_inspector(bind)
    for col in (
        "preferred_distributor_id",
        "notes_summary",
        "account_owner_internal",
        "partner_tier",
        "customer_status",
    ):
        if has_column(insp, "dim_customer", col):
            op.drop_column("dim_customer", col)
        insp = get_inspector(bind)
