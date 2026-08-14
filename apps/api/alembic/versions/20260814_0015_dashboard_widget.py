"""P3 widget persist — first-class dashboard_widget; retire dashboard_tile.

Revision ID: 20260814_0015
Revises: 20260812_0014
Create Date: 2026-08-14

Warren approved schema 2026-08-14 (Unit 14B). Backfill tiles → widgets, then drop
dashboard_tile. Expand saved_report visual + period_grain.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision: str = "20260814_0015"
down_revision: Union[str, Sequence[str], None] = "20260812_0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _grant_cip() -> None:
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cip') THEN
                EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON dashboard_widget TO cip';
                EXECUTE 'GRANT USAGE, SELECT ON SEQUENCE dashboard_widget_id_seq TO cip';
              END IF;
            END $$;
            """
        )
    )


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    tables = set(insp.get_table_names())
    saved_cols = {c["name"] for c in insp.get_columns("saved_report")} if "saved_report" in tables else set()

    if "saved_report" in tables and "period_grain" not in saved_cols:
        op.add_column("saved_report", sa.Column("period_grain", sa.Text(), nullable=True))

    if "saved_report" in tables:
        # create_all named CHECKs ck_<table>_ck_<table>_<col>; drop both spellings.
        op.execute("ALTER TABLE saved_report DROP CONSTRAINT IF EXISTS ck_saved_report_visual")
        op.execute(
            "ALTER TABLE saved_report DROP CONSTRAINT IF EXISTS ck_saved_report_ck_saved_report_visual"
        )
        op.execute(
            """
            ALTER TABLE saved_report
              ADD CONSTRAINT ck_saved_report_visual
              CHECK (visual IN ('kpi', 'table', 'bar', 'line', 'area'))
            """
        )
        op.execute("ALTER TABLE saved_report DROP CONSTRAINT IF EXISTS ck_saved_report_period_grain")
        op.execute(
            "ALTER TABLE saved_report DROP CONSTRAINT IF EXISTS ck_saved_report_ck_saved_report_period_grain"
        )
        op.execute(
            """
            ALTER TABLE saved_report
              ADD CONSTRAINT ck_saved_report_period_grain
              CHECK (period_grain IS NULL OR period_grain IN ('week', 'month', 'quarter'))
            """
        )

    if "dashboard_widget" not in tables:
        op.create_table(
            "dashboard_widget",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("dashboard_id", sa.BigInteger(), nullable=False),
            sa.Column("tenant_id", sa.Text(), nullable=False),
            sa.Column("title", sa.Text(), nullable=False),
            sa.Column("visual", sa.Text(), server_default="kpi", nullable=False),
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
            sa.Column("period_grain", sa.Text(), nullable=True),
            sa.Column("layout_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("saved_report_id", sa.BigInteger(), nullable=True),
            sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
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
            sa.ForeignKeyConstraint(["dashboard_id"], ["dashboard.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["saved_report_id"], ["saved_report.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.CheckConstraint(
                "visual IN ('kpi', 'table', 'bar', 'line', 'area')",
                name="ck_dashboard_widget_visual",
            ),
            sa.CheckConstraint(
                "period_grain IS NULL OR period_grain IN ('week', 'month', 'quarter')",
                name="ck_dashboard_widget_period_grain",
            ),
        )
        op.create_index("ix_dashboard_widget_dashboard_id", "dashboard_widget", ["dashboard_id"])
        op.create_index("ix_dashboard_widget_tenant_id", "dashboard_widget", ["tenant_id"])
        op.create_index("ix_dashboard_widget_saved_report_id", "dashboard_widget", ["saved_report_id"])

    tables = set(inspect(bind).get_table_names())
    if "dashboard_tile" in tables and "dashboard_widget" in tables:
        op.execute(
            sa.text(
                """
                INSERT INTO dashboard_widget (
                    dashboard_id, tenant_id, title, visual, metric_key, grains, filters,
                    period_grain, layout_json, saved_report_id, sort_order, created_at, updated_at
                )
                SELECT
                    t.dashboard_id,
                    d.tenant_id,
                    COALESCE(NULLIF(t.title_override, ''), r.name),
                    r.visual,
                    r.metric_key,
                    r.grains,
                    r.filters,
                    NULL,
                    t.layout_json,
                    t.saved_report_id,
                    t.sort_order,
                    now(),
                    now()
                FROM dashboard_tile t
                JOIN dashboard d ON d.id = t.dashboard_id
                JOIN saved_report r ON r.id = t.saved_report_id
                """
            )
        )
        op.drop_table("dashboard_tile")

    _grant_cip()


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if "dashboard_widget" in tables:
        op.drop_table("dashboard_widget")
    if "saved_report" in tables:
        op.execute("ALTER TABLE saved_report DROP CONSTRAINT IF EXISTS ck_saved_report_period_grain")
        op.execute(
            "ALTER TABLE saved_report DROP CONSTRAINT IF EXISTS ck_saved_report_ck_saved_report_period_grain"
        )
        op.execute("ALTER TABLE saved_report DROP COLUMN IF EXISTS period_grain")
        op.execute("ALTER TABLE saved_report DROP CONSTRAINT IF EXISTS ck_saved_report_visual")
        op.execute(
            "ALTER TABLE saved_report DROP CONSTRAINT IF EXISTS ck_saved_report_ck_saved_report_visual"
        )
        op.execute(
            """
            ALTER TABLE saved_report
              ADD CONSTRAINT ck_saved_report_visual
              CHECK (visual IN ('kpi', 'table', 'bar'))
            """
        )
