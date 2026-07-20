"""CPOR H1 — historical case import backbone (AUTHOR ONLY — do not apply to cip without Warren).

Revision ID: 20260720_0073
Revises: 20260710_0072

Adds:
- cpor_case.origin (native | historical_import)
- cpor_case_line.source_snapshot_json
- cpor_historical_mapping_profile (tenant column/value/sheet maps)
- import_cpor_historical_staging_line (source_key upsert staging)
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260720_0073"
down_revision: Union[str, Sequence[str], None] = "20260710_0072"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cpor_case",
        sa.Column("origin", sa.String(length=32), nullable=False, server_default="native"),
    )
    op.create_index("ix_cpor_case_origin", "cpor_case", ["origin"])

    op.add_column(
        "cpor_case_line",
        sa.Column("source_snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    op.create_table(
        "cpor_historical_mapping_profile",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("profile_code", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=256), nullable=False),
        sa.Column("header_row_index", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("sheet_roles_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("column_map_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("value_maps_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("profile_code", name="uq_cpor_historical_mapping_profile_code"),
    )

    op.create_table(
        "import_cpor_historical_staging_line",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("import_job_id", sa.Integer(), sa.ForeignKey("import_job.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_key", sa.String(length=512), nullable=False),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("sheet_name", sa.String(length=128), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("case_code", sa.String(length=64), nullable=False),
        sa.Column("case_name", sa.String(length=256), nullable=True),
        sa.Column("promotion_type_raw", sa.String(length=128), nullable=True),
        sa.Column("promotion_type", sa.String(length=128), nullable=True),
        sa.Column("window_start", sa.Date(), nullable=True),
        sa.Column("window_end", sa.Date(), nullable=True),
        sa.Column("status_raw", sa.String(length=64), nullable=True),
        sa.Column("lifecycle_status", sa.String(length=32), nullable=True),
        sa.Column("pod_quarter", sa.String(length=16), nullable=True),
        sa.Column("product_line", sa.String(length=64), nullable=True),
        sa.Column("distributor_token", sa.String(length=256), nullable=True),
        sa.Column("customer_token", sa.String(length=256), nullable=True),
        sa.Column("sales_model_token", sa.String(length=256), nullable=True),
        sa.Column("resolved_customer_id", sa.Integer(), sa.ForeignKey("dim_customer.id"), nullable=True),
        sa.Column("resolved_distributor_id", sa.Integer(), sa.ForeignKey("dim_distributor.id"), nullable=True),
        sa.Column("resolved_product_id", sa.Integer(), sa.ForeignKey("dim_product.id"), nullable=True),
        sa.Column("soh_snapshot", sa.Numeric(18, 4), nullable=True),
        sa.Column("estimate_qty", sa.Numeric(18, 4), nullable=True),
        sa.Column("result_qty", sa.Numeric(18, 4), nullable=True),
        sa.Column("srp", sa.Numeric(18, 4), nullable=True),
        sa.Column("vat_rate", sa.Numeric(8, 4), nullable=True),
        sa.Column("dealer_margin_pct", sa.Numeric(8, 4), nullable=True),
        sa.Column("cost_basis", sa.Numeric(18, 4), nullable=True),
        sa.Column("dealer_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("support_unit", sa.Numeric(18, 4), nullable=True),
        sa.Column("ttl_support", sa.Numeric(18, 4), nullable=True),
        sa.Column("roe_snapshot", sa.Numeric(18, 6), nullable=True),
        sa.Column("support_usd", sa.Numeric(18, 4), nullable=True),
        sa.Column("ttl_support_usd", sa.Numeric(18, 4), nullable=True),
        sa.Column("ttl_result", sa.Numeric(18, 4), nullable=True),
        sa.Column("ttl_result_usd", sa.Numeric(18, 4), nullable=True),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("skip_apply", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("flags_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source_snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("raw_source_row", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_key", name="uq_import_cpor_historical_staging_source_key"),
    )
    op.create_index(
        "ix_import_cpor_historical_staging_job",
        "import_cpor_historical_staging_line",
        ["import_job_id"],
    )
    op.create_index(
        "ix_import_cpor_historical_staging_case",
        "import_cpor_historical_staging_line",
        ["case_code"],
    )


def downgrade() -> None:
    op.drop_index("ix_import_cpor_historical_staging_case", table_name="import_cpor_historical_staging_line")
    op.drop_index("ix_import_cpor_historical_staging_job", table_name="import_cpor_historical_staging_line")
    op.drop_table("import_cpor_historical_staging_line")
    op.drop_table("cpor_historical_mapping_profile")
    op.drop_column("cpor_case_line", "source_snapshot_json")
    op.drop_index("ix_cpor_case_origin", table_name="cpor_case")
    op.drop_column("cpor_case", "origin")
