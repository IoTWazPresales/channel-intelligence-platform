"""Steward audit event table (P2-3).

Revision ID: 20260801_0004
Revises: 20260801_0003
Create Date: 2026-08-01

Append-only log of steward decisions (resolve/map/ignore/bulk/provisional).
NOT applied until Warren approves alembic upgrade.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260801_0004"
down_revision: Union[str, Sequence[str], None] = "20260801_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "steward_audit_event",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("actor_user_id", sa.BigInteger(), nullable=True),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("importer", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=True),
        sa.Column("entity_token", sa.Text(), nullable=True),
        sa.Column("import_job_id", sa.BigInteger(), nullable=True),
        sa.Column("candidate_id", sa.BigInteger(), nullable=True),
        sa.Column("target_dim", sa.Text(), nullable=True),
        sa.Column("target_id", sa.BigInteger(), nullable=True),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["app_user.id"],
            name="fk_steward_audit_event_actor_user_id_app_user",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name="fk_steward_audit_event_tenant_id_tenant",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_steward_audit_event"),
    )
    op.create_index("ix_steward_audit_event_tenant_id", "steward_audit_event", ["tenant_id"])
    op.create_index("ix_steward_audit_event_created_at", "steward_audit_event", ["created_at"])
    op.create_index("ix_steward_audit_event_importer", "steward_audit_event", ["importer"])
    op.create_index("ix_steward_audit_event_import_job_id", "steward_audit_event", ["import_job_id"])
    op.create_index("ix_steward_audit_event_actor_user_id", "steward_audit_event", ["actor_user_id"])

    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cip') THEN
                EXECUTE 'GRANT SELECT, INSERT ON steward_audit_event TO cip';
                EXECUTE 'GRANT USAGE, SELECT ON SEQUENCE steward_audit_event_id_seq TO cip';
              END IF;
            END $$;
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_steward_audit_event_actor_user_id", table_name="steward_audit_event")
    op.drop_index("ix_steward_audit_event_import_job_id", table_name="steward_audit_event")
    op.drop_index("ix_steward_audit_event_importer", table_name="steward_audit_event")
    op.drop_index("ix_steward_audit_event_created_at", table_name="steward_audit_event")
    op.drop_index("ix_steward_audit_event_tenant_id", table_name="steward_audit_event")
    op.drop_table("steward_audit_event")
