"""U1 — shipping_mailer_recipient table + case-insensitive unique address.

Revision ID: 20260818_0019
Revises: 20260818_0018
Create Date: 2026-08-18

Do not alembic upgrade on cip without Warren approval.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "20260818_0019"
down_revision: Union[str, Sequence[str], None] = "20260818_0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _grant_cip(table: str) -> None:
    op.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cip') THEN
                EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO cip';
                EXECUTE 'GRANT USAGE, SELECT ON SEQUENCE {table}_id_seq TO cip';
              END IF;
            END $$;
            """
        )
    )


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    tables = set(insp.get_table_names())
    if "shipping_mailer_recipient" not in tables:
        op.create_table(
            "shipping_mailer_recipient",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.Text(), nullable=False),
            sa.Column("address", sa.Text(), nullable=False),
            sa.Column("display_name", sa.Text(), nullable=True),
            sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
            sa.Column("added_by", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.execute(
            sa.text(
                "CREATE UNIQUE INDEX uq_shipping_mailer_recipient_tenant_address_lower "
                "ON shipping_mailer_recipient (tenant_id, lower(address))"
            )
        )
    _grant_cip("shipping_mailer_recipient")


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if "shipping_mailer_recipient" not in set(insp.get_table_names()):
        return
    op.execute(sa.text("DROP INDEX IF EXISTS uq_shipping_mailer_recipient_tenant_address_lower"))
    op.drop_table("shipping_mailer_recipient")
