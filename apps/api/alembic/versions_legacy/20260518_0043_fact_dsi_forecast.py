"""DSI distributor forecast fact table (separate from Commercial Planner ``fact_forecast``).

Revision ID: 20260518_0043
Revises: 20260518_0042

- ``fact_dsi_forecast`` with deterministic ``source_key`` upsert grain.
- Key format: ``dsi-forecast:{distributor_id}:{product_id}:{forecast_date}``
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from _alembic_revision_helpers import get_inspector, has_index, has_table, unique_constraint_exists

revision: str = "20260518_0043"
down_revision: Union[str, Sequence[str], None] = "20260518_0042"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = get_inspector(bind)

    if not has_table(insp, "fact_dsi_forecast"):
        op.create_table(
            "fact_dsi_forecast",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("source_key", sa.String(length=256), nullable=False),
            sa.Column("distributor_id", sa.Integer(), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("forecast_date", sa.Date(), nullable=False),
            sa.Column("forecast_units", sa.Numeric(18, 4), nullable=False),
            sa.Column("upper_band", sa.Numeric(18, 4), nullable=True),
            sa.Column("lower_band", sa.Numeric(18, 4), nullable=True),
            sa.Column("confidence_level", sa.String(length=16), nullable=False),
            sa.Column("velocity_basis", sa.String(length=64), nullable=True),
            sa.Column(
                "generated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column("import_job_id", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(["distributor_id"], ["dim_distributor.id"]),
            sa.ForeignKeyConstraint(["import_job_id"], ["import_job.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["product_id"], ["dim_product.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    insp = get_inspector(bind)
    if not unique_constraint_exists(insp, "fact_dsi_forecast", "uq_fact_dsi_forecast_source_key"):
        op.create_unique_constraint(
            "uq_fact_dsi_forecast_source_key",
            "fact_dsi_forecast",
            ["source_key"],
        )

    insp = get_inspector(bind)
    if not unique_constraint_exists(insp, "fact_dsi_forecast", "uq_fact_dsi_forecast_grain"):
        op.create_unique_constraint(
            "uq_fact_dsi_forecast_grain",
            "fact_dsi_forecast",
            ["distributor_id", "product_id", "forecast_date"],
        )

    insp = get_inspector(bind)
    if not has_index(insp, "fact_dsi_forecast", "ix_fact_dsi_forecast_dist_date"):
        op.create_index(
            "ix_fact_dsi_forecast_dist_date",
            "fact_dsi_forecast",
            ["distributor_id", "forecast_date"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = get_inspector(bind)
    if has_table(insp, "fact_dsi_forecast"):
        op.drop_table("fact_dsi_forecast")
