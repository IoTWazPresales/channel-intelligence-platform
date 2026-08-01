"""P3-5 report delivery inbox + schedules.

Revision ID: 20260801_0007
Revises: 20260801_0006
Create Date: 2026-08-01
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260801_0007"
down_revision: Union[str, Sequence[str], None] = "20260801_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "report_delivery",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("recipient_user_id", sa.BigInteger(), nullable=True),
        sa.Column("saved_report_id", sa.BigInteger(), nullable=True),
        sa.Column("dashboard_id", sa.BigInteger(), nullable=True),
        sa.Column("channel", sa.Text(), server_default="inbox", nullable=False),
        sa.Column("trigger", sa.Text(), server_default="manual", nullable=False),
        sa.Column("format", sa.Text(), server_default="xlsx", nullable=False),
        sa.Column("status", sa.Text(), server_default="delivered", nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("body_summary", sa.Text(), nullable=True),
        sa.Column(
            "data_vintage",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("missing_data_alert", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("metric_key", sa.Text(), nullable=True),
        sa.Column("value_preview", sa.Text(), nullable=True),
        sa.Column("storage_key", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["recipient_user_id"], ["app_user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["saved_report_id"], ["saved_report.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["dashboard_id"], ["dashboard.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "channel IN ('inbox', 'email_stub')",
            name="ck_report_delivery_channel",
        ),
        sa.CheckConstraint(
            "trigger IN ('manual', 'schedule', 'import_event')",
            name="ck_report_delivery_trigger",
        ),
        sa.CheckConstraint(
            "format IN ('xlsx', 'pdf')",
            name="ck_report_delivery_format",
        ),
        sa.CheckConstraint(
            "status IN ('delivered', 'failed')",
            name="ck_report_delivery_status",
        ),
    )
    op.create_index("ix_report_delivery_tenant_id", "report_delivery", ["tenant_id"])
    op.create_index("ix_report_delivery_recipient_user_id", "report_delivery", ["recipient_user_id"])
    op.create_index("ix_report_delivery_created_at", "report_delivery", ["created_at"])

    op.create_table(
        "report_schedule",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("owner_user_id", sa.BigInteger(), nullable=True),
        sa.Column("saved_report_id", sa.BigInteger(), nullable=True),
        sa.Column("dashboard_id", sa.BigInteger(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("cadence", sa.Text(), server_default="weekly_monday_0700", nullable=False),
        sa.Column("format", sa.Text(), server_default="xlsx", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "subscriber_user_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["app_user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["saved_report_id"], ["saved_report.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dashboard_id"], ["dashboard.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "cadence IN ('weekly_monday_0700', 'daily_0700', 'on_import_complete')",
            name="ck_report_schedule_cadence",
        ),
        sa.CheckConstraint(
            "format IN ('xlsx', 'pdf')",
            name="ck_report_schedule_format",
        ),
    )
    op.create_index("ix_report_schedule_tenant_id", "report_schedule", ["tenant_id"])
    op.create_index("ix_report_schedule_enabled", "report_schedule", ["enabled"])

    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cip') THEN
                EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON report_delivery TO cip';
                EXECUTE 'GRANT USAGE, SELECT ON SEQUENCE report_delivery_id_seq TO cip';
                EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON report_schedule TO cip';
                EXECUTE 'GRANT USAGE, SELECT ON SEQUENCE report_schedule_id_seq TO cip';
              END IF;
            END $$;
            """
        )
    )


def downgrade() -> None:
    op.drop_table("report_schedule")
    op.drop_table("report_delivery")
