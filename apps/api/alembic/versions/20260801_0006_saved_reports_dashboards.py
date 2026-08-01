"""P3-4 saved reports + dashboards (personal vs published, role-aware share).

Revision ID: 20260801_0006
Revises: 20260801_0005
Create Date: 2026-08-01

Idempotent: tip-ORM ``20260801_0001`` create_all may already have the tables.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision: str = "20260801_0006"
down_revision: Union[str, Sequence[str], None] = "20260801_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _grant_cip() -> None:
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cip') THEN
                EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON saved_report TO cip';
                EXECUTE 'GRANT USAGE, SELECT ON SEQUENCE saved_report_id_seq TO cip';
                EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON dashboard TO cip';
                EXECUTE 'GRANT USAGE, SELECT ON SEQUENCE dashboard_id_seq TO cip';
                EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON dashboard_tile TO cip';
                EXECUTE 'GRANT USAGE, SELECT ON SEQUENCE dashboard_tile_id_seq TO cip';
              END IF;
            END $$;
            """
        )
    )


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())

    if "saved_report" not in tables:
        op.create_table(
            "saved_report",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.Text(), nullable=False),
            sa.Column("owner_user_id", sa.BigInteger(), nullable=True),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("visibility", sa.Text(), server_default="personal", nullable=False),
            sa.Column(
                "shared_roles",
                postgresql.JSONB(astext_type=sa.Text()),
                server_default=sa.text("'[]'::jsonb"),
                nullable=False,
            ),
            sa.Column("metric_key", sa.Text(), nullable=False),
            sa.Column(
                "grains",
                postgresql.JSONB(astext_type=sa.Text()),
                server_default=sa.text("'[]'::jsonb"),
                nullable=False,
            ),
            sa.Column(
                "filters",
                postgresql.JSONB(astext_type=sa.Text()),
                server_default=sa.text("'{}'::jsonb"),
                nullable=False,
            ),
            sa.Column("visual", sa.Text(), server_default="kpi", nullable=False),
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
            sa.ForeignKeyConstraint(["owner_user_id"], ["app_user.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
            sa.CheckConstraint(
                "visibility IN ('personal', 'published')",
                name="ck_saved_report_visibility",
            ),
            sa.CheckConstraint(
                "visual IN ('kpi', 'table', 'bar')",
                name="ck_saved_report_visual",
            ),
        )
        op.create_index("ix_saved_report_tenant_id", "saved_report", ["tenant_id"])
        op.create_index("ix_saved_report_owner_user_id", "saved_report", ["owner_user_id"])
        op.create_index("ix_saved_report_visibility", "saved_report", ["visibility"])

    if "dashboard" not in tables:
        op.create_table(
            "dashboard",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.Text(), nullable=False),
            sa.Column("owner_user_id", sa.BigInteger(), nullable=True),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("visibility", sa.Text(), server_default="personal", nullable=False),
            sa.Column(
                "shared_roles",
                postgresql.JSONB(astext_type=sa.Text()),
                server_default=sa.text("'[]'::jsonb"),
                nullable=False,
            ),
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
            sa.ForeignKeyConstraint(["owner_user_id"], ["app_user.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
            sa.CheckConstraint(
                "visibility IN ('personal', 'published')",
                name="ck_dashboard_visibility",
            ),
        )
        op.create_index("ix_dashboard_tenant_id", "dashboard", ["tenant_id"])
        op.create_index("ix_dashboard_owner_user_id", "dashboard", ["owner_user_id"])
        op.create_index("ix_dashboard_visibility", "dashboard", ["visibility"])

    if "dashboard_tile" not in tables:
        op.create_table(
            "dashboard_tile",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("dashboard_id", sa.BigInteger(), nullable=False),
            sa.Column("saved_report_id", sa.BigInteger(), nullable=False),
            sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
            sa.Column("title_override", sa.Text(), nullable=True),
            sa.Column(
                "layout_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
            sa.ForeignKeyConstraint(["dashboard_id"], ["dashboard.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["saved_report_id"], ["saved_report.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("dashboard_id", "saved_report_id", name="uq_dashboard_tile_report"),
        )
        op.create_index("ix_dashboard_tile_dashboard_id", "dashboard_tile", ["dashboard_id"])
        op.create_index("ix_dashboard_tile_saved_report_id", "dashboard_tile", ["saved_report_id"])

    _grant_cip()


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if "dashboard_tile" in tables:
        op.drop_table("dashboard_tile")
    if "dashboard" in tables:
        op.drop_table("dashboard")
    if "saved_report" in tables:
        op.drop_table("saved_report")
