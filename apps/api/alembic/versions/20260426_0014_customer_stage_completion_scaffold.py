"""Customer stage completion scaffold: child entities + import handler update.

Revision ID: 20260426_0014
Revises: 20260426_0013
Create Date: 2026-04-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from _alembic_revision_helpers import get_inspector, has_index, has_table

revision: str = "20260426_0014"
down_revision: Union[str, Sequence[str], None] = "20260426_0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = get_inspector(bind)

    if not has_table(insp, "customer_location"):
        op.create_table(
            "customer_location",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("customer_id", sa.Integer(), nullable=False),
            sa.Column("location_code", sa.String(length=64), nullable=False),
            sa.Column("location_name", sa.String(length=256), nullable=False),
            sa.Column("location_type", sa.String(length=32), nullable=False),
            sa.Column("region_id", sa.Integer(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("notes_summary", sa.String(length=512), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["customer_id"], ["dim_customer.id"]),
            sa.ForeignKeyConstraint(["region_id"], ["dim_region.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("customer_id", "location_code", name="uq_customer_location_customer_id_location_code"),
        )
    insp = get_inspector(bind)
    if not has_index(insp, "customer_location", "ix_customer_location_customer_id"):
        op.create_index(
            "ix_customer_location_customer_id",
            "customer_location",
            ["customer_id"],
            unique=False,
        )

    insp = get_inspector(bind)
    if not has_table(insp, "customer_contact"):
        op.create_table(
            "customer_contact",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("customer_id", sa.Integer(), nullable=False),
            sa.Column("contact_name", sa.String(length=256), nullable=False),
            sa.Column("contact_role", sa.String(length=32), nullable=False),
            sa.Column("email", sa.String(length=256), nullable=True),
            sa.Column("phone", sa.String(length=64), nullable=True),
            sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("notes_summary", sa.String(length=512), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["customer_id"], ["dim_customer.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    insp = get_inspector(bind)
    if not has_index(insp, "customer_contact", "ix_customer_contact_customer_id"):
        op.create_index(
            "ix_customer_contact_customer_id",
            "customer_contact",
            ["customer_id"],
            unique=False,
        )

    op.execute(
        """
        UPDATE import_template
        SET pipeline_handler = 'customer_master_upsert'
        WHERE slug = 'customer_master'
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    insp = get_inspector(bind)

    op.execute(
        """
        UPDATE import_template
        SET pipeline_handler = 'stub_noop'
        WHERE slug = 'customer_master'
        """
    )
    if has_index(insp, "customer_contact", "ix_customer_contact_customer_id"):
        op.drop_index("ix_customer_contact_customer_id", table_name="customer_contact")
    insp = get_inspector(bind)
    if has_table(insp, "customer_contact"):
        op.drop_table("customer_contact")

    insp = get_inspector(bind)
    if has_index(insp, "customer_location", "ix_customer_location_customer_id"):
        op.drop_index("ix_customer_location_customer_id", table_name="customer_location")
    insp = get_inspector(bind)
    if has_table(insp, "customer_location"):
        op.drop_table("customer_location")
