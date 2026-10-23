"""Dashboard builder on the v2 data model: stored v2 definitions, dashboard filters, more visuals.

Revision ID: 20261023_0048
Revises: 20261022_0047
Create Date: 2026-10-23

N-0116 (spec .eif/audit/PROGRAMME_20261023/N0116_SPEC_PROPOSAL.md s.2.1, decision D1 proposed):

- ``dashboard_widget.definition_v2`` and ``saved_report.definition_v2``: JSONB NULL. The v2 definition
  (query + display options). NULL means the row runs the v1 path exactly as before. The v1 columns stay
  populated (``metric_key`` stays NOT NULL), so old readers keep working.
- ``dashboard.filters_json``: JSONB NOT NULL DEFAULT '{}' (saved dashboard filter bar).
- ``dashboard.template_key``: TEXT NULL (set when a dashboard is created from a starter template).
- ``ck_dashboard_widget_visual`` and ``ck_saved_report_visual`` gain combo, dual_axis, scatter, pivot.

Additive: no row changes on upgrade. Table-level grants (``cip`` holds INSERT/SELECT/UPDATE/DELETE on
all three tables) cover new columns, and none of these tables has row security, so no grant or policy
change is needed. Downgrade drops the columns and restores the 0046 checks; it FAILS LOUDLY (raises)
when any row uses a new visual, instead of rewriting data. Needs the table owner (on cip: ``postgres``):
run with DATABASE_URL_SYNC_MIGRATE set to the owner.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261023_0048"
down_revision: Union[str, Sequence[str], None] = "20261022_0047"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD = "('kpi', 'table', 'bar', 'hbar', 'stacked_bar', 'line', 'area', 'pie', 'donut')"
NEW = (
    "('kpi', 'table', 'bar', 'hbar', 'stacked_bar', 'line', 'area', 'pie', 'donut', "
    "'combo', 'dual_axis', 'scatter', 'pivot')"
)
TABLES = (("dashboard_widget", "ck_dashboard_widget_visual"), ("saved_report", "ck_saved_report_visual"))


def _drop(table: str, name: str) -> None:
    # create_all names CHECKs ck_<table>_ck_<table>_<col>; migrations name them ck_<table>_<col>. Drop both.
    op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
    op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS ck_{table}_{name}")


def upgrade() -> None:
    op.add_column("dashboard_widget", sa.Column("definition_v2", postgresql.JSONB(), nullable=True))
    op.add_column("saved_report", sa.Column("definition_v2", postgresql.JSONB(), nullable=True))
    op.add_column(
        "dashboard",
        sa.Column("filters_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column("dashboard", sa.Column("template_key", sa.Text(), nullable=True))
    for table, name in TABLES:
        _drop(table, name)
        op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK (visual IN {NEW})")


def downgrade() -> None:
    # Fail loudly rather than rewrite a user's chart: the operator decides what those rows become.
    op.execute(
        f"""
        DO $$
        DECLARE n_w bigint; n_r bigint;
        BEGIN
          SELECT count(*) INTO n_w FROM dashboard_widget WHERE visual NOT IN {OLD};
          SELECT count(*) INTO n_r FROM saved_report WHERE visual NOT IN {OLD};
          IF n_w > 0 OR n_r > 0 THEN
            RAISE EXCEPTION 'Downgrade 20261023_0048 refused: % dashboard_widget and % saved_report rows use a visual added in 0048 (combo, dual_axis, scatter, pivot). Change them first; nothing was changed.', n_w, n_r;
          END IF;
        END $$;
        """
    )
    for table, name in TABLES:
        _drop(table, name)
        op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK (visual IN {OLD})")
    op.drop_column("dashboard", "template_key")
    op.drop_column("dashboard", "filters_json")
    op.drop_column("saved_report", "definition_v2")
    op.drop_column("dashboard_widget", "definition_v2")
