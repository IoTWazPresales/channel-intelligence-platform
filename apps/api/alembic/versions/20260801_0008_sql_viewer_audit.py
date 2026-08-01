"""P3-6 SQL viewer audit log.

Revision ID: 20260801_0008
Revises: 20260801_0007
Create Date: 2026-08-01

Idempotent: tip-ORM ``20260801_0001`` create_all may already have the table.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "20260801_0008"
down_revision: Union[str, Sequence[str], None] = "20260801_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _grant_cip() -> None:
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cip') THEN
                EXECUTE 'GRANT SELECT, INSERT ON sql_viewer_audit TO cip';
                EXECUTE 'GRANT USAGE, SELECT ON SEQUENCE sql_viewer_audit_id_seq TO cip';
              END IF;
            END $$;
            """
        )
    )


def upgrade() -> None:
    bind = op.get_bind()
    if "sql_viewer_audit" not in inspect(bind).get_table_names():
        op.create_table(
            "sql_viewer_audit",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.Text(), nullable=False),
            sa.Column("actor_user_id", sa.BigInteger(), nullable=True),
            sa.Column("actor", sa.Text(), nullable=False),
            sa.Column("sql_text", sa.Text(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False),
            sa.Column("row_count", sa.Integer(), nullable=True),
            sa.Column("truncated", sa.Boolean(), server_default="false", nullable=False),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["actor_user_id"], ["app_user.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.CheckConstraint(
                "status IN ('ok', 'refused', 'error', 'timeout')",
                name="ck_sql_viewer_audit_status",
            ),
        )
        op.create_index("ix_sql_viewer_audit_tenant_id", "sql_viewer_audit", ["tenant_id"])
        op.create_index("ix_sql_viewer_audit_actor_user_id", "sql_viewer_audit", ["actor_user_id"])
        op.create_index("ix_sql_viewer_audit_created_at", "sql_viewer_audit", ["created_at"])

    _grant_cip()


def downgrade() -> None:
    bind = op.get_bind()
    if "sql_viewer_audit" not in inspect(bind).get_table_names():
        return
    op.drop_table("sql_viewer_audit")
