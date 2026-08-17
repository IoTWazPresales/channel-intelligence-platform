"""BACKLOG-097 — weeks_of_cover_observation + A3 fact indexes.

Revision ID: 20260817_0017
Revises: 20260814_0016
Create Date: 2026-08-17

Derived observation series (not a fact). Composite fact indexes support
per-distributor as-of reconstruction. Do not alembic upgrade on cip
without Warren approval.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision: str = "20260817_0017"
down_revision: Union[str, Sequence[str], None] = "20260814_0016"
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


def _create_index_if_missing(insp, table: str, name: str, ddl: str) -> None:
    existing = {ix["name"] for ix in insp.get_indexes(table)} if table in set(insp.get_table_names()) else set()
    if name in existing:
        return
    op.execute(sa.text(ddl))


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    tables = set(insp.get_table_names())

    if "weeks_of_cover_observation" not in tables:
        op.create_table(
            "weeks_of_cover_observation",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.String(length=64), nullable=False),
            sa.Column("distributor_id", sa.Integer(), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("snapshot_date", sa.Date(), nullable=False),
            sa.Column("cover_as_of_date", sa.Date(), nullable=False),
            sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("import_job_id", sa.Integer(), nullable=True),
            sa.Column("trigger", sa.String(length=32), nullable=False),
            sa.Column("reported_soh", sa.Numeric(18, 4), nullable=False),
            sa.Column("sell_out_since", sa.Numeric(18, 4), nullable=False),
            sa.Column("landed_since", sa.Numeric(18, 4), nullable=False),
            sa.Column("derived_stock", sa.Numeric(18, 4), nullable=False),
            sa.Column("weekly_velocity", sa.Numeric(18, 6), nullable=True),
            sa.Column("weeks_of_cover", sa.Numeric(18, 6), nullable=True),
            sa.Column("replenishment_flag", sa.Boolean(), nullable=False),
            sa.Column("replenishment_threshold_weeks", sa.Numeric(8, 4), nullable=False),
            sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("formula_version", sa.String(length=32), nullable=False),
            sa.Column("data_vintage", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("source_key", sa.String(length=256), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.CheckConstraint(
                "trigger IN ('dsi_apply', 'shipment_apply', 'as_of_backfill')",
                name="ck_woc_observation_trigger",
            ),
            sa.ForeignKeyConstraint(["distributor_id"], ["dim_distributor.id"]),
            sa.ForeignKeyConstraint(["product_id"], ["dim_product.id"]),
            sa.ForeignKeyConstraint(["import_job_id"], ["import_job.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("source_key", name="uq_weeks_of_cover_observation_source_key"),
        )
        op.create_index(
            "ix_weeks_of_cover_observation_tenant_id",
            "weeks_of_cover_observation",
            ["tenant_id"],
        )
        op.execute(
            sa.text(
                """
                CREATE INDEX IF NOT EXISTS ix_woc_observation_current
                ON weeks_of_cover_observation
                (tenant_id, distributor_id, product_id, cover_as_of_date DESC)
                """
            )
        )
        _grant_cip("weeks_of_cover_observation")

    insp = inspect(bind)
    _create_index_if_missing(
        insp,
        "fact_inventory_distributor",
        "ix_fact_inventory_distributor_woc_asof",
        """
        CREATE INDEX IF NOT EXISTS ix_fact_inventory_distributor_woc_asof
        ON fact_inventory_distributor (tenant_id, distributor_id, product_id, as_of_date)
        """,
    )
    _create_index_if_missing(
        insp,
        "fact_sales_sellout",
        "ix_fact_sales_sellout_woc_asof",
        """
        CREATE INDEX IF NOT EXISTS ix_fact_sales_sellout_woc_asof
        ON fact_sales_sellout (distributor_id, product_id, transaction_date)
        """,
    )
    _create_index_if_missing(
        insp,
        "fact_inbound_shipment",
        "ix_fact_inbound_shipment_woc_asof",
        """
        CREATE INDEX IF NOT EXISTS ix_fact_inbound_shipment_woc_asof
        ON fact_inbound_shipment (distributor_id, product_id, pod_date, line_state)
        """,
    )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    tables = set(insp.get_table_names())
    if "weeks_of_cover_observation" in tables:
        op.drop_index("ix_woc_observation_current", table_name="weeks_of_cover_observation")
        op.drop_index("ix_weeks_of_cover_observation_tenant_id", table_name="weeks_of_cover_observation")
        op.drop_table("weeks_of_cover_observation")
    for table, name in (
        ("fact_inventory_distributor", "ix_fact_inventory_distributor_woc_asof"),
        ("fact_sales_sellout", "ix_fact_sales_sellout_woc_asof"),
        ("fact_inbound_shipment", "ix_fact_inbound_shipment_woc_asof"),
    ):
        if table not in tables:
            continue
        existing = {ix["name"] for ix in insp.get_indexes(table)}
        if name in existing:
            op.drop_index(name, table_name=table)
