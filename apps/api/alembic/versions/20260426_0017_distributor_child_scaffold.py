"""Add distributor location and contact child tables.

Revision ID: 20260426_0017
Revises: 20260426_0016
Create Date: 2026-04-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from _alembic_revision_helpers import get_inspector, has_index, has_table

revision: str = "20260426_0017"
down_revision: Union[str, Sequence[str], None] = "20260426_0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = get_inspector(bind)

    if not has_table(insp, "distributor_location"):
        op.create_table(
            "distributor_location",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("distributor_id", sa.Integer(), sa.ForeignKey("dim_distributor.id"), nullable=False),
            sa.Column("location_code", sa.String(length=64), nullable=False),
            sa.Column("location_name", sa.String(length=256), nullable=False),
            sa.Column("location_type", sa.String(length=32), nullable=False, server_default="branch"),
            sa.Column("country_code", sa.String(length=8), nullable=True),
            sa.Column("address_summary", sa.String(length=512), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("notes_summary", sa.String(length=512), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.UniqueConstraint("distributor_id", "location_code", name="uq_distributor_location_code_per_distributor"),
        )
    insp = get_inspector(bind)
    if not has_index(insp, "distributor_location", "ix_distributor_location_distributor_id"):
        op.create_index("ix_distributor_location_distributor_id", "distributor_location", ["distributor_id"])

    insp = get_inspector(bind)
    if not has_table(insp, "distributor_contact"):
        op.create_table(
            "distributor_contact",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("distributor_id", sa.Integer(), sa.ForeignKey("dim_distributor.id"), nullable=False),
            sa.Column("contact_name", sa.String(length=256), nullable=False),
            sa.Column("contact_role", sa.String(length=32), nullable=False, server_default="general"),
            sa.Column("email", sa.String(length=256), nullable=True),
            sa.Column("phone", sa.String(length=64), nullable=True),
            sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("notes_summary", sa.String(length=512), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
    insp = get_inspector(bind)
    if not has_index(insp, "distributor_contact", "ix_distributor_contact_distributor_id"):
        op.create_index("ix_distributor_contact_distributor_id", "distributor_contact", ["distributor_id"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = get_inspector(bind)

    if has_index(insp, "distributor_contact", "ix_distributor_contact_distributor_id"):
        op.drop_index("ix_distributor_contact_distributor_id", table_name="distributor_contact")
    insp = get_inspector(bind)
    if has_table(insp, "distributor_contact"):
        op.drop_table("distributor_contact")

    insp = get_inspector(bind)
    if has_index(insp, "distributor_location", "ix_distributor_location_distributor_id"):
        op.drop_index("ix_distributor_location_distributor_id", table_name="distributor_location")
    insp = get_inspector(bind)
    if has_table(insp, "distributor_location"):
        op.drop_table("distributor_location")
