"""More chart types for dashboard widgets and saved reports.

Revision ID: 20261020_0046
Revises: 20261019_0045
Create Date: 2026-10-20

Warren 2026-10-20: dashboards and reports offer horizontal bars, stacked bars, pie and donut charts
besides KPI, table, bar, line and area. Widens the visual check constraint on ``dashboard_widget`` and
``saved_report``; no row changes. Downgrade turns rows using a new visual back into ``table`` first.
Needs the table owner (on cip: ``postgres``): run with DATABASE_URL_SYNC_MIGRATE set to the owner.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20261020_0046"
down_revision: Union[str, Sequence[str], None] = "20261019_0045"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD = "('kpi', 'table', 'bar', 'line', 'area')"
NEW = "('kpi', 'table', 'bar', 'hbar', 'stacked_bar', 'line', 'area', 'pie', 'donut')"
TABLES = (("dashboard_widget", "ck_dashboard_widget_visual"), ("saved_report", "ck_saved_report_visual"))


def _drop(table: str, name: str) -> None:
    # create_all names CHECKs ck_<table>_ck_<table>_<col>; migrations name them ck_<table>_<col>. Drop both.
    op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
    op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS ck_{table}_{name}")


def upgrade() -> None:
    for table, name in TABLES:
        _drop(table, name)
        op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK (visual IN {NEW})")


def downgrade() -> None:
    for table, name in TABLES:
        op.execute(f"UPDATE {table} SET visual = 'table' WHERE visual NOT IN {OLD}")
        _drop(table, name)
        op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK (visual IN {OLD})")
